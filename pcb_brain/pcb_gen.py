"""
pcb_gen — DNA → .kicad_pcb 生成器

从 DNA 模板生成完整的 KiCad PCB 文件.
"""
from __future__ import annotations

import uuid as _uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.sexpr import Symbol
from kicad_origin.pcb.board import Board
from pcb_brain.circuit_dna import CircuitDNA, DNA, Comp


def _fp_property(key: str, value: str, layer: str,
                 px: float, py: float) -> List[Any]:
    """KiCad 10 结构化 footprint property (含 at/layer/uuid/effects)。"""
    return [
        Symbol("property"), key, value,
        [Symbol("at"), px, py, 0],
        [Symbol("layer"), layer],
        [Symbol("uuid"), str(_uuid.uuid4())],
        [Symbol("effects"),
         [Symbol("font"),
          [Symbol("size"), 1.0, 1.0],
          [Symbol("thickness"), 0.15]]],
    ]


def dna_to_board(dna: DNA) -> Board:
    """Convert a DNA template to a Board with footprints and nets."""
    board = Board.empty()
    bw, bh = dna.board_size

    # Board outline
    board.tree.append([
        Symbol("gr_rect"),
        [Symbol("start"), 90.0, 90.0],
        [Symbol("end"), 90.0 + bw, 90.0 + bh],
        [Symbol("layer"), "Edge.Cuts"],
        [Symbol("width"), 0.05],
        [Symbol("uuid"), str(_uuid.uuid4())],
    ])

    # Nets
    net_map: Dict[str, int] = {"": 0}
    net_idx = 1
    for net_name in sorted(dna.nets.keys()):
        net_map[net_name] = net_idx
        board.add_net(net_idx, net_name)
        net_idx += 1

    # Footprints
    for comp in dna.components:
        ox, oy = 90.0, 90.0  # board origin offset
        x, y = ox + comp.position[0], oy + comp.position[1]
        lib_id = f"{comp.fp_lib}:{comp.fp_name}"

        node: List[Any] = [
            Symbol("footprint"), lib_id,
            [Symbol("layer"), "F.Cu"],
            [Symbol("uuid"), str(_uuid.uuid4())],
            [Symbol("at"), x, y],
            _fp_property("Reference", comp.ref, "F.SilkS", 0.0, -2.0),
            _fp_property("Value", comp.value, "F.Fab", 0.0, 2.0),
        ]

        # Find which nets this component's pads connect to
        pad_nets: Dict[str, str] = {}
        for net_name, connections in dna.nets.items():
            for ref, pad_num in connections:
                if ref == comp.ref:
                    pad_nets[pad_num] = net_name

        # Generate placeholder pads (will be inlined later from .kicad_mod)
        pad_numbers = sorted(set(pad_nets.keys()) | {"1", "2"})
        for i, pn in enumerate(pad_numbers):
            net_name = pad_nets.get(pn, "")
            net_num = net_map.get(net_name, 0)
            pad_x = (i - len(pad_numbers) / 2.0 + 0.5) * 1.27
            pad_node = [
                Symbol("pad"), pn, Symbol("smd"), Symbol("rect"),
                [Symbol("at"), round(pad_x, 3), 0],
                [Symbol("size"), 1.0, 1.0],
                [Symbol("layers"), "F.Cu", "F.Paste", "F.Mask"],
            ]
            if net_name:
                pad_node.append([Symbol("net"), net_num, net_name])
            node.append(pad_node)

        board.add_footprint(node)

    return board


def generate_pcb(dna_name: str, output_dir: str = ".") -> Dict[str, Any]:
    """Generate a .kicad_pcb from a registered DNA template.

    Returns: {"ok": bool, "path": str, "summary": dict}
    """
    dna = CircuitDNA.get(dna_name)
    if dna is None:
        return {"ok": False, "error": f"Unknown DNA template: {dna_name}",
                "available": CircuitDNA.list_names()}

    board = dna_to_board(dna)
    out_path = Path(output_dir) / f"{dna_name}.kicad_pcb"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    board.save(str(out_path))

    return {
        "ok": True,
        "path": str(out_path),
        "dna": dna_name,
        "summary": board.summary(),
    }


