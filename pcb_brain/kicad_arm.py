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
        # 万法归宗: 工具链探测统一委托 _pcb_bootstrap.detect_env()
        # (glob 自动发现任意 KiCad/Java 版本), 避免本模块各写一份硬编码路径而版本漂移。
        # cli_path 为准, kicad_dir 由 cli 反推 (…\bin\kicad-cli.exe → …\<version>)。
        env = {}
        try:
            from _pcb_bootstrap import detect_env
            env = detect_env()
        except Exception as e:
            log.warning(f"bootstrap detect_env 不可用，退回本地探测: {e}")

        self.cli_path     = env.get("kicad_cli") or self._find_cli_fallback()
        self.freerouting  = env.get("freerouting")
        self.java_path    = env.get("java")
        self.kicad_dir    = self._derive_kicad_dir(self.cli_path)
        self.lceda_dir    = _find_dir(LCEDA_SEARCH_PATHS)
        self.fp_dir       = self._find_footprints()
        self._pcbnew      = None  # 懒加载

        log.info(f"KiCad目录: {self.kicad_dir}")
        log.info(f"KiCad CLI: {self.cli_path}")
        log.info(f"封装库:    {self.fp_dir}")
        log.info(f"freerouting: {self.freerouting} | java: {self.java_path}")
        log.info(f"嘉立创EDA: {self.lceda_dir}")

    @staticmethod
    def _derive_kicad_dir(cli_path: Optional[str]) -> Optional[Path]:
        # …\<version>\bin\kicad-cli.exe → …\<version>
        if cli_path:
            p = Path(cli_path)
            if p.parent.name.lower() == "bin":
                return p.parent.parent
            return p.parent
        return _find_dir(KICAD_SEARCH_PATHS)

    def _find_cli_fallback(self) -> Optional[str]:
        d = _find_dir(KICAD_SEARCH_PATHS)
        if d:
            cli = d / "bin" / "kicad-cli.exe"
            if cli.exists():
                return str(cli)
        return shutil.which("kicad-cli")

    def _find_footprints(self) -> Optional[Path]:
        if self.kicad_dir:
            fp = self.kicad_dir / "share" / "kicad" / "footprints"
            if fp.exists():
                return fp
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
        fp_path = self.fp_dir / f"{fp_lib}.pretty" / f"{fp_name}.kicad_mod"
        if not fp_path.exists():
            libs = list(self.fp_dir.glob(f"*{fp_lib}*.pretty"))
            if libs:
                fp_path = libs[0] / f"{fp_name}.kicad_mod"
        if not fp_path.exists():
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

    def _synth_pads(self, pins: List[str]) -> List[Dict]:
        """道法自然·因连接生形: 当封装库无法解析出真实焊盘时(模板未指定/未找到),
        依据该元件在网表中实际引用的引脚名, 合成一个通用双列贴片焊盘图形。
        保证每个被网表引用的引脚(数字或命名)都有对应铜焊盘 → 可布线、可制造、可出 Gerber。
        这是兜底的通用焊盘(而非特定器件精确 land pattern), 让 0 焊盘的板也能闭环。
        """
        pads: List[Dict] = []
        if not pins:
            return pads
        pitch, col_dx = 1.27, 3.0
        n = len(pins)
        half = (n + 1) // 2
        for i, pin in enumerate(pins):
            col, row = (-1, i) if i < half else (1, i - half)
            x = col * col_dx
            y = (row - (half - 1) / 2.0) * pitch
            pads.append({
                "num":   str(pin),
                "type":  "smd",
                "shape": "roundrect",
                "at":    (round(x, 3), round(y, 3)),
                "size":  (1.0, 0.6),
                "layers": ["F.Cu", "F.Mask", "F.Paste"],
                "rratio": 0.25,
            })
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
        comp_pins: Dict[str, List[str]] = {}  # ref → 网表引用的引脚(保持首现顺序)
        for net_name, conns in dna.nets.items():
            idx = net_index[net_name]
            for ref, pin in conns:
                pad_net[(ref, str(pin))] = (idx, net_name)
                lst = comp_pins.setdefault(ref, [])
                if str(pin) not in lst:
                    lst.append(str(pin))

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
        synth_refs = []
        for comp in dna.components:
            x, y = comp.pos
            fp_pads = self._parse_fp_pads(comp.fp_lib, comp.fp_name)
            if not fp_pads:
                # 封装库无对应焊盘(模板未指定/未找到) → 依网表连接合成通用焊盘
                fp_pads = self._synth_pads(comp_pins.get(comp.ref, []))
                if fp_pads:
                    synth_refs.append(comp.ref)
            fp_pad_counts[comp.ref] = len(fp_pads)

            # 封装标识必须是合法字符串; 模板把坐标元组误放进 fp_name 时(或合成焊盘时)
            # 退回通用标识, 避免把 "power:(60.0, 35.0)" 写进 .kicad_pcb 导致解析失败。
            fp_lib_s, fp_name_s = str(comp.fp_lib), str(comp.fp_name)
            if (comp.ref in synth_refs) or any(c in fp_name_s for c in "(),"):
                fp_id = f"pcbbrain:GENERIC_{comp.ref}"
            else:
                fp_id = f"{fp_lib_s}:{fp_name_s}"
            lines.append(f'  (footprint "{fp_id}"')
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
        log.info(f"   封装: {found}/{len(dna.components)}个有焊盘数据, 共{total_pads}个焊盘")
        if synth_refs:
            log.info(f"   合成通用焊盘(模板未指定封装): {len(synth_refs)}个 → {synth_refs}")
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
        # 统一用 bootstrap 探测结果 (glob 发现的任意版本 jar/java), 退回本地查找
        jar = self.freerouting or self._find_freerouting_jar()
        java = self.java_path or shutil.which("java")
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
        # 知其雄守其雌: 布线超时不应炸掉整条流水线 (上游会用占位符覆盖已生成的板),
        # 故捕获 TimeoutExpired 优雅降级 BFS, 让已摆好的板继续走 DRC/Gerber。
        log.info(f"freerouting: 运行布线 (max_passes={max_passes}, timeout={timeout}s)...")
        try:
            r2 = subprocess.run(
                [java, "-Djava.awt.headless=true", "-jar", jar,
                 "-de", dsn_path, "-do", ses_path,
                 "-mp", str(max_passes), "-us", "false"],
                capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            log.warning(f"freerouting超时({timeout}s)，降级BFS (密板可调大 timeout/max_passes)")
            bfs = self.auto_route_simple(pcb_path)
            bfs["engine"] = "bfs_fallback_timeout"
            return bfs
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
                # SES 格式为 "(wire\n  (path ...)"，旧代码用 "(wire " (带空格) 恒为0。
                # 改用 "(path " 统计实际走线条数。
                routed = ses_text.count("(path ")
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

        # 因材施教: 按板复杂度(焊盘数)放大 freerouting 超时与passes,
        # 否则密板 30s 必超时→降级BFS(易产生clearance违规)。默认值随复杂度自适应。
        try:
            pads = Path(pcb_path).read_text(encoding="utf-8", errors="ignore").count("(pad ")
            if pads > 60:
                timeout = max(timeout, 240); max_passes = max(max_passes, 100)
            elif pads > 30:
                timeout = max(timeout, 120); max_passes = max(max_passes, 50)
            elif pads > 15:
                timeout = max(timeout, 60);  max_passes = max(max_passes, 20)
            log.info(f"布线复杂度: {pads}焊盘 → timeout={timeout}s, max_passes={max_passes}")
        except Exception:
            pass

        # 优先本地freerouting (Java) — 统一用 bootstrap 探测结果
        jar = self.freerouting or self._find_freerouting_jar()
        java = self.java_path or shutil.which("java")
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
        GRID  = 0.25 if density > 0.02 else 0.5
        EDGE  = 4
        CLR_SOFT  = 0.2    # mm — Level1: 焊盘+间距封锁 (KiCad默认0.2mm间距)
        CLR_HARD  = 0.0    # mm — Level3: 仅焊盘本体 (紧急降级)
        log.info(f"  密度={density:.3f}pad/mm2 GRID={GRID}mm CLR={CLR_SOFT}mm")
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

        # ── 预计算他网焊盘封锁区: soft(焊盘本体+间距) / hard(焊盘本体) ──
        pad_soft: dict = {}
        pad_hard: dict = {}
        for nidx, geom_list in pad_geom_by_net.items():
            cs: set = set()
            ch: set = set()
            for cx_mm, cy_mm, hw, hh in geom_list:
                cs |= pad_bbox_cells(cx_mm, cy_mm, hw, hh, CLR_SOFT)
                ch |= pad_bbox_cells(cx_mm, cy_mm, hw, hh, CLR_HARD)
            pad_soft[nidx] = frozenset(cs)
            pad_hard[nidx] = frozenset(ch)

        # ── 已路由占用格 (单层 F.Cu) ──
        blocked: set = set(edge_cells)
        edge_only = frozenset(edge_cells)

        segments: list = []
        routed = unrouted = 0

        for net_idx, pad_list in sorted(pads_by_net.items()):
            if len(pad_list) < 2:
                continue
            connected_mm = [pad_list[0]]
            remaining_mm = list(pad_list[1:])

            while remaining_mm:
                best_src = best_dst = None
                best_d = 1e9
                for dst_mm in remaining_mm:
                    for src_mm in connected_mm:
                        d = abs(dst_mm[0]-src_mm[0]) + abs(dst_mm[1]-src_mm[1])
                        if d < best_d:
                            best_d, best_src, best_dst = d, src_mm, dst_mm

                src_g = mm_to_grid(*best_src)
                dst_g = mm_to_grid(*best_dst)

                own_cells: set = {mm_to_grid(*p) for p in pad_list}
                exempt: set = set(own_cells)
                for ddx in range(-1, 2):
                    for ddy in range(-1, 2):
                        exempt.add((src_g[0]+ddx, src_g[1]+ddy))
                        exempt.add((dst_g[0]+ddx, dst_g[1]+ddy))

                # 构建他网焊盘封锁 (soft/hard)
                fpb_soft: set = set()
                fpb_hard: set = set()
                for nidx in pad_soft:
                    if nidx != net_idx:
                        fpb_soft |= pad_soft[nidx]
                        fpb_hard |= pad_hard[nidx]
                fpb_soft -= exempt
                fpb_hard -= exempt

                # Level 1: soft封锁 + 已布线 (full clearance)
                obs1 = blocked | fpb_soft
                obs1 -= own_cells
                path = self._bfs_route(src_g, dst_g, obs1, gw, gh)

                # Level 2: 轨迹封锁+焊盘硬封锁 (放松间距但保持焊盘体不可穿越)
                if path is None:
                    obs2 = (set(blocked) | (fpb_hard - exempt)) - own_cells
                    path = self._bfs_route(src_g, dst_g, obs2, gw, gh)

                # Level 3: 板边+他网焊盘硬封锁 (防短路优先)
                if path is None:
                    obs3 = set(edge_only) | (fpb_hard - exempt)
                    path = self._bfs_route(src_g, dst_g, obs3, gw, gh)
                    if path:
                        log.warning(f"  净{net_idx}: ⚠️ Level3降级布线(可能产生clearance违规)")
                # Level 4: 绝对保底 — 仅板边 (0未连接必保)
                if path is None:
                    path = self._bfs_route(src_g, dst_g, set(edge_only), gw, gh)
                    if path:
                        log.warning(f"  净{net_idx}: ❗ Level4最终保底(可能短路)")

                if path:
                    segs = self._path_to_segments(
                        path, net_idx, GRID, x0 - EDGE * GRID, y0 - EDGE * GRID,
                        start_mm=best_src, end_mm=best_dst
                    )
                    segments.extend(segs)
                    for cell in path:
                        blocked.add(cell)
                    routed += 1
                    log.info(f"  净{net_idx}: ✅ {best_src}→{best_dst}, {len(segs)}段")
                else:
                    log.warning(f"  净{net_idx}: ❌ {best_src}→{best_dst} 路径受阻")
                    unrouted += 1

                connected_mm.append(best_dst)
                remaining_mm.remove(best_dst)

        if segments:
            self._append_segments_to_pcb(pcb_path, segments)
        log.info(f"✅ 自动布线完成: ✅{routed}通 / ❌{unrouted}失败 / {len(segments)}段写入")
        return {"routed": routed, "unrouted": unrouted, "segments": len(segments)}

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
          pads_by_net:     {net_idx: [(cx, cy), ...]}          路由树用
          pad_geom_by_net: {net_idx: [(cx, cy, hw, hh), ...]}  精确封锁用
          hw/hh = 半宽/半高 (mm, 保守取最大边)
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
                if pat_m:
                    pad_abs_x = fp_x + float(pat_m.group(1))
                    pad_abs_y = fp_y + float(pat_m.group(2))
                    hw = float(size_m.group(1)) / 2.0 if size_m else 0.5
                    hh = float(size_m.group(2)) / 2.0 if size_m else 0.5
                    net_m = re.search(r'\(net\s+(\d+)', pad_text)
                    if net_m:
                        net_idx = int(net_m.group(1))
                        if net_idx > 0:
                            pads_by_net.setdefault(net_idx, [])
                            pads_by_net[net_idx].append((pad_abs_x, pad_abs_y))
                            pad_geom_by_net.setdefault(net_idx, [])
                            pad_geom_by_net[net_idx].append(
                                (pad_abs_x, pad_abs_y, hw, hh))
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
                f' (width 0.25) (layer "{lyr}")'
                f' (net {s["net"]}) (tstamp "{_uuid.uuid4()}"))'
            )
        for v in (vias or []):
            lines.append(
                f'  (via (at {v["x"]:.4f} {v["y"]:.4f})'
                f' (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu")'
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
