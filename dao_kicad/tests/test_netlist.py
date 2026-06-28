"""Netlist parser: KiCad .net -> build spec (universal construction front door)."""
from daokicad import netlist


SAMPLE = """
(export (version "E")
  (components
    (comp (ref "U1") (value "ATtiny85") (footprint "Package_DIP:DIP-8_W7.62mm"))
    (comp (ref "R1") (value "330") (footprint "Resistor_SMD:R_0805_2012Metric"))
    (comp (ref "X9") (value "nofp")))
  (nets
    (net (code "1") (name "VCC")
      (node (ref "U1") (pin "8")) (node (ref "R1") (pin "1")))
    (net (code "2") (name "PB0")
      (node (ref "U1") (pin "5")) (node (ref "X9") (pin "1")))))
"""


def test_parse_components_and_footprints():
    spec = netlist.parse_netlist(SAMPLE)
    refs = {f["ref"] for f in spec["footprints"]}
    assert refs == {"U1", "R1"}  # X9 has no footprint -> skipped
    u1 = next(f for f in spec["footprints"] if f["ref"] == "U1")
    assert u1["lib"] == "Package_DIP" and u1["fp"] == "DIP-8_W7.62mm"
    assert u1["value"] == "ATtiny85"


def test_unassigned_component_warns():
    spec = netlist.parse_netlist(SAMPLE)
    assert any("X9" in w for w in spec["warnings"])


def test_connections_only_for_placed_parts():
    spec = netlist.parse_netlist(SAMPLE)
    # VCC connects U1.8 + R1.1
    vcc = [c for c in spec["connections"] if c["net"] == "VCC"]
    assert {(c["ref"], c["pad"]) for c in vcc} == {("U1", "8"), ("R1", "1")}
    # PB0's X9 node is dropped (no footprint); only U1.5 survives
    pb0 = [c for c in spec["connections"] if c["net"] == "PB0"]
    assert {(c["ref"], c["pad"]) for c in pb0} == {("U1", "5")}


def test_nets_listed():
    spec = netlist.parse_netlist(SAMPLE)
    assert set(spec["nets"]) == {"VCC", "PB0"}


def test_quoted_strings_with_spaces():
    spec = netlist.parse_netlist(
        '(export (components (comp (ref "C1") (value "100 nF")'
        ' (footprint "Capacitor_SMD:C_0805_2012Metric"))) (nets))')
    assert spec["footprints"][0]["value"] == "100 nF"


def test_not_a_netlist_raises():
    import pytest
    with pytest.raises(ValueError):
        netlist.parse_netlist("(something_else (foo))")


def test_missing_footprints_flagged_with_suggestions():
    """A bogus footprint is reported (with suggestions); a real one isn't."""
    from daokicad import env
    if not env.detect().available:
        import pytest
        pytest.skip("KiCad not installed")
    from daokicad.live import LiveKiCad

    lk = LiveKiCad()
    fps = [
        {"ref": "R1", "lib": "Resistor_SMD", "fp": "R_0603_1608Metric"},
        {"ref": "X1", "lib": "Resistor_SMD", "fp": "R_does_not_exist_9999"},
    ]
    miss = lk.missing_footprints(fps)
    assert {m["ref"] for m in miss} == {"X1"}
    assert miss[0]["lib_exists"] is True
    assert miss[0]["suggestions"]  # close R_* names exist


def test_heal_footprints_gender_rename(tmp_path):
    """A renamed footprint (Female->Socket) heals to the in-lib name; a real
    name and a truly-absent one are left untouched."""
    from daokicad.live import LiveKiCad

    lib = tmp_path / "Connector_Dsub.pretty"
    lib.mkdir()
    for n in ("DSUB-25_Socket_Horizontal_P2.77x2.84mm",
              "DSUB-9_Socket_Horizontal_P2.77x2.84mm"):
        (lib / (n + ".kicad_mod")).write_text("(footprint)", encoding="utf-8")
    lib_dirs = {"Connector_Dsub": str(lib)}
    fps = [
        {"ref": "P1", "lib": "Connector_Dsub",
         "fp": "DSUB-25_Female_Horizontal_P2.77x2.84mm"},          # rename -> heal
        {"ref": "P2", "lib": "Connector_Dsub",
         "fp": "DSUB-9_Socket_Horizontal_P2.77x2.84mm"},           # exact -> untouched
        {"ref": "P3", "lib": "Connector_Dsub", "fp": "TOTALLY_BOGUS"},  # absent
    ]
    subs = LiveKiCad().heal_footprints(fps, lib_dirs)
    assert {s["ref"] for s in subs} == {"P1"}
    assert fps[0]["fp"] == "DSUB-25_Socket_Horizontal_P2.77x2.84mm"
    assert fps[1]["fp"] == "DSUB-9_Socket_Horizontal_P2.77x2.84mm"
    assert fps[2]["fp"] == "TOTALLY_BOGUS"


