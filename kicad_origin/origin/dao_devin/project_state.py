"""project_state — 项目全貌感知 (Agent 的眼睛: 一眼看清整个 PCB 项目)。

道法自然: 写代码的 Agent 看一眼文件树+diff 即知全貌; PCB Agent 此前是盲人摸象——
板况散在活板/DRC 报告/流程产物/git 三处, 无一处归一。本模块把项目实时状态收拢成
**一次调用 / 一份文件** 的全貌:

  * snapshot()        → 结构化 dict: 板况/DRC/流程报告/产物/git/动作日志
  * render_markdown() → PROJECT_STATE.md (人与 Agent 同读的一页全貌)
  * write_state()     → 落盘 state.json + PROJECT_STATE.md (每次动作后可刷新)
  * journal()         → 动作日志 (谁在何时对板做了什么), snapshot 自带尾部

板况优先取活板 (live.summary() — GUI 内 GuiLive / 无头 LiveSession 同构); 无活板时
直接文本解析 .kicad_pcb (零 pcbnew 依赖 → CI 纯测 / 云端 Agent 免装 KiCad 也可读)。

反臆造: 所有数字取自真实文件/活板/git 回传, 解析不到的字段显式置 None, 不臆造。
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_DIRNAME = "dao_state"          # <project>/out/dao_state/
JOURNAL_NAME = "journal.jsonl"
STATE_JSON = "state.json"
STATE_MD = "PROJECT_STATE.md"
_JOURNAL_TAIL = 20


# ── 路径 ─────────────────────────────────────────────────────────────────
def state_dir(project_dir: Path) -> Path:
    d = Path(project_dir) / "out" / STATE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def detect_project_dir(board_file: str = "") -> Optional[Path]:
    """从板文件路径反推项目根 (…/<project>/out/xxx.kicad_pcb → <project>)。"""
    if not board_file:
        return None
    p = Path(board_file).resolve()
    for parent in p.parents:
        if parent.name == "out":
            return parent.parent
    return p.parent


# ── 动作日志 (journal) ───────────────────────────────────────────────────
def journal(project_dir: Path, event: Dict[str, Any]) -> Path:
    """追记一条动作 (actor/action/detail…), 自动补时间戳。"""
    path = state_dir(project_dir) / JOURNAL_NAME
    rec = {"ts": time.time(), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def journal_tail(project_dir: Path, n: int = _JOURNAL_TAIL) -> List[Dict[str, Any]]:
    path = Path(project_dir) / "out" / STATE_DIRNAME / JOURNAL_NAME
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text("utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


# ── 板况 (活板优先; 兜底纯文本解析 .kicad_pcb) ────────────────────────────
_PATTERNS = {
    "footprints": re.compile(r"^\s*\(footprint\s", re.M),
    "segments": re.compile(r"^\s*\(segment\s", re.M),
    "vias": re.compile(r"^\s*\(via\s", re.M),
    "zones": re.compile(r"^\s*\(zone\s", re.M),
    "nets": re.compile(r"^\s*\(net\s+\d+\s", re.M),
}


def parse_board_text(board_file: Path) -> Dict[str, Any]:
    """纯文本解析 .kicad_pcb 计数 (无 pcbnew 依赖, 数字来自真实文件)。"""
    text = Path(board_file).read_text("utf-8", errors="replace")
    counts = {k: len(p.findall(text)) for k, p in _PATTERNS.items()}
    return {
        "file": str(board_file),
        "footprints": counts["footprints"],
        "tracks": counts["segments"] + counts["vias"],
        "segments": counts["segments"],
        "vias": counts["vias"],
        "zones": counts["zones"],
        "nets": counts["nets"],
        "source": "file",
    }


def latest_board(project_dir: Path) -> Optional[Path]:
    """项目 out/ 下最近修改的正式板 (跳过自动保存/锁文件)。"""
    out = Path(project_dir) / "out"
    if not out.is_dir():
        return None
    boards = [p for p in out.glob("*.kicad_pcb")
              if not p.name.startswith(("_autosave", "~"))]
    return max(boards, key=lambda p: p.stat().st_mtime) if boards else None


def board_metrics(project_dir: Optional[Path] = None,
                  live: Any = None) -> Optional[Dict[str, Any]]:
    """板况: 活板在场取活板 (真实内存态), 否则解析磁盘板文件。"""
    if live is not None:
        try:
            s = live.summary()
            b = s.get("board") if isinstance(s, dict) else None
            if isinstance(b, dict):
                return {**b, "source": "live"}
        except Exception:  # noqa: BLE001
            pass
    if project_dir:
        bf = latest_board(Path(project_dir))
        if bf:
            return parse_board_text(bf)
    return None


# ── DRC / 流程报告 ───────────────────────────────────────────────────────
def drc_metrics(project_dir: Path) -> Optional[Dict[str, Any]]:
    """最近一次 kicad-cli DRC 报告 (out/ 下 *drc*.json), 解析不到则 None。"""
    out = Path(project_dir) / "out"
    if not out.is_dir():
        return None
    cands = sorted(out.rglob("*drc*.json"), key=lambda p: p.stat().st_mtime)
    if not cands:
        return None
    try:
        raw = json.loads(cands[-1].read_text("utf-8"))
    except ValueError:
        return None
    viol = raw.get("violations") or []
    sev = {"error": 0, "warning": 0}
    for v in viol:
        s = str(v.get("severity", "")).lower()
        if s in sev:
            sev[s] += 1
    return {"report": str(cands[-1]), "violations": len(viol),
            "errors": sev["error"], "warnings": sev["warning"],
            "unconnected": len(raw.get("unconnected_items") or [])}


def flow_report(project_dir: Path) -> Optional[Dict[str, Any]]:
    """native_flow 的 out/report.json (全流程真报告), 无则 None。"""
    p = Path(project_dir) / "out" / "report.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except ValueError:
        return None


# ── 产物 / git ───────────────────────────────────────────────────────────
def artifacts(project_dir: Path) -> Dict[str, Any]:
    out = Path(project_dir) / "out"
    fab = out / "fab"
    gerbers = sorted(p.name for p in fab.glob("*.g*")) if fab.is_dir() else []
    drill = sorted(p.name for p in fab.glob("*.drl")) if fab.is_dir() else []
    boards = sorted(p.name for p in out.glob("*.kicad_pcb")
                    if not p.name.startswith(("_autosave", "~"))) if out.is_dir() else []
    return {"boards": boards, "gerbers": len(gerbers), "drill": len(drill),
            "fab_ready": bool(gerbers and drill)}


def _git(args: List[str], cwd: Path) -> str:
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def git_metrics(project_dir: Path) -> Optional[Dict[str, Any]]:
    root = _git(["rev-parse", "--show-toplevel"], Path(project_dir))
    if not root:
        return None
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], Path(root))
    dirty = _git(["status", "--porcelain"], Path(root))
    log = _git(["log", "--oneline", "-5"], Path(root))
    return {"root": root, "branch": branch,
            "dirty_files": len(dirty.splitlines()) if dirty else 0,
            "recent_commits": log.splitlines()}


# ── 全貌 ─────────────────────────────────────────────────────────────────
def snapshot(project_dir: Optional[Path] = None, live: Any = None,
             journal_n: int = _JOURNAL_TAIL) -> Dict[str, Any]:
    """一次调用拿全貌。project_dir 缺省时从活板文件反推。"""
    board = board_metrics(project_dir, live=live)
    if project_dir is None and board and board.get("file"):
        project_dir = detect_project_dir(board["file"])
    pd = Path(project_dir) if project_dir else None
    snap: Dict[str, Any] = {
        "ok": True,
        "ts": time.time(),
        "project_dir": str(pd) if pd else None,
        "board": board,
        "drc": drc_metrics(pd) if pd else None,
        "flow": flow_report(pd) if pd else None,
        "artifacts": artifacts(pd) if pd else None,
        "git": git_metrics(pd) if pd else None,
        "journal": journal_tail(pd, journal_n) if pd else [],
    }
    return snap


def _fmt_ts(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def render_markdown(snap: Dict[str, Any]) -> str:
    """全貌 → 一页 Markdown (人与 Agent 同读)。"""
    L: List[str] = ["# PROJECT_STATE — 项目实时全貌", ""]
    L.append(f"- 生成时间: {_fmt_ts(snap.get('ts', time.time()))}")
    if snap.get("project_dir"):
        L.append(f"- 项目目录: `{snap['project_dir']}`")
    b = snap.get("board")
    L.append("\n## 板况 (board)")
    if b:
        L.append(f"- 来源: {'活板(内存实时)' if b.get('source') == 'live' else '板文件解析'}")
        L.append(f"- 文件: `{b.get('file', '?')}`")
        L.append(f"- 封装 {b.get('footprints')} · 走线项 {b.get('tracks')} · "
                 f"网络 {b.get('nets')} · 铜皮 {b.get('zones')}")
    else:
        L.append("- (无板 — 尚未 build 或活板未开)")
    d = snap.get("drc")
    L.append("\n## DRC")
    if d:
        L.append(f"- 违例 {d.get('violations')} (错误 {d.get('errors')} / 警告 "
                 f"{d.get('warnings')}) · 未连接 {d.get('unconnected')}")
        L.append(f"- 报告: `{d.get('report')}`")
    else:
        L.append("- (无 DRC 报告 — 跑 kicad_run_flow 或 kicad-cli drc 后自动出现)")
    f = snap.get("flow")
    L.append("\n## 流程报告 (out/report.json)")
    if f:
        route = f.get("route") or {}
        L.append(f"- 项目 {f.get('project')} · 元件 {f.get('components')} · "
                 f"网 {f.get('nets')} · 铜层 {f.get('copper_layers')}")
        L.append(f"- 布线: ok={route.get('ok')} · 余未连 {route.get('unrouted_after')}")
    else:
        L.append("- (无)")
    a = snap.get("artifacts")
    L.append("\n## 产物 (artifacts)")
    if a:
        L.append(f"- 板文件: {', '.join(a.get('boards') or []) or '(无)'}")
        L.append(f"- Gerber {a.get('gerbers')} · 钻孔 {a.get('drill')} · "
                 f"可投厂: {'✔' if a.get('fab_ready') else '✘'}")
    else:
        L.append("- (无)")
    g = snap.get("git")
    L.append("\n## git")
    if g:
        L.append(f"- 分支 `{g.get('branch')}` · 脏文件 {g.get('dirty_files')}")
        for c in (g.get("recent_commits") or [])[:5]:
            L.append(f"  - {c}")
    else:
        L.append("- (非 git 仓库)")
    j = snap.get("journal") or []
    L.append("\n## 最近动作 (journal)")
    if j:
        for e in reversed(j):
            L.append(f"- {_fmt_ts(e.get('ts', 0))} · [{e.get('actor', '?')}] "
                     f"{e.get('action', '?')} — {str(e.get('detail', ''))[:100]}")
    else:
        L.append("- (无 — 每次 AI 工具调用会自动追记)")
    L.append("")
    return "\n".join(L)


def write_state(project_dir: Path, live: Any = None) -> Dict[str, str]:
    """刷新落盘: out/dao_state/state.json + <project>/PROJECT_STATE.md。"""
    pd = Path(project_dir)
    snap = snapshot(pd, live=live)
    sd = state_dir(pd)
    (sd / STATE_JSON).write_text(
        json.dumps(snap, ensure_ascii=False, indent=1), "utf-8")
    md_path = pd / STATE_MD
    md_path.write_text(render_markdown(snap), "utf-8")
    return {"json": str(sd / STATE_JSON), "markdown": str(md_path)}
