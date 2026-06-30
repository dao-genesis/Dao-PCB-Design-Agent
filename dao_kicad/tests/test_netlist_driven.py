"""build_from_spec full-flow: ground pours must be poured, not left empty."""
import pcbnew
import pytest

from dao_kicad.core.netlist_driven import (
    ComponentSpec, DesignSpec, NetConnection, build_from_spec)


def _two_resistor_spec(**kw):
    return DesignSpec(
        name="pourtest", width_mm=40, height_mm=30, copper_layers=2,
        components=[
            ComponentSpec("R1", "Resistor_SMD", "R_0805_2012Metric", "10k", 10, 10),
            ComponentSpec("R2", "Resistor_SMD", "R_0805_2012Metric", "10k", 25, 10),
        ],
        nets=[
            NetConnection("GND", [("R1", "2"), ("R2", "2")]),
            NetConnection("SIG", [("R1", "1"), ("R2", "1")]),
        ],
        **kw)


def test_ground_pour_is_actually_filled(tmp_path):
    """A requested ground plane must carry real copper. ZONE_FILLER computes
    zero area on a freshly-built in-memory board, so build_from_spec used to
    save an empty pour outline — the plane the caller asked for did not exist.
    Reload-and-fill must give the zone a positive filled area."""
    spec = _two_resistor_spec(ground_pour_layers=[pcbnew.B_Cu])
    res = build_from_spec(spec, tmp_path / "out")
    board = pcbnew.LoadBoard(str(res.board_path))
    areas = [z.GetFilledArea() for z in board.Zones()]
    assert areas, "no zone on board"
    assert all(a > 0 for a in areas), f"pour not filled: {areas}"
    assert res.drc_errors == 0


def test_no_pour_requested_still_builds(tmp_path):
    """Without ground_pour_layers the flow stays DRC-clean and adds no zone."""
    spec = _two_resistor_spec()
    res = build_from_spec(spec, tmp_path / "out")
    board = pcbnew.LoadBoard(str(res.board_path))
    assert len(board.Zones()) == 0
    assert res.drc_errors == 0
