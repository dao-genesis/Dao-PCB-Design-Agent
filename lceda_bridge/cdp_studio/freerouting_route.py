"""外部布线器(Freerouting)闭环编排:EasyEDA DSN 出 → Freerouting 布线 → SES 回灌 EasyEDA。

道:嘉立创内置自动布线器是"够用",Freerouting 是业界最强开源布线器;把二者接成一条
程序化闭环,等于给本系统接上一个可替换的"外部大脑"。本会话攻克的三段边界(全部已硬验证):

  1. **DSN 出**:`Flow.export_dsn` 从**未布线**板导出标准 Specctra DSN(已布线板导出会层名错配)。
  2. **Freerouting**:`java -jar freerouting.jar -de in.dsn -do out.ses` 跑批布线、自动写 SES。
     v1.9.0 在有显示器时会弹 GUI 确认框("Autorouter is about to start"),用 SendKeys 回车自动确认;
     布完即按 -do 路径落 SES 并退出。
  3. **SES 回**:`Flow.import_ses` 把 SES 字节 in-page 构造成浏览器 File 直传 `importAutoRouteSesFile`。

用法:先用 dao_board 造好**未布线**的板(scaffold/place/wire/sync + auto_board_outline),
再 `python freerouting_route.py`(脚本里改 PCB 句柄或在已打开的板上跑)。
"""
import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eda_flow

HOME = os.path.expanduser("~")
JAVA = os.path.join(HOME, "jre_extracted", "jdk-21.0.11+10-jre", "bin", "java.exe")
JAR = os.path.join(HOME, "freerouting.jar")


def _win(p):
    """MSYS/绝对路径 → Freerouting(原生 Windows)能认的反斜杠路径。"""
    return os.path.abspath(p)


def _auto_confirm_dialogs(rounds=6, gap=1.5):
    """Freerouting v1.9.0 弹 GUI 确认框时,用 PowerShell SendKeys 回车逐个确认(无显示器可省)。"""
    titles = ["DSN file reader - Freerouting", "Autorouter confirmation - Freerouting"]
    ps = ("Add-Type -AssemblyName Microsoft.VisualBasic,System.Windows.Forms; "
          + "; ".join(
              "try{ [Microsoft.VisualBasic.Interaction]::AppActivate('%s'); "
              "Start-Sleep -Milliseconds 400; "
              "[System.Windows.Forms.SendKeys]::SendWait('{ENTER}') }catch{}" % t
              for t in titles))
    for _ in range(rounds):
        subprocess.run(["powershell", "-Command", ps], capture_output=True)
        time.sleep(gap)