def test_heal_footprints_male_to_pins(tmp_path):
    """Male->Pins is a DIFFERENT rename than Female->Socket; the directional
    swap must not be ambiguous (the sonde-xilinx demo regression)."""
    from daokicad.live import LiveKiCad

    lib = tmp_path / "Connector_Dsub.pretty"
    lib.mkdir()
    # both genders present so a naive 'strip gender token' key would be ambiguous
    for n in ("DSUB-25_Pins_EdgeMount_P2.77mm",
              "DSUB-25_Socket_EdgeMount_P2.77mm"):
        (lib / (n + ".kicad_mod")).write_text("(footprint)", encoding="utf-8")
    fps = [{"ref": "J1", "lib": "Connector_Dsub",
            "fp": "DSUB-25_Male_EdgeMount_P2.77mm"}]
    subs = LiveKiCad().heal_footprints(fps, {"Connector_Dsub": str(lib)})
    assert len(subs) == 1
    assert fps[0]["fp"] == "DSUB-25_Pins_EdgeMount_P2.77mm"


def test_heal_footprints_pad_dimension_drop(tmp_path):
    """Newer libs dropped the ``_Pad<W>x<H>mm`` annotation from hand-solder
    names (the video demo's tantalum-cap regression); healing removes the
    token and accepts the verbatim in-lib name, leaving real names untouched."""
    from daokicad.live import LiveKiCad

    lib = tmp_path / "Capacitor_Tantalum_SMD.pretty"
    lib.mkdir()
    for n in ("CP_EIA-3528-21_Kemet-B_HandSolder",
              "CP_EIA-3528-21_Kemet-B"):
        (lib / (n + ".kicad_mod")).write_text("(footprint)", encoding="utf-8")
    lib_dirs = {"Capacitor_Tantalum_SMD": str(lib)}
    fps = [
        {"ref": "C56", "lib": "Capacitor_Tantalum_SMD",
         "fp": "CP_EIA-3528-21_Kemet-B_Pad1.50x2.35mm_HandSolder"},  # heal
        {"ref": "C57", "lib": "Capacitor_Tantalum_SMD",
         "fp": "CP_EIA-3528-21_Kemet-B"},                            # exact
        {"ref": "C58", "lib": "Capacitor_Tantalum_SMD",
         "fp": "CP_EIA-9999-99_Pad9.99x9.99mm_HandSolder"},          # absent
    ]
    subs = LiveKiCad().heal_footprints(fps, lib_dirs)
    assert {s["ref"] for s in subs} == {"C56"}
    assert fps[0]["fp"] == "CP_EIA-3528-21_Kemet-B_HandSolder"
    assert fps[1]["fp"] == "CP_EIA-3528-21_Kemet-B"
    assert fps[2]["fp"] == "CP_EIA-9999-99_Pad9.99x9.99mm_HandSolder"