def _route_via_kicad_python(pcb_path: str, out_dir: str,
                            passes: int = 8) -> Optional[Dict[str, Any]]:
    """在 KiCad 自带 python 子进程里跑 freerouting 布线闭环 (优雅降级)。

    build_fab_package 跑在 devin python (无 pcbnew); 布线须经 KiCad python +
    freerouting。工具不全则返回 None, 不影响只布局的制造产出。
    """
    import json as _json
    import subprocess as _sp
    from kicad_origin.origin.env import find_kicad_python

    kpy = find_kicad_python()
    if not kpy:
        return None
    root = str(Path(__file__).resolve().parents[1])
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "from kicad_origin.examples import forward_route as f;"
        "import json; print('FRROUTE'+json.dumps("
        "f.route_board(r'%s', out_dir=r'%s', passes=%d)))"
    ) % (root, pcb_path, out_dir, passes)
    try:
        cp = _sp.run([str(kpy), "-c", code], capture_output=True,
                     text=True, timeout=900)
    except Exception:  # noqa: BLE001
        return None
    for line in (cp.stdout or "").splitlines():
        if line.startswith("FRROUTE"):
            try:
                return _json.loads(line[len("FRROUTE"):])
            except Exception:  # noqa: BLE001
                return None
    return None


def build_fab_package(dna_name: str, output_dir: str = "output/fab",
                      *, solve: bool = True,
                      render: bool = True,
                      route: bool = False) -> Dict[str, Any]:
    """全链路: DNA → board → (solve_drc) → save → (freerouting 布线) → 真实 kicad-cli 制造文件。

    工具在则产出真实 Gerber/钻孔/坐标/STEP/3D 渲染 + 真实 DRC; 工具不在则
    优雅降级到纯 Python Gerber/BOM。route=True 且 KiCad python+freerouting 可用时,
    先把已布局板交给真实 freerouting 布线 (unconnected→0), 制造文件即反映布好的铜。
    返回每一步的结构化结果。
    """
    dna = CircuitDNA.get(dna_name)
    if dna is None:
        return {"ok": False, "error": f"Unknown DNA template: {dna_name}",
                "available": CircuitDNA.list_names()}

    from kicad_origin.engine.drc import DRCEngine
    from kicad_origin.engine import kicad_cli as kc
    from kicad_origin.engine.bom import save_bom

    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    board = dna_to_board(dna)
    raw_e = DRCEngine(board).run().error_count
    solved_e = raw_e
    if solve:
        from kicad_origin.dao.dao import Dao
        from kicad_origin.agent.loop import PcbAgent
        dao = Dao(); dao._board = board
        PcbAgent(dao, max_iters=300).solve_drc()
        solved_e = DRCEngine(board).run().error_count

    pcb_path = out / f"{dna_name}.kicad_pcb"
    board.save(str(pcb_path))

    steps: Dict[str, Any] = {}
    fab_path = pcb_path
    route_info: Optional[Dict[str, Any]] = None
    if route:
        route_info = _route_via_kicad_python(str(pcb_path), str(out / "route"))
        steps["route"] = route_info or {"ok": False,
                                        "reason": "kicad-python/freerouting unavailable"}
        if route_info and route_info.get("routed_path"):
            fab_path = Path(route_info["routed_path"])
    steps["bom"] = save_bom(board, str(out / f"{dna_name}_bom.csv")).to_dict()

    used_real_tool = kc.kicad_cli_available()
    if used_real_tool:
        steps["gerbers"] = kc.export_gerbers(str(fab_path), str(out / "gerber")).to_dict()
        steps["drill"] = kc.export_drill(str(fab_path), str(out / "gerber")).to_dict()
        steps["pos"] = kc.export_pos(str(fab_path), str(out / f"{dna_name}_pos.csv")).to_dict()
        steps["step"] = kc.export_step(str(fab_path), str(out / f"{dna_name}.step")).to_dict()
        if render:
            steps["render"] = kc.render_3d(str(fab_path), str(out / f"{dna_name}.png")).to_dict()
        steps["drc"] = kc.run_drc(str(fab_path), str(out / f"{dna_name}_drc.json")).to_dict()
    else:
        from kicad_origin.engine.gerber import generate_gerber
        steps["gerbers"] = {"ok": generate_gerber(
            board, str(out / "gerber"), project_name=dna_name).ok,
            "backend": "pure_python"}

    return {
        "ok": True,
        "dna": dna_name,
        "path": str(pcb_path),
        "fab_path": str(fab_path),
        "routed": bool(route_info and route_info.get("routed_path")),
        "internal_drc": {"raw_errors": raw_e, "solved_errors": solved_e},
        "kicad_cli": kc.kicad_cli_version() if used_real_tool else None,
        "backend": "kicad-cli" if used_real_tool else "pure_python",
        "steps": steps,
    }


def generate_all(output_dir: str = ".") -> Dict[str, Any]:
    """Generate all 21 DNA templates as .kicad_pcb files."""
    results = []
    ok_count = 0
    for name in CircuitDNA.list_names():
        r = generate_pcb(name, output_dir)
        results.append(r)
        if r.get("ok"):
            ok_count += 1
    return {
        "total": len(results),
        "ok": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
    }
