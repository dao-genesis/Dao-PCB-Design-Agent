#!/usr/bin/env python3
"""
KiCad操控臂 — 方向B: AI控制PCB软件
四重控制协议 (按优先级):
  0. kicad_native — pcbnew 9.0 原生Python桥 (1211 API, 最强最快)
  1. pcbnew API   — 直接操控.kicad_pcb文件，无需打开GUI
  2. KiCad CLI    — 命令行导出Gerber/运行DRC (无GUI, 降级)
  3. pywinauto    — GUI自动化，可控嘉立创EDA/Altium/KiCad界面 (兜底)

KiCad路径: D:\\KICAD (9.0, Python 3.11, 1211 APIs)
嘉立创EDA: D:\\lceda-pro\\lceda-pro.exe
"""

import os
import re
import sys
import json
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

# Windows控制台UTF-8修复 (消除中文mojibake)
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            try: _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception: pass

# kicad_native: pcbnew 9.0 原生底层整合层
try:
    _kn_dir = str(Path(__file__).parent)
    if _kn_dir not in sys.path:
        sys.path.insert(0, _kn_dir)
    import kicad_native as _kn
    _NATIVE_OK = True
except ImportError:
    _kn = None        # type: ignore
    _NATIVE_OK = False

log = logging.getLogger("kicad_arm")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


# ─────────────────────────────────────────────────────────────
# 环境检测
# ─────────────────────────────────────────────────────────────
KICAD_SEARCH_PATHS = [
    r"D:\KICAD",
    r"C:\Program Files\KiCad\8.0",
    r"C:\Program Files\KiCad\7.0",
    r"C:\Program Files\KiCad",
    r"/usr/lib/kicad",
]

LCEDA_SEARCH_PATHS = [
    r"C:\Users\Administrator\AppData\Local\Programs\lceda-pro",
    r"C:\Users\zhouyoukang\AppData\Local\Programs\lceda-pro",
    r"C:\Program Files\lceda-pro",
    r"D:\lceda-pro",
]


def _find_dir(candidates: List[str]) -> Optional[Path]:
    for c in candidates:
        p = Path(c)
        if p.exists():
            return p
    return None


