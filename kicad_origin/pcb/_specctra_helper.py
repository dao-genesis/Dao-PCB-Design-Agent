r"""
_specctra_helper — 在 KiCAD 自带 python (含 pcbnew) 下跑的 Specctra DSN/SES 桥接帮手。

本源: KiCAD 的 `pcbnew` 原生暴露 `ExportSpecctraDSN` / `ImportSpecctraSES` —— 这正是
KiCAD 官方与生态自动布线器 (Freerouting) 对接的本来通道。本脚本只是把这两个原生调用
包成命令行, 供主流程 (系统 python) 以子进程方式驱动 KiCAD python 调用。

用法 (须由 KiCAD 的 python.exe 执行, 它才有 pcbnew):
    python _specctra_helper.py export <board.kicad_pcb> <out.dsn> [clearance_margin_nm]
    python _specctra_helper.py import <board.kicad_pcb> <in.ses>   # 导入后原地保存

clearance_margin_nm (可选): 导出 DSN 前把各网类间距临时加宽这么多纳米, 好让 Freerouting
多留一线余量 —— 否则它会贴着 DRC 间距边界走, 因几何取整偶尔差 0.001mm 而被 KiCAD DRC 判违例。
此加宽只作用于送给布线器的 DSN; 最终导回的板仍用原始板自带的间距规则。
"""
import sys

import pcbnew


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print("USAGE: _specctra_helper.py export|import <board> <dsn|ses> [margin_nm]")
        return 2
    mode, board_path, io_path = sys.argv[1], sys.argv[2], sys.argv[3]
    b = pcbnew.LoadBoard(board_path)
    if mode == "export":
        margin = int(sys.argv[4]) if len(sys.argv) == 5 else 0
        if margin > 0:
            ncs = b.GetAllNetClasses()
            for k in ncs.keys():
                nc = ncs[k]
                nc.SetClearance(nc.GetClearance() + margin)
        ok = pcbnew.ExportSpecctraDSN(b, io_path)
        print("EXPORT_OK" if ok else "EXPORT_FAIL")
        return 0 if ok else 1
    if mode == "import":
        ok = pcbnew.ImportSpecctraSES(b, io_path)
        if ok:
            pcbnew.SaveBoard(board_path, b)
            print(f"IMPORT_OK tracks={len(list(b.GetTracks()))}")
            return 0
        print("IMPORT_FAIL")
        return 1
    print(f"UNKNOWN_MODE {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
