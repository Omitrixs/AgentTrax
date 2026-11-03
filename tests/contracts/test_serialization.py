"""Tests for strict JSON validation and canonical serialization."""

import pytest

from agenttrax.contracts.serialization import (
    DIGEST_CANONICALIZATION_VERSION,
    MAX_ARGUMENT_BYTES,
    MAX_ARGUMENT_DEPTH,
    PROPOSAL_DIGEST_HEX_LENGTH,
    TRACE_DETAILS_MAX_BYTES,
    TRACE_DETAILS_MAX_DEPTH,
    TRACE_STRING_MAX_CHARS,
    FrozenJsonArray,
    FrozenJsonObject,
    canonical_json_bytes,
    canonical_json_bytes_from_immutable,
    enforce_json_limits,
    freeze_json_value,
    validate_json_value,
)


def test_named_limits_are_pinned() -> None:
    assert MAX_ARGUMENT_BYTES == 65536
    assert MAX_ARGUMENT_DEPTH == 10
    assert TRACE_DETAILS_MAX_BYTES == 8192
    assert TRACE_DETAILS_MAX_DEPTH == 5
    assert TRACE_STRING_MAX_CHARS == 512
    assert PROPOSAL_DIGEST_HEX_LENGTH == 64
    assert DIGEST_CANONICALIZATION_VERSION == 1


def test_canonical_json_sorts_keys_recursively() -> None:
    value = {"z": 1, "nested": {"y": 2, "x": 3}}
    assert canonical_json_bytes(value) == b'{"nested":{"x":3,"y":2},"z":1}'


def test_canonical_json_uses_compact_utf8_and_preserves_scalar_types() -> None:
    assert canonical_json_bytes({"name": "café", "flag": True}) == (
        '{"flag":true,"name":"café"}'.encode()
    )
    assert canonical_json_bytes(1) == b"1"
    assert canonical_json_bytes(1.0) == b"1.0"
    assert canonical_json_bytes(True) == b"true"


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        (1, 2),
        {1, 2},
        b"bytes",
        {1: "non-string key"},
        object(),
    ],
)
def test_rejects_unsupported_json_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        validate_json_value(value)


def test_accepts_exact_depth_limit() -> None:
    value: object = "leaf"
    for _ in range(MAX_ARGUMENT_DEPTH):
        value = [value]
    validate_json_value(value)


def test_rejects_depth_over_limit() -> None:
    value: object = "leaf"
    for _ in range(MAX_ARGUMENT_DEPTH + 1):
        value = [value]
    with pytest.raises(ValueError, match="nesting"):
        validate_json_value(value)


def test_accepts_exact_byte_limit() -> None:
    value = "x" * (MAX_ARGUMENT_BYTES - 2)
    enforce_json_limits(value, max_bytes=MAX_ARGUMENT_BYTES)


def test_rejects_one_byte_over_limit() -> None:
    value = "x" * (MAX_ARGUMENT_BYTES - 1)
    with pytest.raises(ValueError, match="size"):
        enforce_json_limits(value, max_bytes=MAX_ARGUMENT_BYTES)


def test_size_limit_counts_utf8_bytes() -> None:
    value = "é" * 10
    assert len(value) == 10
    assert len(canonical_json_bytes(value)) == 22
    with pytest.raises(ValueError, match="size"):
        enforce_json_limits(value, max_bytes=21)


def test_empty_containers_are_valid_json() -> None:
    assert canonical_json_bytes({}) == b"{}"
    assert canonical_json_bytes([]) == b"[]"
    assert canonical_json_bytes(None) == b"null"


def test_frozen_json_serializes_to_canonical_bytes() -> None:
    value = {"items": [1, True], "name": "AgentTrax"}
    frozen = freeze_json_value(value)

    assert canonical_json_bytes_from_immutable(frozen) == (
        b'{"items":[1,true],"name":"AgentTrax"}'
    )


def test_freezing_copies_nested_input() -> None:
    original = {"items": [1, 2]}
    frozen = freeze_json_value(original)

    original["items"].append(3)

    assert canonical_json_bytes_from_immutable(frozen) == b'{"items":[1,2]}'


