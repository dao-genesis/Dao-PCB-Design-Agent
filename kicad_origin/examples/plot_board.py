r"""plot_board — 把一块 .kicad_pcb 画成 PNG (焊盘+走线 按网着色), 用于实践可视化."""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from kicad_origin.pcb.board import Board
from kicad_origin.pcb.route import _pad_world

_PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0",
            "#f032e6", "#bcf60c", "#fabebe", "#008080", "#9a6324", "#800000"]


def plot(board_path: str, out_png: str, title: str = "") -> str:
    b = Board.load(board_path)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_aspect("equal")
    ax.invert_yaxis()   # KiCad Y 向下

    ol = b.board_outline()
    if ol:
        x0, y0, x1, y1 = ol.to_tuple()
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False,
                               edgecolor="#222", lw=1.5))

    def color(net: int) -> str:
        return "#999" if net <= 0 else _PALETTE[(net - 1) % len(_PALETTE)]

    # 焊盘
    for fp in b.footprints():
        for pad in fp.pads():
            wp = _pad_world(fp, pad)
            w, h = pad.width, pad.height
            ax.add_patch(Rectangle((wp.x - w / 2, wp.y - h / 2), w, h,
                                   facecolor=color(pad.net_number),
                                   edgecolor="black", lw=0.3, alpha=0.9))
        ax.text(fp.position.x, fp.position.y, fp.ref, fontsize=7,
                ha="center", va="center", color="black", weight="bold")

    # 走线 (F.Cu 实线, B.Cu 虚线以区分双层)
    for seg in b.segments():
        s, e = seg.start, seg.end
        bottom = str(seg.layer).startswith("B.")
        ax.plot([s.x, e.x], [s.y, e.y], color=color(seg.net),
                lw=seg.width * 3, solid_capstyle="round",
                ls="--" if bottom else "-", alpha=0.7 if bottom else 1.0)

    # 过孔 (换层点)
    for via in b.vias():
        p = via.position
        ax.plot([p.x], [p.y], marker="o", markersize=via.size * 6,
                markerfacecolor="white", markeredgecolor=color(via.net),
                markeredgewidth=1.2)

    # 网络图例
    seen = {}
    for n in b.nets():
        if n.number > 0:
            seen[n.number] = n.name
    handles = [plt.Line2D([0], [0], color=color(num), lw=3, label=name)
               for num, name in sorted(seen.items())]
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)

    ax.set_title(title or Path(board_path).stem)
    ax.margins(0.05)
    ax.grid(True, ls=":", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    return out_png


if __name__ == "__main__":
    bp = sys.argv[1] if len(sys.argv) > 1 else "_agent_work/ams1117_power_designed.kicad_pcb"
    op = sys.argv[2] if len(sys.argv) > 2 else "_agent_work/ams1117_power_designed.png"
    print("saved", plot(bp, op))
