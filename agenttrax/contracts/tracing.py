"""Trace event contracts and trace-detail sanitization."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from agenttrax.contracts.models import (
    NonBlankString,
    StrictContractModel,
    _validate_nonblank_string,
    _validate_utc_datetime,
)
from agenttrax.contracts.serialization import (
    TRACE_DETAILS_MAX_BYTES,
    TRACE_DETAILS_MAX_DEPTH,
    TRACE_STRING_MAX_CHARS,
    FrozenJsonObject,
    enforce_json_limits,
)


class TraceEventType(StrEnum):
    """Supported event types in the auditable action lifecycle."""

    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    POLICY_DECIDED = "POLICY_DECIDED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_SKIPPED = "EXECUTION_SKIPPED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"


_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "privatekey",
    "sessionid",
)
_TRUNCATION_SUFFIX = "…[TRUNCATED]"
_TRUNCATION_PREFIX_LENGTH = TRACE_STRING_MAX_CHARS - len(_TRUNCATION_SUFFIX)


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[-_ ]", "", key.lower())
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_value(value: object) -> object:
    if type(value) is dict:
        sanitized: dict[str, object] = {}

        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("JSON object keys must be strings.")

            if _is_sensitive_key(key):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = _sanitize_value(item)

        return sanitized

    if type(value) is list:
        return [_sanitize_value(item) for item in value]

    if type(value) is str and len(value) > TRACE_STRING_MAX_CHARS:
        return value[:_TRUNCATION_PREFIX_LENGTH] + _TRUNCATION_SUFFIX

    return value


def sanitize_details(details: dict[str, object]) -> dict[str, object]:
    """Redact sensitive-key values and truncate long strings without mutation."""
    if type(details) is not dict:
        raise TypeError("Trace details must be a dictionary.")

    sanitized = _sanitize_value(details)

    if type(sanitized) is not dict:
        raise TypeError("Trace details must be a dictionary.")

    # Validate and enforce trace-specific limits after sanitization.
    enforce_json_limits(
        sanitized,
        max_bytes=TRACE_DETAILS_MAX_BYTES,
        max_depth=TRACE_DETAILS_MAX_DEPTH,
    )

    return sanitized


class TraceEvent(StrictContractModel):
    """One structured event in the auditable action lifecycle."""

    event_id: NonBlankString
    task_id: NonBlankString
    action_id: NonBlankString | None = None
    event_type: TraceEventType
    sequence: Annotated[int, Field(gt=0, strict=True)]
    timestamp: datetime
    details: FrozenJsonObject

    @field_validator("event_id", "task_id")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        return _validate_nonblank_string(value)

    @field_validator("action_id")
    @classmethod
    def validate_optional_action_id(cls, value: str | None) -> str | None:
        if value is not None:
            return _validate_nonblank_string(value)
        return value

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, value: object) -> datetime:
        if isinstance(value, str):
            if not re.search(r"(Z|[+-]\d{2}:\d{2})$", value):
                raise ValueError("Timestamp string must include a timezone offset.")

            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid ISO 8601 timestamp.") from exc

        if not isinstance(value, datetime):
            raise ValueError("Timestamp must be a datetime or ISO 8601 string.")

        return _validate_utc_datetime(value)

    @field_validator("details", mode="before")
    @classmethod
    def validate_details(cls, value: object) -> FrozenJsonObject:
        if type(value) is not dict:
            raise ValueError("Trace details must be a JSON object.")

        try:
            enforce_json_limits(
                value,
                max_bytes=TRACE_DETAILS_MAX_BYTES,
                max_depth=TRACE_DETAILS_MAX_DEPTH,
            )
            _reject_unredacted_sensitive_values(value)
            return FrozenJsonObject(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid trace details: {exc}") from exc


def _reject_unredacted_sensitive_values(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if _is_sensitive_key(key) and item != "[REDACTED]":
                raise ValueError(f"Sensitive trace key {key!r} is not redacted.")
            _reject_unredacted_sensitive_values(item)

    elif type(value) is list:
        for item in value:
            _reject_unredacted_sensitive_values(item)
