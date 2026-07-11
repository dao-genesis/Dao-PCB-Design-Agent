"""Unit tests for the route-engine selection gate (no router invoked)."""

from __future__ import annotations

from dao_kicad.core.auto_designer import (
    DesignSpec, _resolve_route_engine, _FR_DENSE_DEMAND, _FR_DENSE_PARTS,
    _FR_DENSE_LAYERS)

YES = lambda: True   # noqa: E731  — freerouting available
NO = lambda: False   # noqa: E731  — freerouting unavailable


def test_default_engine_is_auto():
    assert DesignSpec(name="x").route_engine == "auto"


def test_builtin_never_uses_freerouting():
    # Even a huge board on an explicit builtin request stays builtin.
    assert _resolve_route_engine("builtin", 9999, 6, 999, YES) is False


def test_freerouting_uses_it_when_available_regardless_of_density():
    assert _resolve_route_engine("freerouting", 1, 2, 1, YES) is True


def test_freerouting_falls_back_when_unavailable():
    assert _resolve_route_engine("freerouting", 9999, 6, 999, NO) is False


def test_auto_stays_builtin_on_sparse_board():
    # A simple template-scale board: below every density threshold.
    assert _resolve_route_engine("auto", 20, 2, 8, YES) is False


def test_auto_uses_freerouting_on_high_demand_board():
    assert _resolve_route_engine("auto", _FR_DENSE_DEMAND, 2, 8, YES) is True


def test_auto_uses_freerouting_on_dense_multilayer_board():
    assert _resolve_route_engine(
        "auto", 10, _FR_DENSE_LAYERS, _FR_DENSE_PARTS, YES) is True


def test_auto_needs_both_layers_and_parts_for_multilayer_gate():
    # 6 layers but few parts, and low demand -> still builtin.
    assert _resolve_route_engine(
        "auto", 10, _FR_DENSE_LAYERS, _FR_DENSE_PARTS - 1, YES) is False


def test_auto_falls_back_to_builtin_without_freerouting():
    # Dense board, but no jar/JDK present -> deterministic builtin fallback.
    assert _resolve_route_engine("auto", 9999, 6, 999, NO) is False
