"""Tests for trace event contracts and detail sanitization."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from agenttrax.contracts.serialization import (
    TRACE_DETAILS_MAX_BYTES,
    TRACE_DETAILS_MAX_DEPTH,
    TRACE_STRING_MAX_CHARS,
    canonical_json_bytes,
)
from agenttrax.contracts.tracing import (
    TraceEvent,
    TraceEventType,
    sanitize_details,
)


def valid_trace_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "event_id": "event-001",
        "task_id": "task-001",
        "action_id": "action-001",
        "event_type": TraceEventType.PROPOSAL_CREATED,
        "sequence": 1,
        "timestamp": "2026-10-01T12:00:00Z",
        "details": {"tool_name": "get_order"},
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "PASSWORD",
        "user_passwd",
        "client-secret",
        "access_token",
        "API-Key",
        "api_key",
        "Api Key",
        "authorization",
        "cookie",
        "credential",
        "private_key",
        "session-id",
    ],
)
def test_sanitize_details_redacts_sensitive_keys(key: str) -> None:
    details = {key: "sensitive-value"}

    assert sanitize_details(details) == {key: "[REDACTED]"}
    assert details == {key: "sensitive-value"}


def test_sanitize_details_redacts_recursively_through_dicts_and_lists() -> None:
    details = {
        "nested": {
            "api_key": "secret-one",
            "items": [
                {"password": "secret-two"},
                {"ordinary": "visible"},
            ],
        }
    }

    assert sanitize_details(details) == {
        "nested": {
            "api_key": "[REDACTED]",
            "items": [
                {"password": "[REDACTED]"},
                {"ordinary": "visible"},
            ],
        }
    }


def test_sanitize_details_preserves_non_sensitive_values() -> None:
    details = {"name": "order-123", "count": 3, "active": True}

    assert sanitize_details(details) == details

def test_sanitize_details_does_not_scan_free_text_for_secrets() -> None:
    details = {
        "message": "My password is example-secret-123",
        "description": "Bearer example-token-456",
    }

    assert sanitize_details(details) == details

def test_sanitize_details_truncates_long_strings_to_limit() -> None:
    result = sanitize_details({"message": "x" * (TRACE_STRING_MAX_CHARS + 20)})
    value = result["message"]

    assert isinstance(value, str)
    assert len(value) == TRACE_STRING_MAX_CHARS
    assert value.endswith("…[TRUNCATED]")


def test_sanitize_details_leaves_string_at_limit_unchanged() -> None:
    value = "x" * TRACE_STRING_MAX_CHARS

    assert sanitize_details({"message": value}) == {"message": value}


def test_sanitize_details_does_not_mutate_input_and_is_idempotent() -> None:
    details = {
        "nested": [{"password": "secret"}, {"message": "x" * 600}],
        "status": "ok",
    }
    original = {
        "nested": [{"password": "secret"}, {"message": "x" * 600}],
        "status": "ok",
    }

    once = sanitize_details(details)

    assert details == original
    assert sanitize_details(once) == once


def test_sanitize_details_rejects_non_dictionary_input() -> None:
    with pytest.raises(TypeError):
        sanitize_details([{"password": "secret"}])  # type: ignore[arg-type]

def test_sanitize_details_rejects_non_string_dictionary_keys() -> None:
    with pytest.raises(TypeError, match="JSON object keys must be strings"):
        sanitize_details({123: "value"})  # type: ignore[dict-item]

@pytest.mark.parametrize("event_type", list(TraceEventType))
def test_trace_event_accepts_every_known_event_type(
    event_type: TraceEventType,
) -> None:
    event = TraceEvent.model_validate(valid_trace_data(event_type=event_type))

    assert event.event_type == event_type


def test_trace_event_rejects_unknown_event_type() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(event_type="UNKNOWN_EVENT"))

@pytest.mark.parametrize(
    "missing_field",
    [
        "event_id",
        "task_id",
        "event_type",
        "sequence",
        "timestamp",
        "details",
    ],
)
def test_trace_event_rejects_missing_required_fields(
    missing_field: str,
) -> None:
    data = valid_trace_data()
    del data[missing_field]

    with pytest.raises(ValidationError):
        TraceEvent.model_validate(data)


def test_trace_event_rejects_unknown_fields() -> None:
    data = valid_trace_data()
    data["unexpected"] = "value"

    with pytest.raises(ValidationError):
        TraceEvent.model_validate(data)

@pytest.mark.parametrize("sequence", [0, -1])
def test_trace_event_rejects_non_positive_sequence(sequence: int) -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(sequence=sequence))


def test_trace_event_rejects_boolean_sequence() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(sequence=True))


def test_trace_event_rejects_blank_required_strings() -> None:
    for field in ("event_id", "task_id"):
        with pytest.raises(ValidationError):
            TraceEvent.model_validate(valid_trace_data(**{field: "  "}))


def test_trace_event_accepts_none_action_id() -> None:
    event = TraceEvent.model_validate(valid_trace_data(action_id=None))

    assert event.action_id is None


def test_trace_event_rejects_blank_action_id() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(action_id="  "))


def test_trace_event_normalizes_timestamp_to_utc() -> None:
    timestamp = datetime(
        2026,
        10,
        1,
        14,
        0,
        tzinfo=timezone(timedelta(hours=2)),
    )
    event = TraceEvent.model_validate(valid_trace_data(timestamp=timestamp))

    assert event.timestamp.tzinfo is UTC
    assert event.timestamp.hour == 12


def test_trace_sequence_is_independent_of_timestamp_order() -> None:
    later_sequence = TraceEvent.model_validate(
        valid_trace_data(
            event_id="event-002",
            sequence=2,
            timestamp="2026-10-01T10:00:00Z",
        )
    )
    earlier_sequence = TraceEvent.model_validate(
        valid_trace_data(
            event_id="event-001",
            sequence=1,
            timestamp="2026-10-01T12:00:00Z",
        )
    )

    assert later_sequence.sequence > earlier_sequence.sequence
    assert later_sequence.timestamp < earlier_sequence.timestamp

@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-10-01T12:00:00",
        datetime(2026, 10, 1, 12, 0),
    ],
)
def test_trace_event_rejects_naive_timestamp(timestamp: object) -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(timestamp=timestamp))


@pytest.mark.parametrize(
    "details",
    [
        {"password": "not-redacted"},
        {"nested": [{"API_Key": "not-redacted"}]},
    ],
)
def test_trace_event_rejects_unredacted_sensitive_values(
    details: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(details=details))


def test_trace_event_accepts_redacted_sensitive_value() -> None:
    event = TraceEvent.model_validate(
        valid_trace_data(details={"api_key": "[REDACTED]"})
    )

    assert event.details["api_key"] == "[REDACTED]"


def test_trace_event_rejects_details_over_byte_limit() -> None:
    details = {"value": "x" * TRACE_DETAILS_MAX_BYTES}

    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(details=details))


def test_trace_event_rejects_details_over_depth_limit() -> None:
    details: dict[str, object] = {}
    current = details

    for _ in range(TRACE_DETAILS_MAX_DEPTH):
        nested: dict[str, object] = {}
        current["nested"] = nested
        current = nested

    current["value"] = "too-deep"

    with pytest.raises(ValidationError):
        TraceEvent.model_validate(valid_trace_data(details=details))


def test_trace_event_does_not_sanitize_automatically() -> None:
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(
            valid_trace_data(details={"password": "must-not-be-redacted-here"})
        )


def test_trace_event_details_are_immutable() -> None:
    original_details = {
        "nested": {
            "items": ["original"],
        }
    }

    event = TraceEvent.model_validate(
        valid_trace_data(details=original_details)
    )

    # Mutating the original input must not affect the event.
    original_details["nested"]["items"].append("mutated")

    assert list(event.details["nested"]["items"]) == ["original"]

    # Top-level and nested dictionaries must be immutable.
    with pytest.raises(TypeError):
        event.details["new"] = "value"  # type: ignore[index]

    with pytest.raises(TypeError):
        event.details["nested"]["new"] = "value"  # type: ignore[index]

    # Nested lists must also be immutable.
    with pytest.raises((TypeError, AttributeError)):
        event.details["nested"]["items"].append("mutated")  # type: ignore[union-attr]

    # The Pydantic model itself must be immutable.
    with pytest.raises(ValidationError):
        event.details = event.details

def test_sanitize_details_redacts_sensitive_value_before_depth_check() -> None:
    deeply_nested: object = "sensitive-value"
    for _ in range(TRACE_DETAILS_MAX_DEPTH + 5):
        deeply_nested = {"nested": deeply_nested}

    details = {"password": deeply_nested}

    assert sanitize_details(details) == {"password": "[REDACTED]"}

def test_sanitize_details_accepts_maximum_depth() -> None:
    details = {"a": {"b": {"c": {"d": "value"}}}}

    assert sanitize_details(details) == details


def test_sanitize_details_rejects_depth_over_limit() -> None:
    details: dict[str, object] = {}
    current = details

    for _ in range(TRACE_DETAILS_MAX_DEPTH):
        nested: dict[str, object] = {}
        current["nested"] = nested
        current = nested

    with pytest.raises(ValueError):
        sanitize_details(details)

def test_sanitize_details_accepts_exact_byte_limit() -> None:
    details = {"k" * (TRACE_DETAILS_MAX_BYTES - 8): "x"}

    assert len(canonical_json_bytes(details)) == TRACE_DETAILS_MAX_BYTES
    assert sanitize_details(details) == details


def test_sanitize_details_rejects_one_byte_over_limit() -> None:
    details = {"k" * (TRACE_DETAILS_MAX_BYTES - 7): "x"}

    with pytest.raises(ValueError):
        sanitize_details(details)

def test_trace_event_normalizes_json_timestamp_to_utc() -> None:
    data = valid_trace_data(
        timestamp="2026-10-01T14:00:00+02:00"
    )

    event = TraceEvent.model_validate_json(json.dumps(data))

    assert event.timestamp.tzinfo is UTC
    assert event.timestamp.hour == 12