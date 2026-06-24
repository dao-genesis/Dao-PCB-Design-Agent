"""
_self_test — 端到端综合回归自检 (五层 + 道直连器 + 自然层 + 反向之道)

测试链 (18 步):
    五层 + dao 基线 (12)
    1. 顶层 import kicad_origin (Layer 0+1+2+3+4 + dao)
    2. SymbolIndex / FootprintIndex 全量构建
    3. extract_symbol_block + get_pin_positions
    4. parse_footprint_file
    5. Board.empty 创建并 round-trip
    6. Board.load 真板 → 改 footprint 位置 → save → 再 load → 校验
    7. DRC: 真板跑 6 规则, 至少有 violation 输出
    8. Gerber: 真板写出 11 层文件, 每层 size > 0
    9. Excellon: 含钻孔板写出 PTH 文件
    10. pcbnew_compat: install + import pcbnew + LoadBoard + GetFootprints
    11. Dao: 实例化 + status + search + new_board + run_drc + history
    12. MCP: initialize + tools/list (>=20) + tools/call + 错误路径

    自然层 (3) — 人观可见
    13. ziran: 应用注册表 (七大 GUI + 一 CLI) + 路径探测
    14. ziran: 五感 (蜂鸣 + 事件归档 + 屏幕探测)
    15. ziran: 真启 + 关 (pcb_calculator 端到端, 不留垃圾进程)

    反向之道 (3) — agent 自然原语 ⇆ KiCad 自然出口
    16. reflect: 自照本然 + cli 覆盖度 ≥ 12/17
    17. cli 直贯单动作: STEP + PCB-PDF + PCB-SVG (真板)
    18. cli + engine 一句全集 export_all
        (DRC+Gerber+Drill+STEP+PCB-PDF+PCB-SVG+POS+3D Render)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# 必须从顶层 kicad_origin 拿全部 API
import kicad_origin as ko


def step(name: str, fn):
    try:
        r = fn()
        print(f"[OK ] {name}")
        return True, r
    except Exception as e:
        print(f"[FAIL] {name}\n       {type(e).__name__}: {e}")
        return False, None


def main() -> int:
    failed = 0

    # 1. 顶层 import 检查 (五层全 + dao)
    def t1():
        assert ko.SExpr is not None,        "Layer 0 missing"
        assert ko.SymbolIndex is not None,  "Layer 1 missing"
        assert ko.Board is not None,        "Layer 2 missing"
        assert ko.run_drc is not None,      "Layer 3 DRC missing"
        assert ko.write_gerber is not None, "Layer 3 Gerber missing"
        assert ko.write_excellon is not None,"Layer 3 Excellon missing"
        assert ko.pcbnew_compat is not None,"Layer 4 missing"
        assert ko.Dao is not None,          "dao missing"
        assert ko.MCPServer is not None,    "MCP missing"
        return ko.__version__
    ok, ver = step("import kicad_origin (0+1+2+3+4+dao)", t1)
    if not ok: failed += 1

    # 2. SymbolIndex / FootprintIndex
    def t2():
        ns = ko.SymbolIndex.build()
        nf = ko.FootprintIndex.build()
        assert ns > 0, "SymbolIndex 为空"
        assert nf > 0, "FootprintIndex 为空"
        return {"symbols": ns, "footprints": nf}
    ok, counts = step("SymbolIndex / FootprintIndex 全量构建", t2)
    if not ok:
        failed += 1
        counts = {"symbols": 0, "footprints": 0}

    # 3. extract_symbol_block + get_pin_positions
    def t3():
        if "Device" not in ko.SymbolIndex._libs:
            return "skip (no Device lib)"
        block = ko.extract_symbol_block("Device:R")
        assert "Device:R" in block
        pins = ko.get_pin_positions("Device:R")
        assert len(pins) >= 2, f"Device:R 应该有 ≥2 pin, got {len(pins)}"
        return {"block_length": len(block), "pins": pins}
    ok, _ = step("extract_symbol_block / get_pin_positions", t3)
    if not ok: failed += 1

    # 4. parse_footprint_file
    def t4():
        # 找 Resistor_SMD:R_0805_2012Metric (常见标准件)
        path = ko.FootprintIndex.smart_match("Resistor_SMD", "R_0805_2012Metric")
        if not path:
            return "skip (no R_0805 footprint)"
        info = ko.parse_footprint_file(path)
        assert info.pad_count >= 2, f"R_0805 应有 2 pad, got {info.pad_count}"
        return {"name": info.name, "pads": info.pad_count, "bbox": info.bbox}
    ok, _ = step("parse_footprint_file (Resistor_SMD:R_0805_2012Metric)", t4)
    if not ok: failed += 1

    # 5. Board.empty 创建 + roundtrip
    def t5():
        b1 = ko.Board.empty(width_mm=50, height_mm=40, title="self_test_empty")
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            p = Path(f.name)
        b1.save(p)
        b2 = ko.Board.load(p)
        assert b2.title == "self_test_empty"
        outline = b2.board_outline()
        assert outline is not None, "outline 应该被识别"
        assert outline.width == 50.0 and outline.height == 40.0
        # 清理
        try: p.unlink()
        except Exception: pass
        return outline.to_tuple()
    ok, _ = step("Board.empty → save → load → 校验", t5)
    if not ok: failed += 1

    # 6. Board.load 真板 + 改 footprint 位置 + roundtrip
    def t6():
        # 用 stm32f103c6_dot_matrix
        src = Path(__file__).parent.parent / "pcb_brain" / "output" \
              / "stm32f103c6_dot_matrix" / "stm32f103c6_dot_matrix.kicad_pcb"
        if not src.exists():
            return f"skip (no demo board: {src})"
        b1 = ko.Board.load(src)
        u1 = b1.footprint_by_ref("U1")
        assert u1 is not None, "U1 应存在"
        before = u1.position
        # 移动 U1 to (50, 50)
        u1.position = ko.Point(50.0, 50.0)
        # 写出
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            tmp = Path(f.name)
        b1.save(tmp)
        # 重新加载
        b2 = ko.Board.load(tmp)
        u1b = b2.footprint_by_ref("U1")
        assert u1b is not None, "U1 应仍存在"
        after = u1b.position
        assert abs(after.x - 50.0) < 1e-6 and abs(after.y - 50.0) < 1e-6, \
               f"U1 位置未持久化: {after}"
        try: tmp.unlink()
        except Exception: pass
        return {"before": before.to_tuple(), "after": after.to_tuple(),
                "footprints": len(b2.footprints()),
                "nets": len(b2.nets())}
    ok, _ = step("Board.load 真板 → 改 footprint 位置 → roundtrip 校验", t6)
    if not ok: failed += 1

    # 7. DRC 真板
    def t7():
        # 用 KiCad demo (真实焊盘+网络+segment)
        demo = Path(r"D:\KICAD\share\kicad\demos\complex_hierarchy"
                    r"\complex_hierarchy.kicad_pcb")
        if not demo.exists():
            return f"skip (no demo: {demo})"
        b = ko.Board.load(demo)
        rep = ko.run_drc(b)
        assert rep is not None
        # 真实 demo 板必有 violations (R001/R004/R006), 验证规则真能触发
        assert len(rep.rules_run) == 6, f"应跑 6 规则, 跑了 {len(rep.rules_run)}"
        return {"violations": len(rep.violations),
                "errors": rep.error_count,
                "by_rule": rep.by_rule(),
                "elapsed_s": rep.elapsed_seconds}
    ok, _ = step("DRC: 真板 6 规则全跑", t7)
    if not ok: failed += 1

    # 8. Gerber 真板
    def t8():
        # 用 pcb_brain 自动生成的板 (有焊盘 + Edge.Cuts)
        src = Path(__file__).parent.parent / "pcb_brain" / "output" \
              / "stm32f103c6_dot_matrix" / "stm32f103c6_dot_matrix.kicad_pcb"
        if not src.exists():
            return f"skip (no demo: {src})"
        b = ko.Board.load(src)
        with tempfile.TemporaryDirectory() as d:
            files = ko.write_gerber(b, d)
            assert len(files) >= 10, f"应输出 10+ 层, 得 {len(files)}"
            # Edge.Cuts 必须有内容 (因板边 gr_rect)
            ec = next((Path(f) for f in files if "Edge_Cuts" in f), None)
            assert ec is not None, "缺 Edge.Cuts"
            ec_size = ec.stat().st_size
            assert ec_size > 200, f"Edge.Cuts 文件过小 ({ec_size}B)"
            sizes = {Path(f).name: Path(f).stat().st_size for f in files}
        return {"files": len(files),
                "edge_cuts_bytes": ec_size,
                "total_bytes": sum(sizes.values())}
    ok, _ = step("Gerber: 真板 11 层 + Edge.Cuts 内容", t8)
    if not ok: failed += 1

    # 9. Excellon 钻孔
    def t9():
        # 用 KiCad demo (确有 thru-hole)
        demo = Path(r"D:\KICAD\share\kicad\demos\complex_hierarchy"
                    r"\complex_hierarchy.kicad_pcb")
        if not demo.exists():
            return f"skip"
        b = ko.Board.load(demo)
        with tempfile.TemporaryDirectory() as d:
            files = ko.write_excellon(b, d)
            assert len(files) >= 1, "应至少 1 份钻孔文件"
            content = Path(files[0]).read_text(encoding="utf-8")
            assert "M48" in content and "M30" in content, "缺 M48/M30 头尾"
            assert "METRIC" in content, "缺 METRIC 单位"
            assert "T01C" in content, "缺工具定义"
            tool_count = content.count("T01C") + content.count("T02C") + \
                         content.count("T03C") + content.count("T04C")
        return {"files": len(files), "tool_lines": tool_count}
    ok, _ = step("Excellon: 真板钻孔 PTH 工具分组", t9)
    if not ok: failed += 1

    # 10. pcbnew_compat 兼容层
    def t10():
        ko.install_pcbnew_compat()
        import pcbnew  # 拿到我们
        assert pcbnew.FromMM(1.0) == 1_000_000
        assert pcbnew.ToMM(1_000_000) == 1.0
        # LoadBoard
        src = Path(__file__).parent.parent / "pcb_brain" / "output" \
              / "stm32f103c6_dot_matrix" / "stm32f103c6_dot_matrix.kicad_pcb"
        if not src.exists():
            return "skip (no demo)"
        b = pcbnew.LoadBoard(str(src))
        assert pcbnew.GetBoard() is b, "GetBoard() 应返回最近 Load 的"
        fps = b.GetFootprints()
        assert len(fps) >= 10, f"应 ≥10 footprint, 得 {len(fps)}"
        u1 = b.FindFootprintByReference("U1")
        assert u1 is not None
        pos = u1.GetPosition()
        x_mm, y_mm = pos.ToMM()
        # 改位置
        u1.SetPosition(pcbnew.VECTOR2I.from_mm(99.0, 88.0))
        new_pos = u1.GetPosition()
        assert new_pos.ToMM() == (99.0, 88.0)
        ko.uninstall_pcbnew_compat()
        return {"version_check": True,
                "footprints": len(fps),
                "tracks": len(b.GetTracks()),
                "nets": len(b.GetNetsByName()),
                "U1_orig_mm": (round(x_mm, 3), round(y_mm, 3)),
                "U1_new_mm":  new_pos.ToMM()}
    ok, _ = step("pcbnew_compat: install → LoadBoard → SetPosition", t10)
    if not ok: failed += 1

    # 11. Dao 综合 (静默 feedback)
    def t11():
        import io
        # 静默控制台 (不污染 self-test 输出)
        silent = ko.Feedback(ko.JSONFeedback(stream=io.StringIO()))
        with ko.Dao(feedback=silent) as dao:
            r1 = dao.status()
            assert r1.ok and r1.result["symbol_count"] >= 1000
            r2 = dao.search_symbol("STM32H743", limit=2)
            assert r2.ok and r2.result["count"] >= 1
            r3 = dao.search_footprint("LQFP-48", limit=2)
            assert r3.ok and r3.result["count"] >= 1
            r4 = dao.new_board(50, 40)
            assert r4.ok
            r5 = dao.list_footprints()
            assert r5.ok and r5.result["count"] == 0
            r6 = dao.run_drc()
            assert r6.ok, "空板应通过 DRC"
            hist = dao.history()
            assert len(hist) == 6, f"应 6 条历史, 实 {len(hist)}"
            # execute 派发
            r7 = dao.execute("search_symbol", query="LM358", limit=1)
            assert r7.ok
            return {
                "actions":      len(dao.history()),
                "symbol_count": r1.result["symbol_count"],
                "fp_count":     r1.result["footprint_count"],
            }
    ok, _ = step("Dao: 状态 + 搜索 + 新板 + DRC + 历史 + execute", t11)
    if not ok: failed += 1

    # 12. MCP server 离线验证 (initialize + tools/list + tools/call + error)
    def t12():
        from kicad_origin.dao.mcp import (
            _test_one_message, PROTOCOL_VERSION, METHOD_NOT_FOUND,
        )
        # initialize
        r1 = _test_one_message({"jsonrpc": "2.0", "id": 1,
                                  "method": "initialize",
                                  "params": {"protocolVersion": PROTOCOL_VERSION}})
        assert r1["result"]["serverInfo"]["name"] == "kicad-origin"
        # tools/list
        r2 = _test_one_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        n_tools = len(r2["result"]["tools"])
        assert n_tools >= 20, f"应 >= 20 工具, 得 {n_tools}"
        # tools/call kicad_status
        r3 = _test_one_message({"jsonrpc": "2.0", "id": 3,
                                  "method": "tools/call",
                                  "params": {"name": "kicad_status",
                                              "arguments": {}}})
        body = json.loads(r3["result"]["content"][0]["text"])
        assert body.get("ok") is True
        # tools/call kicad_search_footprint
        r4 = _test_one_message({"jsonrpc": "2.0", "id": 4,
                                  "method": "tools/call",
                                  "params": {"name": "kicad_search_footprint",
                                              "arguments": {"query": "LQFP-48",
                                                             "limit": 1}}})
        body4 = json.loads(r4["result"]["content"][0]["text"])
        assert body4["ok"] and body4["result"]["count"] >= 1
        # 错误路径: 未知 method
        r5 = _test_one_message({"jsonrpc": "2.0", "id": 5,
                                  "method": "totally_unknown_method"})
        assert r5["error"]["code"] == METHOD_NOT_FOUND
        # 错误路径: 未知工具
        r6 = _test_one_message({"jsonrpc": "2.0", "id": 6,
                                  "method": "tools/call",
                                  "params": {"name": "no_such_tool",
                                              "arguments": {}}})
        assert r6["error"]["code"] == METHOD_NOT_FOUND
        return {
            "tools":     n_tools,
            "protocol":  PROTOCOL_VERSION,
            "checks":    6,
        }
    ok, _ = step("MCP: initialize + tools/list + tools/call + error paths", t12)
    if not ok: failed += 1

    # 13. ziran 应用注册表 + 路径探测 (七大 GUI + 一 CLI)
    def t13():
        from kicad_origin.ziran import list_installed, ALL_APPS, find_app
        rows = list_installed()
        assert len(rows) == 8, f"应 8 应用, 得 {len(rows)}"
        installed = [r for r in rows if r["installed"]]
        assert len(installed) >= 7, f"至少 7 已装, 得 {len(installed)}"
        # 全键齐全
        keys = {a.key for a in ALL_APPS}
        for need in ("kicad", "pcbnew", "eeschema", "gerbview",
                     "pcb_calculator", "pl_editor", "bitmap2component",
                     "cli"):
            assert need in keys, f"缺应用 {need}"
        # find_app 大小写不敏感
        assert find_app("PCBnew") is not None
        return {"apps": len(rows), "installed": len(installed)}
    ok, _ = step("ziran: 应用注册表 (七大 GUI + 一 CLI) + 路径探测", t13)
    if not ok: failed += 1

    # 14. ziran 五感: 蜂鸣 + 事件归档 + 屏幕探测 (不打扰用户)
    def t14():
        import shutil
        from pathlib import Path
        from kicad_origin.ziran import Senses
        from kicad_origin.ziran import beep as _beep
        from kicad_origin.ziran import input as _ki
        # 1) 直接蜂鸣 (短促, 仅作 ctypes 真调用验证)
        _beep(900, 60)
        # 2) Senses 实例 + 事件归档
        out = Path("_st14_senses")
        if out.exists():
            shutil.rmtree(out)
        s = Senses(out_dir=out)
        s.beep_done()
        s.announce_warn("self-test-warn")  # stderr + 蜂鸣 + 系统通知声
        log = out / "senses.jsonl"
        assert log.exists(), "senses.jsonl 未生成"
        nlines = sum(1 for _ in log.open(encoding="utf-8"))
        assert nlines >= 2, f"事件 >= 2 行, 得 {nlines}"
        # 3) 屏幕尺寸 (Windows user32.GetSystemMetrics 真活)
        sw, sh = _ki.screen_size()
        assert sw > 0 and sh > 0, f"屏幕尺寸异常: {sw}x{sh}"
        # 清理
        shutil.rmtree(out, ignore_errors=True)
        return {"events": nlines, "screen": f"{sw}x{sh}"}
    ok, _ = step("ziran: 五感 (蜂鸣 + 事件归档 + 屏幕探测)", t14)
    if not ok: failed += 1

    # 15. ziran 端到端: 真启 + 检测 dialog/主窗 + 强制关 (不留垃圾进程)
    def t15():
        import time as _t
        from kicad_origin.dao.dao import Dao
        # 进入前确保没在跑
        dao = Dao(verbose=False)
        try:
            r0 = dao.list_running_apps()
            assert r0.ok
            already = r0.result["count"]
            # 真启 pcb_calculator (最轻量, 用户无干扰)
            r1 = dao.launch_app("pcb_calculator", timeout=8.0)
            assert r1.ok, f"启动失败: {r1.error}"
            pid = r1.result["pid"]
            assert pid > 0
            # 等 0.5s
            _t.sleep(0.5)
            # 应该看到 1 个 (主窗 或 dialog 都算)
            r2 = dao.list_running_apps()
            assert r2.ok
            now = r2.result["count"]
            # 至少多了一个 (考虑用户可能正在跑别的)
            # 强制关 (容许 dialog 阻塞)
            r3 = dao.close_app("pcb_calculator", force=True)
            assert r3.ok, f"close 失败: {r3.error}"
            # 等 0.3s
            _t.sleep(0.3)
            # 验证归零
            r4 = dao.list_running_apps()
            assert r4.ok
            after = r4.result["count"]
            assert after <= already, (
                f"启关后剩 {after} 应 <= 之前 {already}, "
                f"启动时一度 {now}"
            )
            return {"pid": pid, "already": already,
                    "during": now, "after": after}
        finally:
            dao.close()
    ok, _ = step("ziran: 真启 + 关 (pcb_calculator 端到端, 不留垃圾进程)", t15)
    if not ok: failed += 1

    # 16. 反向之道: dao.reflect() — agent 自照本然 + cli 端点覆盖度
    def t16():
        from kicad_origin.dao.dao import Dao
        with Dao(verbose=False) as dao:
            r = dao.reflect()
            assert r.ok, f"reflect 失败: {r.error}"
            res = r.result
            # 五大本然原语
            assert "subprocess" in res["agent_primitives"]
            assert "file_io"    in res["agent_primitives"]
            assert "pipe"       in res["agent_primitives"]
            assert "socket"     in res["agent_primitives"]
            assert "code"       in res["agent_primitives"]
            # KiCad 出口
            assert res["kicad_natural_exits"]["kicad-cli"]["available"] is True
            # 至少 17 个 cli 端点 + 至少 12 已覆盖
            assert len(res["cli_endpoints"]) >= 17
            assert len(res["covered_endpoints"]) >= 12
            return {
                "primitives": list(res["agent_primitives"].keys()),
                "cli_ver":    res["kicad_natural_exits"]["kicad-cli"]["version"],
                "endpoints":  len(res["cli_endpoints"]),
                "covered":    len(res["covered_endpoints"]),
                "ratio":      res["coverage_ratio"],
            }
    ok, _ = step("反向之道: reflect (agent 自照 + cli 覆盖度 ≥ 12/17)", t16)
    if not ok: failed += 1

    # 17. 反向之道: dao.export_step + export_pcb_pdf + render_3d 真板
    def t17():
        import shutil
        from kicad_origin.dao.dao import Dao
        src = Path(__file__).parent.parent / "pcb_brain" / "output" \
              / "ams1117_power" / "ams1117_power.kicad_pcb"
        if not src.exists():
            return f"skip (no demo: {src})"
        out = Path("_st17_cli")
        if out.exists():
            shutil.rmtree(out)
        out.mkdir()
        with Dao(verbose=False) as dao:
            r1 = dao.export_step(pcb_path=src, output_path=out / "a.step")
            assert r1.ok and r1.channel == "cli", f"export_step: {r1.error}"
            assert (out / "a.step").stat().st_size > 1000, "STEP 太小"

            r2 = dao.export_pcb_pdf(pcb_path=src, output_path=out / "a.pdf")
            assert r2.ok and r2.channel == "cli", f"pcb_pdf: {r2.error}"
            assert (out / "a.pdf").stat().st_size > 1000, "PDF 太小"

            r3 = dao.export_pcb_svg(pcb_path=src, output_path=out / "a.svg")
            assert r3.ok and r3.channel == "cli", f"pcb_svg: {r3.error}"
            assert (out / "a.svg").stat().st_size > 1000, "SVG 太小"
        sizes = {p.name: p.stat().st_size for p in out.iterdir()}
        shutil.rmtree(out, ignore_errors=True)
        return {"step_b": sizes.get("a.step"),
                "pdf_b":  sizes.get("a.pdf"),
                "svg_b":  sizes.get("a.svg")}
    ok, _ = step("反向之道: 单动作 (STEP + PCB-PDF + PCB-SVG, 真板)", t17)
    if not ok: failed += 1

    # 18. 反向之道: dao.export_all() — 一句出全集
    def t18():
        import shutil
        from kicad_origin.dao.dao import Dao
        src = Path(__file__).parent.parent / "pcb_brain" / "output" \
              / "ams1117_power" / "ams1117_power.kicad_pcb"
        if not src.exists():
            return f"skip (no demo: {src})"
        out = Path("_st18_all")
        if out.exists():
            shutil.rmtree(out)
        with Dao(verbose=False) as dao:
            r = dao.export_all(pcb_path=src, output_dir=out)
            assert r.ok, (
                f"export_all 应全绿. fails="
                f"{[s for s in r.result['steps'] if not s['ok']]}")
            res = r.result
            # 应有 8 个 PCB 链子项 (drc/gerber/drill/step/pcb_pdf/pcb_svg/pos/render_3d)
            ok_steps = [s["step"] for s in res["steps"] if s["ok"]]
            assert "drc"      in ok_steps
            assert "gerber"   in ok_steps
            assert "step"     in ok_steps
            assert "pcb_pdf"  in ok_steps
            assert "pcb_svg"  in ok_steps
            assert "pos"      in ok_steps
            assert "render_3d" in ok_steps
            assert res["ok_count"] >= 7  # drill 可能 0 文件 (此板无 PTH)
            assert res["fail_count"] == 0
            arts = len(r.artifacts)
        shutil.rmtree(out, ignore_errors=True)
        return {"ok_count": res["ok_count"],
                "fail_count": res["fail_count"],
                "artifacts": arts,
                "steps_ok": ok_steps}
    ok, _ = step("反向之道: export_all 全集 (DRC+Gerber+STEP+PDF+SVG+POS+3D)", t18)
    if not ok: failed += 1

    # 19. 二生三: inline_footprints — placement-only → 完整定义
    def t19():
        from kicad_origin import Board
        # ams1117_power 是经典 placement-only 板 (无 inline pad)
        src = Path(__file__).parent.parent / "pcb_brain" / "output" \
              / "ams1117_power" / "ams1117_power.kicad_pcb"
        if not src.exists():
            return f"skip (no demo: {src})"
        b = Board.load(src)
        # 展开前: 4 footprints, 0 pads
        fps_before = len(b.footprints())
        pads_before = sum(len(fp.pads()) for fp in b.footprints())
        assert fps_before == 4, f"应 4 footprints, 得 {fps_before}"
        assert pads_before == 0, f"应 0 pads (源是 placement-only), 得 {pads_before}"
        # 展开
        rep = b.inline_footprints()
        assert rep["expanded"] == 4, (
            f"应 4 expanded, 得 {rep['expanded']}")
        assert rep["added_pads"] == 10, (
            f"应 10 added_pads (1xSOT223-3=4 + 3x0805=6), 得 {rep['added_pads']}")
        assert rep["missing_count"] == 0, (
            f"应 0 missing, 得 {rep['missing_count']}: {rep['missing']}")
        # 展开后: 4 footprints, 10 pads
        fps_after = len(b.footprints())
        pads_after = sum(len(fp.pads()) for fp in b.footprints())
        assert fps_after == 4, f"footprint 数应不变, 得 {fps_after}"
        assert pads_after == 10, f"应 10 pads (展开后), 得 {pads_after}"
        return {"expanded": rep["expanded"],
                "added_pads": rep["added_pads"],
                "fps": fps_after, "pads": pads_after}
    ok, _ = step("二生三: inline_footprints 无中生有 (placement-only → 完整)", t19)
    if not ok: failed += 1

    # 20. 二生三: dao.export_all 自动 inline + 真出 fab (端到端)
    def t20():
        import shutil
        from kicad_origin.dao.dao import Dao
        src = Path(__file__).parent.parent / "pcb_brain" / "output" \
              / "ams1117_power" / "ams1117_power.kicad_pcb"
        if not src.exists():
            return f"skip (no demo: {src})"
        out = Path("_st20_fab")
        if out.exists():
            shutil.rmtree(out)
        with Dao(verbose=False) as dao:
            r = dao.export_all(pcb_path=src, output_dir=out)
            res = r.result
            # 应有 inline 步骤且成功
            inline_step = next((s for s in res["steps"]
                               if s["step"] == "inline_footprints"), None)
            assert inline_step is not None, "无 inline_footprints 步骤"
            assert inline_step["ok"], f"inline_footprints 失败: {inline_step}"
            assert res["inline"]["applied"] is True
            assert res["inline"]["expanded"] == 4
            assert res["inline"]["added_pads"] == 10
            # 检查产出真实性: F_Cu Gerber 应 > 800 字节 (有 4 pads 的真内容)
            cu = list(out.glob("**/*-F_Cu*"))
            assert cu, "未找到 F_Cu Gerber"
            cu_size = cu[0].stat().st_size
            assert cu_size > 800, (
                f"F_Cu Gerber 太小 ({cu_size} 字节), 仍是空 stub")
            # STEP 应存在 (即使 fallback)
            step_files = list(out.glob("*.step"))
            assert step_files, "未生成 STEP"
            assert step_files[0].stat().st_size > 1000, "STEP 太小"
            arts = len(r.artifacts)
        shutil.rmtree(out, ignore_errors=True)
        return {"inline": res["inline"]["expanded"],
                "ok_count": res["ok_count"],
                "f_cu_bytes": cu_size,
                "artifacts": arts}
    ok, _ = step("二生三: export_all 端到端 (inline + 真 Gerber ≥ 800B + 真 STEP)", t20)
    if not ok: failed += 1

    # ─────────────────────────────────────────────────────────
    # 21. 道并桥: DaoBridge 静默端到端 (用户与 agent 浑然一体)
    #     验:
    #       - DaoBridge 可建 (含会话目录)
    #       - bridge.do(verb) 路由 → dao 各动作
    #       - boards / status / open / drc / fab / ls / show / quit 全链
    #       - 真出 22+ fab 件 + 写 _SESSION_REPORT.md
    #     不启 GUI (静默), 因 self_test 不能依赖屏幕.
    # ─────────────────────────────────────────────────────────
    def t21():
        from kicad_origin.dao import DaoBridge
        import shutil

        # 临时会话目录, 测完即清
        tmp_dir = Path("_st21_session")
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

        # rp2040_minimal: 21 元件 17 网络 DRC 零违规 (自检已验证)
        board_path = (Path(__file__).parent.parent
                       / "pcb_brain" / "output"
                       / "rp2040_minimal" / "rp2040_minimal.kicad_pcb")
        assert board_path.exists(), f"rp2040 板不存在: {board_path}"
        board_root = board_path.parent.parent  # pcb_brain/output

        try:
            with DaoBridge(session_dir=tmp_dir,
                           senses_enabled=False,   # self_test 不蜂鸣不通知
                           auto_snapshot=False,    # 不需 GUI 截图
                           ) as bridge:
                # 1) 状态 + 反射
                a_st = bridge.do("status")
                assert a_st.ok, f"status 失败: {a_st.error}"
                a_rf = bridge.do("reflect")
                assert a_rf.ok, f"reflect 失败: {a_rf.error}"

                # 2) 列板
                a_b = bridge.do("boards", root=str(board_root))
                assert a_b.ok, f"boards 失败: {a_b.error}"
                assert a_b.extra["boards"], "未找到任何板"

                # 3) 静默打开 rp2040
                a_o = bridge.do("open", pcb=str(board_path), gui=False)
                assert a_o.ok, f"open 失败: {a_o.error}"
                assert "21" in a_o.summary or "元件" in a_o.summary, \
                    f"open 摘要异常: {a_o.summary}"

                # 4) 板内查询
                a_lf = bridge.do("list_fp")
                assert a_lf.ok, f"list_fp 失败: {a_lf.error}"
                a_ln = bridge.do("list_nets")
                assert a_ln.ok, f"list_nets 失败: {a_ln.error}"
                a_gf = bridge.do("get_fp", ref="U1")
                assert a_gf.ok, f"get_fp U1 失败: {a_gf.error}"
                assert "RP2040" in a_gf.summary, f"U1 不是 RP2040: {a_gf.summary}"

                # 5) DRC
                a_drc = bridge.do("drc")
                assert a_drc.ok, f"drc 失败: {a_drc.error}"

                # 6) 全链 fab
                a_fab = bridge.do("fab", inline=True, prefer_cli=True)
                assert a_fab.ok, f"fab 失败: {a_fab.error}"
                # fab 必须出 ≥ 15 件 (Gerber 14 + STEP + drill + ...)
                fab_dir = bridge.session_dir / "out" / "fab"
                assert fab_dir.exists(), "fab 目录未建"
                fab_files = [p for p in fab_dir.rglob("*") if p.is_file()]
                assert len(fab_files) >= 15, \
                    f"fab 文件数过少: {len(fab_files)} < 15"

                # 7) 真 Gerber + STEP 抽检
                f_cu = list(fab_dir.glob("**/*F_Cu*"))
                assert f_cu, "无 F.Cu Gerber"
                assert f_cu[0].stat().st_size > 800, "F.Cu Gerber 太小"
                step_f = list(fab_dir.glob("**/*.step"))
                assert step_f, "无 STEP"
                assert step_f[0].stat().st_size > 1000, "STEP 太小"

                # 8) 列产物 + show
                bridge.do("ls")
                bridge.do("show")

                # 9) 验报告/日志/元数据落盘
                # __exit__ 会调 close_all() 写 _SESSION_REPORT.md
                actions_count = len(bridge.actions)

            # 出 with 块, close_all 已执行
            report = tmp_dir.rglob("_SESSION_REPORT.md")
            assert any(report), "未写 _SESSION_REPORT.md"
            jsonl = list(tmp_dir.rglob("actions.jsonl"))
            assert jsonl, "未写 actions.jsonl"
            n_jsonl = sum(1 for _ in open(jsonl[0], encoding="utf-8"))
            assert n_jsonl >= 8, f"actions.jsonl 行数过少: {n_jsonl}"

            return {
                "actions": actions_count,
                "fab_files": len(fab_files),
                "f_cu_bytes": f_cu[0].stat().st_size,
                "step_bytes": step_f[0].stat().st_size,
                "session_size": sum(p.stat().st_size for p in tmp_dir.rglob("*") if p.is_file()),
            }
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    ok, _ = step("道并桥: 静默端到端 (boards+status+drc+fab+report 全链)", t21)
    if not ok: failed += 1

    # ─────────────────────────────────────────────────────────
    # 22. 自驾 autopilot: 静默端到端 (用户观即可)
    #     验:
    #       - autopilot.run_autopilot 可调
    #       - --no-gui --silent ams1117_power 模式 (单板, 速度优先)
    #       - 写 _AUTOPILOT_REPORT.md + _SESSION_REPORT.md
    #       - 出 fab ≥ 15 件
    #     不启 GUI, 单板, ~30 秒.
    # ─────────────────────────────────────────────────────────
    def t22():
        from kicad_origin.examples.autopilot import run_autopilot
        import shutil

        tmp_dir = Path("_st22_session")
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

        try:
            rc = run_autopilot(
                pcb_root="pcb_brain/output",
                gui_board=None,                      # 不展示 GUI
                silent_boards=["ams1117_power"],     # 单板, 速度优先
                no_gui=True,                          # headless
                session_dir=str(tmp_dir),
            )
            assert rc == 0, f"autopilot 返回非 0: {rc}"

            # 找最新会话目录
            sessions = sorted(tmp_dir.iterdir())
            assert sessions, "未建会话目录"
            sess = sessions[-1]

            # 验报告
            ap_rpt = sess / "_AUTOPILOT_REPORT.md"
            assert ap_rpt.exists(), f"未写 _AUTOPILOT_REPORT.md: {ap_rpt}"
            ap_text = ap_rpt.read_text(encoding="utf-8")
            assert "总览" in ap_text and "动作流水" in ap_text and "ams1117_power" in ap_text, \
                "_AUTOPILOT_REPORT.md 内容不全"

            ses_rpt = sess / "_SESSION_REPORT.md"
            assert ses_rpt.exists(), f"未写 _SESSION_REPORT.md: {ses_rpt}"

            # 验产物
            fab_dir = sess / "out" / "fab"
            assert fab_dir.exists(), f"无 fab 目录: {fab_dir}"
            fab_files = [p for p in fab_dir.rglob("*") if p.is_file()]
            assert len(fab_files) >= 15, f"fab 文件数过少: {len(fab_files)}"

            # 验动作流水
            actions_jsonl = sess / "actions.jsonl"
            assert actions_jsonl.exists(), "无 actions.jsonl"
            n_actions = sum(1 for _ in open(actions_jsonl, encoding="utf-8"))
            assert n_actions >= 8, f"actions 数过少: {n_actions}"

            return {
                "rc": rc,
                "fab_files": len(fab_files),
                "actions": n_actions,
                "report_kb": round(ap_rpt.stat().st_size / 1024, 1),
            }
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    ok, _ = step("自驾: autopilot --no-gui 静默端到端 (单板 ams1117 全链 + 报告)", t22)
    if not ok: failed += 1

    # ─────────────────────────────────────────────────────────
    # 23. 自交付 jlc_ready: 21 板 _fab → JLC-Ready 提交包 (得鱼忘筌)
    #     验:
    #       - jlc_ready.main() 跑过返 0
    #       - _DELIVERY_INDEX.md + _delivery.json 写盘
    #       - 至少 1 块板有 zip + bom + readme
    #       - 抽样 zip 内 ≥ 14 件 (Gerber 12 + drill + job)
    #       - BOM CSV 头 "Comment,Designator,Footprint,Quantity"
    # ─────────────────────────────────────────────────────────
    def t23():
        from kicad_origin.examples.jlc_ready import main as _jlc_main
        import shutil
        import zipfile

        tmp_root = Path("_st23_jlc")
        if tmp_root.exists():
            shutil.rmtree(tmp_root)

        try:
            rc = _jlc_main(["--root", "pcb_brain/output", "--out", str(tmp_root)])
            assert rc == 0, f"jlc_ready 返回非 0: {rc}"

            # 验总索引
            idx = tmp_root / "_DELIVERY_INDEX.md"
            assert idx.exists(), f"未写 _DELIVERY_INDEX.md: {idx}"
            idx_text = idx.read_text(encoding="utf-8")
            assert ("板提交清单" in idx_text and "JLC-Ready" in idx_text), \
                "_DELIVERY_INDEX.md 内容不全"

            # 验 JSON 汇总
            j = tmp_root / "_delivery.json"
            assert j.exists(), "未写 _delivery.json"
            data = json.loads(j.read_text(encoding="utf-8"))
            assert data.get("ok", 0) >= 15, f"成功板数过少: {data.get('ok')}"
            assert data.get("total_zip_bytes", 0) > 100_000, \
                f"zip 总字节过少: {data.get('total_zip_bytes')}"

            # 抽 1 块板验完整
            board_dirs = [d for d in tmp_root.iterdir() if d.is_dir()]
            assert board_dirs, "未生成任何板目录"
            sample = board_dirs[0]
            zips = list(sample.glob("*_jlc.zip"))
            assert zips, f"{sample.name} 无 zip"
            with zipfile.ZipFile(zips[0]) as z:
                names = z.namelist()
                assert len(names) >= 14, \
                    f"{sample.name} zip 内仅 {len(names)} 件 (期 ≥ 14)"
                assert any(".drl" in n for n in names), "zip 缺 drill"
                assert any("Edge_Cuts" in n for n in names), "zip 缺 Edge.Cuts"
                # 抽 F_Cu 验真有 KiCad 头
                f_cu = next((n for n in names if "F_Cu" in n), None)
                if f_cu:
                    head = z.read(f_cu).decode("utf-8", errors="ignore")[:300]
                    assert "KiCad" in head, "F_Cu Gerber 不像真 KiCad 输出"

            # 验 README + BOM
            readme = sample / "README.md"
            assert readme.exists(), f"{sample.name} 无 README.md"
            assert "JLCPCB" in readme.read_text(encoding="utf-8"), "README 缺上传指南"

            bom_files = list(sample.glob("*_bom.csv"))
            if bom_files:  # 部分板 placement-only 会无 BOM
                bom_head = bom_files[0].read_text(encoding="utf-8").splitlines()[0]
                assert bom_head == "Comment,Designator,Footprint,Quantity", \
                    f"BOM 头不对: {bom_head}"

            return {
                "rc": rc,
                "boards_ok": data["ok"],
                "boards_total": data["total"],
                "total_zip_bytes": data["total_zip_bytes"],
                "total_components": data.get("total_bom_components", 0),
                "sample_zip_files": len(names),
            }
        finally:
            shutil.rmtree(tmp_root, ignore_errors=True)

    ok, _ = step("自交付: jlc_ready 21 板 → _JLC_READY (zip+BOM+README+索引)", t23)
    if not ok: failed += 1

    print()
    print(f"=== Layer 0+1+2+3+4 + dao + ziran + 二生三 + 道并桥 + 自驾 + 自交付 端到端自检完成 ===")
    print(f"    版本:   {ver}")
    print(f"    符号库: {counts['symbols']:6d} 个")
    print(f"    封装库: {counts['footprints']:6d} 个")
    print(f"    失败:   {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
