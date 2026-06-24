"""
ziran_workflow — 自然层全链路工作流 (dao 干活 + ziran 让你看见)

> "为之于未有, 治之于未乱;
>  合抱之木, 生于毫末;
>  九层之台, 起于累土." (《道德经》第六十四章)

Workflow.design_minimal_board 端到端:
    1. dao.new_board       内存中创空板 (50x40mm)
    2. dao.save            保存到 .kicad_pcb
    3. ziran.show_pcb      启 pcbnew 让你看到空板 (4 秒)
    4. dao.run_drc         跑 6 条规则 (空板应 0 错)
    5. dao.export_fab      出 11 张 Gerber + 钻孔 + DRC 报告
    6. ziran.show_gerber   启 gerbview 让你看到制造文件 (4 秒)
    7. close_all           优雅关掉所有 KiCad 进程

跑法:
    python kicad_origin/examples/ziran_workflow.py
    python kicad_origin/examples/ziran_workflow.py 100 80     # 自定义板尺寸 mm

注意:
    KiCad 9 首次启动会弹"数据收集选择加入"对话框, 你需要手动同意一次,
    之后再不会弹. 本 demo 在 dialog-only 状态下也能跑通制造文件流程,
    但 GUI 视觉确认会被跳过.
"""
from __future__ import annotations

import sys
import shutil
from pathlib import Path

_THIS = Path(__file__).resolve()
_ROOT = _THIS.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from kicad_origin import Dao  # noqa: E402
from kicad_origin.ziran import Workflow  # noqa: E402


def main() -> int:
    # 解析尺寸
    width = float(sys.argv[1]) if len(sys.argv) > 1 else 50.0
    height = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0

    out_dir = Path("_ziran_demo")
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)

    print("=" * 60)
    print(f"ziran_workflow — 全链路最小板 ({width:.1f}x{height:.1f} mm)")
    print("=" * 60)
    print(f"输出目录: {out_dir.absolute()}")
    print()

    # 用 Workflow 上下文 — 退出时自动 close_all
    with Workflow(verbose=True) as wf:
        result = wf.design_minimal_board(
            project_name="demo",
            project_dir=out_dir,
            size_mm=(width, height),
            review_seconds=4.0,
        )

    print()
    print("=" * 60)
    print(f"OK={result.ok}")
    print(f"Steps: {len(result.steps)}")
    if result.error:
        print(f"Error: {result.error}")
    print("Artifacts:")
    for k, v in result.artifacts.items():
        print(f"  {k:25s} = {v}")
    print("=" * 60)

    # 列输出文件
    if (out_dir / "fab").exists():
        print("\n制造文件:")
        for p in sorted((out_dir / "fab").iterdir()):
            print(f"  {p.name:30s} {p.stat().st_size:>8d} bytes")

    print("\n道法自然 — 全链路一气呵成. ✅")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
