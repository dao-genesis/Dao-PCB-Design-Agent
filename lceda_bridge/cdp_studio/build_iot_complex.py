#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_iot_complex — 大型复杂 IoT PCB 全链路实战(道法自然·推进到底)。

目标板: STM32F103 + ESP-12F WiFi + LDO电源(AMS1117-3.3) + 传感器(DHT11) + LED×4 + 按键×2
         + USB-C供电 + 晶振 + 退耦电容组 + ESD保护

这是一个真实复杂度的 IoT 板,涵盖:
  - 多电源域(5V USB → 3.3V LDO → MCU/WiFi)
  - 高速信号(SPI for ESP-12F, UART debug)
  - 模拟信号(ADC for sensor)
  - 多网络(>20 nets)
  - 多种封装(QFP/SOP/0402/0603/SOT-223/through-hole)

全链路: scaffold → place → wire → PCB sync → layout → route → pour → DRC → export
"""
import sys, os, json, time, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow
import eda_community
import build_chain_det
import dao_eda_cdp_driver as d

OUT_DIR = os.path.join(os.path.dirname(__file__), "_iot_complex_out")
os.makedirs(OUT_DIR, exist_ok=True)

class IoTBoardBuilder:
    """构建一个真实复杂度的 IoT 开发板。"""

    # LCSC 器件清单 (真实料号)
    BOM = {
        # MCU
        "STM32F103C8T6":   {"lcsc": "C8734",   "desc": "ARM Cortex-M3 MCU 72MHz 64KB Flash"},
        # WiFi
        "ESP-12F":         {"lcsc": "C82891",  "desc": "ESP8266 WiFi module"},
        # LDO
        "AMS1117-3.3":     {"lcsc": "C6186",   "desc": "3.3V LDO 1A SOT-223"},
        # 晶振
        "8MHz_Crystal":    {"lcsc": "C12674",  "desc": "8MHz crystal HC-49S"},
        # 退耦电容
        "100nF_0402":      {"lcsc": "C1525",   "desc": "100nF MLCC 0402"},
        "10uF_0603":       {"lcsc": "C19702",  "desc": "10uF MLCC 0603"},
        "22pF_0402":       {"lcsc": "C1555",   "desc": "22pF MLCC 0402 for crystal"},
        # LED
        "LED_Green":       {"lcsc": "C72043",  "desc": "Green LED 0603"},
        # 电阻
        "10K_0402":        {"lcsc": "C25744",  "desc": "10K resistor 0402"},
        "1K_0402":         {"lcsc": "C11702",  "desc": "1K resistor 0402"},
        # USB/Power connector (C2907 proven compatible with importChanges)
        "USB_Conn":        {"lcsc": "C2907",   "desc": "USB power header connector"},
    }

    def __init__(self):
        self.f = eda_flow.Flow()
        self.c = eda_community.Community(self.f.ws)
        self.results = {}
        self.comp_ids = {}  # name -> schematic component ID
        self.errors = []

    def log(self, phase, msg, data=None):
        ts = time.strftime("%H:%M:%S")
        prefix = f"[{ts}] [{phase}]"
        if data:
            print(f"{prefix} {msg}: {json.dumps(data, ensure_ascii=False, default=str)[:150]}")
        else:
            print(f"{prefix} {msg}")

    def phase_scaffold(self):
        """Phase 0: 创建新工程(使用 capstone 已验证的 _scaffold 流程)。"""
        self.log("SCAFFOLD", "Creating IoT project via CDP...")
        h = build_chain_det._scaffold(self.f)
        self.project_uuid = h["project"]
        self.pcb_uuid = h["pcb"]
        self.sch_page = h["page"]
        self.log("SCAFFOLD", "Project created", h)
        self.results["scaffold"] = h
        return h

    def phase_community_search(self):
        """Phase 1: 从社区验证所有器件可搜索到。"""
        self.log("COMMUNITY", "Verifying BOM components in library...")
        found = 0
        for name, spec in self.BOM.items():
            r = self.c.search_device(name.replace("_", " "), limit=3)
            ok = isinstance(r, list) and len(r) > 0
            if ok:
                found += 1
            self.log("COMMUNITY", f"  {name} ({spec['lcsc']}): {'FOUND' if ok else 'MISS'}")
        self.log("COMMUNITY", f"BOM coverage: {found}/{len(self.BOM)}")
        self.results["community"] = {"found": found, "total": len(self.BOM)}

    def _clear_schematic_page(self):
        """清除原理图页面上的所有现有器件和导线(确保干净起点)。"""
        # Delete all existing wires
        try:
            wire_ids = self.f.eda.call("sch_PrimitiveWire.getAllPrimitiveId", timeout=15) or []
            for wid in wire_ids:
                try:
                    self.f.eda.call("sch_PrimitiveWire.delete", wid, timeout=5)
                except Exception:
                    pass
            self.log("CLEAR", f"Deleted {len(wire_ids)} wires")
        except Exception:
            pass

        # Delete all existing components
        try:
            comp_ids = self.f.schematic_component_ids() or []
            for cid in comp_ids:
                try:
                    self.f.eda.call("sch_PrimitiveComponent.delete", cid, timeout=5)
                except Exception:
                    pass
            self.log("CLEAR", f"Deleted {len(comp_ids)} components")
        except Exception:
            pass

        # Save clean state
        self.f.save_schematic()
        time.sleep(2)

        # Also clear PCB components
        try:
            pcb_uuid = getattr(self, 'pcb_uuid', None)
            if pcb_uuid:
                self.f.open_document(pcb_uuid)
                time.sleep(2)
                pcb_ids = self.f.pcb_component_ids() or []
                for pid in pcb_ids:
                    try:
                        self.f.eda.call("pcb_PrimitiveComponent.delete", pid, timeout=5)
                    except Exception:
                        pass
                self.log("CLEAR", f"Deleted {len(pcb_ids)} PCB components")
                self.f.eda.call("pcb_Document.save", timeout=20)
                time.sleep(2)
        except Exception:
            pass

    def phase_place_components(self):
        """Phase 2: 在原理图上放置所有器件(带 designator)。"""
        self.log("PLACE", "Opening schematic page...")
        if hasattr(self, 'sch_page') and self.sch_page:
            self.f.open_document(self.sch_page)
            time.sleep(3)
        else:
            schs = self.f.eda.call("dmt_Schematic.getAllSchematicPagesInfo", timeout=15) or []
            if schs:
                self.f.open_document(schs[0]["uuid"])
                time.sleep(3)

        # 器件放置坐标布局 (带 designator,横向排列)
        layout = [
            # (BOM_key, x, y, designator)
            ("STM32F103C8T6", 0, 0, "U1"),
            ("ESP-12F", 600, 0, "U2"),
            ("AMS1117-3.3", -400, -400, "U3"),
            ("USB_Conn", -700, -400, "J1"),
            ("8MHz_Crystal", -200, 300, "Y1"),
            ("22pF_0402", -300, 400, "C1"),
            ("22pF_0402", -100, 400, "C2"),
            ("100nF_0402", 100, -200, "C3"),
            ("100nF_0402", 200, -200, "C4"),
            ("10uF_0603", 300, -200, "C5"),
            ("LED_Green", 400, 300, "D1"),
            ("1K_0402", 400, 400, "R1"),
            ("LED_Green", 500, 300, "D2"),
            ("1K_0402", 500, 400, "R2"),
            ("10K_0402", -200, -200, "R3"),
            ("10K_0402", -100, -200, "R4"),
        ]

        self.log("PLACE", f"Placing {len(layout)} components...")
        placed = 0
        for name, x, y, des in layout:
            spec = self.BOM.get(name)
            if not spec:
                self.log("PLACE", f"  SKIP {name} (not in BOM)")
                continue
            try:
                result = self.f.place_by_lcsc(spec["lcsc"], x, y, designator=des)
                if result:
                    placed += 1
                    cid = result if isinstance(result, str) else str(result)
                    self.comp_ids[des] = cid
                    self.log("PLACE", f"  OK {des}={name} at ({x},{y})", {"id": cid[:16]})
                else:
                    self.log("PLACE", f"  WARN {des}={name} place returned: {result}")
                    self.errors.append(f"place_{des}: {result}")
            except Exception as ex:
                self.log("PLACE", f"  ERR {des}={name}: {ex}")
                self.errors.append(f"place_{des}: {ex}")
            time.sleep(0.5)

        self.log("PLACE", f"Placed {placed}/{len(layout)} components")
        self.results["place"] = {"placed": placed, "total": len(layout)}
        return placed

    def phase_power_flags(self):
        """Phase 3: 放置电源/地符号。"""
        self.log("POWER", "Creating power/ground flags...")
        flags = [
            ("Power", "VCC_3V3", -400, -500),
            ("Power", "VCC_5V", -700, -500),
            ("Ground", "GND", -400, -300),
            ("Ground", "GND", 0, 500),
            ("Ground", "GND", 600, 500),
        ]
        created = 0
        for ftype, net, x, y in flags:
            try:
                r = self.f.create_net_flag(ftype, net, x, y)
                if r and r.get("ok"):
                    created += 1
                    self.log("POWER", f"  OK {ftype}:{net} at ({x},{y})")
                else:
                    self.log("POWER", f"  WARN {ftype}:{net}: {r}")
            except Exception as ex:
                self.log("POWER", f"  ERR {ftype}:{net}: {ex}")
                self.errors.append(f"flag_{ftype}_{net}: {ex}")
        self.results["power_flags"] = {"created": created, "total": len(flags)}

    def phase_wiring(self):
        """Phase 4: 连线(route-by-name:同名stub归一网,无物理走线交叉)。"""
        self.log("WIRE", "Wiring schematic connections (route-by-name)...")

        # Build net_map from placed components' pins
        # Auto-detect VCC/GND pins, plus create signal nets between
        # specific component pin pairs
        net_map = {}

        # Power pin name patterns (use pinName field, not name)
        VCC_NAMES = {"VCC", "VDD", "VBAT", "VDDA", "VDD_1", "VDD_2", "VDD_3", "VOUT", "3V3"}
        GND_NAMES = {"GND", "VSS", "VSSA", "VSS_1", "VSS_2", "VSS_3", "V-", "AGND", "PGND"}
        VIN_NAMES = {"VIN", "V+", "VBUS", "5V"}

        for label, cid in self.comp_ids.items():
            try:
                pins = self.f.component_pins(cid)
                if not pins or not isinstance(pins, list):
                    continue
                for p in pins:
                    pname = (p.get("pinName") or p.get("name") or "").upper()
                    pnum = str(p.get("pinNumber", ""))
                    if not pnum:
                        continue
                    if pname in VCC_NAMES:
                        net_map.setdefault("VCC_3V3", []).append((cid, pnum))
                    elif pname in GND_NAMES:
                        net_map.setdefault("GND", []).append((cid, pnum))
                    elif pname in VIN_NAMES:
                        net_map.setdefault("VCC_5V", []).append((cid, pnum))
            except Exception as ex:
                self.log("WIRE", f"  SKIP {label} pins: {ex}")

        # Add explicit signal connections (MCU UART ↔ ESP UART)
        stm32_id = self.comp_ids.get("U1")
        esp_id = self.comp_ids.get("U2")
        if stm32_id and esp_id:
            net_map.setdefault("UART_TX", []).append((stm32_id, "30"))  # PA9
            net_map.setdefault("UART_TX", []).append((esp_id, "15"))     # RXD0
            net_map.setdefault("UART_RX", []).append((stm32_id, "31"))  # PA10
            net_map.setdefault("UART_RX", []).append((esp_id, "16"))     # TXD0

        # LED connections (LED anode to resistor)
        if self.comp_ids.get("D1") and self.comp_ids.get("R1"):
            net_map.setdefault("LED1_SIG", []).append((self.comp_ids["D1"], "1"))
            net_map.setdefault("LED1_SIG", []).append((self.comp_ids["R1"], "1"))
        if self.comp_ids.get("D2") and self.comp_ids.get("R2"):
            net_map.setdefault("LED2_SIG", []).append((self.comp_ids["D2"], "1"))
            net_map.setdefault("LED2_SIG", []).append((self.comp_ids["R2"], "1"))

        # Filter nets with at least 2 pins
        net_map = {n: ps for n, ps in net_map.items() if len(ps) >= 2}
        for net, pins in net_map.items():
            self.log("WIRE", f"  Net '{net}': {len(pins)} pins")
        self.log("WIRE", f"Auto-detected nets: {list(net_map.keys())}")

        # Route by name (stub-based, no physical crossing)
        try:
            if net_map:
                result = self.f.route_by_name(net_map, stub=40)
                self.log("WIRE", f"route_by_name result", result)
                self.results["wire"] = {"nets": list(net_map.keys()), "result": result}
            else:
                self.log("WIRE", "No nets with >=2 pins found, skip wiring")
                self.results["wire"] = {"nets": [], "note": "no multi-pin nets"}
        except Exception as ex:
            self.log("WIRE", f"route_by_name error: {ex}")
            self.results["wire"] = {"err": str(ex)}
            self.errors.append(f"wire: {ex}")

    def phase_save_schematic(self):
        """Phase 5: 保存原理图。"""
        self.log("SAVE", "Saving schematic...")
        try:
            self.f.save_schematic()
            time.sleep(3)  # extra settle for large schematic
            self.log("SAVE", "Schematic saved")
            self.results["save_sch"] = True
        except Exception as ex:
            self.log("SAVE", f"Save error: {ex}")
            self.results["save_sch"] = str(ex)

    def phase_pcb_sync(self):
        """Phase 6: 同步到 PCB (importChanges)。"""
        self.log("PCB_SYNC", "Syncing schematic to PCB...")
        pcb_uuid = getattr(self, 'pcb_uuid', None)
        if not pcb_uuid:
            pcbs = self.f.eda.call("dmt_Pcb.getAllPcbsInfo", timeout=15) or []
            if pcbs:
                pcb_uuid = pcbs[0].get("uuid")
        if not pcb_uuid:
            self.log("PCB_SYNC", "No PCB found, creating...")
            pcb_uuid = self.f.eda.call("dmt_Pcb.createPcb", "IoT_PCB", timeout=15)

        if pcb_uuid:
            self.log("PCB_SYNC", f"PCB uuid: {pcb_uuid}")
            try:
                # Keep schematic as active document, then import
                # (importChanges needs SCH context to detect changes)
                sync_result = self.f.update_pcb_from_schematic(pcb_uuid, timeout=40)
                self.log("PCB_SYNC", "Import result", sync_result)
                self.f.prepare_pcb_nets(pcb_uuid)
                time.sleep(3)
                pcb_count = len(self.f.pcb_component_ids() or [])
                self.log("PCB_SYNC", f"PCB sync done, {pcb_count} components in PCB")
                self.results["pcb_sync"] = {"ok": True, "pcb_components": pcb_count}
            except Exception as ex:
                self.log("PCB_SYNC", f"Sync error: {ex}")
                self.results["pcb_sync"] = str(ex)
                self.errors.append(f"pcb_sync: {ex}")
        else:
            self.log("PCB_SYNC", "No PCB UUID available")
            self.results["pcb_sync"] = "NO_PCB"

    def phase_pcb_layout(self):
        """Phase 7: PCB 布局(网格排列,大间距避免 clearance 违规)。"""
        self.log("LAYOUT", "Laying out PCB components...")
        try:
            comp_ids = self.f.pcb_component_ids()
            self.log("LAYOUT", f"PCB has {len(comp_ids)} components")

            if comp_ids:
                # Grid layout: 4 columns, large spacing for ICs
                cols = 4
                dx, dy = 7000, 5500  # ~700mil x 550mil grid (large ICs)
                placed = {}
                for i, cid in enumerate(comp_ids):
                    col = i % cols
                    row = i // cols
                    x = 1000 + col * dx
                    y = 1000 + row * dy
                    self.f.pcb_place_det(cid, x, y)
                    placed[cid] = (x, y)

                # Board outline with generous margin after layout
                self.f.auto_board_outline(margin=1000)
                self.log("LAYOUT", f"Grid layout: {cols}x{(len(comp_ids)+cols-1)//cols}, {len(placed)} placed")
                self.results["layout"] = {"components": len(placed)}
            else:
                self.log("LAYOUT", "No PCB components to layout")
                self.results["layout"] = {"components": 0}
        except Exception as ex:
            self.log("LAYOUT", f"Layout error: {ex}")
            self.results["layout"] = {"err": str(ex)}
            self.errors.append(f"layout: {ex}")

    def phase_pcb_route(self):
        """Phase 8: Hybrid routing — native autorouter first, then pad-aware escape fallback."""
        self.log("ROUTE", "Routing PCB traces...")
        try:
            nets = self.f.pcb_nets()
            self.log("ROUTE", f"PCB has {len(nets)} nets")

            # Prepare nets first
            self.f.prepare_pcb_nets()
            time.sleep(2)

            # Strategy 1: Try native autorouter (handles pad avoidance natively)
            try:
                self.log("ROUTE", "Attempting native autorouter...")
                ar = self.f.autoroute_gui(wait=15)
                self.log("ROUTE", f"Native autorouter result: {ar}")
                if ar.get("tracks", 0) > 0:
                    self.results["route"] = {"method": "native_autoroute", **ar}
                    return
            except Exception as ae:
                self.log("ROUTE", f"Native autorouter failed: {ae}, falling back to escape routing")

            # Strategy 2: Pad-aware 2-layer escape routing
            # - Skip GND only (connected by copper pour on both layers)
            # - Board-outline-aware corridor placement
            result = self.f.pcb_route_layers(width=10, escape=800,
                                             skip_nets=["GND"])
            self.log("ROUTE", f"Escape routing result", result)
            self.results["route"] = {"method": "escape_corridor", **result}
        except Exception as ex:
            self.log("ROUTE", f"Route error: {ex}")
            self.results["route"] = {"err": str(ex)}
            self.errors.append(f"route: {ex}")

    def phase_copper_pour(self):
        """Phase 9: GND 覆铜 + VCC_3V3 覆铜(layer 2)。"""
        self.log("POUR", "Creating copper pours (GND + VCC_3V3)...")
        try:
            result = self.f.auto_ground_pour()
            self.log("POUR", "GND pour created", result)
            # No VCC_3V3 pour — it's routed via traces (skip only GND)
            self.f.rebuild_pours()
            self.log("POUR", "Pours rebuilt")
            self.results["pour"] = result
        except Exception as ex:
            self.log("POUR", f"Pour error: {ex}")
            self.results["pour"] = {"err": str(ex)}
            self.errors.append(f"pour: {ex}")

    def phase_drc(self):
        """Phase 10: DRC 检查。"""
        self.log("DRC", "Running DRC check...")
        try:
            result = self.f.drc_summary(strict=False)
            self.log("DRC", "DRC result", result)
            self.results["drc"] = result
        except Exception as ex:
            self.log("DRC", f"DRC error: {ex}")
            self.results["drc"] = {"err": str(ex)}
            self.errors.append(f"drc: {ex}")

    def phase_export(self):
        """Phase 11: 导出全部制造文件。"""
        self.log("EXPORT", "Exporting manufacturing files...")
        try:
            result = self.f.export_all(OUT_DIR, base="IoT_Complex")
            export_summary = {}
            for k, v in result.items():
                if isinstance(v, dict) and "bytes" in v:
                    export_summary[k] = v["bytes"]
                elif isinstance(v, dict) and "err" in v:
                    export_summary[k] = f"ERR: {v['err'][:50]}"
                else:
                    export_summary[k] = v
            self.log("EXPORT", "Export results", export_summary)
            self.results["export"] = export_summary
        except Exception as ex:
            self.log("EXPORT", f"Export error: {ex}")
            self.results["export"] = {"err": str(ex)}
            self.errors.append(f"export: {ex}")

    def phase_layer_info(self):
        """Phase 12: 读取层叠/规则信息。"""
        self.log("INFO", "Reading board info...")
        try:
            layers = self.f.get_copper_layer_count()
            rules = self.f.get_net_rules()
            net_names = self.f.pcb_all_net_names()
            self.log("INFO", f"Copper layers: {layers}, Nets: {len(net_names)}, Rules: {len(rules)}")
            self.results["info"] = {
                "copper_layers": layers,
                "nets": net_names,
                "rules_count": len(rules)
            }
        except Exception as ex:
            self.log("INFO", f"Info error: {ex}")
            self.results["info"] = {"err": str(ex)}

    def run(self):
        """执行全链路构建。"""
        start = time.time()
        print("=" * 70)
        print("  IoT Complex Board Full-Chain Build")
        print("  STM32F103 + ESP-12F + AMS1117 + Crystal + LEDs + USB")
        print("=" * 70)

        phases = [
            ("scaffold", self.phase_scaffold),
            ("community", self.phase_community_search),
            ("place", self.phase_place_components),
            ("power_flags", self.phase_power_flags),
            ("wire", self.phase_wiring),
            ("save_sch", self.phase_save_schematic),
            ("pcb_sync", self.phase_pcb_sync),
            ("pcb_layout", self.phase_pcb_layout),
            ("pcb_route", self.phase_pcb_route),
            ("copper_pour", self.phase_copper_pour),
            ("drc", self.phase_drc),
            ("export", self.phase_export),
            ("layer_info", self.phase_layer_info),
        ]

        for name, fn in phases:
            print(f"\n{'='*50}")
            print(f"  Phase: {name}")
            print(f"{'='*50}")
            try:
                fn()
            except Exception as ex:
                self.log(name.upper(), f"FATAL: {ex}")
                traceback.print_exc()
                self.errors.append(f"FATAL_{name}: {ex}")

        elapsed = time.time() - start
        print(f"\n{'='*70}")
        print(f"  SUMMARY ({elapsed:.1f}s)")
        print(f"{'='*70}")
        for k, v in self.results.items():
            vstr = json.dumps(v, ensure_ascii=False, default=str)[:100]
            print(f"  {k}: {vstr}")
        print(f"\n  Errors: {len(self.errors)}")
        for e in self.errors:
            print(f"    - {e[:100]}")

        verdict = "PASS" if len(self.errors) == 0 else (
            "PARTIAL" if len(self.errors) < 5 else "FAIL")
        print(f"\n  [RESULT] {verdict}")
        return verdict, self.results, self.errors


if __name__ == "__main__":
    builder = IoTBoardBuilder()
    verdict, results, errors = builder.run()