def test_frozen_containers_reject_mutation() -> None:
    frozen = freeze_json_value({"nested": {"items": [1, 2]}})

    assert isinstance(frozen, FrozenJsonObject)
    nested = frozen["nested"]
    assert isinstance(nested, FrozenJsonObject)
    items = nested["items"]
    assert isinstance(items, FrozenJsonArray)

    with pytest.raises(TypeError):
        frozen["new"] = "value"  # type: ignore[index]

    with pytest.raises(AttributeError, match="immutable"):
        frozen._data = {}  # type: ignore[attr-defined]

    with pytest.raises(AttributeError, match="immutable"):
        items._items = ()  # type: ignore[attr-defined]

    with pytest.raises(AttributeError, match="immutable"):
        frozen._FrozenJsonObject__data = {}  # type: ignore[attr-defined]

    with pytest.raises(AttributeError, match="immutable"):
        items._FrozenJsonArray__items = ()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "value",
    [
        (1, 2),
        {"items": (1, 2)},
    ],
)
def test_immutable_serializer_rejects_arbitrary_tuples(
    value: object,
) -> None:
    with pytest.raises(TypeError, match="Unsupported immutable JSON value type"):
        canonical_json_bytes_from_immutable(value)


def test_freezing_rejects_invalid_input_before_conversion() -> None:
    with pytest.raises(TypeError, match="Unsupported JSON value type: tuple"):
        freeze_json_value({"items": (1, 2)})


@pytest.mark.parametrize("max_depth", [0, -1, True, 1.5])
def test_validate_json_rejects_invalid_max_depth(
    max_depth: object,
) -> None:
    with pytest.raises(ValueError, match="max_depth"):
        validate_json_value("valid", max_depth=max_depth)  # type: ignore[arg-type]


@pytest.mark.parametrize("max_bytes", [-1, True, 1.5])
def test_enforce_json_limits_rejects_invalid_max_bytes(
    max_bytes: object,
) -> None:
    with pytest.raises(ValueError, match="max_bytes"):
        enforce_json_limits("valid", max_bytes=max_bytes)  # type: ignore[arg-type]


def test_frozen_nested_array_rejects_item_assignment() -> None:
    frozen = freeze_json_value({"items": [1, 2]})
    assert isinstance(frozen, FrozenJsonObject)

    items = frozen["items"]
    assert isinstance(items, FrozenJsonArray)

    with pytest.raises(TypeError):
        items[0] = 99  # type: ignore[index]

    assert canonical_json_bytes_from_immutable(frozen) == b'{"items":[1,2]}'


def test_freezing_copies_nested_arrays() -> None:
    original = [1, {"values": [2, 3]}]
    frozen = freeze_json_value(original)

    original[1]["values"].append(4)

    assert canonical_json_bytes_from_immutable(frozen) == (b'[1,{"values":[2,3]}]')


def test_json_validation_does_not_treat_boolean_as_integer() -> None:
    assert canonical_json_bytes(True) == b"true"
    assert canonical_json_bytes(1) == b"1"
    assert canonical_json_bytes(1.0) == b"1.0"


def test_frozen_json_array_rejects_attribute_reassignment() -> None:
    frozen = freeze_json_value([1, 2])
    assert isinstance(frozen, FrozenJsonArray)

    with pytest.raises(AttributeError, match="immutable"):
        frozen._items = (3, 4)  # type: ignore[attr-defined]


def test_direct_object_construction_recursively_freezes_input() -> None:
    original = {"items": [1, {"value": 2}]}
    frozen = FrozenJsonObject(original)

    original["items"].append(3)

    assert canonical_json_bytes_from_immutable(frozen) == (b'{"items":[1,{"value":2}]}')


def test_direct_array_construction_recursively_freezes_input() -> None:
    original = [1, {"values": [2, 3]}]
    frozen = FrozenJsonArray(tuple(original))

    original[1]["values"].append(4)

    assert canonical_json_bytes_from_immutable(frozen) == (b'[1,{"values":[2,3]}]')
