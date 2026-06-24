#!/usr/bin/env python3
"""
PCB基础设施层 — 万法归宗之根基

"道生一" — 此文件是PCBBrain全部模块的唯一公共根基。
所有模块 import _pcb_bootstrap 即获得:
  1. Windows UTF-8控制台修复 (自动, import即生效)
  2. 统一日志配置
  3. 路径常量 (PCB_ROOT, OUTPUT_ROOT, 工具路径)
  4. 环境检测 (KiCad/freerouting/Java/pcbnew一次探测, 全局缓存)
  5. 通用工具函数

用法:
  import _pcb_bootstrap as B
  B.init_logging("my_module")
  log = B.get_logger("my_module")
  env = B.detect_env()          # 缓存, 多次调用不重复探测
  pcb = B.OUTPUT_ROOT / "my_template"
"""

import os
import sys
import json
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import lru_cache

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第一层: Windows UTF-8 (import即生效, 无需调用)
#   三重保障:
#     1) 环境变量 (利于子进程)
#     2) 控制台代码页 65001 (Windows Console API)
#     3) sys.stdout/stderr reconfigure (当前进程 I/O)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            try:
                _s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第二层: 路径常量 (全局唯一定义)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PCB_ROOT = Path(__file__).parent                          # pcb_brain/
PROJECT_ROOT = PCB_ROOT.parent                            # PCB设计/
OUTPUT_ROOT = PCB_ROOT / "output"                         # pcb_brain/output/
LOGS_DIR = PCB_ROOT / "logs"                              # pcb_brain/logs/

# 确保关键目录存在
OUTPUT_ROOT.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# 注入pcb_brain到sys.path (仅一次)
_pcb_brain_str = str(PCB_ROOT)
if _pcb_brain_str not in sys.path:
    sys.path.insert(0, _pcb_brain_str)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第三层: 日志配置 (统一格式, 一处定义)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_LOG_DATEFMT = "%H:%M:%S"
_logging_initialized = False


def init_logging(name: str = "pcb", level: int = logging.INFO) -> logging.Logger:
    """初始化日志 — 全局仅配置一次, 返回命名logger"""
    global _logging_initialized
    if not _logging_initialized:
        logging.basicConfig(
            level=level,
            format=_LOG_FORMAT,
            datefmt=_LOG_DATEFMT,
        )
        _logging_initialized = True
    return logging.getLogger(name)


def get_logger(name: str) -> logging.Logger:
    """获取命名logger (不重复初始化)"""
    return logging.getLogger(name)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第四层: 环境检测 (一次探测, 全局缓存)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# KiCad CLI 搜索路径
# 反者道之动: 不写死版本号, 用 glob 自动发现任意已装版本 (10.0/9.0/8.0...), 高版本优先
def _glob_kicad_clis() -> List[str]:
    import glob as _glob
    found: List[str] = []
    for root in (r"C:\Program Files\KiCad", r"C:\Program Files (x86)\KiCad"):
        found += _glob.glob(root + r"\*\bin\kicad-cli.exe")
    # 版本号降序 (字符串内嵌数字, 用自然序近似: 按目录名逆序)
    found.sort(reverse=True)
    return found

_KICAD_CLI_CANDIDATES = _glob_kicad_clis() + [
    r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
    r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
    r"D:\KICAD\bin\kicad-cli.exe",
    r"C:\Program Files\KiCad\bin\kicad-cli.exe",
]

# freerouting 搜索路径
_FREEROUTING_CANDIDATES = [
    PCB_ROOT / "freerouting.jar",
    Path(r"D:\freerouting\freerouting.jar"),
    Path.home() / "freerouting" / "freerouting.jar",
]

# Java 搜索路径
# freerouting 2.x 需要较新的 JDK (2.2.4 需 Java 25), 故 glob 发现系统 JDK 并按版本降序优先
def _glob_javas() -> List[str]:
    import glob as _glob
    found: List[str] = []
    for pat in (
        r"C:\Program Files\Microsoft\jdk-*\bin\java.exe",
        r"C:\Program Files\Eclipse Adoptium\jdk-*\bin\java.exe",
        r"C:\Program Files\Java\jdk-*\bin\java.exe",
        r"C:\Program Files\Java\jre-*\bin\java.exe",
    ):
        found += _glob.glob(pat)
    found.sort(reverse=True)  # 高版本优先 (jdk-25 > jdk-17)
    return found