def run_freerouting(dsn_path, ses_path, max_passes=6, wait_s=40):
    """跑 Freerouting:启动 jar(后台)→ 自动确认 GUI 框 → 轮询 SES 落地。返回 SES 路径或 None。"""
    if os.path.exists(ses_path):
        os.remove(ses_path)
    proc = subprocess.Popen(
        [JAVA, "-jar", _win(JAR), "-de", _win(dsn_path), "-do", _win(ses_path),
         "-mp", str(max_passes)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        _auto_confirm_dialogs(rounds=1, gap=1.0)
        if os.path.exists(ses_path) and os.path.getsize(ses_path) > 200:
            time.sleep(1)
            break
        time.sleep(2)
    try:
        proc.terminate()
    except Exception:
        pass
    return ses_path if os.path.exists(ses_path) else None


def _bump_clearance(dsn_path, clear_mil):
    """把 DSN 的 (rule(clear 6.03...)) 间距统一抬到 clear_mil。

    本会话攻克的**规则对齐**边界:嘉立创导出的 DSN 默认 clearance=6.03mil,Freerouting 会贴着
    6mil 布,落回 EasyEDA 后 JLCPCB DRC(6mil 下限)边界处零容差 → 几处违规。把 DSN 间距**预抬**到
    8.5mil 让 Freerouting 留余量,布完落回即 **DRC 全过**(NE555 实测 6.03→DRC False,8.5→DRC True)。

    **历史局限(已被 _apply_jlc_rules 取代)**:本函数只改 structure 段的 `(clear N)`,而**每个网类**
    `(class .. (rule (clearance N)))` 仍留 4.02mil。Freerouting 实际**优先吃网类 clearance**(覆盖
    structure 默认)→ 仍可能贴着 4mil 布,低于 JLC 6mil 下限。新板请用 `route_with_freerouting(jlc=True)`。
    """
    import re
    txt = open(dsn_path, "r", encoding="utf-8", errors="ignore").read()
    txt = re.sub(r"\(clear\s+[\d.]+", "(clear %s" % clear_mil, txt)
    open(dsn_path, "w", encoding="utf-8").write(txt)


# JLCPCB 2 层标准工艺(单位 mil;DSN resolution=mil 1000)。值取「下限 + 安全余量」:
#  - 线宽 10mil(=0.254mm):JLC 最小 3.5mil,常规推荐 ≥6mil;10mil 给细间距板留足铜厚余量。
#  - 间距 8mil:JLC 最小/推荐 6mil;预抬到 8mil 让布线落回 EasyEDA 后过 6mil DRC 零违规。
#  - 过孔 外径 24mil(=0.6mm)/ 钻孔 11.8mil(=0.3mm):JLC 标准过孔,annular ring 充足。
JLC_2LAYER = {"track_mil": 10.0, "clear_mil": 8.0, "via_pad_mil": 24.0, "via_hole_mil": 11.8}


def _apply_jlc_rules(dsn_path, profile=JLC_2LAYER):
    """把**完整 JLC 制造规则**写进 DSN——比 _bump_clearance 多覆盖三处真盲点,让 Freerouting 全程按
    嘉立创口径布线。返回实测改动计数 dict 供断言。

    覆盖(逐一为之前会漏的真盲点):
      1. structure `(rule(clear N..))` 全部 → clear_mil(含 default_smd / smd_smd 子类型)。
      2. structure `(rule(width N))` → track_mil。
      3. **每个网类** `(class .. (rule (clearance N) (width N)))` 的 clearance/width 一并改——
         这是旧 _bump_clearance 的真盲点:网类 clearance 留在 4.02mil 且**优先级高于 structure 默认**,
         Freerouting 实际贴 4mil 布 → 落回 JLC 6mil 下限边界违规。必须同步抬。
      4. 过孔 padstack `(shape(circle <layer> D ..))` 的外径 → via_pad_mil(JLC 0.6mm 标准过孔)。
    """
    import re
    txt = open(dsn_path, "r", encoding="utf-8", errors="ignore").read()
    cm, tw, vp = profile["clear_mil"], profile["track_mil"], profile["via_pad_mil"]
    n = {"clear": 0, "width": 0, "class_clearance": 0, "class_width": 0, "via_pad": 0}

    def _c(m):
        n["clear"] += 1
        return "(clear %s" % cm
    txt = re.sub(r"\(clear\s+[\d.]+", _c, txt)

    def _w(m):
        n["width"] += 1
        return "(rule(width %s))" % tw
    txt = re.sub(r"\(rule\(width\s+[\d.]+\)\)", _w, txt)

    def _cc(m):
        n["class_clearance"] += 1
        return "(clearance %s)" % cm
    txt = re.sub(r"\(clearance\s+[\d.]+\)", _cc, txt)

    def _cw(m):
        n["class_width"] += 1
        return "(width %s)" % tw
    # 网类 rule 内的 (width N)(与 structure 的 (rule(width N)) 已先行处理过、形态不同)
    txt = re.sub(r"\(width\s+[\d.]+\)", _cw, txt)

    def _vp(m):
        n["via_pad"] += 1
        return "(shape(circle %s %s" % (m.group(1), vp)
    # 仅改 via padstack 的圆;焊盘 padstack 圆形态带额外 "0 0" 偏移参数,正则不匹配,天然规避
    txt = re.sub(r"\(shape\(circle\s+(\w+)\s+24(?:\.\d+)?\b", _vp, txt)

    open(dsn_path, "w", encoding="utf-8").write(txt)
    return n


def route_with_freerouting(base="DAO_FR", clear_mil=8.5, jlc=True, profile=JLC_2LAYER):
    """在**当前已打开的未布线 PCB**上跑完整闭环。返回 {dsn, ses, tracks, drc, jlc_rules}。

    jlc=True(默认):把**完整 JLC 制造规则**(structure+网类 clearance/width+过孔外径)写进 DSN,
        让 Freerouting 全程按嘉立创口径布线(见 _apply_jlc_rules)。这覆盖了旧 clear_mil 路径漏掉的
        **网类 clearance(4mil)** 盲点,是真正按 JLC 口径布线的正解。
    jlc=False:退回旧 `_bump_clearance(clear_mil)`,只抬 structure clearance(保留作对照/回归用)。
    """
    f = eda_flow.Flow()
    dsn = os.path.join(HOME, base + ".dsn")
    ses = os.path.join(HOME, base + ".ses")
    f.export_dsn(dsn, name=base)
    rules = None
    if jlc:
        rules = _apply_jlc_rules(dsn, profile)
    elif clear_mil:
        _bump_clearance(dsn, clear_mil)
    out = run_freerouting(dsn, ses)
    if not out:
        return {"dsn": dsn, "ses": None, "tracks": 0, "drc": False, "jlc_rules": rules,
                "err": "freerouting no SES"}
    tracks = f.import_ses(ses)
    f.eda.call("pcb_Document.save", timeout=20)
    time.sleep(1)
    try:
        drc = f.drc_check(timeout=90)
    except Exception as ex:
        drc = "ERR:" + str(ex)[:50]
    return {"dsn": dsn, "ses": ses, "tracks": tracks, "drc": drc}


if __name__ == "__main__":
    import json
    print(json.dumps(route_with_freerouting(), ensure_ascii=False))
