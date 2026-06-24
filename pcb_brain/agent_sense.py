#!/usr/bin/env python3
"""
PCBBrain Agent五感扩展 — 接入台式机 remote_agent :9904
基于 E:\\道\\AI之电脑\\agent\\ 的HTTP API体系

扩展功能:
  眼+ - 通过agent截屏，比mss更可靠（支持锁屏/多显示器）
  耳+ - 通过agent执行shell命令，捕获KiCad/嘉立创EDA输出
  触+ - 通过agent打开文件管理器/资源管理器验证Gerber目录
  鼻+ - 通过agent调用kicad-cli DRC，捕获完整日志
  脑  - 通过agent执行任意Python/命令，实现远程闭环

用法:
  from agent_sense import AgentSense
  agent = AgentSense()
  if agent.alive():
      img_path = agent.screenshot_pcb_window()
      result  = agent.run_kicad_cli("pcb run-drc ...")
"""

import os
import json
import time
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any

log = logging.getLogger("agent_sense")

AGENT_BASE = os.environ.get("PCB_AGENT_BASE", "http://127.0.0.1:9904")
AGENT_TIMEOUT = 15


class AgentSense:
    """
    远程agent五感扩展
    连接台式机 remote_agent (E:\\道\\AI之电脑\\agent\\, :9904)
    所有方法在agent不可用时优雅降级，不抛异常
    """

    def __init__(self, base_url: str = AGENT_BASE):
        self.base = base_url.rstrip("/")
        self._available = None  # 懒检测

    # ─────────────────────────────────────────────────────────
    # 连通性检测
    # ─────────────────────────────────────────────────────────
    def alive(self, timeout: float = 3.0) -> bool:
        """检测agent是否在线 (timeout: 快速检测用1.0, 默认3.0)"""
        try:
            r = urllib.request.urlopen(f"{self.base}/health", timeout=timeout)
            data = json.loads(r.read())
            self._available = data.get("status") == "ok"
            if self._available:
                log.info(f"agent在线: {data.get('hostname')} user={data.get('user')}")
            return self._available
        except Exception as e:
            self._available = False
            log.debug(f"agent不可用: {e}")
            return False

    def _get(self, path: str, timeout: int = AGENT_TIMEOUT) -> Optional[Any]:
        try:
            r = urllib.request.urlopen(f"{self.base}{path}", timeout=timeout)
            return json.loads(r.read())
        except Exception as e:
            log.debug(f"GET {path} 失败: {e}")
            return None

    def _post(self, path: str, data: dict, timeout: int = AGENT_TIMEOUT) -> Optional[Any]:
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                f"{self.base}{path}", data=body,
                headers={"Content-Type": "application/json"}, method="POST"
            )
            r = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(r.read())
        except Exception as e:
            log.debug(f"POST {path} 失败: {e}")
            return None

    # ─────────────────────────────────────────────────────────
    # 眼+ — 截屏
    # ─────────────────────────────────────────────────────────
    def screenshot(self, save_path: str = None, monitor: int = 0,
                   quality: int = 85) -> Optional[str]:
        """
        眼+: 通过agent截屏（比mss更可靠，支持Remote Desktop场景）
        返回保存的图片路径，失败返回None
        """
        if save_path is None:
            save_path = str(Path(__file__).parent / "output" / f"agent_shot_{int(time.time())}.jpg")
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            url = f"{self.base}/screenshot?quality={quality}&monitor={monitor}"
            r = urllib.request.urlopen(url, timeout=AGENT_TIMEOUT)
            data = r.read()
            with open(save_path, "wb") as f:
                f.write(data)
            log.info(f"眼+: agent截屏 {len(data)//1024}KB → {save_path}")
            return save_path
        except Exception as e:
            log.warning(f"眼+: agent截屏失败: {e}")
            return None

    def screenshot_pcb_window(self, save_path: str = None) -> Optional[str]:
        """眼+: 截取当前PCB软件窗口（优先agent，兜底本地mss）"""
        path = self.screenshot(save_path)
        if path:
            return path
        from pcb_eye import eye_screenshot
        return eye_screenshot(save_path or "pcb_eye_shot.png")

    # ─────────────────────────────────────────────────────────
    # 耳+ — Shell命令执行
    # ─────────────────────────────────────────────────────────
    def run_shell(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        """
        耳+: 通过agent在台式机执行shell命令
        返回 {"stdout": ..., "stderr": ..., "returncode": ..., "success": ...}
        """
        result = self._post("/shell", {"command": command, "timeout": timeout},
                           timeout=timeout + 5)
        if result:
            log.info(f"耳+: shell执行完成 rc={result.get('returncode', '?')}")
            return result
        return {"stdout": "", "stderr": "agent不可用", "returncode": -1, "success": False}

    def run_kicad_cli(self, subcmd: str, timeout: int = 90) -> Dict[str, Any]:
        """
        耳+/鼻+: 通过agent调用kicad-cli
        subcmd 示例: 'pcb run-drc --format json --output D:/tmp/drc.json D:/tmp/board.kicad_pcb'
        """
        kicad_cli = r"D:\KICAD\bin\kicad-cli.exe"
        cmd = f'"{kicad_cli}" {subcmd}'
        log.info(f"耳+: 运行 kicad-cli {subcmd[:60]}...")
        return self.run_shell(cmd, timeout=timeout)

    # ─────────────────────────────────────────────────────────
    # 鼻+ — 远程DRC (更完整的日志捕获)
    # ─────────────────────────────────────────────────────────
    def remote_drc(self, pcb_path: str, output_json: str = None) -> Dict[str, Any]:
        """
        鼻+: 通过agent在台式机运行DRC，获取完整JSON报告
        pcb_path: 台式机本地PCB文件路径
        """
        if output_json is None:
            output_json = str(Path(pcb_path).parent / "_agent_drc.json")
        subcmd = f'pcb run-drc --format json --output "{output_json}" "{pcb_path}"'
        shell_result = self.run_kicad_cli(subcmd, timeout=90)

        # 尝试读取生成的JSON
        read_result = self._post("/read_file", {"path": output_json})
        if read_result and read_result.get("content"):
            try:
                drc_data = json.loads(read_result["content"])
                violations = drc_data.get("violations", [])
                unconnected = drc_data.get("unconnected_items", [])
                clean = len(violations) == 0 and len(unconnected) == 0
                log.info(f"鼻+: 远程DRC完成 — {len(violations)}违规 {len(unconnected)}未连接")
                return {
                    "source": "agent_remote",
                    "clean": clean,
                    "violations": violations,
                    "unconnected": unconnected,
                    "total_violations": len(violations),
                    "unconnected_count": len(unconnected),
                    "verdict": "✅ DRC通过" if clean else f"❌ {len(violations)}违规 {len(unconnected)}未连接",
                    "shell": shell_result,
                }
            except json.JSONDecodeError:
                pass

        return {
            "source": "agent_remote",
            "clean": False,
            "error": "无法读取DRC JSON报告",
            "shell": shell_result,
        }

    # ─────────────────────────────────────────────────────────
    # 触+ — 文件系统验证
    # ─────────────────────────────────────────────────────────
    def verify_path_exists(self, path: str) -> bool:
        """触+: 验证台式机路径是否存在"""
        result = self._post("/shell", {"command": f'Test-Path "{path}"'})
        if result:
            stdout = result.get("stdout", "").strip().lower()
            return "true" in stdout
        return False

    def list_remote_dir(self, path: str) -> Dict[str, Any]:
        """触+: 列出台式机目录内容"""
        cmd = f'Get-ChildItem "{path}" | Select-Object Name,Length,LastWriteTime | ConvertTo-Json'
        result = self.run_shell(cmd)
        files = []
        if result.get("stdout"):
            try:
                files = json.loads(result["stdout"])
                if isinstance(files, dict):
                    files = [files]
            except Exception:
                pass
        return {"path": path, "files": files, "count": len(files)}

    def open_gerber_in_explorer(self, gerber_dir: str) -> bool:
        """触+: 通过agent在台式机打开Gerber目录（资源管理器）"""
        result = self.run_shell(f'explorer.exe "{gerber_dir}"', timeout=10)
        return result.get("returncode", -1) in (0, None)

    # ─────────────────────────────────────────────────────────
    # 脑 — 环境信息 + 智能辅助
    # ─────────────────────────────────────────────────────────
    def sysinfo(self) -> Dict[str, Any]:
        """脑: 获取台式机系统信息"""
        return self._get("/sysinfo") or {}

    def pcb_env_check(self) -> Dict[str, Any]:
        """脑: 检查PCB相关环境（KiCad/嘉立创EDA/Python）"""
        checks = {}

        # KiCad CLI
        r = self.run_shell(r'& "D:\KICAD\bin\kicad-cli.exe" --version 2>&1', timeout=10)
        checks["kicad_cli"] = {
            "available": r.get("returncode") == 0,
            "version": r.get("stdout", "").strip()[:80],
        }

        # 嘉立创EDA
        r2 = self.run_shell(r'Test-Path "D:\lceda-pro\lceda-pro.exe"', timeout=5)
        checks["lceda"] = {
            "available": "true" in r2.get("stdout", "").lower(),
            "path": r"D:\lceda-pro\lceda-pro.exe",
        }

        # pcbnew API
        r3 = self.run_shell(
            r'python -c "import sys; sys.path.insert(0,r\"D:\KICAD\bin\Lib\site-packages\"); import pcbnew; print(pcbnew.GetBuildVersion())"',
            timeout=15
        )
        checks["pcbnew_api"] = {
            "available": r3.get("returncode") == 0,
            "version": r3.get("stdout", "").strip()[:80],
        }

        log.info(f"脑: PCB环境检查完成")
        return checks

    # ─────────────────────────────────────────────────────────
    # 综合报告
    # ─────────────────────────────────────────────────────────
    def full_agent_sense_report(self, pcb_path: str = None,
                                gerber_dir: str = None) -> Dict[str, Any]:
        """
        五感综合报告（agent增强版）
        在 pcb_eye.full_sense_report 基础上叠加agent远程感知
        """
        report = {"source": "agent_sense", "agent_base": self.base, "senses": {}}

        if not self.alive():
            report["error"] = f"agent离线 ({self.base})，请确认 remote_agent 已启动"
            report["fallback"] = "已降级到本地pcb_eye五感"
            return report

        # 眼+
        shot = self.screenshot()
        if shot:
            report["senses"]["眼+_agent_screenshot"] = shot

        # 脑: 环境检查
        env = self.pcb_env_check()
        report["senses"]["脑_env"] = env

        # 鼻+: 远程DRC
        if pcb_path:
            drc = self.remote_drc(pcb_path)
            report["senses"]["鼻+_remote_drc"] = drc

        # 触+: Gerber验证
        if gerber_dir:
            dir_info = self.list_remote_dir(gerber_dir)
            report["senses"]["触+_gerber_dir"] = dir_info
            report["senses"]["触+_gerber_count"] = dir_info["count"]

        # 综合判断
        drc_sense = report["senses"].get("鼻+_remote_drc", {})
        issues = []
        if not drc_sense.get("clean", True) and pcb_path:
            issues.append(drc_sense.get("verdict", "DRC未通过"))

        env_issues = []
        for tool, info in env.items():
            if not info.get("available"):
                env_issues.append(f"{tool}不可用")
        if env_issues:
            issues.extend(env_issues)

        report["issues"] = issues
        report["summary"] = (
            "✅ agent五感全绿，PCB环境就绪" if not issues
            else "⚠️ " + " | ".join(issues)
        )
        return report


# ─────────────────────────────────────────────────────────────
# 便捷函数（供 pcb_brain.py 直接调用）
# ─────────────────────────────────────────────────────────────
_agent: Optional[AgentSense] = None


def get_agent() -> AgentSense:
    """单例获取AgentSense实例"""
    global _agent
    if _agent is None:
        _agent = AgentSense()
    return _agent


def agent_screenshot(save_path: str = None) -> Optional[str]:
    """眼+快捷函数"""
    return get_agent().screenshot(save_path)


def agent_drc(pcb_path: str) -> Dict[str, Any]:
    """鼻+快捷函数"""
    return get_agent().remote_drc(pcb_path)


def agent_env_check() -> Dict[str, Any]:
    """脑快捷函数"""
    return get_agent().pcb_env_check()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    agent = AgentSense()
    if not agent.alive():
        print(f"⚠️  agent离线 ({agent.base})")
        print("   请确认: E:\\道\\AI之电脑\\agent\\ remote_agent 已启动(:9904)")
        sys.exit(1)

    print("\n── agent五感检测 ─────────────────────────────────")
    env = agent.pcb_env_check()
    for k, v in env.items():
        status = "✅" if v.get("available") else "❌"
        ver = v.get("version", v.get("path", ""))
        print(f"  {status} {k}: {ver[:60] if ver else '—'}")

    print("\n── 截屏测试 ──────────────────────────────────────")
    shot = agent.screenshot()
    print(f"  截屏: {shot if shot else '失败'}")

    print()