def test_heal_footprints_generic_easyeda_chip_remap(tmp_path):
    """EasyEDA exports bare ``C0402``/``R0805``/``LED0603`` in an absent
    ``easyeda2kicad`` lib (the openair-max demo); healing remaps them onto the
    KiCad-standard chip footprints by the IPC imperial↔metric equivalence, and
    only when the standard target genuinely exists — unknown packages are left
    untouched so they are honestly reported missing, never invented."""
    from daokicad.live import LiveKiCad

    cap = tmp_path / "Capacitor_SMD.pretty"; cap.mkdir()
    res = tmp_path / "Resistor_SMD.pretty"; res.mkdir()
    led = tmp_path / "LED_SMD.pretty"; led.mkdir()
    (cap / "C_0402_1005Metric.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (res / "R_0805_2012Metric.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (led / "LED_0603_1608Metric.kicad_mod").write_text("(footprint)", encoding="utf-8")
    lib_dirs = {"Capacitor_SMD": str(cap), "Resistor_SMD": str(res),
                "LED_SMD": str(led)}
    fps = [
        {"ref": "C1", "lib": "easyeda2kicad", "fp": "C0402"},     # -> cap
        {"ref": "R1", "lib": "easyeda2kicad", "fp": "R0805"},     # -> res
        {"ref": "D1", "lib": "easyeda2kicad", "fp": "LED0603"},   # -> led
        {"ref": "U1", "lib": "easyeda2kicad",
         "fp": "CONN-SMD_HC-1.25-8PWT"},                          # untouched
    ]
    subs = LiveKiCad().heal_footprints(fps, lib_dirs)
    assert {s["ref"] for s in subs} == {"C1", "R1", "D1"}
    assert (fps[0]["lib"], fps[0]["fp"]) == ("Capacitor_SMD", "C_0402_1005Metric")
    assert (fps[1]["lib"], fps[1]["fp"]) == ("Resistor_SMD", "R_0805_2012Metric")
    assert (fps[2]["lib"], fps[2]["fp"]) == ("LED_SMD", "LED_0603_1608Metric")
    assert (fps[3]["lib"], fps[3]["fp"]) == ("easyeda2kicad", "CONN-SMD_HC-1.25-8PWT")


def test_heal_generic_remap_requires_target_exists(tmp_path):
    """A generic name whose standard target is *absent* must not be remapped
    (no inventing footprints): C2512 with no Capacitor_SMD lib stays as-is."""
    from daokicad.live import LiveKiCad

    cap = tmp_path / "Capacitor_SMD.pretty"; cap.mkdir()  # exists but empty
    fps = [{"ref": "C9", "lib": "easyeda2kicad", "fp": "C2512"}]
    subs = LiveKiCad().heal_footprints(fps, {"Capacitor_SMD": str(cap)})
    assert subs == []
    assert (fps[0]["lib"], fps[0]["fp"]) == ("easyeda2kicad", "C2512")


def test_heal_generic_discrete_package_remap(tmp_path):
    """EasyEDA emits discrete packages with a trailing land-pattern detail
    (``SOD-123_L2.7-...``, ``SOT-23-6_L2.9-...``); the leading token alone fixes
    the standard KiCad footprint (Diode_SMD / Package_TO_SOT_SMD)."""
    from daokicad.live import LiveKiCad

    dio = tmp_path / "Diode_SMD.pretty"; dio.mkdir()
    sot = tmp_path / "Package_TO_SOT_SMD.pretty"; sot.mkdir()
    (dio / "D_SOD-123.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (sot / "SOT-23-6.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (sot / "SOT-23.kicad_mod").write_text("(footprint)", encoding="utf-8")
    lib_dirs = {"Diode_SMD": str(dio), "Package_TO_SOT_SMD": str(sot)}
    fps = [
        {"ref": "D1", "lib": "easyeda2kicad", "fp": "SOD-123_L2.7-W1.6-LS3.7-FD"},
        {"ref": "Q1", "lib": "easyeda2kicad", "fp": "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BR"},
        {"ref": "Q2", "lib": "easyeda2kicad", "fp": "SOT-583-8_L2.1-W1.2"},  # untouched
    ]
    subs = LiveKiCad().heal_footprints(fps, lib_dirs)
    assert {s["ref"] for s in subs} == {"D1", "Q1"}
    assert (fps[0]["lib"], fps[0]["fp"]) == ("Diode_SMD", "D_SOD-123")
    assert (fps[1]["lib"], fps[1]["fp"]) == ("Package_TO_SOT_SMD", "SOT-23-6")
    assert fps[2]["fp"] == "SOT-583-8_L2.1-W1.2"


def test_heal_ipc7351_geometric_names(tmp_path):
    """Vendor/Ultra-Librarian exports (the multichannel demo) name footprints by
    IPC-7351 geometry: chip passives ``CAPC3216X140N``/``RESC3216X65N`` (metric
    body), polarized radial THT caps ``CAPPRB254-500X840`` (pitch/Ø) and narrow
    SOICs ``SOIC127P600X175-8N`` (pitch/pins). Each maps onto a KiCad-stock
    footprint by exact geometry, accepted only when the target really exists."""
    from daokicad.live import LiveKiCad

    cap = tmp_path / "Capacitor_SMD.pretty"; cap.mkdir()
    res = tmp_path / "Resistor_SMD.pretty"; res.mkdir()
    cth = tmp_path / "Capacitor_THT.pretty"; cth.mkdir()
    so = tmp_path / "Package_SO.pretty"; so.mkdir()
    sot = tmp_path / "Package_TO_SOT_SMD.pretty"; sot.mkdir()
    (cap / "C_1206_3216Metric.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (res / "R_1206_3216Metric.kicad_mod").write_text("(footprint)", encoding="utf-8")
    # only the 2.50mm metric-grid radial exists, not a verbatim 2.54mm one
    (cth / "CP_Radial_D5.0mm_P2.50mm.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (so / "SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (sot / "SOT-23.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (sot / "SOT-363_SC-70-6.kicad_mod").write_text("(footprint)", encoding="utf-8")
    lib_dirs = {"Capacitors SMD": str(cap), "Resistors SMD": str(res),
                "Capacitors THD": str(cth), "ICs And Semiconductors SMD": str(so),
                "Transistors SMD": str(sot),
                "Capacitor_SMD": str(cap), "Resistor_SMD": str(res),
                "Capacitor_THT": str(cth), "Package_SO": str(so),
                "Package_TO_SOT_SMD": str(sot)}
    fps = [
        {"ref": "C35", "lib": "Capacitors SMD", "fp": "CAPC3216X140N"},
        {"ref": "R37", "lib": "Resistors SMD", "fp": "RESC3216X65N"},
        {"ref": "C40", "lib": "Capacitors THD", "fp": "CAPPRB254-500X840"},
        {"ref": "IC5", "lib": "ICs And Semiconductors SMD", "fp": "SOIC127P600X175-8N"},
        {"ref": "Q1", "lib": "Transistors SMD", "fp": "SOT95P240X110-3N"},   # SOT-23
        {"ref": "U7", "lib": "Transistors SMD", "fp": "SOT65P210X110-6N"},   # SC-70-6
        {"ref": "J1", "lib": "Connectors", "fp": "CLIFF_FC68148(DC-10A)"},  # custom
    ]
    subs = LiveKiCad().heal_footprints(fps, lib_dirs)
    assert {s["ref"] for s in subs} == {"C35", "R37", "C40", "IC5", "Q1", "U7"}
    assert (fps[0]["lib"], fps[0]["fp"]) == ("Capacitor_SMD", "C_1206_3216Metric")
    assert (fps[1]["lib"], fps[1]["fp"]) == ("Resistor_SMD", "R_1206_3216Metric")
    assert (fps[2]["lib"], fps[2]["fp"]) == ("Capacitor_THT", "CP_Radial_D5.0mm_P2.50mm")
    assert (fps[3]["lib"], fps[3]["fp"]) == ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm")
    assert (fps[4]["lib"], fps[4]["fp"]) == ("Package_TO_SOT_SMD", "SOT-23")
    assert (fps[5]["lib"], fps[5]["fp"]) == ("Package_TO_SOT_SMD", "SOT-363_SC-70-6")
    assert fps[6]["fp"] == "CLIFF_FC68148(DC-10A)"  # truly custom: untouched


def test_heal_stock_name_relibrary(tmp_path):
    """Real boards (KiCad's jetson-agx-thor-baseboard demo) vendor every part
    into one private library whose ``.pretty`` isn't shipped, so the cited lib
    can't resolve — yet the footprint names are verbatim KiCad-stock names. When
    a name is owned by exactly one stock library, keep the name and fix only the
    library; ambiguous or truly-unknown names are left untouched (never guess).
    """
    import types
    from daokicad.live import LiveKiCad

    stock = tmp_path / "stock"; stock.mkdir()
    res = stock / "Resistor_SMD.pretty"; res.mkdir()
    tp = stock / "TestPoint.pretty"; tp.mkdir()
    a = stock / "LibA.pretty"; a.mkdir()
    b = stock / "LibB.pretty"; b.mkdir()
    (res / "R_0402_1005Metric.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (tp / "TestPoint_Pad_D1.0mm.kicad_mod").write_text("(footprint)", encoding="utf-8")
    # same name in two libs -> ambiguous, must be left alone
    (a / "AMBIG.kicad_mod").write_text("(footprint)", encoding="utf-8")
    (b / "AMBIG.kicad_mod").write_text("(footprint)", encoding="utf-8")

    lk = LiveKiCad()
    lk.env = types.SimpleNamespace(footprints=str(stock))
    fps = [
        {"ref": "R1", "lib": "antmicro-footprints", "fp": "R_0402_1005Metric"},
        {"ref": "TP1", "lib": "antmicro-footprints", "fp": "TestPoint_Pad_D1.0mm"},
        {"ref": "X1", "lib": "antmicro-footprints", "fp": "AMBIG"},          # 2 libs
        {"ref": "U1", "lib": "antmicro-footprints", "fp": "TOTALLY_CUSTOM"},  # none
    ]
    subs = lk.heal_footprints(fps, {})
    assert {s["ref"] for s in subs} == {"R1", "TP1"}
    assert (fps[0]["lib"], fps[0]["fp"]) == ("Resistor_SMD", "R_0402_1005Metric")
    assert (fps[1]["lib"], fps[1]["fp"]) == ("TestPoint", "TestPoint_Pad_D1.0mm")
    assert fps[2]["lib"] == "antmicro-footprints"  # ambiguous: untouched
    assert fps[3]["lib"] == "antmicro-footprints"  # unknown: untouched


def test_parse_scales_linearly_on_large_netlist():
    """A real board (KiCad's vme-wren demo, ~1500 parts / hundreds of thousands
    of tokens) must parse in seconds, not minutes. The s-expression reader uses
    an index cursor; a ``tokens.pop(0)`` front-pop is O(n) and made this
    quadratic (>20 min). Build a big synthetic netlist and require it parse
    quickly with exact counts — reintroducing the front-pop would time this out.
    """
    import time
    from daokicad import netlist as nl

    n = 3000
    comps = "".join(
        f'(comp (ref "R{i}") (value "1k") (footprint "Resistor_SMD:R_0402_1005Metric"))'
        for i in range(n))
    nets = "".join(
        f'(net (code "{i}") (name "N{i}") '
        f'(node (ref "R{i}") (pin "1")) (node (ref "R{(i + 1) % n}") (pin "2")))'
        for i in range(n))
    text = f"(export (version D) (components {comps}) (nets {nets}))"

    t0 = time.time()
    spec = nl.parse_netlist(text)
    dt = time.time() - t0
    assert len(spec["footprints"]) == n
    assert len(spec["nets"]) == n
    assert len(spec["connections"]) == 2 * n
    assert dt < 10.0, f"parse took {dt:.1f}s — quadratic regression?"


def test_power_nets_detection():
    from daokicad import netlist as nl
    nets = ["GND", "VCC", "+5V", "+3V3", "-12V", "V+", "/GND",
            "Net-(R1-Pad1)", "SCL", "D0", "CLK", "VBUS"]
    found = nl.power_nets(nets)
    for p in ("GND", "VCC", "+5V", "+3V3", "-12V", "V+", "/GND", "VBUS"):
        assert p in found, p
    for s in ("Net-(R1-Pad1)", "SCL", "D0", "CLK"):
        assert s not in found, s


def test_route_timeout_scales_with_size():
    from daokicad.live import LiveKiCad
    f = LiveKiCad.route_timeout_for
    assert f(None) == 600          # unknown -> floor
    assert f(5) == 600             # tiny -> floor
    assert f(279) == 2700          # coldfire -> proportional, hits ceiling
    assert f(120) == 1200          # mid -> proportional
    assert f(10_000) == 2700       # huge -> clamped to ceiling


def test_safe_route_stem():
    from daokicad.live import LiveKiCad
    f = LiveKiCad._safe_stem
    assert f("sonde xilinx") == "sonde_xilinx"   # the demo regression
    assert f("plain") == "plain"
    assert f("a (b) c") == "a_b_c"
    assert f("with.dots-and_underscores") == "with.dots-and_underscores"
    assert f("") == "board"


def test_inset_dsn_boundary(tmp_path):
    from daokicad.live import LiveKiCad
    dsn = tmp_path / "b.dsn"
    dsn.write_text(
        "(pcb x\n  (structure\n    (boundary\n"
        "      (path pcb 0  114060 -111424  15000 -111424  15000 -15000  "
        "114060 -15000  114060 -111424)\n    )\n  )\n)\n", encoding="utf-8")
    assert LiveKiCad._inset_dsn_boundary(dsn, 500) is True
    t = dsn.read_text(encoding="utf-8")
    # each edge moved inward by 500 units; new extents 15500..113560, -110924..-15500
    assert "15500" in t and "113560" in t
    assert "-110924" in t and "-15500" in t
    assert "15000 -111424" not in t  # original corner gone
    # idempotent guards: zero clearance and non-rect are no-ops
    dsn2 = tmp_path / "c.dsn"
    dsn2.write_text(t, encoding="utf-8")
    before = dsn2.read_text(encoding="utf-8")
    assert LiveKiCad._inset_dsn_boundary(dsn2, 0) is False
    assert dsn2.read_text(encoding="utf-8") == before


def test_inset_dsn_boundary_non_rectangle(tmp_path):
    from daokicad.live import LiveKiCad
    dsn = tmp_path / "tri.dsn"
    body = "(boundary\n      (path pcb 0  0 0  1000 0  500 1000  0 0)\n    )"
    dsn.write_text(body, encoding="utf-8")
    assert LiveKiCad._inset_dsn_boundary(dsn, 100) is False  # triangle untouched
    assert dsn.read_text(encoding="utf-8") == body


def test_build_from_schematic_missing_file():
    from daokicad.live import LiveKiCad
    res = LiveKiCad().build_from_schematic("nope_does_not_exist.kicad_sch", "out/x.kicad_pcb")
    assert res["ok"] is False and "原理图" in res["reason"]
