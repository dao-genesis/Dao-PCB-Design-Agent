#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""嘉立创 EDA 专业版 · 桌面端「一键复现」部署器(零 GUI · 纯 RPC 底座的地基)。

道法自然 · 无为而无不为 —— 把上一会话「人肉摸索出来」的桌面端部署链路,沉淀成
**任意干净机器一条命令即起**的确定性脚本,让 `dao_rpc_driver` / `examples/run.py`
的全链路建板有稳定的运行时地基。

它做四件事,且**每步幂等**(已就位即跳过,可反复跑):

  1. 下载官方 Linux 客户端 zip(并行分段 · 断点续传 · 校验大小)。
  2. 解压到 ``~/lceda/client``,定位 Electron 主程序 ``lceda-pro``。
  3. 安放**离线激活文件**到 ``~/Documents/LCEDA-Pro/lceda-pro-activation.txt``
     (半离线版凭此免登录激活;**激活文件含 license,绝不入库**,经 ``--license``
     或环境变量 ``LCEDA_ACTIVATION`` 传入)。
  4. 以 CDP 远程调试端口拉起客户端(``--remote-debugging-port``),等到
     ``/json/version`` 可达;再探一次 ``_EXTAPI_ROOT_`` 命名空间数确认编辑器活。

用法::

    # 首次部署(需提供激活文件路径):
    python bootstrap_desktop.py --license /path/to/lceda-pro-activation.txt

    # 已部署过,仅(重新)拉起并自检:
    python bootstrap_desktop.py --launch-only --verify

    # 顺带备好 freerouting(DSN→SES 自动布线闭环):
    python bootstrap_desktop.py --license ... --with-freerouting

部署完成后即可::

    cd examples && PYTHONPATH=.. python3 run.py all --tries 5
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dao_platform as _plat  # noqa: E402

# ---- 平台矩阵(Linux/Windows/macOS 归一,详见 dao_platform) ------------------
PLATFORM = _plat.current()

# ---- 版本与落地路径(本源默认,可经 CLI 覆盖) -------------------------------
DEFAULT_VERSION = "3.2.149"
# 便携客户端下载地址模板由平台矩阵给出(Windows/macOS 走安装器 → None)。
DL_TMPL = PLATFORM.client_archive_url("%s") if PLATFORM.has_portable_archive else None
HOME = Path.home()
LCEDA_ROOT = HOME / "lceda"
CLIENT_DIR = LCEDA_ROOT / "client"
ZIP_PATH = LCEDA_ROOT / "lceda-pro.zip"
ACTIVATION_DST = PLATFORM.activation_dst()
DEFAULT_PORT = _plat.DEFAULT_CDP_PORT


def _log(msg: str) -> None:
    print(f"[bootstrap-desktop] {msg}", flush=True)


# ---- 1. 下载(并行分段 · 断点续传) -----------------------------------------
def _remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers.get("Content-Length", "0"))


def download(url: str, out: Path, segments: int = 8) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    size = _remote_size(url)
    if size <= 0:
        raise RuntimeError(f"无法获取远端大小: {url}")
    if out.exists() and out.stat().st_size == size:
        _log(f"已存在且大小匹配,跳过下载 ({size} bytes)")
        return
    _log(f"下载 {url}  ({size} bytes, {segments} 段并行)")
    chunk = (size + segments - 1) // segments
    done = [0] * segments
    lock = threading.Lock()

    def worker(i: int) -> None:
        start = i * chunk
        end = min(start + chunk, size) - 1
        if start > end:
            return
        part = out.with_suffix(out.suffix + f".part{i}")
        have = part.stat().st_size if part.exists() else 0
        if have >= (end - start + 1):
            with lock:
                done[i] = have
            return
        rstart = start + have
        for _ in range(50):
            try:
                req = urllib.request.Request(
                    url, headers={"Range": f"bytes={rstart}-{end}"})
                with urllib.request.urlopen(req, timeout=60) as r, \
                        open(part, "ab") as f:
                    while True:
                        buf = r.read(262144)
                        if not buf:
                            break
                        f.write(buf)
                        with lock:
                            done[i] += len(buf)
                if part.stat().st_size >= (end - start + 1):
                    return
            except Exception:
                time.sleep(3)
            rstart = start + (part.stat().st_size if part.exists() else 0)
        raise RuntimeError(f"段 {i} 下载失败")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(segments)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        time.sleep(5)
        with lock:
            tot = sum(done)
        _log(f"  {100 * tot / size:.1f}% ({tot}/{size})")
    for t in threads:
        t.join()
    with open(out, "wb") as o:
        for i in range(segments):
            part = out.with_suffix(out.suffix + f".part{i}")
            if part.exists():
                o.write(part.read_bytes())
    if out.stat().st_size != size:
        raise RuntimeError(f"下载不完整: {out.stat().st_size} != {size}")
    for i in range(segments):
        out.with_suffix(out.suffix + f".part{i}").unlink(missing_ok=True)
    _log(f"下载完成 {out} ({size} bytes)")


