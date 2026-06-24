"""install — 静默种因之具.

道常无为而无不为. 此模块自动种下"未来用户启 EDA 即全链路自通"之因:

  - **agent 准入快捷方式** (Windows .lnk)
       公共桌面 / 用户桌面 / 开始菜单中, 立 "嘉立创EDA Pro (Agent准入)"
       Target 同原 lceda-pro.exe, 但 Arguments 加 `--remote-debugging-port=9222`
       不删原快捷方式, 仅旁立副本. 用户欲深用 agent 时双击之即可,
       agent 自此即可 CDP 直入 _MSG_BUS2_EXTAPI_ 之活体.

  - **扩展导入提示** (.eext)
       检测 dist/lceda-bridge.eext 是否新鲜, 旧则 rebuild.
       报告"已建好之 .eext 待用户一次导入" — 我无法绕 EDA 扩展管理器自动安装,
       但可清晰指引.

  - **桥进程长驻** (`:9907`)
       检测 `lceda_bridge_server.py` 是否在跑, 不在则后台起. 用户启 EDA 时,
       .eext (含 auto-connect) 自连此桥.

道德经:
   "善建者不拔, 善抱者不脱, 子孙以祭祀不辍."
   "深根固柢, 长生久视之道."

本模块函数皆 idempotent — 调多次不害.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_DEBUG_PORT = 9222
DEFAULT_BRIDGE_PORT = 9907
SHORTCUT_NAME = "嘉立创EDA Pro (Agent准入).lnk"
EEXT_NAME = "lceda-bridge.eext"


# ──────────────────────────────────────────────────────────
# 报告模型
# ──────────────────────────────────────────────────────────
@dataclass
class InstallState:
    """install 当下状态全息."""
    platform: str = field(default_factory=lambda: platform.system())

    # 快捷方式
    shortcut_path: Optional[str] = None        # 已存在或我们刚建之 .lnk 全路径
    shortcut_target: Optional[str] = None      # 其指向的 lceda-pro.exe
    shortcut_args: Optional[str] = None        # Arguments
    shortcut_has_debug_port: bool = False      # 含 --remote-debugging-port
    shortcut_created_now: bool = False         # 此次调用建的

    # .eext
    eext_path: Optional[str] = None            # dist/lceda-bridge.eext
    eext_size: int = 0
    eext_version: Optional[str] = None         # 从 extension.json 读
    eext_age_seconds: Optional[float] = None
    eext_built_now: bool = False               # 此次调用建的

    # 桥
    bridge_running: bool = False
    bridge_pid: Optional[int] = None
    bridge_started_now: bool = False

    # 原快捷方式 (参考)
    original_shortcuts: list[str] = field(default_factory=list)

    # 备注
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────
# Windows 快捷方式 (COM)
# ──────────────────────────────────────────────────────────
_PS_CREATE_LNK = r"""
$lnkPath = "{lnk}"
$target  = "{exe}"
$args    = "{args}"
$wd      = "{wd}"
$desc    = "{desc}"
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = $target
$lnk.Arguments = $args
$lnk.WorkingDirectory = $wd
$lnk.IconLocation = "$target,0"
$lnk.Description = $desc
$lnk.Save()
Write-Host "OK: $lnkPath"
"""

_PS_READ_LNK = r"""
$lnkPath = "{lnk}"
if (Test-Path $lnkPath) {{
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($lnkPath)
    $obj = @{{
        target = $lnk.TargetPath
        args = $lnk.Arguments
        wd = $lnk.WorkingDirectory
        desc = $lnk.Description
    }}
    $obj | ConvertTo-Json -Compress
}} else {{
    Write-Host "(none)"
}}
"""


def _run_pwsh(script: str, timeout: float = 10.0) -> tuple[int, str, str]:
    """跑 pwsh 脚本, 返 (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _read_lnk(lnk_path: Path) -> Optional[dict]:
    """读 .lnk 之 target/args/wd/desc. 不存在则 None."""
    if platform.system() != "Windows":
        return None
    if not lnk_path.exists():
        return None
    script = _PS_READ_LNK.format(lnk=str(lnk_path).replace("\\", "\\\\"))
    code, out, err = _run_pwsh(script)
    if code != 0 or not out or out == "(none)":
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def _public_desktop() -> Path:
    """公共桌面 (所有用户可见)."""
    return Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"


def _user_desktop() -> Path:
    """当前用户桌面."""
    return Path(os.environ["USERPROFILE"]) / "Desktop"


def _start_menu_programs() -> Path:
    """开始菜单 → 程序 (公共)."""
    return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


_LNK_NAME_HINTS = ("lceda", "嘉立创", "eda", "jlc")


def find_original_shortcuts() -> list[Path]:
    """找用户已有之 lceda-pro 原快捷方式 (供参考, 不动).

    速度关键: 先按文件名预筛 (不起 pwsh), 再批读 target — 一次 pwsh 调用读多.
    """
    if platform.system() != "Windows":
        return []

    # 1) 预筛 — 按名含 'lceda'/'嘉立创'/'eda'/'jlc' 收集候选 .lnk (快, 不起 pwsh)
    candidates: list[Path] = []
    for base in (
        _public_desktop(),
        _user_desktop(),
        _start_menu_programs(),
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ):
        if not base or not base.exists():
            continue
        try:
            for lnk in base.rglob("*.lnk"):
                n_low = lnk.name.lower()
                if any(h in n_low for h in _LNK_NAME_HINTS) and SHORTCUT_NAME not in lnk.name:
                    candidates.append(lnk)
        except (OSError, PermissionError):
            continue

    if not candidates:
        return []

    # 2) 一次 pwsh 调用批读所有候选 (而非 N 次)
    # 构造 PS 脚本数组 + 输出 JSON
    paths_json = json.dumps([str(p) for p in candidates], ensure_ascii=False)
    script = r"""
$paths = '""" + paths_json.replace("'", "''") + r"""' | ConvertFrom-Json
$ws = New-Object -ComObject WScript.Shell
$results = @()
foreach ($p in $paths) {
    try {
        $lnk = $ws.CreateShortcut($p)
        $results += @{
            path = $p
            target = $lnk.TargetPath
        }
    } catch {}
}
$results | ConvertTo-Json -Compress -AsArray
"""
    try:
        code, out, err = _run_pwsh(script, timeout=20.0)
        if code != 0 or not out:
            return []
        data = json.loads(out) if out.strip().startswith(("[", "{")) else []
        if isinstance(data, dict):
            data = [data]
        found = []
        for item in data:
            t = (item.get("target") or "").lower()
            if "lceda-pro" in t:
                found.append(Path(item.get("path")))
        return found
    except Exception:
        return []


def find_agent_shortcut() -> Optional[Path]:
    """找已建之 Agent 准入 .lnk (优先公共桌面)."""
    if platform.system() != "Windows":
        return None
    for base in (_public_desktop(), _user_desktop(), _start_menu_programs()):
        if not base or not base.exists():
            continue
        cand = base / SHORTCUT_NAME
        if cand.exists():
            return cand
    return None


def create_agent_shortcut(
    lceda_exe: str,
    debug_port: int = DEFAULT_DEBUG_PORT,
    target_dir: Optional[Path] = None,
    overwrite: bool = False,
) -> Optional[Path]:
    """建 'Agent 准入' 快捷方式. Windows only.

    target_dir 默认 = 公共桌面 (与原 lceda-pro 快捷方式同处, 用户一望即见).
    返回创建之 .lnk 路径, 或 None (失败/非 Windows).

    幂等: 若已存在且含 debug-port, 不重建; 若 overwrite=True 强重.
    """
    if platform.system() != "Windows":
        return None
    if not lceda_exe or not Path(lceda_exe).exists():
        return None

    # 优先公共桌面 (与原快捷方式齐, 用户一望即见)
    if target_dir is None:
        candidates = [_public_desktop(), _user_desktop()]
        target_dir = next((d for d in candidates if d.exists()), None)
    if target_dir is None or not target_dir.exists():
        return None

    lnk_path = target_dir / SHORTCUT_NAME

    # 幂等检查
    if lnk_path.exists() and not overwrite:
        info = _read_lnk(lnk_path)
        if info and "remote-debugging-port" in (info.get("args") or ""):
            return lnk_path  # 已就位

    args = f"--remote-debugging-port={debug_port} --remote-allow-origins=*"
    desc = "嘉立创EDA Pro (Agent 准入版) — 启 CDP debug 端口, agent 可深接管. 道法自然, 用户欲深用 agent 时双击之."
    wd = str(Path(lceda_exe).parent)

    # PowerShell escape: backslash in lnk_path
    def _esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '`"')

    script = _PS_CREATE_LNK.format(
        lnk=_esc(str(lnk_path)),
        exe=_esc(lceda_exe),
        args=_esc(args),
        wd=_esc(wd),
        desc=_esc(desc),
    )
    code, out, err = _run_pwsh(script, timeout=15.0)
    if code != 0:
        return None
    if lnk_path.exists():
        return lnk_path
    return None


