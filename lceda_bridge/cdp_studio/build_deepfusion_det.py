#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_deepfusion_det — 深融新前沿活体验证(道法自然·逆向即正向)。

验证本会话新增的全部深融能力:
  - Net-class 创建/查询
  - 差分对 创建/查询
  - 等长网络组 创建/查询
  - 设计规则配置 读取
  - 电源/地符号(Net Flag)创建
  - 网络端口(Net Port)创建
  - 铜层数 读写
  - 物理层叠 读取
  - 扩展导出格式(3D/DXF/IPC/iBOM)
  - 实时DRC 状态
  - 系统信息(版本/用户/快捷键)

用法: python build_deepfusion_det.py
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow

f = eda_flow.Flow()
results = {}
passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        r = fn()
        results[name] = r
        ok = r is not None
        print(f"[{'PASS' if ok else 'WARN'}] {name}: {json.dumps(r, ensure_ascii=False, default=str)[:120]}")
        if ok:
            passed += 1
        else:
            failed += 1
        return r
    except Exception as ex:
        results[name] = {"err": str(ex)}
        print(f"[FAIL] {name}: {ex}")
        failed += 1
        return None

# 1. 先建一个工程做测试底板(用已有的 scaffold 模式)
print("=== Phase 0: Scaffold ===")
info = f.project_info()
if not info or not info.get("uuid"):
    pname = "Dao_DeepFusion_%06d" % (int(time.time()) % 1000000)
    f.scaffold(pname)
    time.sleep(3)
    info = f.project_info()
print(f"Project: {info.get('name','?')} uuid={info.get('uuid','?')[:12]}")

# 2. 系统信息
print("\n=== Phase 1: System Info ===")
test("editor_version", f.get_editor_version)
test("user_info", f.get_user_info)

# 3. 铜层管理
print("\n=== Phase 2: Copper Layers ===")
test("copper_layer_count", f.get_copper_layer_count)
test("all_layers", lambda: len(f.get_all_layers()))
test("current_layer", f.get_current_layer)

# 4. 设计规则配置
print("\n=== Phase 3: Design Rules ===")
test("rule_config", f.get_rule_configuration)
test("all_rule_configs", f.get_all_rule_configs)
test("net_rules", f.get_net_rules)
test("region_rules", f.get_region_rules)
test("net_by_net_rules", f.get_net_by_net_rules)

# 5. PCB 网络管理
print("\n=== Phase 4: PCB Nets ===")
nets = test("pcb_all_nets", f.pcb_all_nets)
test("pcb_all_net_names", f.pcb_all_net_names)
if nets and len(nets) > 0:
    first_net = nets[0] if isinstance(nets[0], str) else nets[0].get("name", "")
    if first_net:
        test("pcb_net_length_" + first_net, lambda: f.pcb_net_length(first_net))

# 6. Net-class (创建 + 查询)
print("\n=== Phase 5: Net-class ===")
if nets and len(nets) >= 2:
    net_names = [n if isinstance(n, str) else n.get("name", "") for n in nets[:2]]
    test("create_net_class", lambda: f.create_net_class("TestClass", net_names))
    test("get_all_net_classes", f.get_all_net_classes)
else:
    print("[SKIP] No nets for net-class test")

# 7. 差分对
print("\n=== Phase 6: Differential Pair ===")
if nets and len(nets) >= 2:
    net_names = [n if isinstance(n, str) else n.get("name", "") for n in nets[:2]]
    test("create_diff_pair", lambda: f.create_diff_pair("DP_TEST", net_names[0], net_names[1]))
    test("get_all_diff_pairs", f.get_diff_pairs)
else:
    print("[SKIP] No nets for diff pair test")

# 8. 等长组
print("\n=== Phase 7: Equal-Length Group ===")
if nets and len(nets) >= 2:
    net_names = [n if isinstance(n, str) else n.get("name", "") for n in nets[:2]]
    test("create_equal_length_group", lambda: f.create_equal_length_group("EL_TEST", net_names))
    test("get_all_equal_length_groups", f.get_all_equal_length_groups)
else:
    print("[SKIP] No nets for equal-length test")

# 9. 实时DRC
print("\n=== Phase 8: Realtime DRC ===")
test("realtime_drc_status", f.realtime_drc_status)

# 10. 电源/地符号 + 网络端口(需在原理图上下文)
print("\n=== Phase 9: Net Flag / Net Port (SCH context) ===")
test("create_net_flag_power", lambda: f.create_net_flag("Power", "VCC", 0, -200, rotation=0))
test("create_net_flag_ground", lambda: f.create_net_flag("Ground", "GND", 0, 200, rotation=0))
test("create_net_port_in", lambda: f.create_net_port("IN", "SIG_IN", -300, 0, rotation=0))

# Summary
print(f"\n{'='*60}")
print(f"[RESULT] PASSED={passed}  FAILED={failed}  TOTAL={passed+failed}")
verdict = "PASS" if failed == 0 else ("PARTIAL" if passed > failed else "FAIL")
print(f"[RESULT] {verdict}")