# ---- 2. 解压 + 定位主程序 ---------------------------------------------------
def extract(zip_path: Path, dest: Path) -> Path:
    binary = dest / PLATFORM.exe_rel_in_archive
    if binary.exists():
        _log(f"已解压,跳过 ({binary})")
        return binary
    _log(f"解压 {zip_path} -> {dest}")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
    # zip 内不保留可执行位,补回(仅 POSIX)。
    if PLATFORM.os != "windows":
        for name in ("lceda-pro", "chrome-sandbox"):
            p = dest / "lceda-pro" / name
            if p.exists():
                p.chmod(0o755)
    if not binary.exists():
        found = list(dest.rglob(PLATFORM.exe_name))
        found = [f for f in found if f.is_file() and os.access(f, os.X_OK)]
        if not found:
            raise RuntimeError("解压后未找到 lceda-pro 主程序")
        binary = found[0]
    _log(f"主程序: {binary}")
    return binary


# ---- 3. 安放离线激活文件 ----------------------------------------------------
def place_license(license_path: Path) -> None:
    if not license_path.exists():
        raise RuntimeError(f"激活文件不存在: {license_path}")
    ACTIVATION_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(license_path, ACTIVATION_DST)
    _log(f"激活文件就位 -> {ACTIVATION_DST}")


# ---- 4. 拉起客户端 + 等 CDP --------------------------------------------------
def cdp_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def editor_target(port: int) -> bool:
    """编辑器页 target 是否已出现(浏览器 CDP 活 ≠ 编辑器页已加载)。"""
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json", timeout=4) as r:
            for t in json.loads(r.read()):
                if t.get("type") == "page" and "editor" in t.get("url", ""):
                    return True
    except Exception:
        pass
    return False


def extapi_ns(port: int) -> int:
    """探编辑器渲染层 `_EXTAPI_ROOT_` 的命名空间数。

    本源教训:编辑器 page target 出现 ≠ RPC 总线就绪——target 先现,
    `_EXTAPI_ROOT_` 还要再等渲染层 bundle 跑起来才挂上(冷启动期 ns 由 0 → 90+)。
    故真正的「可建板」就绪信号是 ns>0,而非仅 target 存在。
    """
    try:
        sys.path.insert(0, str(HERE))
        import dao_eda_cdp_driver as _d  # noqa: E402
        if not editor_target(port):
            return 0
        ws = _d.connect_editor(port)
        v, e = _d.evaluate(
            ws, "window._EXTAPI_ROOT_?Object.keys(window._EXTAPI_ROOT_).length:0",
            await_promise=False, timeout=6)
        return 0 if e else int(v or 0)
    except Exception:
        return 0


def editor_ready(port: int) -> bool:
    return extapi_ns(port) > 0