_JAVA_CANDIDATES = [
    PCB_ROOT / "jre" / "bin" / "java.exe",
    PCB_ROOT / "jre" / "bin" / "java",
] + _glob_javas()


def _find_executable(name: str, candidates: List, check_cmd: List[str] = None) -> Optional[str]:
    """在候选路径中查找可执行文件, 找到即返回"""
    for c in candidates:
        p = Path(c)
        if p.exists():
            return str(p)
    # 尝试 PATH
    found = shutil.which(name)
    if found:
        return found
    return None


@lru_cache(maxsize=1)
def detect_env() -> Dict[str, Any]:
    """
    一次性探测全部PCB工具链环境, 结果全局缓存。

    返回:
      kicad_cli:      str|None  — kicad-cli路径
      kicad_version:  str       — KiCad版本号
      freerouting:    str|None  — freerouting.jar路径
      java:           str|None  — java可执行路径
      pcbnew_api:     bool      — pcbnew Python API是否可用
      python_version: str       — Python版本
      platform:       str       — 操作系统
    """
    env = {
        "kicad_cli": None,
        "kicad_version": "",
        "freerouting": None,
        "java": None,
        "pcbnew_api": False,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
    }

    # KiCad CLI
    cli = _find_executable("kicad-cli", _KICAD_CLI_CANDIDATES)
    if cli:
        env["kicad_cli"] = cli
        try:
            r = subprocess.run([cli, "version"], capture_output=True, text=True, timeout=5)
            env["kicad_version"] = r.stdout.strip()
        except Exception:
            env["kicad_version"] = "unknown"

    # freerouting
    for c in _FREEROUTING_CANDIDATES:
        if Path(c).exists():
            env["freerouting"] = str(c)
            break

    # Java
    java = _find_executable("java", _JAVA_CANDIDATES)
    if java:
        env["java"] = java

    # pcbnew API
    try:
        import pcbnew  # noqa: F401
        env["pcbnew_api"] = True
    except ImportError:
        env["pcbnew_api"] = False

    return env


def env_summary() -> str:
    """环境摘要 (一行文本)"""
    e = detect_env()
    parts = []
    parts.append(f"KiCad={'✅'+e['kicad_version'] if e['kicad_cli'] else '❌'}")
    parts.append(f"pcbnew={'✅' if e['pcbnew_api'] else '❌'}")
    parts.append(f"freerouting={'✅' if e['freerouting'] else '❌'}")
    parts.append(f"Java={'✅' if e['java'] else '❌'}")
    parts.append(f"Python={e['python_version']}")
    return " | ".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第五层: 通用工具函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def find_latest_pcb(template: str = "", search_dir: Path = None) -> Optional[Path]:
    """查找最新的.kicad_pcb文件"""
    root = search_dir or OUTPUT_ROOT
    if template:
        tpl_dir = root / template
        if tpl_dir.is_dir():
            pcbs = sorted(tpl_dir.glob("*.kicad_pcb"), key=lambda p: p.stat().st_mtime, reverse=True)
            if pcbs:
                return pcbs[0]
    # 全局搜索
    pcbs = sorted(root.rglob("*.kicad_pcb"), key=lambda p: p.stat().st_mtime, reverse=True)
    return pcbs[0] if pcbs else None


def ensure_output_dir(template: str) -> Path:
    """确保模板输出目录存在, 返回路径"""
    d = OUTPUT_ROOT / template
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_json_serialize(obj: Any) -> Any:
    """递归清洗对象使其可JSON序列化"""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): safe_json_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [safe_json_serialize(i) for i in obj]
    # dataclass / namedtuple / custom object
    if hasattr(obj, "__dict__"):
        return safe_json_serialize(vars(obj))
    if hasattr(obj, "_asdict"):
        return safe_json_serialize(obj._asdict())
    return str(obj)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模块自检 (python _pcb_bootstrap.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    log = init_logging("bootstrap")
    log.info("PCB基础设施层自检")
    log.info(f"PCB_ROOT:    {PCB_ROOT}")
    log.info(f"OUTPUT_ROOT: {OUTPUT_ROOT}")
    log.info(f"环境: {env_summary()}")
    env = detect_env()
    for k, v in env.items():
        log.info(f"  {k}: {v}")
    log.info("基础设施层就绪 ✅")