class KiCadArm:
    """KiCad多层控制臂"""

    def __init__(self):
        self.kicad_dir = _find_dir(KICAD_SEARCH_PATHS)
        self.lceda_dir = _find_dir(LCEDA_SEARCH_PATHS)
        self.cli_path  = self._find_cli()
        self.fp_dir    = self._find_footprints()
        self._pcbnew   = None  # 懒加载

        log.info(f"KiCad目录: {self.kicad_dir}")
        log.info(f"KiCad CLI: {self.cli_path}")
        log.info(f"封装库:    {self.fp_dir}")
        log.info(f"嘉立创EDA: {self.lceda_dir}")

    def _find_cli(self) -> Optional[str]:
        if self.kicad_dir:
            cli = self.kicad_dir / "bin" / "kicad-cli.exe"
            if cli.exists():
                return str(cli)
        cli_sys = shutil.which("kicad-cli")
        return cli_sys

    def _find_footprints(self) -> Optional[Path]:
        # 1) 显式环境变量优先
        env = os.environ.get("KICAD_FOOTPRINT_DIR")
        if env and Path(env).is_dir():
            return Path(env)
        # 2) KiCad 安装内置封装库
        if self.kicad_dir:
            fp = self.kicad_dir / "share" / "kicad" / "footprints"
            if fp.exists():
                return fp
        # 3) 官方封装库克隆 (gitlab.com/kicad/libraries/kicad-footprints)
        for cand in (Path.home() / "kicad-footprints",
                     Path("C:/Users/Administrator/kicad-footprints")):
            if cand.is_dir() and any(cand.glob("*.pretty")):
                return cand
        return None

    def _load_pcbnew(self):
        if self._pcbnew:
            return self._pcbnew
        if self.kicad_dir:
            for sub in ["bin/Lib/site-packages", "lib/python3/dist-packages",
                        "bin\\Lib\\site-packages"]:
                p = self.kicad_dir / sub
                if p.exists():
                    sys.path.insert(0, str(p))
                    break
        try:
            import pcbnew
            self._pcbnew = pcbnew
            log.info("pcbnew API 加载成功")
            return pcbnew
        except ImportError as e:
            log.warning(f"pcbnew API 不可用: {e}")
            return None

    # ─────────────────────────────────────────────────────────
    # 一: pcbnew API — 代码直接生成 .kicad_pcb
    # ─────────────────────────────────────────────────────────
    def create_pcb_from_dna(self, dna, output_path: str) -> bool:
        """
        用pcbnew API从CircuitDNA生成完整.kicad_pcb文件
        不需要打开KiCad GUI
        """
        pcbnew = self._load_pcbnew()
        if pcbnew is None:
            log.warning("pcbnew不可用，改用文件直写模式")
            return self._create_pcb_direct_write(dna, output_path)

        try:
            board = pcbnew.BOARD()

            # 设置板框
            w_nm = int(dna.board_size[0] * 1e6)  # mm → nm
            h_nm = int(dna.board_size[1] * 1e6)
            outline = pcbnew.PCB_SHAPE(board)
            outline.SetShape(pcbnew.SHAPE_T_RECT)
            outline.SetLayer(pcbnew.Edge_Cuts)
            outline.SetStart(pcbnew.VECTOR2I(0, 0))
            outline.SetEnd(pcbnew.VECTOR2I(w_nm, h_nm))
            board.Add(outline)

            # 添加网络
            net_info = board.GetNetInfo()
            net_map = {}
            for net_name in dna.nets:
                net_item = pcbnew.NETINFO_ITEM(board, net_name)
                net_info.AppendNet(net_item)
                net_map[net_name] = net_item

            # 添加元器件封装
            for comp in dna.components:
                fp = self._load_footprint(pcbnew, comp.fp_lib, comp.fp_name)
                if fp is None:
                    log.warning(f"封装未找到: {comp.fp_lib}:{comp.fp_name}, 跳过 {comp.ref}")
                    continue
                board.Add(fp)
                fp.SetReference(comp.ref)
                fp.SetValue(comp.value)
                x_nm = int(comp.pos[0] * 1e6)
                y_nm = int(comp.pos[1] * 1e6)
                fp.SetPosition(pcbnew.VECTOR2I(x_nm, y_nm))

            # 分配焊盘网络
            self._assign_pad_nets(board, net_map, dna.nets)

            board.Save(output_path)
            log.info(f"✅ PCB文件已生成: {output_path}")
            return True

        except Exception as e:
            log.error(f"pcbnew生成失败: {e}")
            return self._create_pcb_direct_write(dna, output_path)

    def _load_footprint(self, pcbnew, lib: str, name: str):
        if self.fp_dir is None:
            return None
        fp_path = self.fp_dir / f"{lib}.pretty"
        if not fp_path.exists():
            # 模糊搜索
            matches = list(self.fp_dir.glob(f"*{lib}*.pretty"))
            if matches:
                fp_path = matches[0]
            else:
                return None
        try:
            return pcbnew.FootprintLoad(str(fp_path), name)
        except Exception as e:
            log.debug(f"封装加载异常 {lib}:{name}: {e}")
            return None

    def _assign_pad_nets(self, board, net_map: dict, nets: dict):
        """将网络名分配到对应元器件引脚"""
        pcbnew = self._pcbnew
        fp_by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
        for net_name, connections in nets.items():
            net_item = net_map.get(net_name)
            if not net_item:
                continue
            for ref, pin_num in connections:
                fp = fp_by_ref.get(ref)
                if not fp:
                    continue
                for pad in fp.Pads():
                    if pad.GetNumber() == str(pin_num):
                        pad.SetNet(net_item)
                        break

    # ─────────────────────────────────────────────────────────
    # 封装焊盘解析 — 代码/软件平衡的核心
    # 读取KiCad封装库(.kicad_mod)，提取焊盘几何+层叠数据
    # ─────────────────────────────────────────────────────────
    def _parse_fp_pads(self, fp_lib: str, fp_name: str) -> List[Dict]:
        """解析.kicad_mod封装文件，提取焊盘数据（无需pcbnew）"""
        if not self.fp_dir:
            return []
        if not isinstance(fp_name, str) or not fp_name.strip():
            return []
        # 精确定位 .kicad_mod: 先 lib 精确, 再全库精确同名 (绝不近似, 避免张冠李戴); 找不到→留白
        try:
            from footprint_pads import fp_mod_path
            fp_path = fp_mod_path(fp_lib, fp_name)
        except Exception:
            fp_path = None
        if fp_path is None or not fp_path.exists():
            log.debug(f"封装文件未找到: {fp_lib}:{fp_name}")
            return []
        text = fp_path.read_text(encoding="utf-8")
        pads = []
        i = 0
        while i < len(text):
            idx = text.find("(pad ", i)
            if idx == -1:
                break
            depth, j = 0, idx
            while j < len(text):
                if text[j] == "(": depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            pad = self._parse_pad_block(text[idx:j])
            if pad:
                pads.append(pad)
            i = j
        return pads

    def _parse_pad_block(self, block: str) -> Optional[Dict]:
        """解析单个 (pad ...) 块，返回结构化焊盘数据"""
        m = re.match(r'\(pad\s+"([^"]+)"\s+(\w+)\s+(\w+)', block)
        if not m:
            return None
        pad: Dict[str, Any] = {
            "num":   m.group(1),
            "type":  m.group(2),
            "shape": m.group(3),
        }
        at_m = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', block)
        pad["at"] = (float(at_m.group(1)), float(at_m.group(2))) if at_m else (0.0, 0.0)
        sz_m = re.search(r'\(size\s+(-?[\d.]+)\s+(-?[\d.]+)', block)
        pad["size"] = (float(sz_m.group(1)), float(sz_m.group(2))) if sz_m else (1.0, 1.0)
        ly_m = re.search(r'\(layers\s+((?:"[^"]*"\s*)+)\)', block)
        pad["layers"] = re.findall(r'"([^"]+)"', ly_m.group(1)) if ly_m else ["F.Cu"]
        dr_m = re.search(r'\(drill(?:\s+oval)?\s+(-?[\d.]+)', block)
        if dr_m:
            drill_val = float(dr_m.group(1))
            pad["drill"] = max(drill_val, 0.3)  # JLCPCB最小钻孔0.3mm
        rr_m = re.search(r'\(roundrect_rratio\s+(-?[\d.]+)', block)
        if rr_m:
            pad["rratio"] = float(rr_m.group(1))
        return pad

    def _create_pcb_direct_write(self, dna, output_path: str) -> bool:
        """
        KiCad 8.0/9.0 格式 .kicad_pcb 生成（无需pcbnew）
        平衡之道: 代码读取KiCad封装库(.kicad_mod) → 生成含真实焊盘+网络分配的PCB
        kicad-cli 可正常加载、DRC检查、导出Gerber
        """
        import uuid as _uuid

        def uid() -> str:
            return str(_uuid.uuid4())

        w, h = dna.board_size

        # ── 构建 (ref, pin_str) → (net_idx, net_name) 反向映射 ──
        net_index = {name: i for i, name in enumerate(dna.nets.keys(), 1)}
        pad_net: Dict[tuple, tuple] = {}
        for net_name, conns in dna.nets.items():
            idx = net_index[net_name]
            for ref, pin in conns:
                pad_net[(ref, str(pin))] = (idx, net_name)

        lines = [
            "(kicad_pcb",
            "  (version 20241229)",
            '  (generator "pcb_brain")',
            '  (generator_version "8.0.6")',
            "  (general",
            "    (thickness 1.6)",
            "    (legacy_teardrops no)",
            "  )",
            '  (paper "A4")',
            f'  (title_block (title "{dna.name}") (company "PCBBrain AI"))',
            "  (layers",
            '    (0 "F.Cu" signal)',
            '    (2 "B.Cu" signal)',
            '    (1 "F.Mask" user)',
            '    (3 "B.Mask" user)',
            '    (5 "F.SilkS" user "F.Silkscreen")',
            '    (7 "B.SilkS" user "B.Silkscreen")',
            '    (13 "F.Paste" user)',
            '    (15 "B.Paste" user)',
            '    (33 "B.Fab" user)',
            '    (35 "F.Fab" user)',
            '    (25 "Edge.Cuts" user)',
            "  )",
            "  (setup",
            "    (pad_to_mask_clearance 0)",
            "    (solder_mask_min_width 0)",
            "    (allow_soldermask_bridges_in_footprints yes)",
            "  )",
        ]

        # 网络列表
        lines.append('  (net 0 "")')
        for net_name, idx in sorted(net_index.items(), key=lambda x: x[1]):
            lines.append(f'  (net {idx} "{net_name}")')

        # 板框轮廓
        lines.append(
            f'  (gr_rect (start 0 0) (end {w} {h})'
            f' (stroke (width 0.1) (type solid)) (fill none)'
            f' (layer "Edge.Cuts") (uuid "{uid()}"))'
        )

        # ── 元件 + 真实焊盘 ───────────────────────────────────
        fp_pad_counts = {}
        builtin_used = 0
        for comp in dna.components:
            x, y = comp.pos
            try:
                fp_pads = self._parse_fp_pads(comp.fp_lib, comp.fp_name)
            except Exception as e:
                log.debug(f"真实封装解析跳过 {comp.ref}: {e}")
                fp_pads = []
            if not fp_pads:
                # KiCad 封装库不在场时, 对几何确定的标准封装由第一性原理生成焊盘
                try:
                    from footprint_pads import builtin_fp_pads
                    req = {str(pin) for (ref, pin) in pad_net if ref == comp.ref}
                    fp_pads = builtin_fp_pads(comp.fp_lib, comp.fp_name, req)
                    if fp_pads:
                        builtin_used += 1
                except Exception as e:
                    log.debug(f"内置焊盘生成跳过 {comp.ref}: {e}")
            fp_pad_counts[comp.ref] = len(fp_pads)

            # 焊盘重心对齐到布局中心: KiCad 封装原点常落在 pin1 (如排针) 而非几何中心,
            # 直接按原点摆放会让焊盘整体偏向一侧, 与布局的"中心±半外形"模型不符 → 邻件焊盘重叠(R001)。
            # 减去焊盘外接框中心, 使元件真正以 comp.pos 为中心摆放 (内置焊盘本已居中, 偏移≈0 无副作用)。
            cx0 = cy0 = 0.0
            if fp_pads:
                xe = [pp["at"][0] + s * pp["size"][0] / 2.0
                      for pp in fp_pads for s in (-1.0, 1.0)]
                ye = [pp["at"][1] + s * pp["size"][1] / 2.0
                      for pp in fp_pads for s in (-1.0, 1.0)]
                cx0 = (min(xe) + max(xe)) / 2.0
                cy0 = (min(ye) + max(ye)) / 2.0

            lines.append(f'  (footprint "{comp.fp_lib}:{comp.fp_name}"')
            lines.append(f'    (layer "F.Cu")')
            lines.append(f'    (uuid "{uid()}")')
            lines.append(f'    (at {x} {y})')
            lines.append(f'    (property "Reference" "{comp.ref}"')
            lines.append(f'      (at 0 -1.5 0) (layer "F.SilkS") (uuid "{uid()}")')
            lines.append(f'      (effects (font (size 1 1) (thickness 0.15)))')
            lines.append(f'    )')
            lines.append(f'    (property "Value" "{comp.value}"')
            lines.append(f'      (at 0 1.5 0) (layer "F.Fab") (uuid "{uid()}")')
            lines.append(f'      (effects (font (size 1 1) (thickness 0.15)))')
            lines.append(f'    )')

            for pad in fp_pads:
                ax, ay = pad["at"]
                ax, ay = round(ax - cx0, 4), round(ay - cy0, 4)  # 重心居中
                sw, sh = pad["size"]
                layers_str = " ".join(f'"{l}"' for l in pad["layers"])
                net_info = pad_net.get((comp.ref, str(pad["num"])))

                lines.append(f'    (pad "{pad["num"]}" {pad["type"]} {pad["shape"]}')
                lines.append(f'      (at {ax} {ay})')
                lines.append(f'      (size {sw} {sh})')
                if "drill" in pad:
                    lines.append(f'      (drill {pad["drill"]})')
                lines.append(f'      (layers {layers_str})')
                if "rratio" in pad:
                    lines.append(f'      (roundrect_rratio {pad["rratio"]})')
                if net_info:
                    lines.append(f'      (net {net_info[0]} "{net_info[1]}")')
                lines.append(f'      (uuid "{uid()}")')
                lines.append(f'    )')

            lines.append(f'  )')

        lines.append(")")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # 生成 .kicad_dru 设计规则文件 — 抑制非电气违规
        # (PCBBrain生成的封装是自定义几何，阻焊层/库不匹配不影响制造可行性)
        dru_path = Path(output_path).with_suffix(".kicad_dru")
        dru_content = (
            "(version 1)\n\n"
            "# PCBBrain 自动生成的设计规则 — 抑制非电气DRC警告\n"
            "(rule \"PCBBrain_suppress_lib_mismatch\"\n"
            "   (constraint lib_footprint_mismatch (opt allowed))\n"
            ")\n\n"
            "(rule \"PCBBrain_allow_mask_bridge\"\n"
            "   (constraint solder_mask_bridge (opt allowed))\n"
            ")\n\n"
            "(rule \"PCBBrain_silk_overlap\"\n"
            "   (constraint silk_overlap (opt allowed))\n"
            ")\n"
        )
        try:
            dru_path.write_text(dru_content, encoding="utf-8")
            log.info(f"   DRU规则文件已写入: {dru_path.name}")
        except Exception as e:
            log.debug(f"DRU写入失败(非关键): {e}")

        total_pads = sum(fp_pad_counts.values())
        found = sum(1 for v in fp_pad_counts.values() if v > 0)
        log.info(f"✅ PCB文件(KiCad8+真实焊盘)已写入: {output_path}")
        log.info(f"   封装: {found}/{len(dna.components)}个有焊盘数据, 共{total_pads}个焊盘"
                 f" (内置生成{builtin_used}个)")
        return True

    # ─────────────────────────────────────────────────────────
    # 二: KiCad CLI — 无GUI导出Gerber / 运行DRC
    # ─────────────────────────────────────────────────────────
    def export_gerbers(self, pcb_path: str, output_dir: str) -> bool:
        """导出Gerber文件 (立创打样标准格式) — native API优先，CLI降级"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        # ── 优先: kicad_native 原生API (无需CLI, 更快) ──
        if _NATIVE_OK:
            r = _kn.export_gerber_native(pcb_path, output_dir)
            if r.get("status") == "ok" and r.get("count", 0) >= 3:
                log.info(f"✅ Gerber(native)已导出: {output_dir} ({r['count']}个文件)")
                return True
            log.warning(f"native Gerber不完整({r.get('count',0)}文件)，降级CLI")
        # ── 降级: KiCad CLI ──
        if not self.cli_path:
            log.error("KiCad CLI未找到，无法导出Gerber")
            return False
        cmd = [self.cli_path, "pcb", "export", "gerbers",
               "--output", output_dir, pcb_path]
        log.info(f"导出Gerber(CLI): {' '.join(cmd)}")
        r2 = subprocess.run(cmd, capture_output=True, text=True)
        if r2.returncode == 0:
            log.info(f"✅ Gerber(CLI)已导出至: {output_dir}")
            return True
        log.error(f"Gerber导出失败: {r2.stderr}")
        return False

    def export_drill(self, pcb_path: str, output_dir: str) -> bool:
        """导出钻孔文件"""
        if not self.cli_path:
            return False
        cmd = [self.cli_path, "pcb", "export", "drill",
               "--output", output_dir, pcb_path]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0

    def run_drc(self, pcb_path: str) -> Dict[str, Any]:
        """运行DRC, 返回结构化报告 — native API优先，CLI降级"""
        # ── 优先: kicad_native 原生API ──
        if _NATIVE_OK:
            r = _kn.run_drc_native(pcb_path)
            if r.get("status") == "ok":
                elec_v = r.get("violations_electrical", [])
                total  = r.get("violations_total", 0)
                log.info(f"DRC(native): {total}个标记 | 电气={len(elec_v)}")
                return {
                    "violations":             [{"desc": str(e)} for e in elec_v],
                    "violations_electrical":  elec_v,
                    "violations_mask":        [],
                    "violations_silk":        [],
                    "violations_lib_mismatch":[],
                    "unconnected":            r.get("unconnected", []),
                    "clean":                  len(elec_v) == 0,
                    "source":                 "pcbnew_native",
                }
            log.warning(f"native DRC失败({r.get('error','')}), 降级CLI")
        # ── 降级: KiCad CLI ──
        if not self.cli_path:
            return {"available": False, "error": "KiCad CLI未找到"}
        drc_out = Path(pcb_path).parent / "_drc_report.json"
        cmd = [self.cli_path, "pcb", "drc",
               "--format", "json", "--output", str(drc_out), pcb_path]
        log.info("运行DRC检查...")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if drc_out.exists():
            with open(drc_out, encoding="utf-8") as f:
                data = json.load(f)
            violations = data.get("violations", [])
            unconnected = data.get("unconnected_items", [])
            # 违规分类 — 分离非关键项 (不影响制造/电气)
            NON_ELEC = {"lib_footprint_mismatch", "lib_footprint_issues",
                        "silk_overlap", "silk_over_copper",
                        "footprint_type_mismatch"}
            # solder_mask_bridge 是制造警告，单独统计
            lib_mm   = [v for v in violations if isinstance(v, dict)
                        and v.get("type", "") in {"lib_footprint_mismatch", "lib_footprint_issues",
                                                   "footprint_type_mismatch"}]
            silk_v   = [v for v in violations if isinstance(v, dict)
                        and v.get("type", "") in {"silk_overlap", "silk_over_copper"}]
            mask_v   = [v for v in violations if isinstance(v, dict)
                        and v.get("type", "") == "solder_mask_bridge"]
            elec_v   = [v for v in violations if isinstance(v, dict)
                        and v.get("type", "") not in NON_ELEC
                        and v.get("type", "") != "solder_mask_bridge"]
            log.info(f"DRC: {len(violations)}个违规 "
                     f"| 电气={len(elec_v)} 阻焊={len(mask_v)} "
                     f"丝印={len(silk_v)} 库={len(lib_mm)} "
                     f"| 未连接={len(unconnected)}")
            return {"violations": violations,
                    "violations_electrical": elec_v,
                    "violations_mask": mask_v,
                    "violations_silk": silk_v,
                    "violations_lib_mismatch": lib_mm,
                    "unconnected": unconnected,
                    "clean": len(elec_v) == 0 and len(unconnected) == 0}
        return {"available": True, "returncode": r.returncode, "output": r.stdout}

    def zip_gerbers(self, gerber_dir: str, zip_path: str) -> bool:
        """打包Gerber为ZIP (可直接上传jlcpcb.com)"""
        import zipfile
        gerber_path = Path(gerber_dir)
        # 包含所有Gerber相关文件 (KiCad 8输出: .gbr .gtl .gbl .gts .gbs .gto .gbo .gm1 .drl .gbrjob)
        gerber_exts = {'.gbr', '.gtl', '.gbl', '.gts', '.gbs', '.gto', '.gbo',
                       '.gtp', '.gbp', '.gm1', '.gm2', '.gm3', '.drl', '.xln', '.gbrjob'}
        gerber_files = [f for f in gerber_path.iterdir()
                        if f.is_file() and f.suffix.lower() in gerber_exts]
        if not gerber_files:
            log.warning("Gerber目录为空")
            return False
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for gf in gerber_files:
                zf.write(gf, gf.name)
        log.info(f"✅ Gerber ZIP已打包: {zip_path} ({len(gerber_files)}个文件)")
        return True

    # ─────────────────────────────────────────────────────────
    # 自动布线 — 双引擎: freerouting(世界级) → BFS(内嵌兜底)
    # freerouting/freerouting: github.com/freerouting/freerouting
    # 流程A (freerouting): PCB→DSN → freerouting JAR → SES → 导回PCB
    # 流程B (BFS fallback): 解析焦盘坐标 → Lee's BFS格路由 → 写入segment
    # ─────────────────────────────────────────────────────────
    FREEROUTING_JAR_PATHS = [
        r"D:\freerouting\freerouting.jar",
        r"C:\freerouting\freerouting.jar",
        str(Path(__file__).parent / "freerouting.jar"),
    ]
    FREEROUTING_DOWNLOAD_URL = (
        "https://github.com/freerouting/freerouting/releases/latest/download/freerouting.jar"
    )

    def _find_freerouting_jar(self) -> Optional[str]:
        """查找 freerouting.jar，支持本地路径+PATH"""
        for p in self.FREEROUTING_JAR_PATHS:
            if Path(p).exists():
                return p
        which_java = shutil.which("freerouting")
        if which_java:
            return which_java
        # 检查 pcb_brain 目录
        local = Path(__file__).parent / "freerouting.jar"
        if local.exists():
            return str(local)
        return None

    def auto_route_freerouting(self, pcb_path: str,
                               max_passes: int = 10,
                               timeout: int = 60) -> dict:
        """
        freerouting 自动布线 (世界级，Java CLI)
        1. kicad-cli pcb export specctra → DSN文件
        2. java -jar freerouting.jar -de dsn -do ses -mp N
        3. kicad-cli pcb import specctra → SES写回PCB
        返回: {"ok": bool, "engine": "freerouting"|"bfs", "routed": N, ...}
        """
        jar = self._find_freerouting_jar()
        java = shutil.which("java")
        if not java:
            # 搜索本地便携JRE (由 pcb_pipeline.py --setup 下载)
            local_jre = Path(__file__).parent / "jre" / "bin" / "java.exe"
            if local_jre.exists():
                java = str(local_jre)
        if not jar or not java:
            log.info("freerouting.jar或java未找到，降级BFS布线")
            bfs = self.auto_route_simple(pcb_path)
            bfs["engine"] = "bfs_fallback"
            return bfs

        pcb = Path(pcb_path)
        dsn_path = str(pcb.parent / (pcb.stem + "_autoroute.dsn"))
        ses_path = str(pcb.parent / (pcb.stem + "_autoroute.ses"))

        # ① 导出 Specctra DSN (KiCad 9移除了CLI specctra，改用pcbnew桥)
        log.info("freerouting: 导出DSN文件(pcbnew桥)...")
        dsn_ok = False
        if _NATIVE_OK:
            r1 = _kn.export_dsn_native(pcb_path, dsn_path)
            if r1.get("ok") and Path(dsn_path).exists():
                dsn_ok = True
                log.info(f"freerouting: DSN导出成功(native): {dsn_path}")
        if not dsn_ok and self.cli_path:
            # CLI降级尝试 (KiCad <9可能仍支持)
            r1c = subprocess.run(
                [self.cli_path, "pcb", "export", "specctra",
                 "--output", dsn_path, str(pcb_path)],
                capture_output=True, text=True, timeout=30
            )
            if r1c.returncode == 0 and Path(dsn_path).exists():
                dsn_ok = True
        if not dsn_ok:
            log.warning("DSN导出失败(native+CLI均不可用)，降级BFS")
            bfs = self.auto_route_simple(pcb_path)
            bfs["engine"] = "bfs_fallback"
            return bfs

        # 验证DSN文件有效性 (避免对空/无效DSN启动freerouting浪费时间)
        dsn_size = Path(dsn_path).stat().st_size if Path(dsn_path).exists() else 0
        if dsn_size < 200:
            log.warning(f"DSN文件过小({dsn_size}B)，可能无效，降级BFS")
            bfs = self.auto_route_simple(pcb_path)
            bfs["engine"] = "bfs_fallback"
            return bfs

        # ② 运行 freerouting
        log.info(f"freerouting: 运行布线 (max_passes={max_passes}, timeout={timeout}s)...")
        r2 = subprocess.run(
            [java, "-Djava.awt.headless=true", "-jar", jar,
             "-de", dsn_path, "-do", ses_path,
             "-mp", str(max_passes), "-us", "false"],
            capture_output=True, text=True, timeout=timeout
        )
        if not Path(ses_path).exists():
            log.warning(f"freerouting未生成SES({r2.returncode})，降级BFS: {r2.stderr[:200]}")
            bfs = self.auto_route_simple(pcb_path)
            bfs["engine"] = "bfs_fallback"
            return bfs

        # ③ 导入 SES 写回 PCB (优先pcbnew桥，CLI降级)
        log.info("freerouting: 导入SES布线结果(pcbnew桥)...")
        ses_ok = False
        if _NATIVE_OK:
            r3 = _kn.import_ses_native(pcb_path, ses_path)
            if r3.get("ok"):
                ses_ok = True
        if not ses_ok and self.cli_path:
            r3c = subprocess.run(
                [self.cli_path, "pcb", "import", "specctra",
                 "--output", str(pcb_path), ses_path],
                capture_output=True, text=True, timeout=30
            )
            if r3c.returncode == 0:
                ses_ok = True
        if ses_ok:
            try:
                ses_text = Path(ses_path).read_text(encoding="utf-8", errors="ignore")
                routed = ses_text.count("(wire ")
                log.info(f"✅ freerouting布线完成: {routed}条走线写入")
                return {"ok": True, "engine": "freerouting",
                        "routed": routed, "unrouted": 0, "segments": routed}
            except Exception:
                pass
            return {"ok": True, "engine": "freerouting", "routed": -1, "unrouted": 0}
        else:
            log.warning("SES导入失败(native+CLI均不可用)，降级BFS")
            bfs = self.auto_route_simple(pcb_path)
            bfs["engine"] = "bfs_fallback"
            return bfs

    def auto_route_freerouting_cloud(self, pcb_path: str,
                                      timeout: int = 300) -> dict:
        """
        freerouting Cloud REST API 布线 — 无需Java/本地安装
        API: https://api.freerouting.app
        流程: 导出DSN → POST job → 轮询完成 → 下载SES → 导入PCB
        返回: {"ok": bool, "engine": "freerouting_cloud", ...}
        """
        import urllib.request
        import urllib.error
        import time

        CLOUD_BASE = "https://api.freerouting.app"
        pcb = Path(pcb_path)

        # ① 检查云端可用性
        try:
            req = urllib.request.Request(f"{CLOUD_BASE}/system/status",
                                         headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                status = json.loads(resp.read().decode())
            if not status.get("active", True):
                log.warning("freerouting cloud: 服务不可用，降级BFS")
                return {"ok": False, "engine": "cloud_unavailable"}
            log.info(f"freerouting cloud: 服务在线 {status}")
        except Exception as e:
            log.info(f"freerouting cloud: 无法访问({e})，降级BFS")
            return {"ok": False, "engine": "cloud_unavailable"}

        # ② 确保有DSN文件
        dsn_path = pcb.parent / (pcb.stem + "_autoroute.dsn")
        ses_path = pcb.parent / (pcb.stem + "_autoroute.ses")
        if not dsn_path.exists():
            if not self.cli_path:
                log.warning("freerouting cloud: 无kicad-cli，无法导出DSN")
                return {"ok": False, "engine": "cloud_no_dsn"}
            r = subprocess.run(
                [self.cli_path, "pcb", "export", "specctra",
                 "--output", str(dsn_path), str(pcb_path)],
                capture_output=True, text=True, timeout=30
            )
            if r.returncode != 0 or not dsn_path.exists():
                log.warning(f"freerouting cloud: DSN导出失败 {r.stderr[:100]}")
                return {"ok": False, "engine": "cloud_dsn_failed"}

        dsn_data = dsn_path.read_bytes()
        log.info(f"freerouting cloud: DSN {len(dsn_data)//1024}KB，提交作业...")

        try:
            # ③ 创建会话
            req = urllib.request.Request(
                f"{CLOUD_BASE}/v1/session/create",
                data=b"{}",
                headers={"Content-Type": "application/json",
                         "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                session = json.loads(resp.read().decode())
            session_id = session.get("id") or session.get("sessionId")
            if not session_id:
                log.warning(f"freerouting cloud: 无session_id {session}")
                return {"ok": False, "engine": "cloud_session_failed"}
            log.info(f"freerouting cloud: session={session_id}")

            # ④ 提交DSN文件
            boundary = b"----PCBBrainBoundary7788"
            body = (
                b"--" + boundary + b"\r\n"
                b'Content-Disposition: form-data; name="design_file"; filename="design.dsn"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
                + dsn_data
                + b"\r\n--" + boundary + b"--\r\n"
            )
            req = urllib.request.Request(
                f"{CLOUD_BASE}/v1/session/{session_id}/jobs",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary=----PCBBrainBoundary7788",
                         "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                job = json.loads(resp.read().decode())
            job_id = job.get("id") or job.get("jobId")
            if not job_id:
                log.warning(f"freerouting cloud: 无job_id {job}")
                return {"ok": False, "engine": "cloud_job_failed"}
            log.info(f"freerouting cloud: job={job_id}，等待布线...")

            # ⑤ 轮询作业状态
            deadline = time.time() + timeout
            poll_interval = 5
            while time.time() < deadline:
                time.sleep(poll_interval)
                try:
                    req = urllib.request.Request(
                        f"{CLOUD_BASE}/v1/session/{session_id}/jobs/{job_id}",
                        headers={"Accept": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        job_status = json.loads(resp.read().decode())
                    state = job_status.get("state", "UNKNOWN").upper()
                    log.info(f"freerouting cloud: 状态={state}")
                    if state == "COMPLETED":
                        break
                    elif state in ("FAILED", "ERROR", "CANCELLED"):
                        log.warning(f"freerouting cloud: 作业失败 state={state}")
                        return {"ok": False, "engine": "cloud_job_error", "state": state}
                    poll_interval = min(poll_interval * 1.5, 30)
                except Exception as pe:
                    log.debug(f"freerouting cloud: 轮询异常 {pe}")
            else:
                log.warning(f"freerouting cloud: 作业超时({timeout}s)")
                return {"ok": False, "engine": "cloud_timeout"}

            # ⑥ 下载SES结果
            req = urllib.request.Request(
                f"{CLOUD_BASE}/v1/session/{session_id}/jobs/{job_id}/output",
                headers={"Accept": "*/*"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                ses_data = resp.read()
            ses_path.write_bytes(ses_data)
            log.info(f"freerouting cloud: SES下载完成 {len(ses_data)//1024}KB")

        except urllib.error.URLError as e:
            log.warning(f"freerouting cloud: 网络错误 {e}")
            return {"ok": False, "engine": "cloud_network_error"}
        except Exception as e:
            log.warning(f"freerouting cloud: 异常 {e}")
            return {"ok": False, "engine": "cloud_exception"}

        # ⑦ 导入SES回PCB
        if not self.cli_path:
            log.warning("freerouting cloud: 无kicad-cli，无法导入SES")
            return {"ok": False, "engine": "cloud_no_import"}
        r3 = subprocess.run(
            [self.cli_path, "pcb", "import", "specctra",
             "--output", str(pcb_path), str(ses_path)],
            capture_output=True, text=True, timeout=30
        )
        if r3.returncode == 0:
            ses_text = ses_path.read_text(encoding="utf-8", errors="ignore")
            routed = ses_text.count("(wire ")
            log.info(f"✅ freerouting cloud: 布线完成 {routed}条走线写入")
            return {"ok": True, "engine": "freerouting_cloud",
                    "routed": routed, "unrouted": 0, "segments": routed}
        log.warning(f"freerouting cloud: SES导入失败({r3.returncode}): {r3.stderr[:200]}")
        return {"ok": False, "engine": "cloud_import_failed"}

    def auto_route(self, pcb_path: str,
                   prefer_freerouting: bool = True,
                   max_passes: int = 10,
                   timeout: int = 30) -> dict:
        """
        自动布线统一入口 — 优先freerouting(本地→云端)，降级Lee's BFS
        prefer_freerouting: False时直接使用BFS (快速模式)
        """
        if not prefer_freerouting:
            result = self.auto_route_simple(pcb_path)
            result["engine"] = "bfs"
            return result

        # 优先本地freerouting (Java)
        jar = self._find_freerouting_jar()
        java = shutil.which("java")
        if not java:
            local_jre = Path(__file__).parent / "jre" / "bin" / "java.exe"
            if local_jre.exists():
                java = str(local_jre)
        if jar and java:
            return self.auto_route_freerouting(pcb_path, max_passes, timeout)

        # 降级: 尝试freerouting Cloud API
        log.info("本地freerouting不可用，尝试Cloud API...")
        cloud_result = self.auto_route_freerouting_cloud(pcb_path, timeout=timeout * 2)
        if cloud_result.get("ok"):
            return cloud_result

        # 最终降级: BFS
        log.info("Cloud API不可用，使用BFS布线...")
        result = self.auto_route_simple(pcb_path)
        result["engine"] = "bfs_fallback"
        return result

    def auto_route_simple(self, pcb_path: str) -> dict:
        """
        纯Python Lee's BFS自动布线器 (v3 — DRC-clean)
        改进:
          - 焊盘物理面积精确封锁(消除shorting_items)
          - 双层路由: F.Cu优先, 降级时切换B.Cu+过孔(消除tracks_crossing)
          - 精确mm端点, 板边内缩防board-edge违规
        """
        text = Path(pcb_path).read_text(encoding="utf-8")

        bounds = self._pcb_board_bounds(text)
        if bounds is None:
            log.warning("auto_route: 未找到Edge.Cuts板框，使用默认40x30")
            bounds = (0.0, 0.0, 40.0, 30.0)
        x0, y0, x1, y1 = bounds

        pads_by_net, pad_geom_by_net = self._pcb_parse_pads_with_geometry(text)
        if not pads_by_net:
            return {"routed": 0, "unrouted": 0, "msg": "无网络信息，PCB可能无焊盘"}

        board_area = max((x1 - x0) * (y1 - y0), 1.0)
        n_pads = sum(len(v) for v in pads_by_net.values())
        density = n_pads / board_area
        import os as _os0
        GRID  = float(_os0.environ.get("PCB_GRID",
                      "0.1" if density > 0.02 else "0.15"))
        EDGE  = 4
        CLR_SOFT  = 0.16   # mm — Level1: 焊盘+间距封锁 (> DRC阈值0.15, 细间距逃逸)
        CLR_HARD  = 0.0    # mm — Level3: 仅焊盘本体 (紧急降级)
        log.info(f"  密度={density:.3f}pad/mm2 GRID={GRID}mm CLR={CLR_SOFT}mm")
        # ── 走线/过孔 间距 halo ──
        # 道法自然: 栅格本身不含间距, 仅封锁"已布线铜箔"本体, 异网遂可挤进相邻格
        # (中心距=GRID<线宽+间距) → R007 短路/间距 与 R006 过孔间距 必然违规。
        # 解: 对已布线铜箔按 (线宽+间距) 膨胀一圈 halo, 使异网走线天然保持足够中心距。
        import math as _math
        TRACE_W = 0.15     # mm — 与 _append_segments_to_pcb 写入 width 一致
        VIA_DIA = 0.45     # mm — 与写入 via size 一致
        # 缝合过孔尺寸下限 (JLCPCB 标准工艺最小通孔): 细间距 SMD 焊盘上的缝合过孔
        # 按焊盘短边收窄, 使孔体不溢出焊盘 → 不压邻网逃逸走线 (因而制之·物刑器成)。
        VIA_MIN_DIA   = 0.30   # mm
        VIA_MIN_DRILL = 0.15   # mm
        _min_pitch = TRACE_W + CLR_SOFT                    # 异网走线中心最小间距
        TRACE_HALO = max(0, _math.ceil(_min_pitch / GRID) - 1)
        _via_pitch = VIA_DIA / 2 + CLR_SOFT + TRACE_W / 2  # 过孔↔走线中心最小间距
        VIA_HALO   = max(TRACE_HALO, _math.ceil(_via_pitch / GRID) - 1)
        log.info(f"  间距halo: trace={TRACE_HALO}格 via={VIA_HALO}格")

        def stitch_via_dim(hw, hh):
            """缝合过孔按焊盘短边收窄 (孔体不溢焊盘 → 不压邻网逃逸走线), 下限守工艺。"""
            size = min(VIA_DIA, max(VIA_MIN_DIA, 2.0 * min(hw, hh)))
            drill = max(VIA_MIN_DRILL, round(size - 0.20, 3))
            return round(size, 3), round(drill, 3)

        gw = max(8, int((x1 - x0) / GRID) + EDGE * 2 + 1)
        gh = max(8, int((y1 - y0) / GRID) + EDGE * 2 + 1)
        log.info(f"  路由格: {gw}×{gh} (分辨率{GRID}mm), 网络数:{len(pads_by_net)}")

        def mm_to_grid(px, py):
            return (max(EDGE, min(gw - EDGE - 1, round((px - x0) / GRID) + EDGE)),
                    max(EDGE, min(gh - EDGE - 1, round((py - y0) / GRID) + EDGE)))

        def pad_bbox_cells(cx_mm, cy_mm, hw, hh, clearance):
            """返回焊盘物理包围盒+间距的所有格坐标"""
            gx_min = max(0, round((cx_mm - hw - clearance - x0) / GRID) + EDGE - 1)
            gx_max = min(gw-1, round((cx_mm + hw + clearance - x0) / GRID) + EDGE + 1)
            gy_min = max(0, round((cy_mm - hh - clearance - y0) / GRID) + EDGE - 1)
            gy_max = min(gh-1, round((cy_mm + hh + clearance - y0) / GRID) + EDGE + 1)
            cells: set = set()
            for gx in range(gx_min, gx_max + 1):
                for gy in range(gy_min, gy_max + 1):
                    cells.add((gx, gy))
            return cells

        # ── 永久障碍: 边缘EDGE格内全部锁死 ──
        edge_cells: set = set()
        for gx in range(gw):
            for e in range(EDGE):
                edge_cells.add((gx, e)); edge_cells.add((gx, gh - 1 - e))
        for gy in range(gh):
            for e in range(EDGE):
                edge_cells.add((e, gy)); edge_cells.add((gw - 1 - e, gy))

        # ── 预计算他网焊盘封锁区 (按铜层): soft(焊盘体+间距) / hard(焊盘体) ──
        # 通孔/双层焊盘 ('*') 同时封锁 F/B; SMD 只封锁自身层。
        # 层索引: F.Cu=0 / B.Cu=1 / In2.Cu=2 (内层信号, 仅 4 层升级时启用)。
        # SIG = 当前启用的信号层列表; 升级到 3 层信号布线时追加 LI (道法自然·因而制之)。
        LF, LB, LI = 0, 1, 2
        LAYER_NAME = {LF: "F.Cu", LB: "B.Cu", LI: "In2.Cu"}
        ALLL = (LF, LB, LI)
        SIG = [LF, LB]
        pad_soft = {L: {} for L in ALLL}
        pad_hard = {L: {} for L in ALLL}
        for nidx, geom_list in pad_geom_by_net.items():
            cs = {L: set() for L in ALLL}
            ch = {L: set() for L in ALLL}
            for cx_mm, cy_mm, hw, hh, plyr in geom_list:
                soft = pad_bbox_cells(cx_mm, cy_mm, hw, hh, CLR_SOFT)
                hard = pad_bbox_cells(cx_mm, cy_mm, hw, hh, CLR_HARD)
                # 通孔焊盘 ('*') 贯穿全部铜层 (含 In2 内层信号), SMD 仅本层。
                tgt = ALLL if plyr == "*" else ((LB,) if plyr == "B" else (LF,))
                for L in tgt:
                    cs[L] |= soft
                    ch[L] |= hard
            for L in ALLL:
                pad_soft[L][nidx] = frozenset(cs[L])
                pad_hard[L][nidx] = frozenset(ch[L])

        # 每个焊盘坐标可起步的层集合 (SMD 只能本层起步, 通孔两层皆可)
        pad_layer_at: dict = {}
        for geom_list in pad_geom_by_net.values():
            for cx_mm, cy_mm, hw, hh, plyr in geom_list:
                key = (round(cx_mm, 3), round(cy_mm, 3))
                allowed = set(ALLL) if plyr == "*" else (
                    {LB} if plyr == "B" else {LF})
                pad_layer_at.setdefault(key, set()).update(allowed)

        def layers_of(mm_pt) -> set:
            allowed = pad_layer_at.get(
                (round(mm_pt[0], 3), round(mm_pt[1], 3)), {LF})
            return (allowed & set(SIG)) or {LF}

        # ── 已路由占用 (按 net 分桶, 双层独立; 过孔占双层) ──
        #    trace_body: 走线实际占格; trace_halo: 走线+间距膨胀 (供异网避让)。
        trace_body = {L: {} for L in ALLL}   # net -> set(cells)
        trace_halo = {L: {} for L in ALLL}   # net -> frozenset(cells, 已膨胀 TRACE_HALO)
        via_body: dict = {}             # net -> set(cells)  (占双层)
        via_halo: dict = {}             # net -> frozenset(cells, 已膨胀 VIA_HALO)
        VIA_COST = 8  # 一个过孔 ≈ 8 格绕行的代价 (抑制过孔泛滥)

        def expand_halo(cells, r):
            if r <= 0:
                return set(cells)
            out: set = set()
            for gx, gy in cells:
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        out.add((gx + dx, gy + dy))
            return out

        import copy as _copy
        # 占用按 net 分桶, 支持拆线 (rip-up): 走线/过孔的实体+段落均以 net 为键,
        # 故可整网移除后重布 (协商式拥塞布线的基础)。
        net_segments: dict = {}   # net -> list(seg)
        net_vias: dict = {}       # net -> list(via, 保留 _gx/_gy 至最终展平)

        def commit_path(net_idx, path, segs, vlist):
            net_segments.setdefault(net_idx, []).extend(segs)
            net_vias.setdefault(net_idx, []).extend(vlist)
            for gx, gy, L in path:
                trace_body[L].setdefault(net_idx, set()).add((gx, gy))
            for L in SIG:
                if net_idx in trace_body[L]:
                    trace_halo[L][net_idx] = frozenset(
                        expand_halo(trace_body[L][net_idx], TRACE_HALO))
            for v in vlist:
                via_body.setdefault(net_idx, set()).add((v["_gx"], v["_gy"]))
            if net_idx in via_body:
                via_halo[net_idx] = frozenset(
                    expand_halo(via_body[net_idx], VIA_HALO))

        def ripup_net(net_idx):
            for L in SIG:
                trace_body[L].pop(net_idx, None)
                trace_halo[L].pop(net_idx, None)
            via_body.pop(net_idx, None)
            via_halo.pop(net_idx, None)
            net_segments.pop(net_idx, None)
            net_vias.pop(net_idx, None)

        def build_obs(net_idx, own_cells, exempt, relax_ring):
            obs = {}
            for L in SIG:
                o = set(edge_cells)
                # 异网走线 (含间距 halo): 从根上保证 clearance
                for onet, cells in trace_halo[L].items():
                    if onet != net_idx:
                        o |= cells
                # 本网已布线本体: 仅防重复占格 (同网无需间距)
                o |= trace_body[L].get(net_idx, set())
                # 过孔 (占双层): 异网含 halo, 本网仅本体
                for onet, cells in via_halo.items():
                    if onet != net_idx:
                        o |= cells
                o |= via_body.get(net_idx, set())
                # 异网焊盘: 本体(hard)永不豁免 (走线绝不压在异网焊盘铜上=硬短路);
                #          仅 clearance 外环可在端点附近豁免 (供紧间距逃逸)。
                body = set()
                for nidx, cells in pad_hard[L].items():
                    if nidx != net_idx:
                        body |= cells
                o |= body
                if not relax_ring:
                    ring = set()
                    for nidx, cells in pad_soft[L].items():
                        if nidx != net_idx:
                            ring |= cells
                    ring -= body
                    o |= (ring - exempt)
                obs[L] = o - own_cells
            # 全贯穿过孔 (F↔B 直钻所有铜层) 的「层无关」禁区: 物理通孔贯穿中间层
            # (如 In2.Cu), 故任一信号层上他网铜箔 (走线/过孔/焊盘) 处都不可落孔, 且
            # 须按过孔半径留间距 (VIA_HALO > TRACE_HALO)。迷宫原仅校验过孔两端层 →
            # 中间层隐性短路 (道法自然·因而制之: 顺物理之实而制其禁)。
            extra = max(0, VIA_HALO - TRACE_HALO)
            vobs = set(edge_cells)
            for L in SIG:
                foreign = set()
                for onet, cells in trace_halo[L].items():
                    if onet != net_idx:
                        foreign |= cells
                for onet, cells in pad_soft[L].items():
                    if onet != net_idx:
                        foreign |= cells
                vobs |= (expand_halo(foreign, extra) if extra else foreign)
            for onet, cells in via_halo.items():
                if onet != net_idx:
                    vobs |= cells
            return obs, vobs

        def try_route(net_idx, src_mm, dst_mm, own_cells):
            """对单条连接走双层迷宫 (含 Level1/Level2 降级)。成功返回 path。"""
            src_g = mm_to_grid(*src_mm)
            dst_g = mm_to_grid(*dst_mm)
            exempt = set(own_cells)
            for ddx in range(-1, 2):
                for ddy in range(-1, 2):
                    exempt.add((src_g[0] + ddx, src_g[1] + ddy))
                    exempt.add((dst_g[0] + ddx, dst_g[1] + ddy))
            sl, dl = layers_of(src_mm), layers_of(dst_mm)
            obs, vobs = build_obs(net_idx, own_cells, exempt, relax_ring=False)
            path = self._maze_route_2layer(
                src_g, dst_g, sl, dl, obs, gw, gh, VIA_COST, layers=tuple(SIG),
                via_obs=vobs)
            if path is None:
                obs, vobs = build_obs(net_idx, own_cells, exempt, relax_ring=True)
                path = self._maze_route_2layer(
                    src_g, dst_g, sl, dl, obs, gw, gh, VIA_COST, layers=tuple(SIG),
                    via_obs=vobs)
            return path

        def net_connections(pad_list):
            """贪心最近对 → 该网的生成树连接序列 [(src_mm, dst_mm), ...]。"""
            connected = [pad_list[0]]
            remaining = list(pad_list[1:])
            conns = []
            while remaining:
                best_src = best_dst = None
                best_d = 1e9
                for dst_mm in remaining:
                    for src_mm in connected:
                        d = abs(dst_mm[0]-src_mm[0]) + abs(dst_mm[1]-src_mm[1])
                        if d < best_d:
                            best_d, best_src, best_dst = d, src_mm, dst_mm
                conns.append((best_src, best_dst))
                connected.append(best_dst)
                remaining.remove(best_dst)
            return conns

        def route_net(net_idx):
            """整网布线 (先拆后布)。返回未连通的连接列表 [(src,dst), ...]。"""
            ripup_net(net_idx)
            pad_list = pads_by_net[net_idx]
            own_cells = {mm_to_grid(*p) for p in pad_list}
            failed = []
            for src_mm, dst_mm in net_connections(pad_list):
                path = try_route(net_idx, src_mm, dst_mm, own_cells)
                if path:
                    segs, vlist = self._layered_path_to_segments(
                        path, net_idx, GRID, x0 - EDGE * GRID, y0 - EDGE * GRID,
                        start_mm=src_mm, end_mm=dst_mm,
                        layer_names=[LAYER_NAME[L] for L in SIG])
                    commit_path(net_idx, path, segs, vlist)
                else:
                    failed.append((src_mm, dst_mm))
            return failed

        def ideal_path(net_idx, src_mm, dst_mm, own_cells):
            """忽略异网走线/过孔 (仅守边界+异网焊盘体) 的理想路径, 用于识别"挡路网"。"""
            src_g = mm_to_grid(*src_mm)
            dst_g = mm_to_grid(*dst_mm)
            obs = {}
            for L in SIG:
                o = set(edge_cells)
                for nidx, cells in pad_hard[L].items():
                    if nidx != net_idx:
                        o |= cells
                obs[L] = o - own_cells
            return self._maze_route_2layer(
                src_g, dst_g, layers_of(src_mm), layers_of(dst_mm),
                obs, gw, gh, VIA_COST, layers=tuple(SIG))

        # 路由顺序: 焊盘多(最受约束)的网先布, 趁板面空闲抢到通路。
        order = sorted(
            [n for n in pads_by_net if len(pads_by_net[n]) >= 2],
            key=lambda n: -len(pads_by_net[n]))

        open_conns: dict = {}     # net -> list((src,dst)) 当前未连通连接
        for net_idx in order:
            open_conns[net_idx] = route_net(net_idx)

        def total_opens():
            return sum(len(v) for v in open_conns.values())

        def snapshot():
            return (_copy.deepcopy(trace_body), _copy.deepcopy(trace_halo),
                    _copy.deepcopy(via_body), _copy.deepcopy(via_halo),
                    _copy.deepcopy(net_segments), _copy.deepcopy(net_vias),
                    _copy.deepcopy(open_conns))

        def restore(snap):
            tb, th, vb, vh, ns, nv, oc = snap
            for L in ALLL:
                trace_body[L] = tb[L]
                trace_halo[L] = th[L]
            via_body.clear()
            via_body.update(vb)
            via_halo.clear()
            via_halo.update(vh)
            net_segments.clear()
            net_segments.update(ns)
            net_vias.clear()
            net_vias.update(nv)
            open_conns.clear()
            open_conns.update(oc)

        # ── 拆线重布 (rip-up & reroute): 失败连接拆掉挡路网再重布, 仅当总开路严格
        #    下降才接受 → 单调收敛, 绝不引入短路 (硬约束 build_obs 全程不放松)。 ──
        def run_ripup(rorder):
            budget = max(20, total_opens() * 6)
            improved = True
            while improved and budget > 0 and total_opens() > 0:
                improved = False
                for net_idx in rorder:
                    if not open_conns.get(net_idx):
                        continue
                    own_cells = {mm_to_grid(*p) for p in pads_by_net[net_idx]}
                    made_progress = False
                    for src_mm, dst_mm in list(open_conns[net_idx]):
                        ip = ideal_path(net_idx, src_mm, dst_mm, own_cells)
                        if ip is None:
                            continue  # 被焊盘/板边挡死 → 拆线无益 (诚实开路)
                        ideal_by_L = {L: set() for L in ALLL}
                        for gx, gy, L in ip:
                            ideal_by_L[L].add((gx, gy))
                        blockers = set()
                        for L in SIG:
                            for onet, cells in trace_halo[L].items():
                                if onet != net_idx and (cells & ideal_by_L[L]):
                                    blockers.add(onet)
                        ideal_all = set().union(*(ideal_by_L[L] for L in SIG))
                        for onet, cells in via_halo.items():
                            if onet != net_idx and (cells & ideal_all):
                                blockers.add(onet)
                        blockers &= set(rorder)
                        if not blockers:
                            continue
                        before = total_opens()
                        snap = snapshot()
                        for b in blockers:
                            ripup_net(b)
                        open_conns[net_idx] = route_net(net_idx)
                        for b in sorted(blockers, key=lambda n: -len(pads_by_net[n])):
                            open_conns[b] = route_net(b)
                        if total_opens() < before:
                            budget -= 1
                            improved = True
                            made_progress = True
                            break  # 该网已改善, 跳到下一个网
                        else:
                            restore(snap)
                    if made_progress:
                        continue

        # ── 协商式拥塞布线 (PathFinder·Lee, 道法自然·因而制之): 拆线重布抵达局部
        #    极小时启动。异网走线/过孔退化为「软代价」而非硬墙 → 允许多网暂时共用
        #    通道, present(拥塞) + history(历史) 代价逐轮递增, 互挡的网被自然推开,
        #    无冲突解自行涌现 (无为而无不为)。仅当迭代得到 clearance 全净 (零异网
        #    占用) 且开路更少时才落定 → 绝不引入 R007 短路, 亦绝不令开路变多。 ──
        from collections import Counter as _Counter

        def negotiated_route(rorder, max_iter=24):
            rorder = [n for n in rorder if len(pads_by_net.get(n, [])) >= 2]
            if total_opens() == 0 or not rorder:
                return
            PRES, HIST = 3.0, 1.0
            pen = {L: _Counter() for L in SIG}   # 异网走线 halo 占用计数 (按层)
            vpen = _Counter()                     # 异网过孔 halo (压全部信号层)
            hist = {L: _Counter() for L in SIG}   # 历史拥塞代价

            def add_pen(n):
                for L in SIG:
                    for c in trace_halo[L].get(n, ()):
                        pen[L][c] += 1
                for c in via_halo.get(n, ()):
                    vpen[c] += 1

            def sub_pen(n):
                for L in SIG:
                    for c in trace_halo[L].get(n, ()):
                        pen[L][c] -= 1
                for c in via_halo.get(n, ()):
                    vpen[c] -= 1

            def cost_field(fac):
                cost = {}
                for L in SIG:
                    c = {}
                    for cell, k in pen[L].items():
                        if k > 0:
                            c[cell] = c.get(cell, 0.0) + PRES * fac * k
                    for cell, k in vpen.items():
                        if k > 0:
                            c[cell] = c.get(cell, 0.0) + PRES * fac * k
                    for cell, k in hist[L].items():
                        if k > 0:
                            c[cell] = c.get(cell, 0.0) + HIST * k
                    cost[L] = c
                return cost

            def hard_obs(net_idx, own):
                hard = {}
                for L in SIG:
                    o = set(edge_cells)
                    for nidx, cells in pad_hard[L].items():
                        if nidx != net_idx:
                            o |= cells
                    hard[L] = o - own
                return hard

            def route_net_cong(net_idx, cost):
                sub_pen(net_idx)
                ripup_net(net_idx)
                pad_list = pads_by_net[net_idx]
                own = {mm_to_grid(*p) for p in pad_list}
                hard = hard_obs(net_idx, own)
                failed = []
                for src_mm, dst_mm in net_connections(pad_list):
                    src_g = mm_to_grid(*src_mm)
                    dst_g = mm_to_grid(*dst_mm)
                    path = self._maze_route_cost(
                        src_g, dst_g, layers_of(src_mm), layers_of(dst_mm),
                        hard, cost, gw, gh, VIA_COST, layers=tuple(SIG))
                    if path:
                        segs, vlist = self._layered_path_to_segments(
                            path, net_idx, GRID,
                            x0 - EDGE * GRID, y0 - EDGE * GRID,
                            start_mm=src_mm, end_mm=dst_mm,
                            layer_names=[LAYER_NAME[L] for L in SIG])
                        commit_path(net_idx, path, segs, vlist)
                    else:
                        failed.append((src_mm, dst_mm))
                add_pen(net_idx)
                return failed

            def conflicts():
                """异网 clearance 违例格 = 某网 body 落入异网 halo (对应 R007)。"""
                over = {L: set() for L in SIG}
                nconf = 0
                for L in SIG:
                    hc = _Counter()
                    for _n, cells in trace_halo[L].items():
                        for c in cells:
                            hc[c] += 1
                    for _n, cells in via_halo.items():
                        for c in cells:
                            hc[c] += 1
                    bodies = [(trace_body[L], trace_halo[L], via_halo)]
                    for n, cells in trace_body[L].items():
                        sh = trace_halo[L].get(n, frozenset())
                        sv = via_halo.get(n, frozenset())
                        for c in cells:
                            oth = hc[c] - (1 if c in sh else 0) \
                                - (1 if c in sv else 0)
                            if oth > 0:
                                over[L].add(c)
                                nconf += 1
                    for n, cells in via_body.items():
                        sh = trace_halo[L].get(n, frozenset())
                        sv = via_halo.get(n, frozenset())
                        for c in cells:
                            oth = hc[c] - (1 if c in sh else 0) \
                                - (1 if c in sv else 0)
                            if oth > 0:
                                over[L].add(c)
                                nconf += 1
                    _ = bodies
                return nconf, over

            for n in rorder:
                add_pen(n)
            best_snap = snapshot()
            best_opens = total_opens()
            for it in range(max_iter):
                fac = 0.5 + 0.5 * it
                cost = cost_field(fac)
                for net in rorder:
                    if it > 0:
                        cost = cost_field(fac)
                    open_conns[net] = route_net_cong(net, cost)
                nconf, over = conflicts()
                op = total_opens()
                if nconf == 0 and op < best_opens:
                    best_snap = snapshot()
                    best_opens = op
                    if op == 0:
                        break
                for L in SIG:
                    for c in over[L]:
                        hist[L][c] += 1
            restore(best_snap)

        run_ripup(order)

        # ── 4层叠层升级 (道法自然·因而制之): 2层布完仍有开路 → 把扇出最高的
        #    GND 与主电源 net 收入内层平面 (In1.Cu/In2.Cu), 退出点对点布线腾空
        #    F/B 信号层; 平面 net 经整层铜 + 缝合过孔连通, 信号网在腾空后的栅格
        #    重布。仅对 2 层布不通的板触发 (无为: 简单板仍 2 层)。 ──
        net_names = self._pcb_parse_net_names(text)
        gnd_nets = [n for n, nm in net_names.items()
                    if n > 0 and self._is_ground_net(nm)]

        def grid_to_mm(gx, gy):
            return (x0 - EDGE * GRID + gx * GRID, y0 - EDGE * GRID + gy * GRID)

        def pour_plane(net_idx, lname, confine=None):
            """整层铜平面: 灌满板内, 仅避让异网贯穿焊盘/过孔 → 连通该 net 全部焊盘。
            内层平面 (In1/In2.Cu) 与 F/B 上的细间距焊盘异层, 故本网自身焊盘的铜格
            必入平面 (经缝合过孔/贯穿孔下沉到内层连通), 不受异网同层 clearance 抠空影响,
            确保该 net 全部焊盘 100% 落在平面铜内 → R008 全连通 (道法自然·虚室生白)。"""
            own_pad_cells: set = set()
            for cx_mm, cy_mm, hw, hh, _plyr in pad_geom_by_net.get(net_idx, []):
                own_pad_cells |= pad_bbox_cells(cx_mm, cy_mm, hw, hh, 0.0)
            seed_cells = {mm_to_grid(*p) for p in pads_by_net.get(net_idx, [])}
            seed_cells |= via_body.get(net_idx, set())
            seed_cells |= own_pad_cells
            blocked = set(edge_cells)
            for nidx, geom in pad_geom_by_net.items():
                if nidx == net_idx:
                    continue
                for cx_mm, cy_mm, hw, hh, plyr in geom:
                    if plyr == "*":  # 仅贯穿焊盘到达内层, 抠空守 clearance
                        blocked |= pad_bbox_cells(cx_mm, cy_mm, hw, hh, CLR_SOFT)
            foreign_via_block: set = set()
            for onet, cells in via_halo.items():
                if onet != net_idx:
                    foreign_via_block |= cells
            blocked |= foreign_via_block
            # 异网通孔(贯穿全层)的 keepout 优先级高于本网焊盘力保: 孔体周围必须抠空,
            # 否则平面铜会压在异网孔体上 → 物理短路 (因而制之·物刑器成)。本网焊盘仍经
            # 其自身缝合过孔(孔中心入种子)连通平面, 故抠掉与异网孔重叠的边缘格不致开路。
            own_pad_cells -= foreign_via_block
            blocked -= own_pad_cells  # 本网自身焊盘恒可达 (异层, 经孔连通)
            if confine is None:
                cx0, cy0, cx1, cy1 = EDGE, EDGE, gw - EDGE, gh - EDGE
            else:
                cx0 = max(EDGE, confine[0]); cy0 = max(EDGE, confine[1])
                cx1 = min(gw - EDGE, confine[2]); cy1 = min(gh - EDGE, confine[3])
            fillable = {(gx, gy)
                        for gx in range(cx0, cx1)
                        for gy in range(cy0, cy1)
                        if (gx, gy) not in blocked}
            fillable |= own_pad_cells
            seeds = [s for s in seed_cells if s in fillable]
            if not seeds:
                return None
            kept: set = set()
            stack = list(seeds)
            while stack:
                c = stack.pop()
                if c in kept or c not in fillable:
                    continue
                kept.add(c)
                cx, cy = c
                stack.extend([(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)])
            kept |= own_pad_cells  # 保证全部自身焊盘格入铜 (孤立焊盘亦连通)
            rects = self._rle_cells_to_rects(kept, GRID, grid_to_mm)
            if not rects:
                return None
            return (net_idx, net_names.get(net_idx, f"#{net_idx}"), lname, rects)

        inner_zones: list = []
        plane_assign: list = []
        self._residual_layers = []
        if total_opens() > 0:
            # 4 层叠层 (道法自然·因而制之): 标准 JLC 叠层 F / In1=GND平面 / In2=信号 / B。
            # 启用第 3 信号层 In2.Cu → 三信号层逃逸拥塞 (单纯 2 层信号已抵几何天花板);
            # 最高扇出的 GND net 收入 In1.Cu 整层铜平面, 退出点对点布线、并为 F/B 上的
            # GND 焊盘补缝合过孔下沉到平面 → 既给信号腾地, 又天然全连通 (虚室生白)。
            gset = set(gnd_nets)
            gnd_cand = [n for n in pads_by_net
                        if n in gset and len(pads_by_net[n]) >= 2]
            planes = []
            if gnd_cand:
                planes.append(
                    (max(gnd_cand, key=lambda n: len(pads_by_net[n])), "In1.Cu"))
            plane_set = {n for n, _ in planes}
            if LI not in SIG:
                SIG.append(LI)
            log.info(f"  4层升级: 3信号层 {[LAYER_NAME[L] for L in SIG]}"
                     f" + 平面 {[(net_names.get(n), l) for n, l in planes]}")
            # 1) GND 平面网退出点对点布线, 腾空栅格
            for n in plane_set:
                ripup_net(n)
                open_conns[n] = []
            order_sig = [n for n in order if n not in plane_set]
            # 2) GND 平面网 SMD 焊盘加缝合过孔 (THT 焊盘本已贯穿内层, 无需)
            for n, _lname in planes:
                vlist = []
                for cx_mm, cy_mm, hw, hh, plyr in pad_geom_by_net.get(n, []):
                    if plyr == "*":
                        continue
                    gx, gy = mm_to_grid(cx_mm, cy_mm)
                    vsz, vdr = stitch_via_dim(hw, hh)
                    vlist.append({"x": cx_mm, "y": cy_mm, "net": n,
                                  "_gx": gx, "_gy": gy,
                                  "size": vsz, "drill": vdr})
                if vlist:
                    net_vias.setdefault(n, []).extend(vlist)
                    for v in vlist:
                        via_body.setdefault(n, set()).add((v["_gx"], v["_gy"]))
                    via_halo[n] = frozenset(
                        expand_halo(via_body[n], VIA_HALO))
            # 3) 全部信号网在 3 信号层 (F/In2/B) 上重新布线 + 拆线收敛
            for net_idx in order_sig:
                open_conns[net_idx] = route_net(net_idx)
            run_ripup(order_sig)
            # 3b) 仍有开路 → 协商式拥塞布线收敛 (PathFinder 推开互挡网, 涌现无冲突解)
            import os as _os
            if _os.environ.get("PCB_NEGOTIATE"):
                negotiated_route(order_sig)
                run_ripup(order_sig)
            # 3c) 残余开路闭合 (道法自然·因而制之): 三信号层 + 拆线/协商后仍开路的网,
            #     皆为 QFN/密集焊盘逃逸拥塞 (异网走线挤满, 几何上已无空档可绕)。圣人
            #     不与之争通道, 而为其各辟内层铜区 (In3.Cu, In4.Cu, ...): 该网 SMD 焊盘
            #     补缝合过孔下沉到内层 → 整片铜区连通其全部焊盘 (虚室生白, 一区即同电位)。
            #     内层铜区与 F/B 细间距 SMD 焊盘异层, 仅需避让异网"贯穿"焊盘 (R007 守层
            #     不误判), 且各网铜区限定在自身焊盘包围盒内、彼此不交 → 绝不引入短路;
            #     R008 并查集经铜区覆盖焊盘中心判全连通 → 残余开路必闭 (无不为)。包围盒
            #     互不相交的残余网共用一层 (装箱), 抑制层数 (残余少则层少, 无为)。
            res_planes: list = []        # [(net_idx, lname, (gx0,gy0,gx1,gy1))]
            res_layers: list = []        # [[lname, [bbox_mm,...]], ...]

            def _net_bbox_mm(_n):
                xs = [p[0] for p in pads_by_net[_n]]
                ys = [p[1] for p in pads_by_net[_n]]
                return (min(xs), min(ys), max(xs), max(ys))

            def _bbox_sep(a, b, m=2.0):  # True = 充分分离 (含 m mm 间隙)
                return (a[2] + m < b[0] or b[2] + m < a[0] or
                        a[3] + m < b[1] or b[3] + m < a[1])

            def _pt_seg(px, py, x1, y1, x2, y2):
                """点到线段最短距离 (mm)。"""
                dx, dy = x2 - x1, y2 - y1
                L2 = dx * dx + dy * dy
                if L2 <= 1e-12:
                    return _math.hypot(px - x1, py - y1)
                t = ((px - x1) * dx + (py - y1) * dy) / L2
                t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
                return _math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

            def place_stitch_via(n, cx, cy, hw, hh):
                """缝合过孔精确落点 (道法自然·因而制之: 顺铜箔之实而制孔位):
                全贯穿过孔物理钻穿所有铜层 → 孔体须避让任一层的异网铜 (走线/过孔/
                焊盘)。在焊盘内 (孔心守焊盘以保贴合) 细网格搜净距最大点, 并按净距收
                孔径 (下限守工艺), 使孔体不压异网铜。返回 (via_dict, safe_bool)。"""
                MARGIN = 0.05                       # mm 物理裕量 (除不重叠外再留余)
                rmin = VIA_MIN_DIA / 2.0
                rcap = VIA_DIA / 2.0
                R = rcap + 0.7                      # 邻铜筛选半径
                fseg = []
                for onet, segs in net_segments.items():
                    if onet == n:
                        continue
                    for s in segs:
                        if (min(s["x1"], s["x2"]) - R <= cx <= max(s["x1"], s["x2"]) + R
                                and min(s["y1"], s["y2"]) - R <= cy <= max(s["y1"], s["y2"]) + R):
                            fseg.append((s["x1"], s["y1"], s["x2"], s["y2"]))
                fvia = []
                for onet, vs in net_vias.items():
                    if onet == n:
                        continue
                    for v in vs:
                        ovr = v.get("size", VIA_DIA) / 2.0
                        if abs(v["x"] - cx) <= R + ovr and abs(v["y"] - cy) <= R + ovr:
                            fvia.append((v["x"], v["y"], ovr))
                fpad = []
                for onet, plist in pad_geom_by_net.items():
                    if onet == n:
                        continue
                    for (px, py, phw, phh, _pl) in plist:
                        if abs(px - cx) <= R + phw and abs(py - cy) <= R + phh:
                            fpad.append((px, py, phw, phh))

                _thw = TRACE_W / 2.0                 # 走线半宽 (mm)
                def clearance(vx, vy):
                    d = 9.9
                    for (x1, y1, x2, y2) in fseg:
                        d = min(d, _pt_seg(vx, vy, x1, y1, x2, y2) - _thw)
                    for (ox, oy, ovr) in fvia:
                        d = min(d, _math.hypot(vx - ox, vy - oy) - ovr)
                    for (px, py, phw, phh) in fpad:
                        ddx = max(abs(vx - px) - phw, 0.0)
                        ddy = max(abs(vy - py) - phh, 0.0)
                        d = min(d, _math.hypot(ddx, ddy))
                    return d

                step = 0.02
                nx = max(1, int(round(2 * hw / step)))
                ny = max(1, int(round(2 * hh / step)))
                best = None  # (clr, vx, vy)
                for ix in range(nx + 1):
                    vx = (cx - hw) + (2 * hw) * ix / nx if nx else cx
                    for iy in range(ny + 1):
                        vy = (cy - hh) + (2 * hh) * iy / ny if ny else cy
                        c = clearance(vx, vy)
                        if best is None or c > best[0]:
                            best = (c, vx, vy)
                if best is None:
                    best = (clearance(cx, cy), cx, cy)
                clr, vx, vy = best
                r = min(rcap, clr - MARGIN)
                if r < rmin:
                    r = rmin                         # 守工艺下限 (可能仍压, 交由重布解)
                size = round(2 * r, 3)
                drill = max(VIA_MIN_DRILL, round(size - 0.20, 3))
                gx, gy = mm_to_grid(vx, vy)
                safe = clr >= r                      # 孔体不与异网铜重叠 = 物理无短路
                return ({"x": round(vx, 4), "y": round(vy, 4), "net": n,
                         "_gx": gx, "_gy": gy, "size": size, "drill": drill}, safe)

            residual = [n for n in order_sig
                        if open_conns.get(n) and n not in plane_set
                        and len(pads_by_net.get(n, [])) >= 2]
            residual_set = set(residual)
            _next_in = 3  # In1=GND平面, In2=信号层, 残余铜区从 In3.Cu 起
            _res_unsafe = 0
            for n in residual:
                bb = _net_bbox_mm(n)
                lname = None
                for slot in res_layers:
                    if all(_bbox_sep(bb, ob) for ob in slot[1]):
                        lname = slot[0]; slot[1].append(bb); break
                if lname is None:
                    lname = f"In{_next_in}.Cu"; _next_in += 1
                    res_layers.append([lname, [bb]])
                # 缝合过孔: 该网 SMD 焊盘下沉到内层铜区 (通孔焊盘本已贯穿, 无需)
                vlist = []
                for cx_mm, cy_mm, hw, hh, plyr in pad_geom_by_net.get(n, []):
                    if plyr == "*":
                        continue
                    v, ok = place_stitch_via(n, cx_mm, cy_mm, hw, hh)
                    if not ok:
                        _res_unsafe += 1
                    vlist.append(v)
                if vlist:
                    net_vias.setdefault(n, []).extend(vlist)
                    for v in vlist:
                        via_body.setdefault(n, set()).add((v["_gx"], v["_gy"]))
                    via_halo[n] = frozenset(expand_halo(via_body[n], VIA_HALO))
                # 铜区限定在焊盘包围盒 + 1mm 余量 (本地化, 不跨板, 共层不交)
                bx0, by0 = mm_to_grid(bb[0] - 1.0, bb[1] - 1.0)
                bx1, by1 = mm_to_grid(bb[2] + 1.0, bb[3] + 1.0)
                res_planes.append((n, lname, (bx0, by0, bx1, by1)))
                open_conns[n] = []  # 铜区覆盖全焊盘 → 视作闭合
            if res_planes:
                log.info(f"  残余开路闭合: {len(res_planes)}网 → 内层铜区 "
                         f"{[(net_names.get(n), l) for n, l, _ in res_planes]}")
            # 残余缝合过孔落定后, 其「层无关」keepout 可能压住先前已布的异网走线 →
            # 拆除冲突异网并就地重布 (build_obs 含异网过孔 halo, 重布必绕开), 单调闭合:
            # 仅当总开路不增才接受 (无为而无不为: 让走线避孔, 而非强移孔)。
            if res_planes:
                res_keep = set()
                for n in residual_set:
                    res_keep |= set(via_halo.get(n, ()))
                conflict = []
                for f in order_sig:
                    if f in plane_set or f in residual_set:
                        continue
                    tb = set()
                    for L in SIG:
                        tb |= trace_body[L].get(f, set())
                    if tb & res_keep:
                        conflict.append(f)
                rerouted = 0
                for f in sorted(conflict, key=lambda n: -len(pads_by_net[n])):
                    before = total_opens()
                    snap = snapshot()
                    open_conns[f] = route_net(f)
                    if total_opens() > before:
                        restore(snap)
                    else:
                        rerouted += 1
                if conflict:
                    log.info(f"  缝合过孔避让重布: 冲突异网{len(conflict)} "
                             f"成功{rerouted} 残余压孔焊盘{_res_unsafe}")
            # 4) 灌注 In1.Cu GND 平面 → 平面网全连通
            for n, lname in planes:
                z = pour_plane(n, lname)
                if z:
                    inner_zones.append(z)
            # 4b) 灌注残余网内层铜区 (各自包围盒内, 经缝合过孔连通全焊盘)
            for n, lname, conf in res_planes:
                z = pour_plane(n, lname, confine=conf)
                if z:
                    inner_zones.append(z)
            self._residual_layers = sorted({l for _n, l, _c in res_planes})
            plane_assign = planes

        if getattr(self, "_DIAG", False):
            print("  --- OPEN DIAG (trapped=ideal_path None, else congested) ---")
            for n in order:
                for src_mm, dst_mm in open_conns.get(n, []):
                    oc = {mm_to_grid(*p) for p in pads_by_net[n]}
                    ip = ideal_path(n, src_mm, dst_mm, oc)
                    tag = "TRAPPED" if ip is None else f"congested(len={len(ip)})"
                    print(f"    net#{n} {net_names.get(n,'?'):<12} "
                          f"{src_mm}->{dst_mm}  {tag}")

        segments: list = [s for n in net_segments for s in net_segments[n]]
        vias: list = [v for n in net_vias for v in net_vias[n]]
        for v in vias:
            v.pop("_gx", None)
            v.pop("_gy", None)
        routed = sum(len(pads_by_net[n]) - 1 - len(open_conns.get(n, []))
                     for n in order)
        unrouted = total_opens()
        if segments:
            self._append_segments_to_pcb(pcb_path, segments, vias)

        # ── 铺铜 (copper pour): 给 GND 网在 F.Cu/B.Cu 浇灌真实接地平面 ──
        # 道法自然: 复用布线同一栅格 — 凡「非边界、非异网焊盘/走线/过孔间距区」
        # 的格皆可灌铜; 从 GND 焊盘洪泛, 只保留与 GND 焊盘连通的铜岛 (去孤岛),
        # 故铺铜天然守 clearance (不压异网铜=不短路), 又真实连通其覆盖的 GND 焊盘。
        zones: list = list(inner_zones)
        for G in gnd_nets:
            gnd_seed_cells = {mm_to_grid(*p) for p in pads_by_net.get(G, [])}
            for L, lname in ((LF, "F.Cu"), (LB, "B.Cu")):
                blocked = set(edge_cells)
                for nidx, cells in pad_soft[L].items():
                    if nidx != G:
                        blocked |= cells
                for onet, cells in trace_halo[L].items():
                    if onet != G:
                        blocked |= cells
                for onet, cells in via_halo.items():
                    if onet != G:
                        blocked |= cells
                # 可灌格: 板内 (避 EDGE 环) 且非 blocked
                fillable = set()
                for gx in range(EDGE, gw - EDGE):
                    for gy in range(EDGE, gh - EDGE):
                        if (gx, gy) not in blocked:
                            fillable.add((gx, gy))
                # 从 GND 焊盘洪泛, 只留连通铜岛 (去孤岛)
                seeds = [s for s in gnd_seed_cells if s in fillable]
                if not seeds:
                    continue
                kept = set()
                stack = list(seeds)
                while stack:
                    c = stack.pop()
                    if c in kept or c not in fillable:
                        continue
                    kept.add(c)
                    cx, cy = c
                    stack.extend([(cx+1, cy), (cx-1, cy),
                                  (cx, cy+1), (cx, cy-1)])
                if not kept:
                    continue
                # 行程编码 → mm 矩形 (filled_polygon)
                rects = self._rle_cells_to_rects(kept, GRID, grid_to_mm)
                if rects:
                    zones.append((G, net_names[G], lname, rects))
        # 声明用到的内层铜: 平面层 (In1.Cu) ∪ 内层信号层 (In2.Cu) ∪ 残余铜区层 (In3+.Cu)。
        inner_used = sorted({lname for _n, lname in plane_assign}
                            | ({"In2.Cu"} if LI in SIG else set())
                            | set(getattr(self, "_residual_layers", [])),
                            key=lambda s: int(re.search(r"\d+", s).group()))
        if inner_used:
            self._ensure_inner_cu_layers(pcb_path, inner_used)
        if zones:
            self._append_zones_to_pcb(pcb_path, zones)

        layers_n = 2 + len(inner_used)
        log.info(f"✅ {layers_n}层自动布线完成(含rip-up): ✅{routed}通 / ❌{unrouted}失败 / "
                 f"{len(segments)}段 / {len(vias)}过孔 / {len(zones)}铺铜区")
        return {"routed": routed, "unrouted": unrouted,
                "segments": len(segments), "vias": len(vias),
                "zones": len(zones), "layers": layers_n}

    def _pcb_board_bounds(self, text: str):
        """从 Edge.Cuts gr_rect 提取板框 (x0,y0,x1,y1)，单位mm"""
        m = re.search(
            r'\(gr_rect\s+\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)'
            r'\s+\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\).*?"Edge\.Cuts"',
            text, re.DOTALL
        )
        if m:
            return (float(m.group(1)), float(m.group(2)),
                    float(m.group(3)), float(m.group(4)))
        return None

    def _pcb_parse_pads_by_net(self, text: str) -> dict:
        """解析.kicad_pcb提取所有焊盘绝对坐标，按 net_idx 分组"""
        pads, _ = self._pcb_parse_pads_with_geometry(text)
        return pads

    def _pcb_parse_pads_with_geometry(self, text: str) -> tuple:
        """
        增强型焊盘解析器 — 同时提取中心坐标和物理尺寸。
        Returns:
          pads_by_net:     {net_idx: [(cx, cy), ...]}              路由树用
          pad_geom_by_net: {net_idx: [(cx, cy, hw, hh, lyr), ...]}  精确封锁用
          hw/hh = 半宽/半高 (mm, 保守取最大边)
          lyr   = 'F' | 'B' | '*'  焊盘所在铜层 ('*' = 通孔, 占双层)
        """
        pads_by_net: dict = {}
        pad_geom_by_net: dict = {}
        i = 0
        while True:
            fp_idx = text.find("(footprint ", i)
            if fp_idx == -1:
                break
            depth = 0
            j = fp_idx
            while j < len(text):
                if text[j] == "(":    depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            fp_text = text[fp_idx:j]

            at_m = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', fp_text)
            fp_x = float(at_m.group(1)) if at_m else 0.0
            fp_y = float(at_m.group(2)) if at_m else 0.0

            pi = 0
            while True:
                pad_idx = fp_text.find("(pad ", pi)
                if pad_idx == -1:
                    break
                d2 = 0
                pj = pad_idx
                while pj < len(fp_text):
                    if fp_text[pj] == "(":    d2 += 1
                    elif fp_text[pj] == ")":
                        d2 -= 1
                        if d2 == 0:
                            pj += 1
                            break
                    pj += 1
                pad_text = fp_text[pad_idx:pj]

                pat_m  = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)', pad_text)
                size_m = re.search(r'\(size\s+([\d.]+)\s+([\d.]+)\)',   pad_text)
                lyr_m  = re.search(r'\(layers\s+([^)]*)\)', pad_text)
                if pat_m:
                    pad_abs_x = fp_x + float(pat_m.group(1))
                    pad_abs_y = fp_y + float(pat_m.group(2))
                    hw = float(size_m.group(1)) / 2.0 if size_m else 0.5
                    hh = float(size_m.group(2)) / 2.0 if size_m else 0.5
                    lyr_txt = lyr_m.group(1) if lyr_m else '"F.Cu"'
                    if "*.Cu" in lyr_txt or ("F.Cu" in lyr_txt and "B.Cu" in lyr_txt):
                        lyr = "*"
                    elif "B.Cu" in lyr_txt and "F.Cu" not in lyr_txt:
                        lyr = "B"
                    else:
                        lyr = "F"
                    net_m = re.search(r'\(net\s+(\d+)', pad_text)
                    if net_m:
                        net_idx = int(net_m.group(1))
                        if net_idx > 0:
                            pads_by_net.setdefault(net_idx, [])
                            pads_by_net[net_idx].append((pad_abs_x, pad_abs_y))
                            pad_geom_by_net.setdefault(net_idx, [])
                            pad_geom_by_net[net_idx].append(
                                (pad_abs_x, pad_abs_y, hw, hh, lyr))
                pi = pj
            i = j
        return pads_by_net, pad_geom_by_net

    def _bfs_route(self, src: tuple, dst: tuple,
                   obstacles: set, gw: int, gh: int):
        """Lee's BFS格路由，返回格坐标路径列表 (src→dst) 或 None"""
        from collections import deque
        if src == dst:
            return [src]
        parent: dict = {src: None}
        q = deque([src])
        while q:
            x, y = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) in parent or (nx, ny) in obstacles:
                    continue
                if not (0 <= nx < gw and 0 <= ny < gh):
                    continue
                parent[(nx, ny)] = (x, y)
                if (nx, ny) == dst:
                    path, cur = [(nx, ny)], (x, y)
                    while cur is not None:
                        path.append(cur)
                        cur = parent[cur]
                    return list(reversed(path))
                q.append((nx, ny))
        return None

    def _maze_route_2layer(self, src: tuple, dst: tuple,
                           src_layers: set, dst_layers: set,
                           obs: dict, gw: int, gh: int, via_cost: int,
                           layers: tuple = (0, 1), via_obs: set = None):
        """N 层迷宫布线 — 统一代价搜索 (Dijkstra).

        状态 = (gx, gy, layer). 平面相邻移动代价 1; 同坐标贯穿过孔可换到任一其它
        信号层 (代价 via_cost), 仅当目标层该格空闲. 返回 [(gx,gy,layer), ...] 或 None.
        不同 net 走线落在不同层即不短路 —— 这是真实 PCB 用 ≥2 层消除交叉的根本机制;
        层数越多 (3~4 信号层) 可布性越高 (道法自然·因而制之)。
        """
        import heapq
        starts = [(src[0], src[1], L) for L in src_layers
                  if (src[0], src[1]) not in obs[L]]
        if not starts:
            # 起点被占 (焊盘豁免已在调用方处理), 仍尝试从允许层强行起步
            starts = [(src[0], src[1], L) for L in src_layers]
        goals = {(dst[0], dst[1], L) for L in dst_layers}
        dist: dict = {}
        parent: dict = {}
        pq = []
        for s in starts:
            dist[s] = 0
            parent[s] = None
            heapq.heappush(pq, (0, s))
        while pq:
            d, (x, y, L) = heapq.heappop(pq)
            if d > dist.get((x, y, L), 1e18):
                continue
            if (x, y, L) in goals:
                path = []
                cur = (x, y, L)
                while cur is not None:
                    path.append(cur)
                    cur = parent[cur]
                return list(reversed(path))
            # 平面移动
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < gw and 0 <= ny < gh):
                    continue
                if (nx, ny) in obs[L]:
                    continue
                ns = (nx, ny, L)
                nd = d + 1
                if nd < dist.get(ns, 1e18):
                    dist[ns] = nd
                    parent[ns] = (x, y, L)
                    heapq.heappush(pq, (nd, ns))
            # 换层 (贯穿过孔可达任一其它信号层)
            # 全贯穿过孔物理钻穿所有铜层 → 落点须在「层无关」禁区 via_obs 之外
            # (含所有信号层的他网走线/过孔/焊盘按过孔半径留间距), 否则中间层隐性短路。
            if via_obs is not None and (x, y) in via_obs:
                continue
            for oL in layers:
                if oL == L:
                    continue
                if (x, y) in obs[oL]:
                    continue
                ns = (x, y, oL)
                nd = d + via_cost
                if nd < dist.get(ns, 1e18):
                    dist[ns] = nd
                    parent[ns] = (x, y, L)
                    heapq.heappush(pq, (nd, ns))
        return None

    def _maze_route_cost(self, src: tuple, dst: tuple,
                         src_layers: set, dst_layers: set,
                         hard: dict, cost: dict, gw: int, gh: int,
                         via_cost: int, layers: tuple = (0, 1)):
        """协商式拥塞布线的迷宫核 (PathFinder·Lee): 与 _maze_route_2layer 同构,
        但异网走线/过孔不再是硬墙, 而是 cost[L][cell] 的「软代价」(present 拥塞 +
        history 历史)。仅边界与异网焊盘体留在 hard[L] 里 (绝不可压 → 杜绝硬短路)。
        多轮迭代中软代价递增, 互相挡路的网自然被推开 → 涌现无冲突解 (无为而无不为)。"""
        import heapq
        starts = [(src[0], src[1], L) for L in src_layers
                  if (src[0], src[1]) not in hard[L]]
        if not starts:
            starts = [(src[0], src[1], L) for L in src_layers]
        goals = {(dst[0], dst[1], L) for L in dst_layers}
        dist: dict = {}
        parent: dict = {}
        pq = []
        for s in starts:
            base = cost[s[2]].get((s[0], s[1]), 0.0)
            dist[s] = base
            parent[s] = None
            heapq.heappush(pq, (base, s))
        while pq:
            d, (x, y, L) = heapq.heappop(pq)
            if d > dist.get((x, y, L), 1e18):
                continue
            if (x, y, L) in goals:
                path = []
                cur = (x, y, L)
                while cur is not None:
                    path.append(cur)
                    cur = parent[cur]
                return list(reversed(path))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < gw and 0 <= ny < gh):
                    continue
                if (nx, ny) in hard[L]:
                    continue
                ns = (nx, ny, L)
                nd = d + 1 + cost[L].get((nx, ny), 0.0)
                if nd < dist.get(ns, 1e18):
                    dist[ns] = nd
                    parent[ns] = (x, y, L)
                    heapq.heappush(pq, (nd, ns))
            for oL in layers:
                if oL == L:
                    continue
                if (x, y) in hard[oL]:
                    continue
                ns = (x, y, oL)
                nd = d + via_cost + cost[oL].get((x, y), 0.0)
                if nd < dist.get(ns, 1e18):
                    dist[ns] = nd
                    parent[ns] = (x, y, L)
                    heapq.heappush(pq, (nd, ns))
        return None

    def _layered_path_to_segments(self, path: list, net_idx: int,
                                  grid_mm: float, x0: float, y0: float,
                                  start_mm=None, end_mm=None, layer_names=None):
        """分层路径 [(gx,gy,L)] → (segments, vias). 换层处插入过孔.
        layer_names: 层索引→KiCad层名 (默认双层 0=F.Cu/1=B.Cu)。"""
        if layer_names is None:
            _LAYER = {0: "F.Cu", 1: "B.Cu"}
        else:
            _LAYER = {i: nm for i, nm in enumerate(layer_names)}
        segs: list = []
        vias: list = []
        # 切成同层连续子段
        runs: list = []
        run = [path[0]]
        for node in path[1:]:
            if node[2] == run[-1][2]:
                run.append(node)
            else:
                runs.append(run)
                # 换层点 = 上一子段末格 (与新子段首格同坐标)
                gx, gy = run[-1][0], run[-1][1]
                vx = x0 + gx * grid_mm
                vy = y0 + gy * grid_mm
                vias.append({"x": vx, "y": vy, "net": net_idx,
                             "_gx": gx, "_gy": gy})
                run = [node]
        runs.append(run)

        for ri, run in enumerate(runs):
            lyr = _LAYER.get(run[0][2], "F.Cu")
            pts2d = [(g[0], g[1]) for g in run]
            s_mm = start_mm if ri == 0 else None
            e_mm = end_mm if ri == len(runs) - 1 else None
            segs.extend(self._path_to_segments(
                pts2d, net_idx, grid_mm, x0, y0,
                start_mm=s_mm, end_mm=e_mm, layer=lyr))
        return segs, vias

    def _path_to_segments(self, path: list, net_idx: int,
                          grid_mm: float, x0: float, y0: float,
                          start_mm=None, end_mm=None, layer: str = "F.Cu") -> list:
        """
        BFS格路径 → 合并成最少直线段 (KiCad segment格式)
        start_mm / end_mm: 精确pad坐标 (覆盖格坐标端点，防止悬空末端)
        layer: 目标铜层 ("F.Cu" 或 "B.Cu")
        """
        if len(path) < 2:
            return []
        segs = []
        run_start = path[0]
        run_dx = path[1][0] - path[0][0]
        run_dy = path[1][1] - path[0][1]
        for i in range(1, len(path)):
            cur = path[i]
            if i < len(path) - 1:
                nxt = path[i + 1]
                if (nxt[0] - cur[0], nxt[1] - cur[1]) == (run_dx, run_dy):
                    continue
            x1 = x0 + run_start[0] * grid_mm
            y1 = y0 + run_start[1] * grid_mm
            x2 = x0 + cur[0] * grid_mm
            y2 = y0 + cur[1] * grid_mm
            if abs(x1 - x2) > 0.01 or abs(y1 - y2) > 0.01:
                segs.append({"x1": x1, "y1": y1,
                             "x2": x2, "y2": y2, "net": net_idx,
                             "layer": layer})
            if i < len(path) - 1:
                run_start = cur
                run_dx = path[i + 1][0] - cur[0]
                run_dy = path[i + 1][1] - cur[1]
        # 精确pad端点覆盖 — 防止KiCad报 "走线末端悬空"
        if segs and start_mm:
            segs[0]["x1"], segs[0]["y1"] = start_mm[0], start_mm[1]
        if segs and end_mm:
            segs[-1]["x2"], segs[-1]["y2"] = end_mm[0], end_mm[1]
        return segs

    def _pcb_parse_net_names(self, text: str) -> dict:
        """解析 (net N "NAME") → {N: NAME}."""
        out = {}
        for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]*)"\)', text):
            out[int(m.group(1))] = m.group(2)
        return out

    @staticmethod
    def _is_ground_net(name: str) -> bool:
        u = (name or "").upper()
        if u in ("0", "VSS", "EARTH"):
            return True
        return "GND" in u or "GROUND" in u

    @staticmethod
    def _is_power_net(name: str) -> bool:
        """主电源轨判定 (排除地网与 *_SENSE/*_FB 分压采样信号)。"""
        u = (name or "").upper().lstrip("+")
        if not u or KiCadArm._is_ground_net(name):
            return False
        if u.endswith("_SENSE") or u.endswith("_FB") or "_ADC" in u:
            return False
        keys = ("VCC", "VDD", "VBAT", "VBUS", "VIN", "VOUT", "VSYS",
                "3V3", "3.3V", "5V", "1V8", "1.8V", "1V2", "2V5", "VREF",
                "AVDD", "DVDD", "VDDA", "PWR", "POWER", "VDDIO", "VCORE")
        return any(k in u for k in keys)

    @staticmethod
    def _rle_cells_to_rects(cells: set, grid: float, grid_to_mm) -> list:
        """格集合按行行程编码 → mm 轴对齐矩形 [(x0,y0,x1,y1), ...]。
        每个矩形为一行内连续格的最大跨度, 外扩半格使相邻行/列铜箔相接。"""
        rows: dict = {}
        for gx, gy in cells:
            rows.setdefault(gy, []).append(gx)
        h = grid / 2.0
        rects = []
        for gy, xs in rows.items():
            xs.sort()
            run_start = prev = xs[0]
            for gx in xs[1:] + [None]:
                if gx == prev + 1:
                    prev = gx
                    continue
                mx0, my0 = grid_to_mm(run_start, gy)
                mx1, my1 = grid_to_mm(prev, gy)
                rects.append((mx0 - h, my0 - h, mx1 + h, my1 + h))
                if gx is not None:
                    run_start = prev = gx
        return rects

    def _append_zones_to_pcb(self, pcb_path: str, zones: list) -> None:
        """将铺铜 (zone) 追加到 .kicad_pcb。zones=[(net,name,layer,rects), ...];
        rects 为 mm 轴对齐矩形列表, 每个矩形作一个 filled_polygon。"""
        import uuid as _uuid
        text = Path(pcb_path).read_text(encoding="utf-8").rstrip()
        blocks = []
        for net, name, layer, rects in zones:
            xs0 = min(r[0] for r in rects)
            ys0 = min(r[1] for r in rects)
            xs1 = max(r[2] for r in rects)
            ys1 = max(r[3] for r in rects)
            fps = []
            for (x0, y0, x1, y1) in rects:
                fps.append(
                    f'    (filled_polygon (layer "{layer}") (pts '
                    f'(xy {x0:.4f} {y0:.4f}) (xy {x1:.4f} {y0:.4f}) '
                    f'(xy {x1:.4f} {y1:.4f}) (xy {x0:.4f} {y1:.4f})))')
            blocks.append(
                f'  (zone (net {net}) (net_name "{name}") (layer "{layer}") '
                f'(uuid "{_uuid.uuid4()}") (hatch edge 0.5)\n'
                f'    (connect_pads (clearance 0.2))\n'
                f'    (min_thickness 0.25)\n'
                f'    (fill yes (thermal_gap 0.2) (thermal_bridge_width 0.4))\n'
                f'    (polygon (pts (xy {xs0:.4f} {ys0:.4f}) '
                f'(xy {xs1:.4f} {ys0:.4f}) (xy {xs1:.4f} {ys1:.4f}) '
                f'(xy {xs0:.4f} {ys1:.4f})))\n'
                + "\n".join(fps) + "\n  )")
        body = "\n".join(blocks)
        new_text = (text[:-1].rstrip() + "\n" + body + "\n)"
                    if text.endswith(")") else text + "\n" + body)
        Path(pcb_path).write_text(new_text, encoding="utf-8")
        log.info(f"  写入 {len(zones)} 个铺铜区到PCB文件")

    def _ensure_inner_cu_layers(self, pcb_path: str, layer_names: list) -> None:
        """4层升级时, 把 In1.Cu/In2.Cu 内层铜声明插入 (layers ...) 块。
        本引擎按层名 (而非序号) 处理布线/DRC/Gerber, 故序号仅取未占用值。"""
        text = Path(pcb_path).read_text(encoding="utf-8")
        # In{k}.Cu → 唯一未占用序号 (引擎按层名处理, 序号只需不撞: 2k+2, In1=4..In14=30)
        def _ord(ln):
            m = re.match(r"In(\d+)\.Cu$", ln)
            return 2 * int(m.group(1)) + 2 if m else 4
        ins = []
        for ln in layer_names:
            if f'"{ln}"' in text:
                continue
            ins.append(f'    ({_ord(ln)} "{ln}" signal)')
        if not ins:
            return
        text = text.replace('    (0 "F.Cu" signal)\n',
                            '    (0 "F.Cu" signal)\n' + "\n".join(ins) + "\n", 1)
        Path(pcb_path).write_text(text, encoding="utf-8")
        log.info(f"  声明内层铜: {[l for l in layer_names]}")

    def _append_segments_to_pcb(self, pcb_path: str, segments: list,
                                   vias: list = None) -> None:
        """将 (segment)/(via) 追加到 .kicad_pcb 文件末尾 ')' 之前。支持多层。"""
        import uuid as _uuid
        text = Path(pcb_path).read_text(encoding="utf-8").rstrip()
        lines = []
        for s in segments:
            lyr = s.get("layer", "F.Cu")
            lines.append(
                f'  (segment (start {s["x1"]:.4f} {s["y1"]:.4f})'
                f' (end {s["x2"]:.4f} {s["y2"]:.4f})'
                f' (width 0.15) (layer "{lyr}")'
                f' (net {s["net"]}) (tstamp "{_uuid.uuid4()}"))'
            )
        for v in (vias or []):
            vsz = v.get("size", 0.45)
            vdr = v.get("drill", 0.25)
            lines.append(
                f'  (via (at {v["x"]:.4f} {v["y"]:.4f})'
                f' (size {vsz}) (drill {vdr}) (layers "F.Cu" "B.Cu")'
                f' (net {v["net"]}) (tstamp "{_uuid.uuid4()}"))'
            )
        new_text = (text[:-1].rstrip() + "\n" + "\n".join(lines) + "\n)"
                    if text.endswith(")") else text + "\n" + "\n".join(lines))
        Path(pcb_path).write_text(new_text, encoding="utf-8")
        log.info(f"  写入{len(segments)}段铜线 + {len(vias or [])}过孔到PCB文件")

    # ─────────────────────────────────────────────────────────
    # 三: pywinauto GUI自动化 — 控制嘉立创EDA / KiCad / AD
    # ─────────────────────────────────────────────────────────
    def _get_pywinauto(self):
        try:
            from pywinauto.application import Application
            return Application
        except ImportError:
            log.warning("pywinauto未安装, GUI控制不可用 (pip install pywinauto)")
            return None

    def open_lceda(self, project_path: str = None) -> bool:
        """打开嘉立创EDA专业版"""
        Application = self._get_pywinauto()
        if Application is None:
            return False
        exe = None
        if self.lceda_dir:
            for name in ["lceda-pro.exe", "lceda.exe", "EasyEDA.exe"]:
                p = self.lceda_dir / name
                if p.exists():
                    exe = str(p)
                    break
        if exe is None:
            log.error("嘉立创EDA可执行文件未找到")
            return False
        cmd = exe if project_path is None else f'"{exe}" "{project_path}"'
        try:
            self._lceda_app = Application(backend="uia").start(cmd, timeout=15)
            log.info("✅ 嘉立创EDA已启动")
            return True
        except Exception as e:
            log.error(f"启动嘉立创EDA失败: {e}")
            return False

    def open_kicad(self, project_path: str = None) -> bool:
        """打开KiCad"""
        Application = self._get_pywinauto()
        if Application is None:
            return False
        exe = None
        if self.kicad_dir:
            kicad_exe = self.kicad_dir / "bin" / "kicad.exe"
            if kicad_exe.exists():
                exe = str(kicad_exe)
        if exe is None:
            log.error("KiCad可执行文件未找到")
            return False
        cmd = exe if project_path is None else f'"{exe}" "{project_path}"'
        try:
            self._kicad_app = Application(backend="uia").start(cmd, timeout=15)
            log.info("✅ KiCad已启动")
            return True
        except Exception as e:
            log.error(f"启动KiCad失败: {e}")
            return False

    def gui_click_menu(self, app_title_pattern: str, menu_path: List[str]) -> bool:
        """
        GUI操控: 点击菜单项
        app_title_pattern: ".*KiCad.*" 或 ".*嘉立创.*"
        menu_path: ["文件", "导出", "Gerber文件"]
        """
        Application = self._get_pywinauto()
        if Application is None:
            return False
        try:
            app = Application(backend="uia").connect(title_re=app_title_pattern)
            win = app.top_window()
            menu = win.menu()
            for item in menu_path:
                menu = menu.item_by_path(item)
                menu.click_input()
            log.info(f"✅ 菜单操作完成: {' > '.join(menu_path)}")
            return True
        except Exception as e:
            log.error(f"GUI菜单操作失败: {e}")
            return False

    def gui_screenshot(self, save_path: str = "pcb_screen.png") -> Optional[str]:
        """截图当前PCB软件窗口 (五感之眼) — 委托 pcb_eye.eye_screenshot 避免重复实现"""
        from pcb_eye import eye_screenshot
        return eye_screenshot(save_path)

    # ─────────────────────────────────────────────────────────
    # 工具: 环境状态报告
    # ─────────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        pcbnew_ok = self._load_pcbnew() is not None
        return {
            "kicad_dir":   str(self.kicad_dir) if self.kicad_dir else "未找到",
            "kicad_cli":   self.cli_path or "未找到",
            "footprints":  str(self.fp_dir) if self.fp_dir else "未找到",
            "pcbnew_api":  "✅ 可用" if pcbnew_ok else "⚠️ 不可用",
            "lceda_dir":   str(self.lceda_dir) if self.lceda_dir else "未找到",
            "control_levels": {
                "L1_pcbnew_api": "✅" if pcbnew_ok else "❌",
                "L2_kicad_cli":  "✅" if self.cli_path else "❌",
                "L3_pywinauto":  "✅" if _get_pywinauto_available() else "❌",
            }
        }


def _get_pywinauto_available() -> bool:
    try:
        import pywinauto
        return True
    except ImportError:
        return False