def launch(binary: Path, port: int, display: str = ":0",
           wait_s: int = 60) -> None:
    if editor_ready(port):
        _log(f"客户端已在 CDP :{port} 运行且编辑器页就绪,跳过启动")
        return
    if not cdp_alive(port):
        log_path = LCEDA_ROOT / "lceda.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, **PLATFORM.launch_env(display))
        cmd = PLATFORM.launch_argv(binary, port=port)
        _log(f"启动: {PLATFORM.os} {' '.join(cmd)}")
        popen_kw = dict(stdout=None, stderr=subprocess.STDOUT,
                        cwd=str(binary.parent), env=env)
        if PLATFORM.os == "windows":
            popen_kw["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
        else:
            popen_kw["start_new_session"] = True
        with open(log_path, "wb") as logf:
            popen_kw["stdout"] = logf
            subprocess.Popen(cmd, **popen_kw)
    # 浏览器 CDP 活 ≠ 编辑器页已加载;必须等到编辑器 target 出现,
    # 否则紧随其后的 connect_editor / 首次建板会扑空(本源教训)。
    for _ in range(wait_s):
        if editor_ready(port):
            _log(f"CDP :{port} 编辑器页已就绪")
            return
        time.sleep(1)
    raise RuntimeError(f"等待 CDP :{port} 编辑器页超时,见 /tmp/lceda.log")


def verify_editor(port: int, tries: int = 30) -> dict:
    """轮询确认编辑器 RPC 总线真活(ns>0),返回命名空间数。"""
    for _ in range(tries):
        ns = extapi_ns(port)
        if ns > 0:
            _log(f"编辑器活: _EXTAPI_ROOT_ ns={ns}")
            return {"ns": ns}
        time.sleep(2)
    raise RuntimeError("超时:_EXTAPI_ROOT_ 始终未就绪 (ns=0)")


# ---- 5. Wine 通道(Linux 上部署 Windows 版 — 双系统同机共存) ------------------
WINE_PREFIX = HOME / ".wine-lceda"
WINE_PORT = 29231  # Linux 原生实例惯用 29230, Wine 实例错开
WINE_EXE = WINE_PREFIX / "drive_c" / "Program Files" / "lceda-pro" / "lceda-pro.exe"


def wine_deploy(version: str, license_path: Path | None, port: int,
                display: str, segments: int, verify: bool,
                prepare_only: bool = False) -> int:
    """在 Linux 上经 Wine 部署并拉起 Windows 版 EDA(幂等)。

    实测链路 (Ubuntu 22.04 + WineHQ stable 11.0, EDA 3.2.149):
      官方 Windows 安装器为 Inno Setup → /VERYSILENT 静默装入 C:\\Program Files\\lceda-pro;
      Electron 以 --no-sandbox --disable-gpu 拉起, CDP 照常监听, EXTAPI 94 命名空间全部就位。
      Wine 把宿主 ~/Documents 映射进 C:\\users\\<u>\\Documents — 激活文件/工程库双端共享。
    """
    if _plat.normalize_os() != "linux":
        _log("--wine 仅在 Linux 上有意义(Windows 直接原生跑)。")
        return 2
    if not shutil.which("wine"):
        _log("未找到 wine；请先安装 WineHQ stable (>=9):\n"
             "  sudo dpkg --add-architecture i386 && sudo mkdir -pm755 /etc/apt/keyrings\n"
             "  sudo wget -qO /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key\n"
             "  sudo wget -qNP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/$(lsb_release -cs)/winehq-$(lsb_release -cs).sources\n"
             "  sudo apt update && sudo apt install -y --install-recommends winehq-stable")
        return 2

    wspec = _plat.spec_for("windows")
    env = dict(os.environ, WINEPREFIX=str(WINE_PREFIX), WINEARCH="win64",
               DISPLAY=display, WINEDEBUG="-all",
               WINEDLLOVERRIDES="mscoree=d;mshtml=d")

    if not WINE_EXE.exists():
        # prefix 初始化(幂等; 旧残留锁会卡死 wineboot — 先杀残留 server)
        if not (WINE_PREFIX / "drive_c" / "windows").exists():
            subprocess.run(["wineserver", "-k"], env=env, check=False)
            _log("初始化 Wine prefix ...")
            subprocess.run(["wineboot", "-i"], env=env, check=False, timeout=300)
        installer = LCEDA_ROOT / f"lceda-pro-windows-x64-{version}.exe"
        download(wspec.installer_url(version), installer, segments=segments)
        _log("静默安装 (Inno Setup /VERYSILENT) ...")
        subprocess.run(["wine", str(installer), "/VERYSILENT", "/SP-",
                        "/SUPPRESSMSGBOXES", "/NORESTART"],
                       env=env, check=False, timeout=600)
        if not WINE_EXE.exists():
            raise RuntimeError(f"安装后未找到 {WINE_EXE}")
        _log(f"安装完成: {WINE_EXE}")
    else:
        _log(f"已安装,跳过 ({WINE_EXE})")

    if license_path:
        place_license(license_path)  # Wine 把宿主 Documents 映射进 C 盘, 落点同一处

    if prepare_only:
        _log("Wine 预置完成(--prepare-only)。")
        return 0

    if not editor_ready(port):
        if not cdp_alive(port):
            log_path = LCEDA_ROOT / "lceda-wine.log"
            _log(f"Wine 拉起 Windows 版 EDA (CDP :{port}) ...")
            with open(log_path, "wb") as logf:
                subprocess.Popen(
                    ["wine", str(WINE_EXE), "--no-sandbox", "--disable-gpu",
                     f"--remote-debugging-port={port}", "--remote-allow-origins=*"],
                    env=env, stdout=logf, stderr=subprocess.STDOUT,
                    start_new_session=True)
        for _ in range(120):
            if editor_ready(port):
                break
            time.sleep(1)
    if verify:
        verify_editor(port)
    _log(f"Windows(Wine) 端就绪: CDP :{port} — 与 Linux 原生端(:{DEFAULT_PORT})同机共存。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="嘉立创 EDA 桌面端一键复现部署器")
    ap.add_argument("--version", default=DEFAULT_VERSION)
    ap.add_argument("--license", help="离线激活文件路径(含 license,绝不入库)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--display", default=os.environ.get("DISPLAY", ":0"))
    ap.add_argument("--segments", type=int, default=8)
    ap.add_argument("--launch-only", action="store_true",
                    help="跳过下载/解压/激活,仅拉起并自检")
    ap.add_argument("--with-freerouting", action="store_true",
                    help="顺带安装 freerouting + JDK25(DSN→SES 自动布线)")
    ap.add_argument("--verify", action="store_true",
                    help="启动后探 _EXTAPI_ROOT_ 命名空间数确认编辑器活")
    ap.add_argument("--prepare-only", action="store_true",
                    help="仅预置(下载/解压/装 freerouting),不启动——供 blueprint 预烘快照")
    ap.add_argument("--wine", action="store_true",
                    help="Linux 上经 Wine 部署/拉起 Windows 版(默认 CDP :29231, 与原生端同机共存)")
    a = ap.parse_args(argv)

    lic = a.license or os.environ.get("LCEDA_ACTIVATION")

    if a.wine:
        port = a.port if a.port != DEFAULT_PORT else WINE_PORT
        return wine_deploy(a.version, Path(lic).expanduser() if lic else None,
                           port, a.display, a.segments, a.verify,
                           prepare_only=a.prepare_only)

    if not a.launch_only:
        if not PLATFORM.has_portable_archive:
            _log(f"⚠ {PLATFORM.os} 无便携下载包(走安装器);请先安装 EDA 后用 "
                 f"--launch-only,或 env LCEDA_HOME 指向安装目录。")
            return 2
        download(DL_TMPL % a.version, ZIP_PATH, segments=a.segments)
        binary = extract(ZIP_PATH, CLIENT_DIR)
        if lic:
            place_license(Path(lic).expanduser())
        elif not ACTIVATION_DST.exists():
            _log("⚠ 未提供 --license 且目标无激活文件;半离线版将无法激活。")
    else:
        binary = CLIENT_DIR / PLATFORM.exe_rel_in_archive
        if not binary.exists():
            found = [f for f in CLIENT_DIR.rglob(PLATFORM.exe_name)
                     if f.is_file() and (PLATFORM.os == "windows" or os.access(f, os.X_OK))]
            if not found:
                _log("未找到已解压客户端;请去掉 --launch-only 先完整部署。")
                return 2
            binary = found[0]

    if a.with_freerouting:
        fr = HERE.parent.parent / "dao_kicad" / "tools" / "install_freerouting.py"
        if fr.exists():
            _log("安装 freerouting + JDK25 ...")
            subprocess.run([sys.executable, str(fr)], check=False)

    if a.prepare_only:
        # blueprint 预烘:只把客户端+freerouting 落进快照,启动留到会话内
        # (运行态进程不入快照、且 initialize 期通常无 DISPLAY)。
        _log("预置完成(--prepare-only)。会话内再 --launch-only --verify 拉起。")
        return 0

    launch(binary, a.port, display=a.display)
    if a.verify:
        verify_editor(a.port)
    _log("就绪。下一步: cd examples && PYTHONPATH=.. python3 run.py all --tries 5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
