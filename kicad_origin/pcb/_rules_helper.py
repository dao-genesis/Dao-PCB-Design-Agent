r"""_rules_helper — 由 KiCAD 自带 python(含 pcbnew) 设定可投产的本源设计规则。

道理: KiCAD 默认最小通孔钻 0.3mm, 但许多标准器件(如 ESP32-WROOM 模块的外露地焊盘
散热过孔)本就用 0.2mm 钻, 且主流厂(JLCPCB 等)支持 0.2mm. 与其去篡改 KiCAD 自带封装
的真实数据, 不如把板级最小钻规则对齐到器件与产线的真实能力 —— 名实相符, 道法自然。

用法: _rules_helper.py <board> [min_drill_mm] [min_hole2hole_mm]
"""
import sys
import pcbnew


def main() -> int:
    if len(sys.argv) < 2:
        print("USAGE: _rules_helper.py <board> [min_drill_mm] [min_hole2hole_mm]")
        return 2
    board_path = sys.argv[1]
    min_drill = pcbnew.FromMM(float(sys.argv[2]) if len(sys.argv) > 2 else 0.2)
    min_h2h = pcbnew.FromMM(float(sys.argv[3]) if len(sys.argv) > 3 else 0.2)

    b = pcbnew.LoadBoard(board_path)
    ds = b.GetDesignSettings()
    before = ds.m_MinThroughDrill
    ds.m_MinThroughDrill = min_drill
    ds.m_MinHoleToHole = min_h2h
    pcbnew.SaveBoard(board_path, b)
    print(f"RULES_OK min_drill {before/1e6:.3f}->{min_drill/1e6:.3f}mm "
          f"min_hole2hole={min_h2h/1e6:.3f}mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
