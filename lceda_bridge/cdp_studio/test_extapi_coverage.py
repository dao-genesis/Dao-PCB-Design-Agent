#!/usr/bin/env python3
"""EXTAPI 全量覆盖测试 — 逆向解构嘉立创 94 命名空间 / 752 方法,
逐一测试每个已封装 API 的可用性,暴露 Web 模式下的一切限制和缺陷。

道法自然 · 反者道之动 — 从测试中发现根本缺陷。
"""
import sys, json, time, traceback
sys.path.insert(0, ".")
import eda_flow
import dao_eda_cdp_driver as d

PASS = 0
FAIL = 0
SKIP = 0
DEFECTS = []

def test(name, fn, expect_fail=False):
    global PASS, FAIL, SKIP, DEFECTS
    try:
        r = fn()
        if expect_fail:
            SKIP += 1
            print(f"  [SKIP] {name}: expected fail but got {type(r).__name__}")
        else:
            PASS += 1
            desc = str(r)[:120] if r is not None else "None"
            print(f"  [PASS] {name}: {desc}")
        return r
    except Exception as e:
        err = str(e)[:120]
        if expect_fail:
            SKIP += 1
            print(f"  [SKIP] {name}: {err}")
        else:
            FAIL += 1
            DEFECTS.append({"api": name, "error": str(e)[:200]})
            print(f"  [FAIL] {name}: {err}")
        return None