# ──────────────────────────────────────────────────────────
# .eext 构建 / 检查
# ──────────────────────────────────────────────────────────
def _eext_path() -> Path:
    return ROOT / "dist" / EEXT_NAME


def _ext_manifest_version() -> Optional[str]:
    p = ROOT / "L2_extension" / "extension.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def _src_newer_than_eext(eext: Path) -> bool:
    """L2_extension/ 中任一文件比 .eext 新?"""
    if not eext.exists():
        return True
    eext_mtime = eext.stat().st_mtime
    src_dir = ROOT / "L2_extension"
    if not src_dir.exists():
        return False
    try:
        for p in src_dir.rglob("*"):
            if p.is_file() and p.stat().st_mtime > eext_mtime:
                return True
    except (OSError, PermissionError):
        pass
    return False


def ensure_eext_fresh() -> tuple[Optional[Path], bool]:
    """确保 dist/lceda-bridge.eext 与源同步. 返 (path, built_now)."""
    eext = _eext_path()
    if not eext.exists() or _src_newer_than_eext(eext):
        # 触发 build_eext.py
        build_script = ROOT / "build_eext.py"
        if not build_script.exists():
            return (eext if eext.exists() else None), False
        proc = subprocess.run(
            [sys.executable, str(build_script)],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30.0,
        )
        if proc.returncode != 0:
            return (eext if eext.exists() else None), False
        return eext if eext.exists() else None, True
    return eext, False


