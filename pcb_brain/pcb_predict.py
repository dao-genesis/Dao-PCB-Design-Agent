#!/usr/bin/env python3
"""
pcb_predict.py — 预测编码核验引擎 (Predictive-Coding Delivery Verifier)
======================================================================

道生一. 此模块为 PCBBrain 补上它一直缺失的那"一": **真正的预测误差信号**。

为什么需要它
------------
旧流水线 (`pcb_pipeline.py`) 把"阶段执行完毕、函数没抛异常"等同于"成功":

    summary = self._finalize(success=True, ...)   # 无论产物真假, 恒为 True

于是当 KiCad 不在场时, 每一阶段都静默降级:
  - 焊盘库找不到 → 生成的 .kicad_pcb **0 个 pad**
  - 无 pad → 网络无法连到引脚 → 布线 **routed=0**
  - DRC 跳过 ("no_kicad_cli") 却记 violations=0
  - Gerber 写成 "G04 Mock Gerber*" 的占位文件
而总报告仍是 "✅ 23/23 PASS"。闭环在**形式上闭合**, 在**实质上空转**。

预测编码 (Predictive Coding / Active Inference) 给出的解法
---------------------------------------------------------
人脑不靠"动作执行完了没有"来确认世界, 而靠**预测 → 观测 → 预测误差**:
  1. 生成模型 (这里是 DNA 模板, 即设计意图) **自上而下预测**产物应有的可观测不变量;
  2. 从真实产物**自下而上观测**实际值;
  3. 只有**预测误差 (surprise)** 才向上传播, 驱动下一步动作;
  4. 误差分两类 —
       · 认知性 (epistemic): "我没法观测" (工具缺位) → 动作=去补足观测手段;
       · 实质性 (pragmatic): "产物确实错了"           → 动作=去修正产物;
  5. 自由能 = Σ 精度ᵢ·误差ᵢ; 自由能=0 时闭环才真正闭合。

本模块不信任任何"状态=ok"自述, 一律**从产物文件重新反演真值**, 再与 DNA 预测对账。

用法
----
    from pcb_predict import predict_verify
    verdict = predict_verify("ams1117_power", "output/ams1117_power")
    print(verdict.delivered, verdict.free_energy)

    python pcb_predict.py ams1117_power output/ams1117_power
    python pcb_predict.py --all                 # 核验 output/ 下全部模板
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 该 Python 发行版不自动把脚本目录加入 sys.path, 与仓库其它模块保持一致手动注入
sys.path.insert(0, str(Path(__file__).parent))

# 统一 stdout 为 UTF-8 (否则在 cp1252 控制台/管道下打印中文与框线会崩)
try:
    import _pcb_bootstrap  # noqa: F401  # 复用仓库的 UTF-8/路径/环境根基
except Exception:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

try:
    from circuit_dna import CircuitDNA, DNA
except Exception:  # pragma: no cover - allow import outside pcb_brain cwd
    CircuitDNA = None  # type: ignore
    DNA = None  # type: ignore


# ─────────────────────────────────────────────────────────────
# 误差类别 — 对应 active inference 的两类动作
# ─────────────────────────────────────────────────────────────
EPISTEMIC = "epistemic"   # 观测缺失 (工具不在场) → 去补足感知
PRAGMATIC = "pragmatic"   # 产物确实错 → 去修正世界


@dataclass
class Prediction:
    """单条预测-观测对账项 (一个'预测单元')。"""
    name: str
    predicted: float
    observed: float
    error: float
    precision: float          # 精度权重 (该误差有多重要 / 多可信)
    kind: str                 # EPISTEMIC | PRAGMATIC | ""(无误差)
    detail: str = ""

    @property
    def surprise(self) -> float:
        """精度加权的预测误差 (free-energy 的一项)。"""
        return self.precision * self.error


@dataclass
class Verdict:
    """整次交付的核验结论。"""
    template: str
    output_dir: str
    predictions: List[Prediction] = field(default_factory=list)
    observed: Dict[str, float] = field(default_factory=dict)
    predicted: Dict[str, float] = field(default_factory=dict)
    error: str = ""

    @property
    def free_energy(self) -> float:
        return round(sum(p.surprise for p in self.predictions), 3)

    @property
    def delivered(self) -> bool:
        """自由能为 0 才算真正交付 (实质闭环)。"""
        return (not self.error) and self.free_energy == 0.0

    @property
    def confidence(self) -> float:
        """0~1 交付置信度, 仅用于展示。"""
        return round(1.0 / (1.0 + self.free_energy), 3)

    @property
    def surprises(self) -> List[Prediction]:
        """按精度加权误差降序的非零误差项。"""
        return sorted([p for p in self.predictions if p.error > 0],
                      key=lambda p: p.surprise, reverse=True)

    @property
    def next_action(self) -> str:
        """主导误差 → 下一步该做什么 (active inference: 最小化最大 surprise)。"""
        s = self.surprises
        if self.error:
            return f"模型缺失: {self.error}"
        if not s:
            return "闭环已实质闭合, 无预测误差。可推进真实打样核验。"
        top = s[0]
        if top.kind == EPISTEMIC:
            return f"[认知误差·去补足观测] {top.name}: {top.detail}"
        return f"[实质误差·去修正产物] {top.name}: {top.detail}"

    def to_dict(self) -> Dict[str, object]:
        return {
            "template": self.template,
            "delivered": self.delivered,
            "free_energy": self.free_energy,
            "confidence": self.confidence,
            "predicted": self.predicted,
            "observed": self.observed,
            "surprises": [
                {
                    "name": p.name, "predicted": p.predicted, "observed": p.observed,
                    "error": p.error, "precision": p.precision, "surprise": p.surprise,
                    "kind": p.kind, "detail": p.detail,
                }
                for p in self.surprises
            ],
            "next_action": self.next_action,
            "error": self.error,
        }


# ─────────────────────────────────────────────────────────────
# 自下而上观测 — 从真实产物反演真值 (不信任任何自述状态)
# ─────────────────────────────────────────────────────────────
def _count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


def observe_pcb(pcb_path: Path) -> Dict[str, int]:
    """从 .kicad_pcb 文本反演: 封装数 / 焊盘数 / 已连网焊盘 / 走线段数 / 声明网络数。"""
    if not pcb_path.exists():
        return {"footprints": 0, "pads": 0, "pads_netted": 0,
                "segments": 0, "nets_declared": 0, "file_ok": 0}
    text = pcb_path.read_text(encoding="utf-8", errors="ignore")
    if text.strip().startswith("# PCB placeholder"):
        return {"footprints": 0, "pads": 0, "pads_netted": 0,
                "segments": 0, "nets_declared": 0, "file_ok": 0}
    # 网络声明在文件头 (首个 footprint 之前)
    fp_start = text.find("(footprint ")
    header = text if fp_start < 0 else text[:fp_start]
    # 精确统计"接入网络的焊盘": 仅数 (pad ..) 块内含 (net ..) 的焊盘,
    # 不把走线/过孔自带的 (net ..) 计进来 (否则与 pad_endpoints 预测错配)。
    pads_netted = 0
    for chunk in text.split("(pad ")[1:]:
        cut = len(chunk)
        for marker in ("(footprint ", "(segment", "(via", "(zone", "(gr_"):
            idx = chunk.find(marker)
            if idx != -1:
                cut = min(cut, idx)
        if "(net " in chunk[:cut]:
            pads_netted += 1
    return {
        "footprints": _count(r"\(footprint ", text),
        "pads": _count(r"\(pad ", text),
        "pads_netted": pads_netted,
        "segments": _count(r"\(segment ", text) + _count(r"\(via ", text),
        "nets_declared": _count(r"\(net \d+ ", header),  # 含 net 0
        "file_ok": 1,
    }


def observe_gerber(gerber_dir: Path) -> Dict[str, int]:
    """从 gerber/ 反演: 是否为 Mock 占位 / 真实铜层文件数 / 含光圈定义的文件数。"""
    if not gerber_dir.exists():
        return {"files": 0, "mock_files": 0, "real_copper": 0}
    files = [f for f in gerber_dir.iterdir() if f.is_file()]
    mock = 0
    real_copper = 0
    for f in files:
        try:
            head = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            head = ""
        # 只认显式 Mock 占位标记; 真实但稀疏的层 (空底铜/丝印) 不算 mock
        if "Mock Gerber" in head:
            mock += 1
        # 真实 Gerber 铜层含光圈定义 %ADD 与绘制指令 (D01/D02/D03 + 坐标)
        if "_Cu" in f.name or f.name.upper().endswith((".GTL", ".GBL")):
            if "%ADD" in head and re.search(r"X-?\d+Y-?\d+D0[123]", head):
                real_copper += 1
    return {"files": len(files), "mock_files": mock, "real_copper": real_copper}


def observe_drc(report: Optional[Dict]) -> Tuple[str, int]:
    """从 pipeline_report.json 的 drc 字段反演真实 DRC 状态与违规数。"""
    if not report:
        return ("absent", -1)
    drc = report.get("drc") or {}
    if not isinstance(drc, dict):
        return ("absent", -1)
    status = str(drc.get("status", "absent"))
    raw = drc.get("violations", drc.get("violations_electrical", 0))
    try:
        violations = int(raw) if not isinstance(raw, (list, tuple)) else len(raw)
    except (TypeError, ValueError):
        violations = 0
    return (status, violations)


# ─────────────────────────────────────────────────────────────
# 自上而下预测 — 由 DNA (设计意图) 推出产物应有的不变量
# ─────────────────────────────────────────────────────────────
def predict_from_dna(dna: "DNA") -> Dict[str, float]:
    n_components = len(dna.components)
    n_nets = len(dna.nets)
    # 每条网络的 (ref,pad) 端点总数 = 应被接入网络的焊盘数下界
    pad_endpoints = sum(len(eps) for eps in dna.nets.values())
    # 每条网络至少需 (端点-1) 段连接才能全连通 → 必需走线数下界
    required_routes = sum(max(0, len(eps) - 1) for eps in dna.nets.values())
    return {
        "components": float(n_components),
        "nets": float(n_nets),
        "pad_endpoints": float(pad_endpoints),
        "required_routes": float(required_routes),
    }


# ─────────────────────────────────────────────────────────────
# 对账 — 预测 vs 观测 → 预测误差 → 自由能
# ─────────────────────────────────────────────────────────────
# 精度权重: 越底层 / 越能"证伪交付"的, 权重越高
P_COMPONENTS = 1.0
P_PADS = 2.0
P_NETS = 2.0
P_ROUTING = 1.5
P_DRC = 3.0
P_GERBER = 3.0


def reconcile(dna: "DNA", output_dir: Path) -> Verdict:
    template = dna.name
    pred = predict_from_dna(dna)

    pcb_path = output_dir / f"{template}.kicad_pcb"
    obs_pcb = observe_pcb(pcb_path)
    obs_gerber = observe_gerber(output_dir / "gerber")

    report = None
    rp = output_dir / "pipeline_report.json"
    if rp.exists():
        try:
            report = json.loads(rp.read_text(encoding="utf-8", errors="ignore"))
        except (json.JSONDecodeError, OSError):
            report = None
    drc_status, drc_violations = observe_drc(report)

    observed = {
        "footprints": obs_pcb["footprints"],
        "pads": obs_pcb["pads"],
        "pads_netted": obs_pcb["pads_netted"],
        "segments": obs_pcb["segments"],
        "nets_declared": max(0, obs_pcb["nets_declared"] - 1),  # 扣掉 net 0
        "gerber_files": obs_gerber["files"],
        "gerber_mock": obs_gerber["mock_files"],
        "gerber_real_copper": obs_gerber["real_copper"],
        "drc_status": drc_status,
        "drc_violations": drc_violations,
    }

    preds: List[Prediction] = []

    # 1) 封装数: 产物里的封装应等于 DNA 元件数
    err = abs(pred["components"] - obs_pcb["footprints"])
    preds.append(Prediction(
        "封装数", pred["components"], obs_pcb["footprints"], err, P_COMPONENTS,
        PRAGMATIC if err else "",
        f"DNA 期望 {int(pred['components'])} 元件, 产物仅 {obs_pcb['footprints']} 个封装"))

    # 2) 焊盘接网: 应接入网络的焊盘数 (这是布线/DRC 的地基)
    missing_pads = max(0.0, pred["pad_endpoints"] - obs_pcb["pads_netted"])
    preds.append(Prediction(
        "焊盘接网", pred["pad_endpoints"], obs_pcb["pads_netted"], missing_pads, P_PADS,
        PRAGMATIC if missing_pads else "",
        (f"应有 {int(pred['pad_endpoints'])} 个焊盘接入网络, 实测 {obs_pcb['pads_netted']} 个"
         + ("; 封装库未解析→0 焊盘, 后续布线/DRC/Gerber 全部落空" if obs_pcb["pads"] == 0 else ""))))

    # 3) 网络连通: 声明的每条网络都应在板上真正连到焊盘
    err = max(0.0, pred["nets"] - observed["nets_declared"])
    preds.append(Prediction(
        "网络连通", pred["nets"], observed["nets_declared"], err, P_NETS,
        PRAGMATIC if err else "",
        f"DNA 定义 {int(pred['nets'])} 条网络, 产物声明 {observed['nets_declared']} 条"))

    # 4) 布线: 必需的连接都应有铜走线
    if pred["required_routes"] > 0:
        err = pred["required_routes"] if obs_pcb["segments"] == 0 \
            else max(0.0, pred["required_routes"] - obs_pcb["segments"])
    else:
        err = 0.0
    preds.append(Prediction(
        "布线", pred["required_routes"], obs_pcb["segments"], err, P_ROUTING,
        PRAGMATIC if err else "",
        f"至少需 {int(pred['required_routes'])} 段走线, 产物 {obs_pcb['segments']} 段 (routed=0 即未布线)"))

    # 5) DRC: 必须由真实工具跑出 violations=0; 工具缺位 = 认知误差(我们是盲的)
    if drc_status in ("no_kicad_cli", "skipped", "mock", "absent", "error"):
        err = max(1.0, pred["nets"])     # 未知即最大惊异, 量级与设计规模相称
        preds.append(Prediction(
            "DRC", 0.0, 0.0, err, P_DRC, EPISTEMIC,
            f"DRC 状态='{drc_status}', 并未真正执行 → violations=0 不可信, 设计是否合规未知"))
    elif drc_violations > 0:
        preds.append(Prediction(
            "DRC", 0.0, float(drc_violations), float(drc_violations), P_DRC, PRAGMATIC,
            f"真实 DRC 发现 {drc_violations} 处违规"))
    else:
        preds.append(Prediction("DRC", 0.0, 0.0, 0.0, P_DRC, "", "真实 DRC 通过, 0 违规"))

    # 6) Gerber: 必须是含光圈/铜的真实文件, 而非 Mock 占位
    if obs_gerber["files"] == 0:
        err = 1.0
        detail = "无 Gerber 产物"
        kind = PRAGMATIC
    elif obs_gerber["mock_files"] > 0 or obs_gerber["real_copper"] == 0:
        err = float(max(1, obs_gerber["mock_files"]))
        detail = (f"{obs_gerber['mock_files']} 个 Mock 占位 Gerber, "
                  f"真实含铜层 {obs_gerber['real_copper']} 个 → 不可制造")
        kind = EPISTEMIC if obs_gerber["mock_files"] > 0 else PRAGMATIC
    else:
        err = 0.0
        detail = f"真实 Gerber, {obs_gerber['real_copper']} 个含铜层"
        kind = ""
    preds.append(Prediction("Gerber", 1.0, float(obs_gerber["real_copper"]), err, P_GERBER, kind, detail))

    return Verdict(template=template, output_dir=str(output_dir),
                   predictions=preds, observed=observed, predicted=pred)


# ─────────────────────────────────────────────────────────────
# 反向传播 — 把预测误差翻译成"下一步该改什么" (active inference 动作)
# ─────────────────────────────────────────────────────────────
# 动作语义 (供 pipeline_converge 据此修正生成过程并重跑):
ACT_COVER_PADS = "cover_pads"    # 焊盘接网误差 → 依需求别名/合成焊盘使端点可接网
ACT_REROUTE = "reroute"          # 布线误差(焊盘已接网) → 换布线策略重跑
ACT_NONE = "none"                # 无可由重跑消解的实质误差 (已闭合 / 仅认知误差)


def corrective_action(verdict: Verdict) -> Dict[str, object]:
    """把主导预测误差反演为一个可执行的修正动作 (反向传播的"梯度方向")。

    返回 {action, reason, kind, target}:
      · action=ACT_COVER_PADS — 主导误差是"焊盘接网"(实质): 端点未落到真实焊盘上,
        下一步令生成器依观测需求补齐焊盘 (cover_required=True) 后重跑;
      · action=ACT_REROUTE   — 焊盘已接网但"布线"仍欠: 换布线策略重跑;
      · action=ACT_NONE      — 自由能=0 已闭合, 或仅剩认知误差(工具缺位, 重跑无益,
        交由人补足观测手段)。
    """
    if verdict.error:
        return {"action": ACT_NONE, "reason": f"模型缺失: {verdict.error}",
                "kind": EPISTEMIC, "target": ""}
    s = verdict.surprises
    if not s:
        return {"action": ACT_NONE, "reason": "自由能=0, 闭环已实质闭合", "kind": "", "target": ""}
    top = s[0]
    if top.kind == EPISTEMIC:
        return {"action": ACT_NONE,
                "reason": f"主导为认知误差(重跑无益, 需补足观测): {top.name}",
                "kind": EPISTEMIC, "target": top.name}
    if top.name == "焊盘接网":
        return {"action": ACT_COVER_PADS,
                "reason": f"{top.name}: 应接网 {int(top.predicted)} 实测 {int(top.observed)}"
                          f" → 依观测需求补齐焊盘后重跑",
                "kind": PRAGMATIC, "target": top.name}
    if top.name == "布线":
        return {"action": ACT_REROUTE,
                "reason": f"{top.name}: 换布线策略重跑", "kind": PRAGMATIC, "target": top.name}
    return {"action": ACT_NONE,
            "reason": f"主导实质误差 {top.name} 暂无自动修正策略, 交人机迭代",
            "kind": PRAGMATIC, "target": top.name}


def predict_verify(template: str, output_dir: str | Path) -> Verdict:
    """对单个模板的产物做预测编码核验。"""
    out = Path(output_dir)
    if CircuitDNA is None:
        return Verdict(template, str(out), error="circuit_dna 不可导入 (请在 pcb_brain/ 下运行)")
    dna = CircuitDNA.get(template)
    if dna is None:
        return Verdict(template, str(out), error=f"DNA 模板 '{template}' 不存在")
    return reconcile(dna, out)


# ─────────────────────────────────────────────────────────────
# 展示
# ─────────────────────────────────────────────────────────────
def render(verdict: Verdict) -> str:
    lines: List[str] = []
    mark = "✅ 真实交付" if verdict.delivered else "❌ 未真正交付"
    lines.append(f"{'='*64}")
    lines.append(f"预测编码核验 · {verdict.template}")
    lines.append(f"{'='*64}")
    if verdict.error:
        lines.append(f"  模型缺失: {verdict.error}")
        return "\n".join(lines)
    lines.append(f"  结论        : {mark}")
    lines.append(f"  自由能      : {verdict.free_energy}   (0 = 实质闭环)")
    lines.append(f"  交付置信度  : {verdict.confidence}")
    lines.append("")
    lines.append(f"  {'预测单元':<10}{'预测':>8}{'观测':>8}{'误差':>8}{'精度':>6}{'惊异':>8}  类别")
    lines.append(f"  {'-'*60}")
    for p in verdict.predictions:
        kind = {EPISTEMIC: "认知·去补足观测", PRAGMATIC: "实质·去修正产物", "": "—"}[p.kind]
        flag = "  " if p.error == 0 else "❗"
        lines.append(
            f"{flag}{p.name:<10}{p.predicted:>8.0f}{p.observed:>8.0f}{p.error:>8.0f}"
            f"{p.precision:>6.1f}{p.surprise:>8.1f}  {kind}")
    lines.append("")
    lines.append(f"  下一步动作  : {verdict.next_action}")
    lines.append(f"{'='*64}")
    return "\n".join(lines)


def _discover_outputs(base: Path) -> List[Tuple[str, Path]]:
    found: List[Tuple[str, Path]] = []
    if not base.exists():
        return found
    for d in sorted(base.iterdir()):
        if d.is_dir() and (d / f"{d.name}.kicad_pcb").exists():
            found.append((d.name, d))
    return found


def main(argv: List[str]) -> int:
    here = Path(__file__).parent
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if argv[0] == "--all":
        base = here / "output"
        outs = _discover_outputs(base)
        if not outs:
            print(f"output/ 下未发现已生成的模板产物: {base}")
            return 1
        delivered = 0
        rows: List[str] = []
        for name, d in outs:
            v = predict_verify(name, d)
            rows.append(f"  {'✅' if v.delivered else '❌'} {name:<26} "
                        f"自由能={v.free_energy:<8} 下一步: {v.next_action[:40]}")
            delivered += int(v.delivered)
        print(f"\n{'='*64}\n预测编码全量核验 · {len(outs)} 个产物\n{'='*64}")
        print("\n".join(rows))
        print(f"{'='*64}")
        print(f"真实交付: {delivered}/{len(outs)}  "
              f"(其余为'形式闭环·实质空转', 详见各模板 next_action)")
        print(f"{'='*64}\n")
        return 0 if delivered == len(outs) else 2

    template = argv[0]
    output_dir = argv[1] if len(argv) > 1 else str(here / "output" / template)
    verdict = predict_verify(template, output_dir)
    print(render(verdict))
    return 0 if verdict.delivered else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
