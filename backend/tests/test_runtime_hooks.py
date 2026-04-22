"""Tests for the day-2 dispatch hook surface in ``vellum.tools.handlers``.

These tests exercise the pure dispatch plumbing (``dispatch``,
``HANDLER_OVERRIDES``, ``TOOL_HOOKS``) without touching storage, so no DB
fixture is required. Each test registers test-only handlers into the real
``HANDLERS`` dict and is responsible for cleaning up via the auto-clean
fixture.
"""
from __future__ import annotations

from typing import Any

import pytest

from vellum.tools import handlers


@pytest.fixture(autouse=True)
def _clean_extension_points():
    """Snapshot and restore HANDLER_OVERRIDES / TOOL_HOOKS / HANDLERS.

    Tests may register a temporary default handler into HANDLERS itself in
    order to exercise dispatch end-to-end without spinning up storage; we
    snapshot the full HANDLERS dict here so we can safely restore it.
    """
    saved_overrides = dict(handlers.HANDLER_OVERRIDES)
    saved_hooks = list(handlers.TOOL_HOOKS)
    saved_handlers = dict(handlers.HANDLERS)
    try:
        yield
    finally:
        handlers.HANDLER_OVERRIDES.clear()
        handlers.HANDLER_OVERRIDES.update(saved_overrides)
        handlers.TOOL_HOOKS.clear()
        handlers.TOOL_HOOKS.extend(saved_hooks)
        handlers.HANDLERS.clear()
        handlers.HANDLERS.update(saved_handlers)


def test_dispatch_calls_default_handler_when_no_override():
    calls: list[tuple[str, dict[str, Any]]] = []

    def default_impl(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
        calls.append((dossier_id, args))
        return {"source": "default", "dossier_id": dossier_id, "args": args}

    handlers.HANDLERS["_test_tool"] = default_impl

    result = handlers.dispatch("dossier-1", "_test_tool", {"x": 1})

    assert result == {
        "source": "default",
        "dossier_id": "dossier-1",
        "args": {"x": 1},
    }
    assert calls == [("dossier-1", {"x": 1})]


def test_dispatch_calls_override_instead_of_default():
    default_called = False
    override_called_with: list[tuple[str, dict[str, Any]]] = []

    def default_impl(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
        nonlocal default_called
        default_called = True
        return {"source": "default"}

    def override_impl(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
        override_called_with.append((dossier_id, args))
        return {"source": "override"}

    handlers.HANDLERS["_test_tool"] = default_impl
    handlers.HANDLER_OVERRIDES["_test_tool"] = override_impl

    result = handlers.dispatch("dossier-1", "_test_tool", {"y": 2})

    assert result == {"source": "override"}
    assert default_called is False
    assert override_called_with == [("dossier-1", {"y": 2})]


def test_dispatch_runs_all_tool_hooks_with_full_signature():
    def impl(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "echo": args}

    handlers.HANDLERS["_test_tool"] = impl

    hook_calls: list[tuple[str, str, dict[str, Any], Any]] = []

    def hook_a(d: str, name: str, args: dict[str, Any], result: Any) -> None:
        hook_calls.append(("a", name, args, result))

    def hook_b(d: str, name: str, args: dict[str, Any], result: Any) -> None:
        hook_calls.append(("b", name, args, result))

    handlers.TOOL_HOOKS.append(hook_a)
    handlers.TOOL_HOOKS.append(hook_b)

    result = handlers.dispatch("dossier-42", "_test_tool", {"k": "v"})

    assert result == {"ok": True, "echo": {"k": "v"}}
    assert hook_calls == [
        ("a", "_test_tool", {"k": "v"}, {"ok": True, "echo": {"k": "v"}}),
        ("b", "_test_tool", {"k": "v"}, {"ok": True, "echo": {"k": "v"}}),
    ]


def test_dispatch_swallows_failing_hook_and_still_runs_later_hooks():
    def impl(dossier_id: str, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    handlers.HANDLERS["_test_tool"] = impl

    later_hook_ran = False

    def bad_hook(*_a: Any, **_kw: Any) -> None:
        raise RuntimeError("boom")

    def good_hook(*_a: Any, **_kw: Any) -> None:
        nonlocal later_hook_ran
        later_hook_ran = True

    handlers.TOOL_HOOKS.append(bad_hook)
    handlers.TOOL_HOOKS.append(good_hook)

    # Must not raise.
    result = handlers.dispatch("dossier-1", "_test_tool", {})

    assert result == {"ok": True}
    assert later_hook_ran is True


def test_dispatch_raises_key_error_for_unknown_tool():
    with pytest.raises(KeyError):
        handlers.dispatch("dossier-1", "_no_such_tool_exists_anywhere", {})


def test_autoclean_fixture_restores_state_between_tests():
    # Sentinel test to confirm the fixture actually cleans up after the
    # preceding tests. If override/hook state leaked, these would be
    # non-empty at the start of this test.
    assert "_test_tool" not in handlers.HANDLER_OVERRIDES
    assert "_test_tool" not in handlers.HANDLERS
    assert handlers.TOOL_HOOKS == []