# ──────────────────────────────────────────────────────────
# 桥进程
# ──────────────────────────────────────────────────────────
def _bridge_pid_from_file() -> Optional[int]:
    p = ROOT / ".bridge.pid"
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except (ValueError, OSError):
        return None


def _bridge_alive(port: int = DEFAULT_BRIDGE_PORT) -> tuple[bool, Optional[int]]:
    """桥是否在跑? 通过 /ping 探."""
    import urllib.request as ur
    opener = ur.build_opener(ur.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/ping", timeout=2) as r:
            if r.status == 200:
                data = json.loads(r.read())
                return True, data.get("pid")
    except Exception:
        pass
    return False, None


def ensure_bridge_running(port: int = DEFAULT_BRIDGE_PORT) -> tuple[bool, Optional[int], bool]:
    """确保桥在跑. 返 (alive, pid, started_now)."""
    alive, pid = _bridge_alive(port)
    if alive:
        return True, pid, False
    # 起之
    server_py = ROOT / "lceda_bridge_server.py"
    if not server_py.exists():
        return False, None, False
    # 后台启 (Windows: CREATE_NO_WINDOW, detached)
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = 0x08000000  # CREATE_NO_WINDOW
        creationflags |= 0x00000200  # CREATE_NEW_PROCESS_GROUP
    try:
        proc = subprocess.Popen(
            [sys.executable, str(server_py)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=creationflags if platform.system() == "Windows" else 0,
            close_fds=True,
        )
    except Exception:
        return False, None, False
    # 等启
    for _ in range(20):  # 10s
        time.sleep(0.5)
        alive, pid = _bridge_alive(port)
        if alive:
            return True, pid, True
    return False, proc.pid, True


# ──────────────────────────────────────────────────────────
# 顶层 install — 一行尽种因
# ──────────────────────────────────────────────────────────
def survey_and_seed(
    debug_port: int = DEFAULT_DEBUG_PORT,
    bridge_port: int = DEFAULT_BRIDGE_PORT,
    seed_shortcut: bool = True,
    seed_eext: bool = True,
    seed_bridge: bool = True,
    overwrite_shortcut: bool = False,
) -> InstallState:
    """一行: 检 + 补 + 报. 用户什么都不需做.

    seed_*=False 即只检不补, 用于 dry-run / 快速诊断.
    """
    from . import env_finder  # 避免顶部 import 循环

    state = InstallState()
    env = env_finder.discover()

    # 1. 找原快捷方式 (参考, 不动)
    originals = find_original_shortcuts()
    state.original_shortcuts = [str(p) for p in originals]

    # 2. agent 准入快捷方式
    if seed_shortcut and env.lceda_exe:
        existing = find_agent_shortcut()
        if existing and not overwrite_shortcut:
            info = _read_lnk(existing)
            state.shortcut_path = str(existing)
            if info:
                state.shortcut_target = info.get("target")
                state.shortcut_args = info.get("args")
                state.shortcut_has_debug_port = "remote-debugging-port" in (info.get("args") or "")
        else:
            new_lnk = create_agent_shortcut(
                env.lceda_exe, debug_port=debug_port, overwrite=overwrite_shortcut
            )
            if new_lnk:
                state.shortcut_created_now = True
                state.shortcut_path = str(new_lnk)
                info = _read_lnk(new_lnk)
                if info:
                    state.shortcut_target = info.get("target")
                    state.shortcut_args = info.get("args")
                    state.shortcut_has_debug_port = "remote-debugging-port" in (info.get("args") or "")
            else:
                state.notes.append("无法建 Agent 准入快捷方式 (非 Windows 或 lceda_exe 找不到)")
    elif not env.lceda_exe:
        state.notes.append("env_finder 未定位 lceda_exe, 跳过快捷方式建立")

    # 3. .eext 构建检查
    if seed_eext:
        eext_p, built_now = ensure_eext_fresh()
        if eext_p and eext_p.exists():
            state.eext_path = str(eext_p)
            state.eext_size = eext_p.stat().st_size
            state.eext_age_seconds = max(0.0, time.time() - eext_p.stat().st_mtime)
            state.eext_built_now = built_now
        else:
            state.notes.append(".eext 构建失败或源缺失")
        state.eext_version = _ext_manifest_version()

    # 4. 桥
    if seed_bridge:
        alive, pid, started_now = ensure_bridge_running(port=bridge_port)
        state.bridge_running = alive
        state.bridge_pid = pid
        state.bridge_started_now = started_now

    return state


# ──────────────────────────────────────────────────────────
# 报告渲染
# ──────────────────────────────────────────────────────────
def render_report(state: InstallState) -> str:
    """渲染人可读之 install 报告."""
    lines = []
    lines.append("=" * 68)
    lines.append("  install — 静默种因报告 (善建者不拔)")
    lines.append("=" * 68)

    # 1. 原快捷方式
    if state.original_shortcuts:
        lines.append(f"\n[原快捷方式 — 不动]  ({len(state.original_shortcuts)} 个)")
        for p in state.original_shortcuts[:5]:
            lines.append(f"  · {p}")

    # 2. Agent 准入快捷方式
    lines.append(f"\n[Agent 准入快捷方式]")
    if state.shortcut_path:
        mark = "★ 此次新建" if state.shortcut_created_now else "(已存)"
        lines.append(f"  路径   : {state.shortcut_path}  {mark}")
        lines.append(f"  目标   : {state.shortcut_target}")
        lines.append(f"  参数   : {state.shortcut_args}")
        lines.append(f"  含 debug port : {'✓' if state.shortcut_has_debug_port else '✗'}")
    else:
        lines.append(f"  (未建)")

    # 3. .eext
    lines.append(f"\n[.eext 扩展包]")
    if state.eext_path:
        mark = "★ 此次重建" if state.eext_built_now else "(就位)"
        age_str = f"{state.eext_age_seconds:.0f}s 前"
        lines.append(f"  路径   : {state.eext_path}  {mark}")
        lines.append(f"  大小   : {state.eext_size:,} bytes ({state.eext_size/1024:.1f} KB)")
        lines.append(f"  版本   : {state.eext_version or '?'}")
        lines.append(f"  生成于 : {age_str}")
    else:
        lines.append(f"  (未建)")

    # 4. 桥
    lines.append(f"\n[Python 桥 :9907]")
    if state.bridge_running:
        mark = "★ 此次新启" if state.bridge_started_now else "(长驻)"
        lines.append(f"  状态   : 运行中  {mark}")
        lines.append(f"  PID    : {state.bridge_pid}")
    else:
        lines.append(f"  状态   : 未运行 (启动失败?)")

    # 5. 备注
    if state.notes:
        lines.append(f"\n[备注]")
        for n in state.notes:
            lines.append(f"  · {n}")

    lines.append("\n" + "=" * 68)
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────
# CLI 直跑
# ──────────────────────────────────────────────────────────
def _cli() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = sys.argv[1:]
    state = survey_and_seed(
        seed_shortcut=("--no-shortcut" not in args),
        seed_eext=("--no-eext" not in args),
        seed_bridge=("--no-bridge" not in args),
        overwrite_shortcut=("--overwrite" in args),
    )
    if "--json" in args:
        print(json.dumps(state.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_report(state))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
