"""Tests for the deep introspection layer."""

from dao_kicad.core.introspect import LibraryIndex, BoardState, parse_sexpr, extract_from_sexpr


class TestLibraryIndex:
    """Test that we can discover and search the real KiCad ecosystem."""

    def test_discover_footprint_libraries(self):
        libs = LibraryIndex().discover()
        # Real KiCad installation has 155 footprint libraries
        assert len(libs.footprint_libraries) > 100

    def test_discover_symbol_libraries(self):
        libs = LibraryIndex().discover()
        assert len(libs.symbol_libraries) > 100

    def test_total_footprints(self):
        libs = LibraryIndex().discover()
        # Real ecosystem has 15,000+ footprints
        assert libs.total_footprints > 10000

    def test_search_footprint_resistor(self):
        libs = LibraryIndex().discover()
        results = libs.search_footprint("R_0402")
        assert len(results) > 0
        # Should find in Resistor_SMD library
        libs_found = {r[0] for r in results}
        assert "Resistor_SMD" in libs_found

    def test_search_footprint_qfp(self):
        libs = LibraryIndex().discover()
        results = libs.search_footprint("LQFP-48")
        assert len(results) > 0

    def test_search_footprint_usbc(self):
        libs = LibraryIndex().discover()
        results = libs.search_footprint("USB_C")
        assert len(results) > 0

    def test_load_footprint(self):
        libs = LibraryIndex().discover()
        fp = libs.load_footprint("Resistor_SMD", "R_0402_1005Metric")
        assert fp is not None
        assert fp.GetPadCount() == 2

    def test_load_complex_footprint(self):
        libs = LibraryIndex().discover()
        fp = libs.load_footprint("Package_QFP", "LQFP-48_7x7mm_P0.5mm")
        assert fp is not None
        assert fp.GetPadCount() == 48


class TestBoardState:
    """Test board state introspection."""

    def test_empty_board(self):
        import pcbnew
        board = pcbnew.BOARD()
        state = BoardState.from_board(board)
        assert len(state.footprints) == 0
        assert state.tracks == 0

    def test_board_with_components(self):
        import pcbnew
        board = pcbnew.BOARD()
        libs = LibraryIndex().discover()

        fp = libs.load_footprint("Resistor_SMD", "R_0402_1005Metric")
        fp.SetReference("R1")
        fp.SetValue("10k")
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(50), pcbnew.FromMM(50)))
        board.Add(fp)

        state = BoardState.from_board(board)
        assert len(state.footprints) == 1
        assert state.footprints[0]["reference"] == "R1"
        assert state.footprints[0]["value"] == "10k"

    def test_summary_output(self):
        import pcbnew
        board = pcbnew.BOARD()
        state = BoardState.from_board(board)
        summary = state.summary()
        assert "Board:" in summary
        assert "Footprints:" in summary


class TestSExprParser:
    """Test S-expression parsing for deep file analysis."""

    def test_simple_sexpr(self):
        result = parse_sexpr('(hello "world" 42)')
        assert result == [["hello", "world", "42"]]

    def test_nested_sexpr(self):
        result = parse_sexpr('(a (b c) (d e))')
        assert result == [["a", ["b", "c"], ["d", "e"]]]

    def test_kicad_footprint_parse(self):
        sexpr = '(footprint "R_0402" (layer "F.Cu") (pad "1" smd rect))'
        result = parse_sexpr(sexpr)
        assert result[0][0] == "footprint"
        assert result[0][1] == "R_0402"

    def test_extract_from_sexpr(self):
        sexpr = '(board (net 0 "") (net 1 "VCC") (net 2 "GND"))'
        parsed = parse_sexpr(sexpr)
        nets = extract_from_sexpr(parsed[0], "net")
        assert len(nets) == 3
