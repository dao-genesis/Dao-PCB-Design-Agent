"""
excellon — Excellon 2 钻孔文件写出器

格式: M48 头 / METRIC / FMAT,2 / T01..Tn 工具定义 / TnXxxYyy 钻点 / M30 尾.

主流制造商 (JLC / PCBWay / OSHPark) 兼容. 单位 mm, 6 位小数.

输出:
    <project>-PTH.drl   电镀通孔 (plated, 走 net 的)
    <project>-NPTH.drl  非电镀通孔 (np_thru_hole, 通常机械孔)

实际上 Excellon 不区分 PTH/NPTH (这是 KiCad 制造文件的约定); 我们也按
KiCad 习惯分两份, 让上传者直接用.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from kicad_origin.pcb.board import Board
from kicad_origin.pcb.geometry import Point


class ExcellonWriter:
    """单文件钻孔写出器."""

    DEC_DIGITS = 6  # mm 6 位小数

    def __init__(self, header_comment: str = "kicad_origin"):
        self.header_comment = header_comment
        # 工具表: dia (mm) → tool_id (T01..)
        self.tools: Dict[float, int] = {}
        # 钻点: (tool_id, Point) 列表
        self.holes: List[Tuple[int, Point]] = []
        self._next_tool = 1

    def _get_or_alloc_tool(self, dia: float) -> int:
        # 量化到 0.001 mm 避免浮点抖动
        key = round(dia, 4)
        if key in self.tools:
            return self.tools[key]
        tid = self._next_tool
        self._next_tool += 1
        self.tools[key] = tid
        return tid

    def add_hole(self, x: float, y: float, dia: float) -> None:
        """添加一个钻孔 (mm 坐标 + mm 直径)."""
        if dia <= 0:
            return
        tid = self._get_or_alloc_tool(dia)
        self.holes.append((tid, Point(x, y)))

    def finalize(self) -> str:
        lines: List[str] = []
        lines.append("M48")
        lines.append(f"; {self.header_comment}")
        lines.append("FMAT,2")
        lines.append("METRIC,TZ")
        # 工具定义 (按 tool id 升序)
        sorted_tools = sorted(self.tools.items(), key=lambda kv: kv[1])
        for dia, tid in sorted_tools:
            lines.append(f"T{tid:02d}C{dia:.4f}")
        lines.append("%")
        lines.append("G90")  # 绝对坐标
        lines.append("G05")  # 钻孔模式
        # 按 tool 分组钻孔
        from itertools import groupby
        # 排序: 同一 tool 集中 (减少换刀)
        ordered = sorted(self.holes, key=lambda h: h[0])
        for tid, group in groupby(ordered, key=lambda h: h[0]):
            lines.append(f"T{tid:02d}")
            for _, pt in group:
                # KiCad y 向下, Excellon y 向上 → 翻转 y
                lines.append(f"X{pt.x:.4f}Y{-pt.y:.4f}")
        lines.append("T0")
        lines.append("M30")
        return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────
# 顶层 API
# ─────────────────────────────────────────────────────────────────────
def write_excellon(board: Board, output_dir: Union[str, Path],
                   *, project_name: Optional[str] = None,
                   split_pth_npth: bool = True) -> List[str]:
    """把 board 中的所有钻孔写成 Excellon 文件.

    Args:
        split_pth_npth: 是否分 PTH / NPTH 两份 (KiCad 默认行为)
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if project_name is None:
        if board.path:
            project_name = Path(board.path).stem
        else:
            project_name = board.title or "project"

    pth = ExcellonWriter("PTH (plated through-hole)")
    npth = ExcellonWriter("NPTH (non-plated through-hole)")

    # 收集 footprint 钻孔 (pad with drill > 0)
    for fp in board.footprints():
        center = fp.position
        for pad in fp.pads():
            if pad.drill <= 0:
                continue
            pp = pad.position
            x = center.x + pp.x
            y = center.y + pp.y
            target = npth if pad.type == "np_thru_hole" else pth
            target.add_hole(x, y, pad.drill)

    # 收集过孔
    for via in board.vias():
        if via.drill <= 0:
            continue
        # via 总是 PTH
        pth.add_hole(via.position.x, via.position.y, via.drill)

    out_paths: List[str] = []

    if split_pth_npth:
        if pth.holes:
            p = out_dir / f"{project_name}-PTH.drl"
            p.write_text(pth.finalize(), encoding="utf-8")
            out_paths.append(str(p))
        if npth.holes:
            p = out_dir / f"{project_name}-NPTH.drl"
            p.write_text(npth.finalize(), encoding="utf-8")
            out_paths.append(str(p))
    else:
        # 合并: 把 npth 的钻孔倒进 pth
        for tid, pt in npth.holes:
            # 反查 dia
            dia = next((d for d, t in npth.tools.items() if t == tid), 0.0)
            if dia > 0:
                pth.add_hole(pt.x, pt.y, dia)
        if pth.holes:
            p = out_dir / f"{project_name}.drl"
            p.write_text(pth.finalize(), encoding="utf-8")
            out_paths.append(str(p))

    return sorted(out_paths)


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import tempfile
    if len(sys.argv) > 1:
        b = Board.load(sys.argv[1])
        out = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="drl_")
        files = write_excellon(b, out)
        for f in files:
            sz = Path(f).stat().st_size
            print(f"{sz:>8} bytes  {f}")
            # 头几行
            for ln in Path(f).read_text(encoding="utf-8").splitlines()[:8]:
                print(f"           {ln}")
    else:
        # 自检: 空板无钻孔
        b = Board.empty(width_mm=50, height_mm=40)
        with tempfile.TemporaryDirectory() as d:
            files = write_excellon(b, d)
            print(f"empty board → {len(files)} drill files")
        # 手动加一个 thru pad 测试
        from kicad_origin.origin.sexpr import Symbol
        fp_node = [
            Symbol("footprint"), "Test:Test",
            [Symbol("layer"), "F.Cu"],
            [Symbol("uuid"), "00000000-0000-0000-0000-000000000001"],
            [Symbol("at"), 25.0, 20.0],
            [Symbol("pad"), "1", Symbol("thru_hole"), Symbol("circle"),
                [Symbol("at"), 0.0, 0.0],
                [Symbol("size"), 1.6, 1.6],
                [Symbol("drill"), 0.8],
                [Symbol("layers"), "*.Cu", "*.Mask"],
                [Symbol("net"), 1, "VCC"],
            ],
        ]
        b.tree.append(fp_node)
        with tempfile.TemporaryDirectory() as d:
            files = write_excellon(b, d)
            print(f"with 1 PTH → {len(files)} drill files: "
                  f"{[Path(f).name for f in files]}")
            assert len(files) == 1
            content = Path(files[0]).read_text(encoding="utf-8")
            assert "T01C0.8000" in content, "工具定义应有 0.8mm"
            assert "X25.0000" in content, "X 坐标应 25.0"
        print("excellon.py 自检 ✅")