def main():
    global PASS, FAIL, SKIP
    f = eda_flow.Flow()

    print("=" * 70)
    print("  EXTAPI Coverage Test — 94 namespaces / 752 methods")
    print("=" * 70)

    # ============ 1. Environment ============
    print("\n--- sys_Environment ---")
    test("getUserInfo", lambda: f.get_user_info())
    test("getEditorVersion", lambda: f.get_editor_version())
    test("isWeb", lambda: f.eda.call("sys_Environment.isWeb", timeout=10))
    test("isClient", lambda: f.eda.call("sys_Environment.isClient", timeout=10))
    test("isOnlineMode", lambda: f.eda.call("sys_Environment.isOnlineMode", timeout=10))

    # ============ 2. FileSystem (Web mode — expect failures) ============
    print("\n--- sys_FileSystem (Web mode limitations) ---")
    test("getEdaPath", lambda: f.eda.call("sys_FileSystem.getEdaPath", timeout=10),
         expect_fail=True)
    test("getDocumentsPath", lambda: f.eda.call("sys_FileSystem.getDocumentsPath", timeout=10),
         expect_fail=True)
    test("getProjectsPaths", lambda: f.eda.call("sys_FileSystem.getProjectsPaths", timeout=10),
         expect_fail=True)

    # ============ 3. Workspace / Team ============
    print("\n--- dmt_Workspace / dmt_Team ---")
    test("getAllWorkspaces", lambda: f.get_workspaces())
    test("getCurrentWorkspace", lambda: f.get_current_workspace())
    test("getAllTeams", lambda: f.get_teams())

    # ============ 4. Project / Board / Schematic ============
    print("\n--- dmt_Project / Board / Schematic ---")
    test("getAllSchematicsInfo", lambda: f.eda.call("dmt_Schematic.getAllSchematicsInfo", timeout=15))
    test("getAllBoardsInfo", lambda: f.eda.call("dmt_Board.getAllBoardsInfo", timeout=15))
    pages = test("getAllSchematicPagesInfo", lambda: f.get_all_schematic_pages())
    test("getCurrentSchematicInfo", lambda: f.eda.call("dmt_Schematic.getCurrentSchematicInfo", timeout=15))

    # ============ 5. Library / Community ============
    print("\n--- lib_* (Library/Community) ---")
    test("getClassificationTree", lambda: f.get_classification_tree())
    test("getAllLibraries", lambda: f.get_all_libraries())
    test("getSystemLibraryUuid", lambda: f.get_system_library_uuid())
    test("getPersonalLibraryUuid", lambda: f.get_personal_library_uuid())

    # Test community search via EXTAPI directly
    test("lib_Device.search(STM32)",
         lambda: f.eda.call("lib_Device.search", "STM32", 1, 2, timeout=15))
    test("lib_Footprint.search(LQFP48)",
         lambda: f.eda.call("lib_Footprint.search", "LQFP48", 1, 2, timeout=15))
    test("lib_Symbol.search(MCU)",
         lambda: f.eda.call("lib_Symbol.search", "MCU", 1, 2, timeout=15))
    test("lib_3DModel.search(LQFP)",
         lambda: f.eda.call("lib_3DModel.search", "LQFP", 1, 2, timeout=15))
    test("lib_Cbb.search(ESP32)",
         lambda: f.eda.call("lib_Cbb.search", "ESP32", 1, 2, timeout=15))

    # ============ 6. Schematic primitives ============
    print("\n--- sch_* (Schematic primitives) ---")
    # Get current page, open schematic
    allsch = f.eda.call("dmt_Schematic.getAllSchematicsInfo", timeout=15)
    if allsch:
        sch_page = allsch[0]["page"][0]["uuid"]
        f.open_document(sch_page)
        time.sleep(2)

    test("sch_PrimitiveComponent.getAll", lambda: f.eda.call("sch_PrimitiveComponent.getAllPrimitiveId", timeout=15))
    test("sch_PrimitiveWire.getAll", lambda: f.eda.call("sch_PrimitiveWire.getAllPrimitiveId", timeout=15))
    test("sch_PrimitiveBus.getAll", lambda: f.get_all_buses())
    # Discover actual sch_Net and sch_Drc method names
    test("sch_Net.getAllNetList",
         lambda: f.eda.call("sch_Net.getAllNetList", timeout=15))
    test("sch_Drc.check",
         lambda: f.eda.call("sch_Drc.check", timeout=15))

    # Schematic auto functions
    test("autoLayout(empty)", lambda: f.sch_auto_layout())
    test("autoRouting(empty)", lambda: f.sch_auto_routing())

    # Multi-page test
    test("createSchematicPage", lambda: f.create_schematic_page("TestPage"))

    # ============ 7. PCB ============
    print("\n--- pcb_* (PCB operations) ---")
    if allsch:
        boards = f.eda.call("dmt_Board.getAllBoardsInfo", timeout=15) or []
        if boards:
            pcb_uuid = boards[0]["pcb"]["uuid"]
            try:
                f.open_document(pcb_uuid)
            except Exception:
                # Fallback: use CDP navigation
                import dao_eda_cdp_driver as drv
                drv.evaluate(f.ws,
                    f'window._EXTAPI_ROOT_.dmt_EditorControl.openDocument("{pcb_uuid}")',
                    await_promise=True, timeout=20)
            time.sleep(3)

    test("pcb_PrimitiveComponent.getAll", lambda: f.pcb_component_ids())
    test("pcb_Net.getAll", lambda: f.eda.call("pcb_Net.getAllNet", timeout=15))
    test("pcb_Layer.getAllLayers", lambda: f.eda.call("pcb_Layer.getAllLayers", timeout=15))

    # Design rules
    test("pcb_Drc.getDrcRulesList", lambda: f.eda.call("pcb_Drc.getDrcRulesList", timeout=15))
    test("pcb_Drc.getAllNetClasses", lambda: f.eda.call("pcb_Drc.getAllNetClasses", timeout=15))

    # PCB manufacturing data
    print("\n--- pcb_ManufactureData ---")
    test("getGerberFile", lambda: f.eda.call("pcb_ManufactureData.getGerberFile", timeout=30))
    test("getDsnFile", lambda: f.get_dsn_file())
    test("getAutoRouteJsonFile", lambda: f.get_autoroute_json())
    test("getPcbInfoFile", lambda: f.get_pcb_info())
    test("getBomFile", lambda: f.eda.call("pcb_ManufactureData.getBomFile", timeout=30))
    test("getNetlistFile", lambda: f.eda.call("pcb_ManufactureData.getNetlistFile", timeout=30))

    # PCB view / selection
    print("\n--- pcb_Document / SelectControl ---")
    test("zoomToBoardOutline", lambda: f.zoom_to_board())
    test("getCanvasOrigin", lambda: f.eda.call("pcb_Document.getCanvasOrigin", timeout=10))
    test("coordConvert", lambda: f.canvas_to_data(100, 200))
    test("getSelectedPrimitives", lambda: f.get_selected_primitives())
    test("clearSelection", lambda: f.clear_selection())
    test("getMousePosition", lambda: f.get_mouse_position())
    test("getRatlineStatus", lambda: f.get_ratline_status())

    # ============ 8. Document Source ============
    print("\n--- sys_FileManager (Document Source) ---")
    if allsch:
        boards = f.eda.call("dmt_Board.getAllBoardsInfo", timeout=15) or []
        pcb_uuid = boards[0]["pcb"]["uuid"] if boards else None
        sch_uuid = allsch[0]["page"][0]["uuid"]

        if pcb_uuid:
            src = test("getDocumentSource(PCB)", lambda: f.get_document_source(pcb_uuid))
            if src:
                items = f.parse_document_source(src)
                print(f"       Parsed: {len(items)} elements, {len(src)} chars")
                from collections import Counter
                types = Counter(i["type"] for i in items)
                print(f"       Types: {dict(types.most_common(10))}")

        src_sch = test("getDocumentSource(SCH)", lambda: f.get_document_source(sch_uuid))
        if src_sch:
            items_sch = f.parse_document_source(src_sch)
            print(f"       Parsed: {len(items_sch)} elements, {len(src_sch)} chars")

    # ============ 9. PCB Primitives ============
    print("\n--- pcb_Primitive* (individual types) ---")
    prim_types = ["Arc", "Attribute", "Dimension", "Fill", "Image",
                  "Object", "Polyline", "Region", "String", "Line", "Via",
                  "Pour", "Poured", "Pad"]
    for pt in prim_types:
        ns = f"pcb_Primitive{pt}"
        test(f"{ns}.getAllPrimitiveId",
             lambda ns=ns: f.eda.call(f"{ns}.getAllPrimitiveId", timeout=10))

    # ============ 10. Schematic Primitives ============
    print("\n--- sch_Primitive* ---")
    sch_prims = ["Arc", "Attribute", "Bus", "Component", "Ellipse",
                 "Image", "Line", "NetFlag", "NetPort", "Pin",
                 "Polyline", "Rect", "String", "Wire"]
    # Need to be on schematic page
    if allsch:
        f.open_document(allsch[0]["page"][0]["uuid"])
        time.sleep(2)
    for sp in sch_prims:
        ns = f"sch_Primitive{sp}"
        test(f"{ns}.getAllPrimitiveId",
             lambda ns=ns: f.eda.call(f"{ns}.getAllPrimitiveId", timeout=10))

    # ============ Summary ============
    print("\n" + "=" * 70)
    print(f"  RESULTS: {PASS} PASS / {FAIL} FAIL / {SKIP} SKIP")
    print(f"  Total tested: {PASS + FAIL + SKIP}")
    print("=" * 70)

    if DEFECTS:
        print(f"\n  DEFECTS ({len(DEFECTS)}):")
        for d in DEFECTS:
            print(f"    - {d['api']}: {d['error']}")

    print(f"\n  [RESULT] {'PASS' if FAIL == 0 else 'FAIL'}")

if __name__ == "__main__":
    main()
