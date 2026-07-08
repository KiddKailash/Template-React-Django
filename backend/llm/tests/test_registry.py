"""Tests for the tool decorator + validator."""

from __future__ import annotations

import pytest

from llm.utils.tools import REGISTRY, read_only_tool
from llm.utils.tools.validator import _scan_writes


def test_decorator_builds_json_schema_from_annotations():
    @read_only_tool(name="test_schema", description="ok")
    def _schema(a: int, b: str = "x", c: list[int] = None) -> dict:  # noqa: RUF013
        return {"a": a, "b": b, "c": c}

    try:
        spec = REGISTRY["test_schema"]
        assert spec.parameters["a"] == {"type": "integer"}
        assert spec.parameters["b"] == {"type": "string"}
        assert spec.parameters["c"] == {"type": "array", "items": {"type": "integer"}}
        # Only `a` has no default → required.
        assert spec.required == ["a"]
    finally:
        REGISTRY.pop("test_schema", None)


def test_decorator_rejects_duplicate_name():
    @read_only_tool(name="test_dup", description="ok")
    def _first() -> dict:
        return {}

    try:
        with pytest.raises(ValueError, match="already registered"):

            @read_only_tool(name="test_dup", description="ok")
            def _second() -> dict:
                return {}
    finally:
        REGISTRY.pop("test_dup", None)


def test_validator_flags_save_call():
    @read_only_tool(name="test_bad", description="ok")
    def _bad() -> dict:
        # Deliberate .save() call so the AST walker sees a violation.
        class _M:
            def save(self):
                return None

        _M().save()
        return {}

    try:
        errors = _scan_writes(REGISTRY["test_bad"])
        assert any(".save()" in e for e in errors)
    finally:
        REGISTRY.pop("test_bad", None)


def test_decorator_rejects_missing_description():
    with pytest.raises(ValueError, match="description is required"):

        @read_only_tool(name="test_no_desc", description="   ")
        def _no_desc() -> dict:
            return {}


def test_decorator_rejects_unannotated_param():
    with pytest.raises(TypeError, match="must be annotated"):

        @read_only_tool(name="test_unannot", description="ok")
        def _unannot(x) -> dict:  # noqa: ANN001
            return {"x": x}
