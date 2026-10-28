
"""Strict JSON validation and canonical serialization utilities."""

from __future__ import annotations

import json
import math
from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType

type JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)

MAX_ARGUMENT_BYTES = 65536
MAX_ARGUMENT_DEPTH = 10
TRACE_DETAILS_MAX_BYTES = 8192
TRACE_DETAILS_MAX_DEPTH = 5
TRACE_STRING_MAX_CHARS = 512
PROPOSAL_DIGEST_HEX_LENGTH = 64
DIGEST_CANONICALIZATION_VERSION = 1



class FrozenJsonObject(Mapping[str, object]):
    """Immutable JSON object backed by a read-only mapping."""

    __slots__ = ("__data",)

    def __init__(self, data: dict[str, object]) -> None:
        validate_json_value(data)
        frozen_data = {
            key: _freeze_validated_json(value)
            for key, value in data.items()
        }
        object.__setattr__(
            self,
            "_FrozenJsonObject__data",
            MappingProxyType(frozen_data),
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("FrozenJsonObject is immutable")

    def __getitem__(self, key: str) -> object:
        return self.__data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)


class FrozenJsonArray(Sequence[object]):
    """Immutable JSON array backed by a tuple."""

    __slots__ = ("__items",)

    def __init__(self, items: tuple[object, ...]) -> None:
        validate_json_value(list(items))
        frozen_items = tuple(
            _freeze_validated_json(item) for item in items
        )
        object.__setattr__(
            self,
            "_FrozenJsonArray__items",
            frozen_items,
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("FrozenJsonArray is immutable")

    def __getitem__(self, index: int | slice) -> object:
        return self.__items[index]

    def __len__(self) -> int:
        return len(self.__items)

def validate_json_value(
    value: object,
    *,
    max_depth: int = MAX_ARGUMENT_DEPTH,
) -> None:
    """Reject values outside the supported JSON data model."""
    if type(max_depth) is not int or max_depth < 1:
        raise ValueError("max_depth must be a positive integer")

    def visit(item: object, depth: int) -> None:
        if depth > max_depth:
            raise ValueError(
                f"JSON nesting exceeds maximum depth of {max_depth}"
            )

        if item is None or type(item) in (str, bool, int):
            return

        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("NaN and Infinity are not valid JSON values")
            return

        if type(item) is list:
            for child in item:
                visit(child, depth + 1)
            return

        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise TypeError("JSON object keys must be strings")
                visit(child, depth + 1)
            return

        raise TypeError(f"Unsupported JSON value type: {type(item).__name__}")

    visit(value, 1)



def _freeze_validated_json(value: JsonValue) -> object:
    """Recursively freeze a value already validated as strict JSON."""
    if type(value) is dict:
        return FrozenJsonObject(value)

    if type(value) is list:
        return FrozenJsonArray(tuple(value))

    return value


def freeze_json_value(value: object) -> object:
    """Validate, copy, and recursively freeze JSON data."""
    validate_json_value(value)
    return _freeze_validated_json(value)


def thaw_json_value(value: object) -> JsonValue:
    """Convert trusted frozen JSON containers into ordinary JSON values."""
    if type(value) is FrozenJsonObject:
        return {
            key: thaw_json_value(item)
            for key, item in value.items()
        }

    if type(value) is FrozenJsonArray:
        return [thaw_json_value(item) for item in value]

    if value is None or type(value) in (str, bool, int):
        return value

    if type(value) is float and math.isfinite(value):
        return value

    raise TypeError(
        f"Unsupported immutable JSON value type: {type(value).__name__}"
    )


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Return deterministic version-1 canonical JSON encoded as UTF-8."""
    validate_json_value(value)
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return encoded.encode("utf-8")


def canonical_json_bytes_from_immutable(value: object) -> bytes:
    """Serialize a trusted frozen JSON value as canonical UTF-8 bytes."""
    thawed = thaw_json_value(value)
    validate_json_value(thawed)
    return canonical_json_bytes(thawed)


def enforce_json_limits(
    value: JsonValue,
    *,
    max_bytes: int = MAX_ARGUMENT_BYTES,
    max_depth: int = MAX_ARGUMENT_DEPTH,
) -> None:
    """Validate JSON shape, nesting depth, and canonical UTF-8 byte size."""
    if type(max_bytes) is not int or max_bytes < 0:
        raise ValueError("max_bytes must be a non-negative integer")

    validate_json_value(value, max_depth=max_depth)
    size = len(canonical_json_bytes(value))
    if size > max_bytes:
        raise ValueError(
            f"Canonical JSON size {size} exceeds maximum of {max_bytes} bytes"
        )
