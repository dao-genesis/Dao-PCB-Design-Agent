#!/usr/bin/env python3
"""schematic_dao CLI — 批量生成原理图工程资料包

用法:
    python -m schematic_dao list                      # 列出全部项目
    python -m schematic_dao build <project_name>      # 生成默认输出位置
    python -m schematic_dao build <project> <output>  # 自定义输出根目录
    python -m schematic_dao validate <project>        # 仅校验, 不写文件
"""

from __future__ import annotations

import sys
from pathlib import Path
from importlib import import_module

from .pipeline import generate_pack
from .schematic_dao import SchematicProject


# ────────────────────────────────────────────────────────────────
# 项目注册 — 添加新项目时在此处加一行
# ────────────────────────────────────────────────────────────────

_PROJECT_REGISTRY = {
    "warehouse_logistics_vehicle": (
        ".projects.warehouse_logistics_vehicle",
        "build_project",
        "实战/仓库车间物流车控制系统设计",
    ),
}


def _load_project(name: str) -> tuple[SchematicProject, str]:
    if name not in _PROJECT_REGISTRY:
        raise SystemExit(
            f"未知项目: {name}\n可用: {', '.join(_PROJECT_REGISTRY.keys())}"
        )
    mod_path, fn, default_out = _PROJECT_REGISTRY[name]
    mod = import_module(mod_path, package=__package__)
    proj: SchematicProject = getattr(mod, fn)()
    return proj, default_out


def _cmd_list():
    print("可用项目:")
    for name, (_, _, out) in _PROJECT_REGISTRY.items():
        print(f"  • {name}  →  {out}")


def _cmd_validate(name: str):
    proj, _ = _load_project(name)
    warns = proj.validate()
    stats = proj.stats()
    print(f"项目: {proj.name}  ({proj.title.title_cn})")
    print(f"  模块: {stats['modules']}  元件: {stats['components']}  "
          f"网络: {stats['nets']}  引脚: {stats['pins']}")
    print(f"  分组: {', '.join(stats['groups'])}")
    if warns:
        print(f"\n[!] 校验告警 ({len(warns)} 条):")
        for w in warns:
            print(f"  - {w}")
    else:
        print("\n[OK] 数据模型一致, 无告警")


def _cmd_build(name: str, output: str | None):
    proj, default_out = _load_project(name)
    if output:
        output_root = Path(output)
    else:
        # 默认输出在 PCB设计/{default_out}/
        # 通过 __file__ 反推 PCB设计 根目录
        pcb_root = Path(__file__).resolve().parent.parent
        output_root = pcb_root / default_out

    print(f"项目: {proj.name}")
    print(f"标题: {proj.title.title_cn}")
    print(f"输出: {output_root}")
    print()

    # 校验
    warns = proj.validate()
    if warns:
        print(f"[!] 校验告警 ({len(warns)} 条) — 已记录至 _VALIDATION.txt, 不阻塞生成")

    files = generate_pack(proj, output_root, clean=True)

    print("生成清单:")
    for sec, fs in files.items():
        print(f"\n  {sec}:")
        for f in fs:
            rel = Path(f).relative_to(output_root)
            print(f"    + {rel}")

    total = sum(len(fs) for fs in files.values())
    print(f"\n[OK] 共生成 {total} 个文件")


def main(argv: list[str] | None = None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return

    cmd = argv[0]
    if cmd == "list":
        _cmd_list()
    elif cmd == "validate":
        if len(argv) < 2:
            raise SystemExit("用法: validate <project>")
        _cmd_validate(argv[1])
    elif cmd == "build":
        if len(argv) < 2:
            raise SystemExit("用法: build <project> [<output_root>]")
        _cmd_build(argv[1], argv[2] if len(argv) > 2 else None)
    else:
        raise SystemExit(f"未知命令: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
