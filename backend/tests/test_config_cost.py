"""Tests for cost_usd_for_turn cache token accounting.

Covers:
    - input-only + output-only cost (original behavior)
    - cache_creation_input_tokens priced at 1.25x base input
    - cache_read_input_tokens priced at 0.1x base input
    - combined input + cache_creation + cache_read + output
    - unknown model returns 0.0 and logs a warning
    - backward compat: calling without cache args still works
"""
from __future__ import annotations

import logging

import pytest

from vellum.config import MODEL_PRICING_USD_PER_MTOK, cost_usd_for_turn


# ---------------------------------------------------------------------------
# Backward compat
# ---------------------------------------------------------------------------


def test_two_arg_call_unchanged():
    """Original 2-arg call signature still works."""
    cost = cost_usd_for_turn("claude-opus-4-7", 1_000_000, 1_000_000)
    assert cost == pytest.approx(5.0 + 25.0)


# ---------------------------------------------------------------------------
# Per-model pricing table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model,input_tok,output_tok,expected",
    [
        ("claude-opus-4-7", 1_000_000, 0, 5.0),
        ("claude-opus-4-7", 0, 1_000_000, 25.0),
        ("claude-sonnet-4-6", 1_000_000, 0, 3.0),
        ("claude-sonnet-4-6", 0, 1_000_000, 15.0),
        ("claude-haiku-4-5", 1_000_000, 0, 1.0),
        ("claude-haiku-4-5", 0, 1_000_000, 5.0),
    ],
)
def test_base_input_output(model: str, input_tok: int, output_tok: int, expected: float):
    assert cost_usd_for_turn(model, input_tok, output_tok) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Cache creation pricing (1.25x base input)
# ---------------------------------------------------------------------------


def test_cache_creation_opus():
    rates = MODEL_PRICING_USD_PER_MTOK["claude-opus-4-7"]
    expected_per_mtok = rates["cache_creation_input"]
    assert expected_per_mtok == pytest.approx(rates["input"] * 1.25)
    cost = cost_usd_for_turn(
        "claude-opus-4-7", 0, 0, cache_creation_input_tokens=1_000_000,
    )
    assert cost == pytest.approx(expected_per_mtok)


def test_cache_creation_sonnet():
    rates = MODEL_PRICING_USD_PER_MTOK["claude-sonnet-4-6"]
    cost = cost_usd_for_turn(
        "claude-sonnet-4-6", 0, 0, cache_creation_input_tokens=1_000_000,
    )
    assert cost == pytest.approx(rates["cache_creation_input"])


def test_cache_creation_haiku():
    rates = MODEL_PRICING_USD_PER_MTOK["claude-haiku-4-5"]
    cost = cost_usd_for_turn(
        "claude-haiku-4-5", 0, 0, cache_creation_input_tokens=1_000_000,
    )
    assert cost == pytest.approx(rates["cache_creation_input"])


# ---------------------------------------------------------------------------
# Cache read pricing (0.1x base input)
# ---------------------------------------------------------------------------


def test_cache_read_opus():
    rates = MODEL_PRICING_USD_PER_MTOK["claude-opus-4-7"]
    expected_per_mtok = rates["cache_read_input"]
    assert expected_per_mtok == pytest.approx(rates["input"] * 0.1)
    cost = cost_usd_for_turn(
        "claude-opus-4-7", 0, 0, cache_read_input_tokens=1_000_000,
    )
    assert cost == pytest.approx(expected_per_mtok)


def test_cache_read_sonnet():
    rates = MODEL_PRICING_USD_PER_MTOK["claude-sonnet-4-6"]
    cost = cost_usd_for_turn(
        "claude-sonnet-4-6", 0, 0, cache_read_input_tokens=1_000_000,
    )
    assert cost == pytest.approx(rates["cache_read_input"])


# ---------------------------------------------------------------------------
# Combined token types
# ---------------------------------------------------------------------------


def test_all_token_types_combined():
    """input + cache_creation + cache_read + output summed correctly."""
    rates = MODEL_PRICING_USD_PER_MTOK["claude-opus-4-7"]
    cost = cost_usd_for_turn(
        "claude-opus-4-7",
        input_tokens=500_000,
        output_tokens=200_000,
        cache_creation_input_tokens=100_000,
        cache_read_input_tokens=2_000_000,
    )
    expected = (
        500_000 / 1_000_000 * rates["input"]
        + 100_000 / 1_000_000 * rates["cache_creation_input"]
        + 2_000_000 / 1_000_000 * rates["cache_read_input"]
        + 200_000 / 1_000_000 * rates["output"]
    )
    assert cost == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Unknown model
# ---------------------------------------------------------------------------


def test_unknown_model_returns_zero(caplog):
    with caplog.at_level(logging.WARNING, logger="vellum.config"):
        cost = cost_usd_for_turn("nonexistent-model", 1_000_000, 1_000_000)
    assert cost == 0.0
    assert "nonexistent-model" in caplog.text


def test_unknown_model_with_cache_tokens_returns_zero():
    cost = cost_usd_for_turn(
        "nonexistent-model", 1_000_000, 1_000_000,
        cache_creation_input_tokens=500_000,
        cache_read_input_tokens=500_000,
    )
    assert cost == 0.0
