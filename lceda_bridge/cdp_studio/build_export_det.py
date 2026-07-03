# -*- coding: utf-8 -*-
"""制造数据「全谱导出」活体验证（桌面纯 RPC 底座，零 GUI）。

证明：官方 `pcb_ManufactureData` 不止 Gerber/BOM/PnP——把整套制造/交换格式
（PDF / 3D-STEP / DXF / IPC-D-356A / ODB++ / 交互式 BOM / Altium / 测试点 /
网络表 / 自动布线 JSON）经同一通用 blob 通道一次性 headless 导齐为真字节。
「官方有的东西我们全都能调用」。

链路：dao_rpc_driver 建一块 DRC=0 的板 → export_all() → 断言各格式 size>0。

用法：cd 到本目录后 `python build_export_det.py [--port 29230]`
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "examples"))
import dao_rpc_driver as D       # noqa: E402
from specs import build_simple   # noqa: E402

# 实测在桌面离线底座必然产出真字节的格式（诚实定界：ipc_2581c 恒挂起、
# 3dshell 无外壳模型 → 不纳入 _EXPORT_SUITE，故不在此断言之列）。
EXPECT = ["gerber", "bom", "pnp", "pdf", "3d_step", "dxf", "ipc_d356a",
          "odb", "ibom", "altium", "testpoint", "netlist", "autoroute_json"]


def main():
    port = 29230
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    drv = D.DaoRpc(port=port)
    audit = drv.build_until_clean(build_simple(), router="freerouting", tries=5)
    drc = audit["steps"]["drc"]["total"]
    print("[build] DRC=%d placed=%d" % (
        drc, audit["steps"]["place_and_net"]["placed"]))

    out_dir = os.path.expanduser("~/dao_pcb_out/_export_det")
    exports = drv.export_all(out_dir)
    for k in EXPECT:
        v = exports.get(k, {})
        print("  %-16s -> %s" % (
            k, ("size=%d name=%s" % (v["size"], v.get("name")))
            if "size" in v else ("ERR %s" % v.get("err"))))

    ok = drc == 0 and all(
        isinstance(exports.get(k, {}).get("size"), int)
        and exports[k]["size"] > 0 for k in EXPECT)
    print("[ASSERT] DRC=0 且全谱 %d 格式均产出真字节(size>0)" % len(EXPECT))
    print("[RESULT]", "PASS" if ok else "PARTIAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
