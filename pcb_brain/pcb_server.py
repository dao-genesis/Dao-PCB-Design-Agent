#!/usr/bin/env python3
"""
PCBBrain Web服务 — 道生一，一生二，二生三，三生万物

  面A (代码之名): REST API  — Agent/IDE/脚本 HTTP调用，机器无感接入
  面B (软件之名): Web  UI   — 用户浏览器操作，人机无感交互
  三  (agent功用): agent_sense集成 + 实时日志 + 状态面板

端口: 9906
访问: http://localhost:9906
API:  http://localhost:9906/api/...

用法:
  python pcb_server.py          # 启动服务 (前台)
  python pcb_server.py 9906     # 指定端口
  # 或从 pcb_brain.py:
  python pcb_brain.py serve
"""

import os
import sys
import json
import time
import uuid
import queue
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

log = logging.getLogger("pcb_server")

# ─────────────────────────────────────────────────────────────
# 全局状态缓存 (后台预热，/api/status 直接返回<10ms)
# ─────────────────────────────────────────────────────────────
_status_lock = threading.Lock()
_status_cache: dict = {
    "pcb_env":    {},
    "agent":      {"available": None, "base": "http://localhost:9904"},
    "warming":    True,  # True = cache is still being populated
    "cached_at":  0.0,
}
_STATUS_TTL = 60.0  # seconds


def _warm_status_cache(full_agent: bool = False):
    """Background task: populate status cache. Runs at startup + every TTL."""
    # PCB env (pcbnew DLL detection)
    try:
        from kicad_arm import KiCadArm
        env = KiCadArm().status()
    except Exception as e:
        env = {"error": str(e)}

    # Agent health (may be slow, runs in parallel via thread already)
    try:
        from agent_sense import AgentSense
        a = AgentSense()
        ok = a.alive(timeout=5.0)  # generous timeout, runs in background
        agent = {"available": ok, "base": a.base}
        if ok and full_agent:
            agent["env"] = a.pcb_env_check()
    except Exception as e:
        agent = {"available": False, "error": str(e)}

    with _status_lock:
        _status_cache["pcb_env"]   = env
        _status_cache["agent"]     = agent
        _status_cache["warming"]   = False
        _status_cache["cached_at"] = time.time()
    log.info("status cache warmed  agent=%s  L2=%s",
             agent.get("available"),
             env.get("control_levels", {}).get("L2_kicad_cli", "?"))


def _schedule_warm(interval: float = _STATUS_TTL, full: bool = False):
    """Fire one background warm, then re-schedule after interval."""
    t = threading.Thread(target=_warm_status_cache, args=(full,), daemon=True)
    t.start()
    # re-schedule next warm
    timer = threading.Timer(interval, _schedule_warm, args=(interval, False))
    timer.daemon = True
    timer.start()


# ─────────────────────────────────────────────────────────────
# 异步任务管理 (线程安全)
# ─────────────────────────────────────────────────────────────
_jobs: Dict[str, Dict] = {}          # job_id → {status, result, logs, ...}
_log_queues: Dict[str, queue.Queue] = {}
_jobs_lock = threading.Lock()


def _new_job(circuit: str, cmd: str) -> str:
    jid = str(uuid.uuid4())[:8]
    with _jobs_lock:
        _jobs[jid] = {"id": jid, "circuit": circuit, "cmd": cmd,
                      "status": "pending", "result": None, "logs": [],
                      "started": time.time(), "ended": None}
        _log_queues[jid] = queue.Queue()
    return jid


def _job_log(jid: str, msg: str):
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid]["logs"].append(msg)
    if jid in _log_queues:
        _log_queues[jid].put(msg)


def _job_done(jid: str, result: dict):
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid]["status"] = "done"
            _jobs[jid]["result"] = result
            _jobs[jid]["ended"] = time.time()
    if jid in _log_queues:
        _log_queues[jid].put(None)  # sentinel


def _job_fail(jid: str, err: str):
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid]["status"] = "error"
            _jobs[jid]["result"] = {"error": err}
            _jobs[jid]["ended"] = time.time()
    if jid in _log_queues:
        _log_queues[jid].put(None)


# ─────────────────────────────────────────────────────────────
# 日志拦截器 — 将 PCBBrain 日志重定向到 job 日志流
# ─────────────────────────────────────────────────────────────
class _JobLogHandler(logging.Handler):
    def __init__(self, jid: str):
        super().__init__()
        self.jid = jid

    def emit(self, record: logging.LogRecord):
        _job_log(self.jid, self.format(record))


# ─────────────────────────────────────────────────────────────
# PCBBrain 调用封装
# ─────────────────────────────────────────────────────────────
def _run_design(jid: str, circuit: str, output_dir: Optional[str]):
    try:
        from pcb_brain import PCBBrain
        _attach_job_logging(jid)
        brain = PCBBrain(output_root=output_dir)
        path = brain.design(circuit, output_dir)
        _job_done(jid, {"success": path is not None, "pcb_path": path})
    except Exception as e:
        _job_fail(jid, str(e))
    finally:
        _detach_job_logging(jid)


def _run_full(jid: str, circuit: str, output_dir: Optional[str],
              auto_fix: bool, iterations: int):
    try:
        from pcb_brain import PCBBrain
        _attach_job_logging(jid)
        brain = PCBBrain(output_root=output_dir)
        result = brain.full_pipeline(circuit, output_dir=output_dir,
                                     auto_fix=auto_fix, max_iterations=iterations)
        _job_done(jid, result)
    except Exception as e:
        _job_fail(jid, str(e))
    finally:
        _detach_job_logging(jid)


def _attach_job_logging(jid: str):
    h = _JobLogHandler(jid)
    h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(h)
    _jobs[jid]["_handler"] = h
    _jobs[jid]["status"] = "running"


def _detach_job_logging(jid: str):
    with _jobs_lock:
        h = _jobs.get(jid, {}).pop("_handler", None)
    if h:
        logging.getLogger().removeHandler(h)


# ─────────────────────────────────────────────────────────────
# Flask 应用
# ─────────────────────────────────────────────────────────────
def create_app():
    from flask import Flask, jsonify, request, Response, stream_with_context
    app = Flask(__name__)
    app.logger.setLevel(logging.WARNING)

    # ── 静态资源: Web UI ──────────────────────────────────────
    @app.route("/")
    def index():
        return _HTML_UI

    # ── GET /api/list ─────────────────────────────────────────
    @app.route("/api/list")
    def api_list():
        from circuit_dna import CircuitDNA, estimate_bom_cost
        items = []
        for name in CircuitDNA.list_all():
            dna = CircuitDNA.get(name)
            cost = estimate_bom_cost(dna)
            items.append({
                "name": name,
                "description": dna.description,
                "board_size": dna.board_size,
                "component_count": len(dna.components),
                "net_count": len(dna.nets),
                "category": dna.category,
                "cost_components": cost["components"],
                "cost_5boards": cost["total_5boards"],
                "design_notes": dna.design_notes,
            })
        return jsonify({"templates": items, "count": len(items)})

    # ── GET /api/status  (?full=1 强制重刷agent详细环境) ──
    @app.route("/api/status")
    def api_status():
        from flask import request as req
        full = req.args.get("full") == "1"
        # 如果请求?full=1，后台重新执行完整env检查
        if full:
            _schedule_warm(interval=_STATUS_TTL, full=True)
        with _status_lock:
            snap = dict(_status_cache)
        return jsonify({
            "pcb_env":     snap["pcb_env"],
            "agent":       snap["agent"],
            "warming":     snap["warming"],
            "cached_at":   snap["cached_at"],
            "output_root": str(Path(__file__).parent / "output"),
            "server":      "pcb_server v9 · 三生万物·JLCPCB·MCP",
        })

    # ── POST /api/design ──────────────────────────────────────
    @app.route("/api/design", methods=["POST"])
    def api_design():
        data = request.get_json() or {}
        circuit = data.get("circuit", "")
        output  = data.get("output")
        if not circuit:
            return jsonify({"error": "circuit参数必填"}), 400
        jid = _new_job(circuit, "design")
        t = threading.Thread(target=_run_design,
                             args=(jid, circuit, output), daemon=True)
        t.start()
        return jsonify({"job_id": jid, "status": "started",
                        "logs_url": f"/api/logs/{jid}",
                        "status_url": f"/api/jobs/{jid}"})

    # ── POST /api/full ────────────────────────────────────────
    @app.route("/api/full", methods=["POST"])
    def api_full():
        data = request.get_json() or {}
        circuit    = data.get("circuit", "")
        output     = data.get("output")
        auto_fix   = data.get("auto_fix", True)
        iterations = int(data.get("iterations", 3))
        if not circuit:
            return jsonify({"error": "circuit参数必填"}), 400
        jid = _new_job(circuit, "full")
        t = threading.Thread(target=_run_full,
                             args=(jid, circuit, output, auto_fix, iterations),
                             daemon=True)
        t.start()
        return jsonify({"job_id": jid, "status": "started",
                        "logs_url": f"/api/logs/{jid}",
                        "status_url": f"/api/jobs/{jid}"})

    # ── GET /api/jobs/<jid> ───────────────────────────────────
    @app.route("/api/jobs/<jid>")
    def api_job(jid):
        with _jobs_lock:
            job = _jobs.get(jid)
        if job is None:
            return jsonify({"error": "任务不存在"}), 404
        safe = {k: v for k, v in job.items() if k != "_handler"}
        return jsonify(safe)

    # ── GET /api/logs/<jid>  (SSE 实时日志流) ─────────────────
    @app.route("/api/logs/<jid>")
    def api_logs(jid):
        with _jobs_lock:
            q = _log_queues.get(jid)
            existing = list(_jobs.get(jid, {}).get("logs", []))

        def generate():
            for line in existing:
                yield f"data: {json.dumps(line)}\n\n"
            if q is None:
                return
            while True:
                try:
                    msg = q.get(timeout=30)
                    if msg is None:
                        yield "data: __DONE__\n\n"
                        break
                    yield f"data: {json.dumps(msg)}\n\n"
                except queue.Empty:
                    yield ": ping\n\n"

        return Response(stream_with_context(generate()),
                        mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    # ── GET /api/jobs  (全部任务列表) ──────────────────────────
    @app.route("/api/jobs")
    def api_jobs():
        with _jobs_lock:
            items = [
                {k: v for k, v in j.items() if k not in ("_handler", "logs")}
                for j in _jobs.values()
            ]
        return jsonify({"jobs": sorted(items, key=lambda x: -x["started"])})

    # ── POST /api/open  (在KiCad中打开PCB文件) ────────────────
    @app.route("/api/open", methods=["POST"])
    def api_open():
        import subprocess, shutil
        pcb = (request.get_json() or {}).get("pcb_path", "")
        if not pcb or not Path(pcb).exists():
            return jsonify({"error": "PCB文件不存在"}), 400
        # 查找KiCad可执行文件
        kicad_exe = None
        for p in [r"D:\KICAD\bin\kicad.exe",
                  r"C:\Program Files\KiCad\8.0\bin\kicad.exe",
                  r"C:\Program Files\KiCad\bin\kicad.exe"]:
            if Path(p).exists():
                kicad_exe = p
                break
        if not kicad_exe:
            kicad_exe = shutil.which("kicad")
        if not kicad_exe:
            return jsonify({"error": "未找到KiCad可执行文件"}), 404
        try:
            subprocess.Popen([kicad_exe, pcb],
                             creationflags=subprocess.DETACHED_PROCESS
                             if hasattr(subprocess, 'DETACHED_PROCESS') else 0)
            return jsonify({"ok": True, "launched": kicad_exe, "pcb": pcb})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/agent  (agent五感快捷调用) ───────────────────
    @app.route("/api/agent", methods=["POST"])
    def api_agent():
        try:
            from agent_sense import AgentSense
            a = AgentSense()
            if not a.alive():
                return jsonify({"error": "agent离线 (localhost:9904)"}), 503
            action = (request.get_json() or {}).get("action", "env")
            if action == "screenshot":
                path = a.screenshot()
                return jsonify({"screenshot": path})
            elif action == "drc":
                pcb = (request.get_json() or {}).get("pcb_path", "")
                return jsonify(a.remote_drc(pcb) if pcb else {"error": "需要pcb_path"})
            else:
                return jsonify(a.pcb_env_check())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/recommend  (PCB顾问推荐) ───────────────────
    @app.route("/api/recommend", methods=["POST"])
    def api_recommend():
        try:
            from pcb_advisor import PCBAdvisor
            desc = (request.get_json() or {}).get("description", "")
            if not desc:
                return jsonify({"error": "description参数必填"}), 400
            advisor = PCBAdvisor()
            return jsonify(advisor.recommend(desc))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/chat  (LLM对话设计顾问) ──────────────────────
    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        try:
            from pcb_advisor import PCBAdvisor
            data    = request.get_json() or {}
            message = data.get("message", "")
            history = data.get("history", [])
            if not message:
                return jsonify({"error": "message参数必填"}), 400
            advisor = PCBAdvisor()
            return jsonify(advisor.chat(message, history))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/report  (完整设计建议报告) ───────────────────
    @app.route("/api/report", methods=["POST"])
    def api_report():
        try:
            from pcb_advisor import PCBAdvisor
            desc = (request.get_json() or {}).get("description", "")
            if not desc:
                return jsonify({"error": "description参数必填"}), 400
            advisor = PCBAdvisor()
            return jsonify(advisor.design_report(desc))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/freeroute  (freerouting自动布线触发) ──────────
    @app.route("/api/freeroute", methods=["POST"])
    def api_freeroute():
        data      = request.get_json() or {}
        pcb_path  = data.get("pcb_path", "")
        max_passes = int(data.get("max_passes", 10))
        timeout   = int(data.get("timeout", 120))
        if not pcb_path or not Path(pcb_path).exists():
            return jsonify({"error": "pcb_path不存在"}), 400
        try:
            from kicad_arm import KiCadArm
            arm = KiCadArm()
            result = arm.auto_route_freerouting(pcb_path, max_passes, timeout)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── GET /api/wugan  (无感评分·老庄六感聚合) ───────────────
    @app.route("/api/wugan", methods=["GET", "POST"])
    def api_wugan():
        try:
            from pcb_wugan import wugan_meta, shi_vision, ting_hearing, chu_touch, xiu_smell, wei_taste
            from circuit_dna import CircuitDNA

            data    = request.get_json() or {}
            circuit = data.get("circuit") or request.args.get("circuit")
            pcb_path = data.get("pcb_path") or request.args.get("pcb_path")

            dna = CircuitDNA.get(circuit) if circuit else None

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=5) as ex:
                f_shi  = ex.submit(shi_vision,  pcb_path, dna)
                f_ting = ex.submit(ting_hearing, None, None)
                f_chu  = ex.submit(chu_touch,    pcb_path, None, None)
                f_xiu  = ex.submit(xiu_smell,    None, dna, None)
                f_wei  = ex.submit(wei_taste,    dna, None)

            senses = {"视": f_shi.result(), "听": f_ting.result(),
                      "触": f_chu.result(), "嗅": f_xiu.result(), "味": f_wei.result()}
            wugan  = wugan_meta(senses, pcb_path, dna)
            return jsonify({"senses": senses, "wugan": wugan,
                           "score": wugan["score"], "paoding_level": wugan["paoding_level"],
                           "verdict": wugan["verdict"], "next_step": wugan["next_step"]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/xinzhai  (心斋·以气听·意图号脉感知) ─────────────
    @app.route("/api/xinzhai", methods=["POST"])
    def api_xinzhai():
        try:
            from pcb_wugan import xinzhai_listen
            description = (request.get_json() or {}).get("description", "")
            if not description:
                return jsonify({"error": "description参数必填"}), 400
            result = xinzhai_listen(description)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/wuwei  (无为流水线·用户无需操控) ──────────────
    @app.route("/api/wuwei", methods=["POST"])
    def api_wuwei():
        data    = request.get_json() or {}
        circuit = data.get("circuit", "")
        output  = data.get("output")
        desc    = data.get("description", "")
        if not circuit and not desc:
            return jsonify({"error": "circuit或description参数必填"}), 400
        jid = _new_job(circuit or desc, "wuwei")
        def _run_wuwei(jid, circuit, output, desc):
            try:
                from pcb_wugan import wuwei_pipeline
                _attach_job_logging(jid)
                result = wuwei_pipeline(circuit, output_dir=output, description=desc)
                _job_done(jid, result)
            except Exception as e:
                _job_fail(jid, str(e))
            finally:
                _detach_job_logging(jid)
        import threading
        t = threading.Thread(target=_run_wuwei, args=(jid, circuit, output, desc), daemon=True)
        t.start()
        return jsonify({"job_id": jid, "status": "started",
                       "logs_url": f"/api/logs/{jid}", "status_url": f"/api/jobs/{jid}",
                       "philosophy": "无为而无不为·用户只需给出意图，筻亁天理自动运转"})

    # ── POST /api/open_lceda  (打开嘉立创EDA) ──────────────────
    @app.route("/api/open_lceda", methods=["POST"])
    def api_open_lceda():
        import subprocess, shutil
        proj = (request.get_json() or {}).get("project_path", "")
        lceda_paths = [
            r"D:\lceda-pro\lceda-pro.exe",
            r"C:\Users\Administrator\AppData\Local\Programs\lceda-pro\lceda-pro.exe",
            r"C:\Users\zhouyoukang\AppData\Local\Programs\lceda-pro\lceda-pro.exe",
        ]
        exe = next((p for p in lceda_paths if Path(p).exists()), None)
        if not exe:
            return jsonify({"error": "嘉立创EDA未找到"}), 404
        try:
            cmd = [exe] + ([proj] if proj and Path(proj).exists() else [])
            subprocess.Popen(cmd, creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0))
            return jsonify({"ok": True, "launched": exe})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/user_sense  (用户五感需求→PCB生成) ──────────
    @app.route("/api/user_sense", methods=["POST"])
    def api_user_sense():
        """
        用户五感需求接口
        输入: {shi, ting, chu, xiu, wei, execute=false, output=null}
        输出: {requirement, selection, [pipeline_result, wugan]}
        """
        data = request.get_json() or {}
        try:
            from pcb_user_sense import UserSenseInput, UserSensePipeline
            inp = UserSenseInput(
                shi=data.get("shi",  ""),
                ting=data.get("ting",""),
                chu=data.get("chu",  ""),
                xiu=data.get("xiu",  ""),
                wei=data.get("wei",  ""),
            )
            if inp.is_empty():
                return jsonify({"error": "五感均为空，至少填写一项"}), 400

            pipeline = UserSensePipeline()
            execute  = data.get("execute", False)
            output   = data.get("output", None)

            if execute:
                # 完整无为流水线（异步任务）
                jid = _new_job(data.get("ting","sense"), "user_sense")
                def _run_sense(jid, inp, output):
                    try:
                        _attach_job_logging(jid)
                        result = pipeline.run(inp, output_dir=output, execute=True)
                        _job_done(jid, result)
                    except Exception as e:
                        _job_fail(jid, str(e))
                    finally:
                        _detach_job_logging(jid)
                import threading
                t = threading.Thread(target=_run_sense, args=(jid, inp, output), daemon=True)
                t.start()
                return jsonify({"job_id": jid, "status": "started",
                               "logs_url": f"/api/logs/{jid}",
                               "philosophy": "无为而无不为·五感→PCB自动闭环"})
            else:
                # 只解析，不执行
                req, selection = pipeline.parse_and_select(inp)
                from dataclasses import asdict
                return jsonify({
                    "input":       asdict(inp),
                    "requirement": asdict(req),
                    "selection":   selection,
                    "next_cmd":    f"python pcb_wugan.py wuwei {selection.get('template','')}",
                })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ─────────────────────────────────────────────────────────
    # v9 新增: JLCPCB/立创商城集成层
    # ─────────────────────────────────────────────────────────

    # ── GET /api/jlcpcb/list  (所有模板+LCSC成本) ──────────
    @app.route("/api/jlcpcb/list")
    def api_jlcpcb_list():
        try:
            from pcb_jlcpcb import JLCPCBHelper
            jlc = JLCPCBHelper()
            return jsonify({"templates": jlc.list_all_with_cost()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── GET /api/jlcpcb/bom?template=xxx  (BOM+LCSC料号) ──
    @app.route("/api/jlcpcb/bom")
    def api_jlcpcb_bom():
        template = request.args.get("template", "")
        if not template:
            return jsonify({"error": "template参数必填"}), 400
        try:
            from pcb_jlcpcb import JLCPCBHelper
            jlc = JLCPCBHelper()
            bom = jlc.generate_bom(template)
            return jsonify({
                "template": template,
                "count": len(bom),
                "bom": [{"ref": e.ref, "value": e.value, "lcsc": e.lcsc,
                          "price": e.price_each, "note": e.note,
                          "smt": e.jlcpcb_smt} for e in bom],
                "total_cost": round(sum(e.price_each for e in bom), 2),
                "jlcpcb_url": jlc.order_url(template),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/jlcpcb/export  (导出BOM+CPL CSV) ─────────
    @app.route("/api/jlcpcb/export", methods=["POST"])
    def api_jlcpcb_export():
        data = request.get_json() or {}
        template = data.get("template", "")
        if not template:
            return jsonify({"error": "template参数必填"}), 400
        try:
            from pcb_jlcpcb import JLCPCBHelper
            jlc = JLCPCBHelper()
            out_dir = data.get("output_dir") or str(Path(__file__).parent / "output" / template)
            report = jlc.full_report(template, out_dir)
            return jsonify({
                "template": template,
                "cost":     report["cost"],
                "files":    report["files"],
                "jlcpcb_url": report["jlcpcb_url"],
                "alternatives_count": len(report["alternatives"]),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── GET /api/jlcpcb/cost?template=xxx&qty=5 ──────────
    @app.route("/api/jlcpcb/cost")
    def api_jlcpcb_cost():
        template = request.args.get("template", "")
        qty = int(request.args.get("qty", 5))
        if not template:
            return jsonify({"error": "template参数必填"}), 400
        try:
            from pcb_jlcpcb import JLCPCBHelper
            jlc = JLCPCBHelper()
            return jsonify(jlc.cost_report(template, qty))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── GET /api/jlcpcb/alt?value=STM32F103C6T6 ──────────
    @app.route("/api/jlcpcb/alt")
    def api_jlcpcb_alt():
        value = request.args.get("value", "")
        if not value:
            return jsonify({"error": "value参数必填"}), 400
        try:
            from pcb_jlcpcb import JLCPCBHelper
            jlc = JLCPCBHelper()
            return jsonify({"value": value, "alternatives": jlc.alternatives(value)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ─────────────────────────────────────────────────────────
    # v9 新增: MCP工具信息端点
    # ─────────────────────────────────────────────────────────

    # ── GET /api/mcp/tools  (MCP工具清单) ─────────────────
    @app.route("/api/mcp/tools")
    def api_mcp_tools():
        return jsonify({
            "mcp_server": "pcb_mcp.py",
            "mcp_port":   9907,
            "mcp_stdio":  "python " + str(Path(__file__).parent / "pcb_mcp.py"),
            "windsurf_config": {
                "mcpServers": {
                    "pcb_brain": {
                        "command": "python",
                        "args": [str(Path(__file__).parent / "pcb_mcp.py")]
                    }
                }
            },
            "tools": [
                {"name": "list_templates",  "desc": "列出所有PCB DNA模板及成本"},
                {"name": "design_pcb",      "desc": "生成PCB文件 (DNA→.kicad_pcb)"},
                {"name": "get_bom",         "desc": "BOM+LCSC料号+成本+下单URL"},
                {"name": "run_drc",         "desc": "运行DRC检查"},
                {"name": "export_gerber",   "desc": "导出Gerber生产文件"},
                {"name": "pcb_sense",       "desc": "PCB环境五感健康报告"},
            ]
        })

    # ── GET /api/mcp/sense  (MCP环境感知) ─────────────────
    @app.route("/api/mcp/sense")
    def api_mcp_sense():
        try:
            import importlib.util
            fastmcp_ok = importlib.util.find_spec("fastmcp") is not None
            mcp_script = Path(__file__).parent / "pcb_mcp.py"
            return jsonify({
                "mcp_script": str(mcp_script),
                "mcp_exists": mcp_script.exists(),
                "fastmcp_installed": fastmcp_ok,
                "fallback": "内置stdio JSON-RPC (无需fastmcp)",
                "jlcpcb_script": str(Path(__file__).parent / "pcb_jlcpcb.py"),
                "jlcpcb_exists": (Path(__file__).parent / "pcb_jlcpcb.py").exists(),
                "ready": mcp_script.exists(),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/ibom  (交互式HTML BOM生成) ──────────────
    @app.route("/api/ibom", methods=["GET", "POST"])
    def api_ibom():
        data = request.get_json() or {}
        template = data.get("template") or request.args.get("template", "")
        output_dir = data.get("output_dir", "")
        if not template:
            from circuit_dna import CircuitDNA
            return jsonify({
                "error": "需要template参数",
                "available": CircuitDNA.list_all(),
                "example": "POST /api/ibom  {\"template\": \"stm32f103c6_dot_matrix\"}"
            }), 400
        try:
            from pcb_ibom import generate_ibom
            result = generate_ibom(template_name=template, output_dir=output_dir)
            if result["status"] == "ok":
                result["url_hint"] = f"file:///{result['html_path'].replace(chr(92), '/')}"
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/pipeline  (全闭环流水线) ────────────────
    @app.route("/api/pipeline", methods=["POST"])
    def api_pipeline():
        data = request.get_json() or {}
        template = data.get("template", "")
        output_dir = data.get("output_dir", "")
        if not template:
            from circuit_dna import CircuitDNA
            return jsonify({
                "error": "需要template参数",
                "available": CircuitDNA.list_all(),
                "example": "POST /api/pipeline  {\"template\": \"stm32f103c6_dot_matrix\"}"
            }), 400
        try:
            from pcb_pipeline import PCBPipeline
            pipeline = PCBPipeline(template, output_dir=output_dir)
            result = pipeline.run()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/setup  (自动配置: freerouting+MCP注册) ──
    @app.route("/api/setup", methods=["POST"])
    def api_setup():
        try:
            from pcb_pipeline import _auto_download_freerouting, auto_register_mcp
            fr = _auto_download_freerouting()
            mcp = auto_register_mcp()
            return jsonify({
                "freerouting": fr or "下载失败，请手动安装",
                "mcp": mcp,
                "note": "重启Windsurf使MCP生效"
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── GET /api/intent  (感知先于开口 — 主动意图溯源) ───────
    @app.route("/api/intent")
    def api_intent():
        force = request.args.get("force") == "1"
        try:
            from pcb_intent import get_intent, intent_to_dict
            model = get_intent(force=force)
            return jsonify(intent_to_dict(model))
        except Exception as e:
            return jsonify({"error": str(e), "note": "pcb_intent.py未找到或扫描失败"}), 500

    # ── GET /api/guardian  (风险预判守护 — 早于用户意识到问题) ─
    @app.route("/api/guardian")
    def api_guardian():
        template = request.args.get("template", "")
        pcb_path = request.args.get("pcb", "")
        if not template:
            from circuit_dna import CircuitDNA
            return jsonify({"error": "需要template参数",
                            "available": CircuitDNA.list_all()}), 400
        try:
            from pcb_guardian import guardian_report
            result = guardian_report(template, pcb_path)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── GET /api/conscious (决策溯源 — 每个参数可回溯至顶层需求) ─
    @app.route("/api/conscious")
    def api_conscious():
        template = request.args.get("template", "")
        try:
            from pcb_intent import get_intent, intent_to_dict
            from pcb_guardian import guardian_report
            intent = intent_to_dict(get_intent())
            guard = guardian_report(template or intent.get("primary_template", ""))
            return jsonify({
                "intent":  intent,
                "guardian": guard,
                "pipeline_state": "ready" if guard["critical"] == 0 else "blocked",
                "recommended_cmd": intent.get("recommended_cmd", ""),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ─────────────────────────────────────────────────────────
    # 道层 API — 意图优先·置信标注·自我进化
    # ─────────────────────────────────────────────────────────

    # ── POST /api/dao/parse  (自然语言→意图确认+置信标注) ──
    @app.route("/api/dao/parse", methods=["POST"])
    def api_dao_parse():
        try:
            from pcb_dao import dao_parse
            text = (request.get_json() or {}).get("text", "")
            if not text:
                return jsonify({"error": "text参数必填"}), 400
            return jsonify(dao_parse(text))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/dao/correct  (用户纠正→进化存储→重新解析) ─
    @app.route("/api/dao/correct", methods=["POST"])
    def api_dao_correct():
        try:
            from pcb_dao import dao_correct
            data = request.get_json() or {}
            return jsonify(dao_correct(
                session_id    = data.get("session_id", ""),
                original_input= data.get("original_input", ""),
                correction_text=data.get("correction_text", ""),
                field         = data.get("field", "general"),
                old_val       = data.get("old_val", ""),
                new_val       = data.get("new_val", ""),
            ))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── POST /api/dao/confirm  (用户确认→静默执行流水线) ─────
    @app.route("/api/dao/confirm", methods=["POST"])
    def api_dao_confirm():
        data    = request.get_json() or {}
        template= data.get("template", "")
        output  = data.get("output", None)
        if not template:
            return jsonify({"error": "template参数必填"}), 400
        jid = _new_job(template, "dao_confirm")
        def _run_dao(jid, template, output):
            try:
                from pcb_brain import PCBBrain
                _attach_job_logging(jid)
                brain  = PCBBrain()
                result = brain.full_pipeline(template, output_dir=output,
                                             auto_fix=True, max_iterations=3)
                _job_done(jid, result)
            except Exception as e:
                _job_fail(jid, str(e))
            finally:
                _detach_job_logging(jid)
        t = threading.Thread(target=_run_dao, args=(jid, template, output), daemon=True)
        t.start()
        return jsonify({"job_id": jid, "status": "started",
                        "logs_url": f"/api/logs/{jid}",
                        "status_url": f"/api/jobs/{jid}"})

    # ── GET /api/dao/evolution  (进化库状态·AI学了什么) ──────
    @app.route("/api/dao/evolution")
    def api_dao_evolution():
        try:
            from pcb_dao import dao_evolution_summary
            return jsonify(dao_evolution_summary())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── 启动后台预热 (服务器就绪后立即开始填充缓存) ──────────
    _schedule_warm(interval=_STATUS_TTL, full=False)
    # 后台预扫描意图 (服务启动时即主动感知，无需用户请求)
    threading.Thread(target=_bg_intent_scan, daemon=True).start()

    return app


def _bg_intent_scan():
    """服务器启动时后台执行意图扫描，缓存结果"""
    try:
        from pcb_intent import get_intent
        get_intent(force=True)
        log.info("后台意图扫描完成")
    except Exception as e:
        log.debug(f"后台意图扫描失败: {e}")


# ─────────────────────────────────────────────────────────────
# Web UI HTML (软件之名 — 用户无感操作面)
# ─────────────────────────────────────────────────────────────
_HTML_UI = r"""<!DOCTYPE html>
<html lang="zh"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI设计助手 · 道</title>
<style>
:root{--bg:#0d1117;--s:#161b22;--b:#30363d;--a:#00c853;--ad:#1b5e20;--t:#e6edf3;--td:#8b949e;--err:#ff5252;--warn:#ffb74d;--blue:#1e88e5;--orange:#ff9800}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--t);font:14px/1.6 "Consolas","Cascadia Code",monospace;min-height:100vh}
a{color:var(--a);text-decoration:none}
/* 置信标签 */
.conf{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:bold;margin-left:6px;vertical-align:middle}
.conf-confirmed{background:#1b5e20;color:#00c853}
.conf-inferred{background:#0d2a4a;color:#64b5f6}
.conf-guessed{background:#3e2000;color:#ffb74d}
/* Header */
header{background:var(--s);border-bottom:1px solid var(--b);padding:10px 20px;display:flex;align-items:center;gap:14px}
header h1{font-size:17px;color:var(--a);letter-spacing:1px}
.hdr-badge{padding:2px 8px;border-radius:3px;font-size:11px;background:var(--ad);color:var(--a)}
.hdr-badge.off{background:#2d1b1b;color:var(--err)}
.mode-toggle{margin-left:auto;padding:4px 12px;border:1px solid var(--b);border-radius:4px;background:var(--s);color:var(--td);font:inherit;font-size:12px;cursor:pointer}
.mode-toggle:hover{border-color:var(--a);color:var(--a)}
/* 道层主视图 */
#view-dao{max-width:800px;margin:0 auto;padding:32px 20px}
.dao-hero{text-align:center;margin-bottom:32px}
.dao-hero h2{font-size:22px;color:var(--t);font-weight:400;letter-spacing:.5px;margin-bottom:6px}
.dao-hero p{color:var(--td);font-size:13px}
.input-card{background:var(--s);border:1px solid var(--b);border-radius:10px;padding:20px;margin-bottom:20px}
.input-row{display:flex;gap:10px;align-items:flex-end}
#dao-input{flex:1;background:var(--bg);border:1px solid var(--b);border-radius:6px;color:var(--t);padding:10px 14px;font:inherit;font-size:14px;resize:none;min-height:64px;transition:border-color .2s}
#dao-input:focus{outline:none;border-color:var(--a)}
.btn-analyze{padding:10px 20px;background:var(--a);color:#000;border:none;border-radius:6px;font:inherit;font-size:14px;font-weight:bold;cursor:pointer;white-space:nowrap;height:64px}
.btn-analyze:hover{opacity:.88}
.btn-analyze:disabled{opacity:.4;cursor:not-allowed}
.examples{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px}
.ex-chip{padding:3px 10px;background:var(--bg);border:1px solid var(--b);border-radius:12px;font-size:11px;color:var(--td);cursor:pointer;transition:all .15s}
.ex-chip:hover{border-color:var(--a);color:var(--a)}
/* 意图确认卡 */
#intent-card{display:none;background:var(--s);border:1px solid var(--b);border-radius:10px;padding:20px;margin-bottom:16px;animation:fadeIn .3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.ic-title{font-size:11px;color:var(--td);text-transform:uppercase;letter-spacing:1px;margin-bottom:14px}
.ic-summary{font-size:16px;color:var(--t);margin-bottom:16px;line-height:1.6;background:rgba(0,200,83,.05);border-left:3px solid var(--a);padding:10px 14px;border-radius:0 6px 6px 0}
.ic-fields{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px}
.ic-field{background:var(--bg);border:1px solid var(--b);border-radius:6px;padding:10px 12px}
.ic-field-label{font-size:10px;color:var(--td);margin-bottom:3px}
.ic-field-value{font-size:13px;color:var(--t);display:flex;align-items:center;flex-wrap:wrap;gap:4px}
.ic-meta{display:flex;gap:16px;font-size:12px;color:var(--td);margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px;border:1px solid var(--b)}
.ic-meta span{display:flex;gap:4px;align-items:center}
/* 置信度详情 */
.conf-detail{margin-bottom:16px;padding:10px 14px;background:var(--bg);border-radius:6px;border:1px solid var(--b)}
.conf-detail-title{font-size:10px;color:var(--td);margin-bottom:6px}
.conf-overall{font-size:13px;color:var(--t);margin-bottom:6px}
.conf-legend{display:flex;gap:10px;font-size:10px;color:var(--td);flex-wrap:wrap}
/* 问题 & 纠正 */
.questions{background:rgba(255,152,0,.06);border:1px solid rgba(255,152,0,.2);border-radius:6px;padding:12px 14px;margin-bottom:14px}
.q-title{font-size:11px;color:var(--warn);margin-bottom:6px}
.q-item{font-size:12px;color:var(--t);margin-bottom:4px;padding-left:12px}
.action-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.btn-confirm{padding:10px 24px;background:var(--a);color:#000;border:none;border-radius:6px;font:inherit;font-size:14px;font-weight:bold;cursor:pointer}
.btn-confirm:hover{opacity:.88}
.btn-correct{padding:10px 18px;background:var(--s);color:var(--t);border:1px solid var(--b);border-radius:6px;font:inherit;font-size:13px;cursor:pointer}
.btn-correct:hover{border-color:var(--a);color:var(--a)}
/* 纠正输入 */
#correction-panel{display:none;background:var(--s);border:1px solid var(--warn);border-radius:10px;padding:16px;margin-bottom:16px;animation:fadeIn .2s ease}
.corr-title{font-size:12px;color:var(--warn);margin-bottom:10px}
.corr-row{display:flex;gap:8px}
#corr-input{flex:1;background:var(--bg);border:1px solid var(--b);border-radius:6px;color:var(--t);padding:8px 12px;font:inherit;font-size:13px}
#corr-input:focus{outline:none;border-color:var(--warn)}
.btn-corr-submit{padding:8px 16px;background:var(--warn);color:#000;border:none;border-radius:6px;font:inherit;font-size:13px;cursor:pointer;font-weight:bold}
/* 执行进度 */
#progress-card{display:none;background:var(--s);border:1px solid var(--b);border-radius:10px;padding:20px;margin-bottom:16px;animation:fadeIn .3s ease}
.prog-title{font-size:14px;color:var(--a);font-weight:bold;margin-bottom:16px}
.prog-step{display:flex;align-items:center;gap:10px;margin-bottom:10px;font-size:13px}
.step-icon{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0}
.step-done{background:var(--ad);color:var(--a)}
.step-active{background:#0d2a4a;color:#64b5f6;border:1px solid #64b5f6}
.step-wait{background:var(--bg);color:var(--td);border:1px solid var(--b)}
.step-err{background:#2d1b1b;color:var(--err)}
.prog-result{margin-top:14px;padding:12px 14px;background:var(--bg);border-radius:6px;border:1px solid var(--b);font-size:12px;line-height:1.7}
/* 工程师模式（高级视图） */
#view-pro{display:none}
.pro-header{background:var(--s);border-bottom:1px solid var(--b);padding:8px 20px;font-size:11px;color:var(--warn)}
main{display:grid;grid-template-columns:240px 1fr 320px;gap:0;height:calc(100vh - 90px)}
.panel-left{border-right:1px solid var(--b);overflow-y:auto;padding:12px}
.panel-left h2{font-size:11px;color:var(--td);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
.dna-card{border:1px solid var(--b);border-radius:6px;padding:10px;margin-bottom:8px;cursor:pointer;transition:border-color .15s}
.dna-card:hover{border-color:var(--a)}.dna-card.selected{border-color:var(--a);background:rgba(0,200,83,.06)}
.dna-card .name{color:var(--a);font-size:13px;font-weight:bold}
.dna-card .desc{color:var(--td);font-size:11px;margin-top:3px}
.dna-card .meta{display:flex;gap:8px;margin-top:5px;font-size:11px;color:var(--td)}
.dna-card .meta span{background:var(--s);padding:1px 5px;border-radius:3px}
.panel-center{overflow-y:auto;padding:16px}
.panel-center h2{font-size:13px;color:var(--td);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
.form-row{margin-bottom:10px}
.form-row label{display:block;font-size:11px;color:var(--td);margin-bottom:4px}
.form-row input,select{width:100%;background:var(--s);border:1px solid var(--b);color:var(--t);padding:6px 10px;border-radius:4px;font:inherit}
.form-row input:focus,select:focus{outline:none;border-color:var(--a)}
.form-row .hint{font-size:10px;color:var(--td);margin-top:2px}
.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 16px;border:none;border-radius:4px;cursor:pointer;font:inherit;font-size:13px;transition:opacity .15s}
.btn:hover{opacity:.85}.btn-primary{background:var(--a);color:#000}.btn-sec{background:var(--s);color:var(--t);border:1px solid var(--b)}
.btn-row{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.btn-sm{padding:1px 7px;border:1px solid var(--b);border-radius:3px;background:var(--s);color:var(--a);font-size:10px;cursor:pointer;font:inherit;transition:opacity .15s}.btn-sm:hover{opacity:.75}
#sel-info{background:var(--s);border:1px solid var(--b);border-radius:6px;padding:12px;margin-bottom:14px;font-size:12px;line-height:1.8}
#sel-info .label{color:var(--td)}
.panel-right{border-left:1px solid var(--b);display:flex;flex-direction:column;overflow:hidden}
.panel-right .tabs{display:flex;border-bottom:1px solid var(--b)}
.panel-right .tab{padding:8px 14px;font-size:12px;cursor:pointer;color:var(--td);border-bottom:2px solid transparent}
.panel-right .tab.active{color:var(--a);border-bottom-color:var(--a)}
.tab-content{flex:1;overflow-y:auto;padding:10px;font-size:12px}
.tab-content.hidden{display:none}
#log-box{font-size:11px;line-height:1.7;white-space:pre-wrap}
.log-info{color:var(--t)}.log-warn{color:var(--warn)}.log-err{color:var(--err)}.log-ok{color:var(--a)}
.job-row{border:1px solid var(--b);border-radius:4px;padding:8px;margin-bottom:6px;font-size:11px}
.job-row .jid{color:var(--a);font-weight:bold}
.job-row .jstatus{padding:1px 6px;border-radius:3px;font-size:10px}
.jstatus.running{background:#1b3a20;color:var(--a)}.jstatus.done{background:#1b3a20;color:var(--a)}.jstatus.error{background:#2d1b1b;color:var(--err)}.jstatus.pending{background:var(--s);color:var(--td)}
.result-block{background:var(--s);border:1px solid var(--b);border-radius:4px;padding:10px;margin-top:8px;font-size:11px}
.result-block .rt{color:var(--td);font-size:10px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.sense-row{display:flex;gap:8px;align-items:flex-start;margin-bottom:6px}
.sense-icon{font-size:16px;width:22px;flex-shrink:0}.sense-val{color:var(--t)}
#status-bar{background:var(--s);border-top:1px solid var(--b);padding:4px 12px;font-size:11px;color:var(--td);display:flex;gap:12px}
</style>
</head>
<body>
<header>
  <h1>⬡ 道 · AI设计助手</h1>
  <span style="color:var(--td);font-size:12px">描述你想做什么，AI承接一切复杂度</span>
  <span id="hdr-agent" class="hdr-badge off" style="margin-left:12px">系统检测中...</span>
  <button class="mode-toggle" onclick="toggleMode()" id="mode-btn">工程师模式</button>
</header>
<!-- ══ 道层（默认）：意图优先界面 ══ -->
<div id="view-dao">
  <div class="dao-hero">
    <h2>你想做什么？</h2>
    <p>用任何方式描述你的想法，AI承接所有工程复杂度</p>
  </div>
  <div class="input-card">
    <div class="input-row">
      <textarea id="dao-input" placeholder="例：我想做一个能用手机查看温湿度的设备，USB供电，越便宜越好&#10;例：帮我做个蓝牙遥控小车的控制板&#10;例：我需要一个带电机控制的工业通信模块"></textarea>
      <button class="btn-analyze" onclick="analyzeIntent()" id="btn-analyze">分析 ▶</button>
    </div>
    <div class="examples">
      <span style="font-size:10px;color:var(--td);margin-right:4px">试试：</span>
      <span class="ex-chip" onclick="setExample(this)">WiFi温湿度传感器</span>
      <span class="ex-chip" onclick="setExample(this)">蓝牙遥控小车</span>
      <span class="ex-chip" onclick="setExample(this)">智能门锁控制板</span>
      <span class="ex-chip" onclick="setExample(this)">无人机飞控</span>
      <span class="ex-chip" onclick="setExample(this)">工业RS485通信模块</span>
    </div>
  </div>

  <!-- 意图确认卡 -->
  <div id="intent-card">
    <div class="ic-title">▌ 我的理解 — 请确认或告诉我哪里不对</div>
    <div class="ic-summary" id="ic-summary"></div>
    <div class="ic-fields" id="ic-fields"></div>
    <div class="ic-meta" id="ic-meta"></div>
    <div class="conf-detail">
      <div class="conf-detail-title">置信度说明</div>
      <div class="conf-overall" id="conf-overall"></div>
      <div class="conf-legend">
        <span><span class="conf conf-confirmed">确认</span> 你明确说了</span>
        <span><span class="conf conf-inferred">推断</span> 合理推导</span>
        <span><span class="conf conf-guessed">猜测</span> AI假设，建议核对</span>
      </div>
    </div>
    <div class="questions" id="questions-block" style="display:none">
      <div class="q-title">⚠ 以下内容为猜测，建议确认：</div>
      <div id="questions-list"></div>
    </div>
    <div class="action-row">
      <button class="btn-confirm" onclick="confirmAndBuild()" id="btn-confirm">没问题，开始制作 ▶</button>
      <button class="btn-correct" onclick="showCorrection()">这里不对...</button>
      <button class="btn-correct" onclick="resetDao()" style="color:var(--td)">重新描述</button>
    </div>
  </div>

  <!-- 纠正面板 -->
  <div id="correction-panel">
    <div class="corr-title">告诉我哪里不对（AI会记住，下次不再犯同样的错）</div>
    <div class="corr-row">
      <input id="corr-input" type="text" placeholder="例：我不需要WiFi，用蓝牙就好 / 我要电池供电不是USB / 板子要尽量小">
      <button class="btn-corr-submit" onclick="submitCorrection()">确认修正</button>
    </div>
  </div>

  <!-- 执行进度卡 -->
  <div id="progress-card">
    <div class="prog-title" id="prog-title">⚡ 正在为你制作...</div>
    <div id="prog-steps"></div>
    <div class="prog-result" id="prog-result" style="display:none"></div>
    <div style="margin-top:12px;text-align:center;display:none" id="prog-done-actions">
      <button class="btn-confirm" onclick="resetDao()" style="background:var(--s);color:var(--a);border:1px solid var(--a)">再做一个</button>
    </div>
  </div>
</div>

<!-- ══ 工程师模式（高级视图）══ -->
<div id="view-pro">
  <div class="pro-header">⚙ 工程师模式 — 直接操控所有参数</div>
  <main>
  <!-- LEFT: DNA模板库 -->
  <div class="panel-left">
    <h2>电路DNA模板</h2>
    <div id="dna-list"></div>
  </div>
<!-- CENTER: 设计配置 -->
<div class="panel-center">
  <h2>设计配置</h2>
  <div id="sel-info" style="color:var(--td)">← 选择左侧模板开始设计</div>
  <div class="form-row">
    <label>电路模板</label>
    <input id="f-circuit" type="text" placeholder="stm32f103c6_dot_matrix" readonly>
  </div>
  <div class="form-row">
    <label>输出目录</label>
    <input id="f-output" type="text" placeholder="默认: pcb_brain/output/">
  </div>
  <div class="form-row">
    <label>流水线模式</label>
    <select id="f-mode">
      <option value="full">完整流水线 (DNA→PCB→DRC→Gerber)</option>
      <option value="design">快速生成 (仅PCB文件)</option>
    </select>
  </div>
  <div class="form-row" id="row-fix">
    <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
      <input id="f-fix" type="checkbox" checked style="width:auto">
      自动修复DRC问题
    </label>
  </div>
  <div class="form-row" id="row-iter">
    <label>最大修复轮数</label>
    <select id="f-iter">
      <option value="1">1轮</option>
      <option value="3" selected>3轮</option>
      <option value="5">5轮</option>
    </select>
  </div>
  <div class="form-row">
    <label>AI顾问 — 自然语言描述需求</label>
    <div style="display:flex;gap:6px">
      <input id="f-ask" type="text" placeholder="例: 我想做一个WiFi温湿度传感器" style="flex:1">
      <button class="btn btn-sec" style="white-space:nowrap" onclick="askAdvisor()">💡 推荐</button>
    </div>
    <div id="advisor-tip" style="font-size:11px;color:var(--a);margin-top:4px"></div>
  </div>
  <div class="btn-row">
    <button class="btn btn-primary" onclick="submitJob()">▶ 开始设计</button>
    <button class="btn btn-sec" onclick="openLceda()">⬢ 嘉立创EDA</button>
    <button class="btn btn-sec" onclick="checkStatus()">⟳ 环境检测</button>
    <button class="btn btn-sec" onclick="loadTemplates()">↺ 刷新模板</button>
  </div>
  <div id="job-result" style="margin-top:16px"></div>
</div>
<!-- RIGHT: 日志+任务 -->
<div class="panel-right">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('logs')">实时日志</div>
    <div class="tab" onclick="switchTab('jobs')">任务列表</div>
    <div class="tab" onclick="switchTab('env')">环境状态</div>
    <div class="tab" onclick="switchTab('wugan')">⬡无感</div>
    <div class="tab" onclick="switchTab('sense5')">🧐五感</div>
    <div class="tab" onclick="switchTab('intent')">🔮感知</div>
  </div>
  <div id="tab-logs" class="tab-content">
    <div id="log-box"><span style="color:var(--td)">等待任务启动...</span></div>
  </div>
  <div id="tab-jobs" class="tab-content hidden">
    <div id="jobs-list"><span style="color:var(--td)">暂无任务</span></div>
  </div>
  <div id="tab-env" class="tab-content hidden">
    <div id="env-content"><span style="color:var(--td)">点击「环境检测」加载...</span></div>
  </div>
  <div id="tab-sense5" class="tab-content hidden" style="padding:8px">
    <div style="font-size:11px;color:var(--td);margin-bottom:8px;line-height:1.5">
      以您之五感描述需求，系统自动解析生成PCB
    </div>
    <div style="margin-bottom:6px">
      <div style="font-size:10px;color:var(--td);margin-bottom:2px">👁 视感 — 我想看见什么</div>
      <input id="s5-shi" type="text" placeholder="LED展示WiFi状态 / OLED屏幕 / 电源指示灯" style="width:100%;background:var(--s);border:1px solid var(--b);color:var(--t);padding:4px 7px;border-radius:3px;font:inherit;font-size:11px">
    </div>
    <div style="margin-bottom:6px">
      <div style="font-size:10px;color:var(--td);margin-bottom:2px">👂 听感 — 我想传递/听到什么</div>
      <input id="s5-ting" type="text" placeholder="WiFi控制 / 串口调试 / 蜂鸣器报警" style="width:100%;background:var(--s);border:1px solid var(--b);color:var(--t);padding:4px 7px;border-radius:3px;font:inherit;font-size:11px">
    </div>
    <div style="margin-bottom:6px">
      <div style="font-size:10px;color:var(--td);margin-bottom:2px">🤝 触感 — 我想触碰/操控什么</div>
      <input id="s5-chu" type="text" placeholder="复位按键 / USB-C供电 / 8个GPIO口" style="width:100%;background:var(--s);border:1px solid var(--b);color:var(--t);padding:4px 7px;border-radius:3px;font:inherit;font-size:11px">
    </div>
    <div style="margin-bottom:6px">
      <div style="font-size:10px;color:var(--td);margin-bottom:2px">👃 嗅感 — 我担忧/预防什么</div>
      <input id="s5-xiu" type="text" placeholder="加保险丝 / 温度传感器 / 过流保护" style="width:100%;background:var(--s);border:1px solid var(--b);color:var(--t);padding:4px 7px;border-radius:3px;font:inherit;font-size:11px">
    </div>
    <div style="margin-bottom:8px">
      <div style="font-size:10px;color:var(--td);margin-bottom:2px">👅 味感 — 我的评判标准</div>
      <input id="s5-wei" type="text" placeholder="越便宜越好 / 小板 / 好焊 / 不限价格" style="width:100%;background:var(--s);border:1px solid var(--b);color:var(--t);padding:4px 7px;border-radius:3px;font:inherit;font-size:11px">
    </div>
    <div style="display:flex;gap:6px;margin-bottom:8px">
      <button class="btn-sm" onclick="parseSense5()" style="flex:1;padding:5px;font-size:11px;background:var(--s)">🔍 解析五感</button>
      <button class="btn-sm" onclick="executeSense5()" style="flex:1;padding:5px;font-size:11px;background:var(--ad);color:var(--a);border-color:var(--a)">⬡ 感于无感</button>
    </div>
    <div id="sense5-result" style="font-size:10px;line-height:1.7"></div>
  </div>
  <div id="tab-wugan" class="tab-content hidden">
    <div id="wugan-content"><span style="color:var(--td)">⬡ 无感评分 — 老庄六感聚合...</span></div>
    <div style="padding:8px;border-top:1px solid var(--b);margin-top:8px">
      <div style="font-size:11px;color:var(--td);margin-bottom:4px">心斋·以气听</div>
      <div style="display:flex;gap:6px">
        <input id="f-xinzhai" type="text" placeholder="虚而待物·输入意图…" style="flex:1;background:var(--s);border:1px solid var(--b);color:var(--t);padding:4px 8px;border-radius:4px;font:inherit;font-size:11px">
        <button class="btn-sm" onclick="callXinzhai()" style="padding:3px 8px;font-size:11px">以气听</button>
      </div>
      <div id="xinzhai-result" style="font-size:10px;color:var(--a);margin-top:4px;line-height:1.6"></div>
    </div>
  </div>
  <!-- 感知仪表盘 tab -->
  <div id="tab-intent" class="tab-content hidden" style="padding:8px;overflow-y:auto">
    <div style="font-size:10px;color:var(--td);margin-bottom:8px;line-height:1.6">
      🔮 <b style="color:var(--a)">感知先于开口</b> — AI主动溯源底层意图，无需用户描述
    </div>
    <div id="intent-loading" style="color:var(--td);font-size:11px">扫描项目文件中...</div>
    <div id="intent-content" style="display:none">
      <div style="background:var(--s);border:1px solid var(--b);border-radius:5px;padding:10px;margin-bottom:8px">
        <div style="font-size:10px;color:var(--td);text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">当前焦点</div>
        <div id="i-focus" style="color:var(--a);font-size:12px;font-weight:bold"></div>
        <div id="i-project" style="color:var(--td);font-size:10px;margin-top:2px"></div>
      </div>
      <div style="background:var(--s);border:1px solid var(--b);border-radius:5px;padding:10px;margin-bottom:8px">
        <div style="font-size:10px;color:var(--td);text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">推断需求</div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span id="i-template" style="color:var(--a);font-size:13px;font-weight:bold"></span>
          <span id="i-conf" style="background:var(--ad);color:var(--a);padding:1px 6px;border-radius:3px;font-size:10px"></span>
        </div>
        <div id="i-reqs" style="font-size:10px;color:var(--td);line-height:1.7"></div>
      </div>
      <div id="guardian-block" style="background:var(--s);border:1px solid var(--b);border-radius:5px;padding:10px;margin-bottom:8px">
        <div style="font-size:10px;color:var(--td);text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">风险预判</div>
        <div id="i-verdict" style="font-size:12px;margin-bottom:4px"></div>
        <div id="i-risks" style="font-size:10px;line-height:1.8"></div>
      </div>
      <div style="background:var(--s);border:1px solid var(--b);border-radius:5px;padding:10px;margin-bottom:8px">
        <div style="font-size:10px;color:var(--td);text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">执行路径</div>
        <div id="i-action" style="color:var(--a);font-size:11px;margin-bottom:4px"></div>
        <code id="i-cmd" style="font-size:10px;color:var(--td);background:#0d1117;padding:3px 6px;border-radius:3px;display:block"></code>
        <button class="btn-sm" id="i-run-btn" style="margin-top:6px;padding:4px 10px;font-size:11px;background:var(--ad);color:var(--a);border-color:var(--a)" onclick="runFromIntent()">▶ 执行推荐流水线</button>
      </div>
      <div style="background:var(--s);border:1px solid var(--b);border-radius:5px;padding:10px;margin-bottom:8px">
        <div style="font-size:10px;color:var(--td);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px">决策溯源</div>
        <div id="i-trace" style="font-size:10px;color:var(--td);line-height:1.7"></div>
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn-sm" onclick="loadIntent(true)" style="flex:1;padding:4px;font-size:10px">⟳ 重新扫描</button>
        <button class="btn-sm" onclick="loadGuardian()" style="flex:1;padding:4px;font-size:10px">🛡 重新检测风险</button>
      </div>
      <div style="font-size:9px;color:var(--td);margin-top:4px;text-align:right">
        <span id="i-scan-info"></span>
      </div>
    </div>
  </div>
</div>
</main>
</div><!-- /view-pro -->
<div id="status-bar" style="display:none">
  <span id="sb-jobs">任务: 0</span>
  <span id="sb-templates">模板: 0</span>
  <span id="sb-agent">Agent: 检测中...</span>
</div>
<script>
// ────── 全局状态 ──────
let _selected = null, _curJobId = null, _sseSource = null;
let _daoData = null, _daoMode = 'dao'; // dao | pro

// ────── 工具 ──────
async function api(path, opts={}) {
  try { const r = await fetch(path, opts); return await r.json(); }
  catch(e) { return {error: e.message}; }
}

// ────── 模式切换 ──────
function toggleMode() {
  _daoMode = _daoMode === 'dao' ? 'pro' : 'dao';
  const isDao = _daoMode === 'dao';
  document.getElementById('view-dao').style.display = isDao ? '' : 'none';
  document.getElementById('view-pro').style.display = isDao ? 'none' : '';
  document.getElementById('status-bar').style.display = isDao ? 'none' : '';
  document.getElementById('mode-btn').textContent = isDao ? '工程师模式' : '← 意图模式';
  if (!isDao) { loadTemplates(); refreshJobs(); }
}

// ────── 置信标签 ──────
function confBadge(c) {
  const cls = c==='确认'?'confirmed': c==='推断'?'inferred':'guessed';
  return `<span class="conf conf-${cls}">${c}</span>`;
}

// ────── 示例 ──────
function setExample(el) {
  document.getElementById('dao-input').value = el.textContent;
  analyzeIntent();
}

// ────── 意图分析 ──────
async function analyzeIntent() {
  const text = document.getElementById('dao-input').value.trim();
  if (!text) return;
  const btn = document.getElementById('btn-analyze');
  btn.disabled = true; btn.textContent = '分析中...';
  const d = await api('/api/dao/parse', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({text})});
  btn.disabled = false; btn.textContent = '分析 ▶';
  if (d.error) { alert('分析失败: ' + d.error); return; }
  _daoData = d;
  renderIntentCard(d);
  document.getElementById('intent-card').style.display = 'block';
  document.getElementById('correction-panel').style.display = 'none';
  document.getElementById('progress-card').style.display = 'none';
}

// ────── 渲染意图卡 ──────
function renderIntentCard(d) {
  const s1 = d.step1_intent_confirmation || {};
  const s2 = d.step2_state_sensing || {};
  const s4 = d.step4_confidence || {};
  const s5 = d.step5_next_action || {};
  const sum = d.summary || {};

  // 摘要
  document.getElementById('ic-summary').textContent = sum.one_line || d.raw_input;

  // 字段网格
  const fields = [
    {icon:'🎯', label:'目的', val: (s1.purpose||{}).text, conf: (s1.purpose||{}).confidence},
    {icon:'📶', label:'连接', val: (s1.connectivity||{}).text, conf: (s1.connectivity||{}).confidence},
    {icon:'🔌', label:'供电', val: (s1.power||{}).text, conf: (s1.power||{}).confidence},
  ];
  const sensors = (s1.sensors||[]);
  if (sensors.length) fields.push({icon:'🌡', label:'传感器', val: sensors.map(x=>x.text).join('、'), conf: sensors[0].confidence});
  const outputs = (s1.outputs||[]);
  if (outputs.length) fields.push({icon:'💡', label:'输出功能', val: outputs.map(x=>x.text).join('、'), conf: outputs[0].confidence});
  const cons = (s1.constraints||[]);
  if (cons.length) fields.push({icon:'⚡', label:'约束', val: cons.map(x=>x.text).join('、'), conf: cons[0].confidence});

  document.getElementById('ic-fields').innerHTML = fields.map(f =>
    `<div class="ic-field"><div class="ic-field-label">${f.icon} ${f.label}</div>
     <div class="ic-field-value">${f.val||'—'}${confBadge(f.conf||'猜测')}</div></div>`
  ).join('');

  // 元信息
  document.getElementById('ic-meta').innerHTML =
    `<span>💰 预计费用: ${s2.cost_range||''}</span>
     <span>📐 尺寸: ${s2.size||''}</span>
     <span>⏱ 交货: ${s2.lead_time||''}</span>`;

  // 置信度
  document.getElementById('conf-overall').textContent = '整体置信度: ' + (s4.overall||'');

  // 猜测问题
  const qs = s5.questions || [];
  if (qs.length) {
    document.getElementById('questions-block').style.display = 'block';
    document.getElementById('questions-list').innerHTML =
      qs.map(q => `<div class="q-item">• ${q}</div>`).join('');
  } else {
    document.getElementById('questions-block').style.display = 'none';
  }
}

// ────── 纠正 ──────
function showCorrection() {
  const p = document.getElementById('correction-panel');
  p.style.display = p.style.display === 'none' ? 'block' : 'none';
  if (p.style.display === 'block') document.getElementById('corr-input').focus();
}

async function submitCorrection() {
  const corrText = document.getElementById('corr-input').value.trim();
  if (!corrText || !_daoData) return;
  const d = await api('/api/dao/correct', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      session_id: _daoData.session_id,
      original_input: _daoData.raw_input,
      correction_text: corrText,
      field: 'general', old_val: '', new_val: corrText,
    })});
  if (d.error) { alert('纠正失败: ' + d.error); return; }
  _daoData = d;
  renderIntentCard(d);
  document.getElementById('corr-input').value = '';
  document.getElementById('correction-panel').style.display = 'none';
  // 视觉反馈
  const card = document.getElementById('intent-card');
  card.style.borderColor = 'var(--warn)';
  setTimeout(() => { card.style.borderColor = 'var(--b)'; }, 800);
}

// ────── 确认执行 ──────
async function confirmAndBuild() {
  if (!_daoData) return;
  const template = (_daoData.step3_execution_path||{}).template_internal || '';
  if (!template) { alert('无法识别对应方案，请补充描述'); return; }

  document.getElementById('intent-card').style.display = 'none';
  document.getElementById('correction-panel').style.display = 'none';
  document.getElementById('progress-card').style.display = 'block';

  const steps = (_daoData.step3_execution_path||{}).steps || [];
  renderProgressSteps(steps, -1);

  const r = await api('/api/dao/confirm', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({template, description: _daoData.raw_input})});
  if (r.error) {
    document.getElementById('prog-title').innerHTML = '<span style="color:var(--err)">启动失败: ' + r.error + '</span>';
    return;
  }
  _curJobId = r.job_id;
  pollDaoProgress(r.job_id, steps);
}

function renderProgressSteps(steps, activeIdx) {
  document.getElementById('prog-steps').innerHTML = steps.map((s, i) => {
    const cls = i < activeIdx ? 'step-done' : i === activeIdx ? 'step-active' : 'step-wait';
    const icon = i < activeIdx ? '✓' : i === activeIdx ? '●' : String(i+1);
    return `<div class="prog-step">
      <div class="step-icon ${cls}">${icon}</div>
      <div>${s.action} <span style="color:var(--td);font-size:11px">${s.duration}</span></div>
    </div>`;
  }).join('');
}

async function pollDaoProgress(jobId, steps) {
  let active = 0;
  const poll = async () => {
    const d = await api(`/api/jobs/${jobId}`);
    if (!d || d.error) { setTimeout(poll, 2000); return; }
    // 根据日志数量推算步骤进度
    const logCount = (d.logs || []).length;
    active = Math.min(Math.floor(logCount / 5), steps.length - 1);
    renderProgressSteps(steps, active);
    if (d.status === 'done') {
      renderProgressSteps(steps, steps.length);
      showDaoResult(d.result || {});
    } else if (d.status === 'error') {
      document.getElementById('prog-title').innerHTML = '<span style="color:var(--err)">制作遇到问题</span>';
      document.getElementById('prog-result').style.display = 'block';
      document.getElementById('prog-result').innerHTML = '<span style="color:var(--err)">错误: ' + (d.result&&d.result.error||'未知') + '</span>';
    } else {
      setTimeout(poll, 1500);
    }
  };
  poll();
}

function showDaoResult(res) {
  document.getElementById('prog-title').innerHTML = '✅ 制作完成！';
  const el = document.getElementById('prog-result');
  el.style.display = 'block';
  let html = '';
  if (res.success) {
    html += `<div style="color:var(--a);font-size:14px;margin-bottom:8px">你的设计已准备好！</div>`;
    if (res.gerber_zip) html += `<div>📦 生产文件已生成（可直接上传JLCPCB下单）</div>`;
    if (res.pcb_path)  html += `<div>📄 设计文件: <span style="color:var(--td);font-size:11px">${res.pcb_path}</span></div>`;
    const bom = res.bom || {};
    if (bom.total_cost) html += `<div>💰 物料成本: ¥${bom.total_cost}</div>`;
  } else {
    html += `<div style="color:var(--warn)">制作遇到一些技术问题，请切换到「工程师模式」查看详情</div>`;
  }
  el.innerHTML = html;
  document.getElementById('prog-done-actions').style.display = 'block';
}

function resetDao() {
  document.getElementById('dao-input').value = '';
  document.getElementById('intent-card').style.display = 'none';
  document.getElementById('correction-panel').style.display = 'none';
  document.getElementById('progress-card').style.display = 'none';
  _daoData = null;
}

// Enter键分析
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('dao-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) analyzeIntent();
  });
  document.getElementById('corr-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') submitCorrection();
  });
  // 状态检测
  checkAgentStatus();
  setInterval(checkAgentStatus, 60000);
});

async function checkAgentStatus() {
  const s = await api('/api/status');
  const badge = document.getElementById('hdr-agent');
  if (s && s.agent && s.agent.available) {
    badge.textContent = 'AI就绪 ✓'; badge.className = 'hdr-badge';
  } else if (s && !s.warming) {
    badge.textContent = '离线模式'; badge.className = 'hdr-badge off';
  }
}

// ────── 工程师模式函数 (下方全部保留) ──────

async function loadTemplates() {
  const d = await api('/api/list');
  if (d.error) return;
  const el = document.getElementById('dna-list');
  el.innerHTML = '';
  d.templates.forEach(t => {
    const div = document.createElement('div');
    div.className = 'dna-card';
    div.dataset.name = t.name;
    div.innerHTML = `<div class="name">${t.name}</div>
      <div class="desc">${t.description}</div>
      <div class="meta">
        <span>${t.component_count}元件</span>
        <span>¥${t.cost_components.toFixed(0)}</span>
        <span>${t.board_size[0]}×${t.board_size[1]}mm</span>
      </div>`;
    div.onclick = () => selectTemplate(t);
    el.appendChild(div);
  });
  document.getElementById('sb-templates').textContent = `模板: ${d.count}`;
}

function selectTemplate(t) {
  _selected = t;
  document.querySelectorAll('.dna-card').forEach(c => {
    c.classList.toggle('selected', c.dataset.name === t.name);
  });
  document.getElementById('f-circuit').value = t.name;
  const notes = t.design_notes ? `<br><span class="label">备注:</span> ${t.design_notes.replace(/\n/g,'<br>')}` : '';
  document.getElementById('sel-info').innerHTML =
    `<span class="label">描述:</span> ${t.description}<br>
     <span class="label">板尺寸:</span> ${t.board_size[0]}×${t.board_size[1]}mm &nbsp;
     <span class="label">元件:</span> ${t.component_count}个 &nbsp;
     <span class="label">网络:</span> ${t.net_count}个<br>
     <span class="label">单板成本:</span> ¥${t.cost_components.toFixed(1)} &nbsp;
     <span class="label">5板打样:</span> ¥${t.cost_5boards.toFixed(0)}${notes}`;
}

async function submitJob() {
  const circuit = document.getElementById('f-circuit').value.trim();
  if (!circuit) { alert('请先选择一个电路模板'); return; }
  const mode    = document.getElementById('f-mode').value;
  const output  = document.getElementById('f-output').value.trim() || null;
  const autoFix = document.getElementById('f-fix').checked;
  const iters   = parseInt(document.getElementById('f-iter').value);

  const body = {circuit, output, auto_fix: autoFix, iterations: iters};
  const ep   = mode === 'full' ? '/api/full' : '/api/design';
  const d    = await api(ep, {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});

  if (d.error) { logLine(`❌ 启动失败: ${d.error}`, 'err'); return; }
  _curJobId = d.job_id;
  clearLog();
  logLine(`▶ 任务已启动 [${d.job_id}] circuit=${circuit} mode=${mode}`, 'ok');
  switchTab('logs');
  startSSE(d.job_id);
  refreshJobs();
}

function startSSE(jid) {
  if (_sseSource) _sseSource.close();
  _sseSource = new EventSource(`/api/logs/${jid}`);
  _sseSource.onmessage = e => {
    if (e.data === '__DONE__') {
      logLine('── 任务完成 ──', 'ok');
      _sseSource.close();
      setTimeout(() => { showJobResult(jid); refreshJobs(); }, 600);
      return;
    }
    try { logLine(JSON.parse(e.data)); } catch{ logLine(e.data); }
  };
}

async function askAdvisor() {
  const desc = document.getElementById('f-ask').value.trim();
  if (!desc) return;
  document.getElementById('advisor-tip').textContent = '💡 分析中...';
  const r = await api('/api/recommend', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({description: desc})});
  if (r.error) { document.getElementById('advisor-tip').textContent = '❌ ' + r.error; return; }
  const hint = r.hint ? ` — ${r.hint}` : '';
  document.getElementById('advisor-tip').textContent = `推荐: ${r.template}${hint}`;
  if (r.template) {
    document.getElementById('f-circuit').value = r.template;
    const dna = r.dna_info || {};
    if (dna.name) {
      document.getElementById('sel-info').innerHTML =
        `<span style="color:var(--a)">💡 AI推荐</span> ${r.reason}<br>`
        + `<span class="label">模板:</span> ${dna.name} · ${dna.description}<br>`
        + (dna.design_notes ? `<span class="label">设计备注:</span> ${dna.design_notes.replace(/\n/g,'<br>')}` : '');
      document.querySelectorAll('.dna-card').forEach(c =>
        c.classList.toggle('selected', c.dataset.name === r.template));
    }
  }
}

async function openLceda() {
  const r = await api('/api/open_lceda', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({})});
  if (r && r.ok) logLine('INFO: 嘉立创EDA已启动', 'ok');
  else logLine('ERROR: 打开嘉立创EDA失败 ' + (r&&r.error||''), 'err');
}

async function openKicad(pcbPath) {
  const r = await api('/api/open', {method:'POST', headers:{'Content-Type':'application/json'},
                                    body: JSON.stringify({pcb_path: pcbPath})});
  if (r && r.ok) logLine('INFO: KiCad已启动 → ' + r.pcb);
  else logLine('ERROR: 打开KiCad失败 ' + (r&&r.error||''), 'err');
}

async function showJobResult(jid) {
  const d = await api(`/api/jobs/${jid}`);
  if (!d || d.error) return;
  const res = d.result || {};
  const sr  = (res.sense_report||{}).senses || {};
  const drc = sr['鼻_drc'] || {};
  const gbr = sr['触_gerbers'] || {};
  const rpt = res.sense_report || {};

  let html = `<div class="result-block"><div class="rt">任务结果 [${jid.toUpperCase()}]</div>`;

  // 成功/失败
  if (res.success !== undefined)
    html += `<div style="color:${res.success?'var(--a)':'var(--err)'};margin-bottom:6px;font-weight:700">${res.success?'✅ 成功':'❌ 失败'}</div>`;

  // PCB 文件 + 打开KiCad
  if (res.pcb_path)
    html += `<div>📄 PCB: <span style="font-size:10px;word-break:break-all">${res.pcb_path}</span>`
          + ` <button class="btn-sm" onclick="openKicad('${res.pcb_path.replace(/\\/g,'\\\\')}')">打开 KiCad</button></div>`;

  // Gerber ZIP
  if (res.gerber_zip)
    html += `<div>📦 Gerber: <span style="font-size:10px;word-break:break-all">${res.gerber_zip}</span></div>`;

  // 自动布线结果行
  const routeStep = (res.steps||[]).find(s => s.step==='autoroute');
  if (routeStep !== undefined) {
    const rOk = routeStep.routed||0, rFail = routeStep.unrouted||0, rSegs = routeStep.segments||0;
    const rEng = routeStep.engine||'bfs';
    const rColor = rFail===0 ? 'var(--a)' : 'var(--warn)';
    const engLabel = rEng==='freerouting'?'🌐freerouting':rEng==='bfs_fallback'?'⚡BFS降级':'⚡BFS';
    html += `<div class="sense-row"><span class="sense-icon">布线</span>`
          + `<span class="sense-val" style="color:${rColor}">${rFail===0?'✅':'⚠️'} `
          + `${rOk}条通 / ${rFail}失败 / ${rSegs}段铜线 [${engLabel}]</span></div>`;
  }

  // 五感行
  if (res.bom) {
    const b = res.bom;
    html += `<div class="sense-row"><span class="sense-icon">舌</span><span class="sense-val">${b.verdict||''} · ${b.difficulty||''}</span></div>`;
  }
  if (drc.verdict)
    html += `<div class="sense-row"><span class="sense-icon">鼻</span><span class="sense-val">${drc.verdict}</span></div>`;
  if (gbr.verdict)
    html += `<div class="sense-row"><span class="sense-icon">触</span><span class="sense-val">${gbr.verdict}</span></div>`;

  // DRC 详情卡
  if (drc.verdict) {
    const uc   = drc.unconnected_count || 0;
    const crit = drc.critical_violations || 0;
    const fpw  = drc.fp_warnings || 0;
    const ucColor = uc>0  ? 'var(--warn)' : 'var(--a)';
    const cvColor = crit>0? 'var(--err)'  : 'var(--a)';
    html += `<div style="margin:8px 0 4px;border-top:1px solid var(--bd);padding-top:6px;font-size:11px;color:var(--td)">── DRC 详情 ──</div>`;
    html += `<div style="display:flex;gap:12px;font-size:12px;margin-bottom:6px">`;
    html += `<span style="color:${ucColor}">📐 未布线 ${uc}</span>`;
    html += `<span style="color:${cvColor}">⚡ 严重违规 ${crit}</span>`;
    html += `<span style="color:var(--td)">ℹ️ 封装提示 ${fpw}</span>`;
    html += `</div>`;
    if (drc.unconnected_nets && drc.unconnected_nets.length>0) {
      const nets = drc.unconnected_nets.slice(0,6).join(', ') + (drc.unconnected_nets.length>6?'…':'');
      html += `<div style="font-size:10px;color:var(--td);margin-bottom:4px">未布线网络: ${nets}</div>`;
    }
  }

  // 下一步卡
  const nextStep = rpt.next_step || (res.error ? '修复错误后重试' : '');
  if (nextStep) {
    const nsColor = rpt.ready_to_order ? 'var(--a)' : (rpt.routing_needed ? 'var(--warn)' : 'var(--err)');
    html += `<div style="margin:8px 0 4px;border-top:1px solid var(--bd);padding-top:6px;font-size:11px;color:var(--td)">── 下一步 ──</div>`;
    html += `<div style="color:${nsColor};font-size:12px;line-height:1.5">${nextStep}</div>`;
  }

  if (res.error) html += `<div style="color:var(--err);margin-top:6px">错误: ${res.error}</div>`;
  html += '</div>';
  document.getElementById('job-result').innerHTML = html;
}

function logLine(msg, cls='') {
  const box = document.getElementById('log-box');
  const lvl = typeof msg === 'string' ?
    (msg.includes('ERROR')||msg.includes('❌') ? 'err' :
     msg.includes('WARNING')||msg.includes('⚠') ? 'warn' :
     msg.includes('✅')||msg.includes('▶') ? 'ok' : 'info') : 'info';
  const span = document.createElement('span');
  span.className = `log-${cls||lvl}`;
  span.textContent = (typeof msg === 'string' ? msg : JSON.stringify(msg)) + '\n';
  box.appendChild(span);
  box.scrollTop = box.scrollHeight;
}

function clearLog() { document.getElementById('log-box').innerHTML = ''; }

async function refreshJobs() {
  const d = await api('/api/jobs');
  if (!d.jobs) return;
  document.getElementById('sb-jobs').textContent = `任务: ${d.jobs.length}`;
  const el = document.getElementById('jobs-list');
  if (!d.jobs.length) { el.innerHTML = '<span style="color:var(--td)">暂无任务</span>'; return; }
  el.innerHTML = d.jobs.map(j =>
    `<div class="job-row">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
        <span class="jid">[${j.id}]</span>
        <span class="jstatus ${j.status}">${j.status}</span>
      </div>
      <div style="color:var(--td)">${j.circuit} · ${j.cmd}</div>
      ${j.status!=='pending'?`<a href="#" onclick="startSSE('${j.id}');switchTab('logs');clearLog();return false" style="font-size:10px">查看日志</a>`:''}
    </div>`
  ).join('');
}

async function checkStatus() {
  switchTab('env');
  document.getElementById('env-content').innerHTML = '<span style="color:var(--td)">检测中 (含agent详细环境，约3-8秒)...</span>';
  const d = await api('/api/status?full=1');
  if (d.error) { document.getElementById('env-content').innerHTML = `<span style="color:var(--err)">${d.error}</span>`; return; }
  const env = d.pcb_env || {};
  const agent = d.agent || {};
  // update badge
  const badge = document.getElementById('agent-badge');
  if (agent.available) { badge.textContent = 'Agent :9904 ✓'; badge.className = 'badge'; }
  else { badge.textContent = 'Agent ✗'; badge.className = 'badge off'; }
  document.getElementById('sb-agent').textContent = `Agent: ${agent.available ? '在线' : '离线'}`;
  let html = `<div class="result-block"><div class="rt">PCB环境</div>`;
  const icons = {'✅ 可用':'✅','⚠️ 不可用':'⚠️'};
  for (const [k, v] of Object.entries(env)) {
    if (k === 'control_levels') {
      for (const [lk, lv] of Object.entries(v))
        html += `<div>${lv} ${lk}</div>`;
    } else {
      html += `<div><span style="color:var(--td)">${k}:</span> ${v}</div>`;
    }
  }
  html += '</div>';
  if (agent.available && agent.env) {
    html += `<div class="result-block"><div class="rt">Agent五感 (:9904)</div>`;
    for (const [k, v] of Object.entries(agent.env)) {
      const ok = v.available;
      html += `<div>${ok?'✅':'❌'} ${k}: ${v.version||v.path||'—'}</div>`;
    }
    html += '</div>';
  }
  document.getElementById('env-content').innerHTML = html;
}

function switchTab(name) {
  ['logs','jobs','env','wugan','sense5','intent'].forEach(n => {
    document.getElementById(`tab-${n}`).classList.toggle('hidden', n!==name);
  });
  if (name === 'intent' && !_intentData) loadIntent(false);
  document.querySelectorAll('.tab').forEach((t,i) =>
    t.classList.toggle('active', ['logs','jobs','env','wugan','sense5','intent'][i]===name));
  if (name === 'jobs')   refreshJobs();
  if (name === 'wugan')  refreshWugan();
}

async function parseSense5() {
  const body = getSense5Input();
  if (!body.shi && !body.ting && !body.chu && !body.xiu && !body.wei) {
    document.getElementById('sense5-result').textContent = '请至少填写一项五感需求';
    return;
  }
  document.getElementById('sense5-result').innerHTML = '<span style="color:var(--td)">解析中...</span>';
  const r = await api('/api/user_sense', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r.error) { document.getElementById('sense5-result').innerHTML = `<span style="color:var(--err)">❌ ${r.error}</span>`; return; }
  const sel = r.selection || {};
  const req = r.requirement || {};
  let html = `<div style="border-top:1px solid var(--b);padding-top:6px">`;
  html += `<div style="color:var(--a);font-weight:bold;margin-bottom:4px">🦴 天理识别: ${sel.template||'?'} <span style="color:var(--td);font-weight:normal">(${Math.round((sel.confidence||0)*100)}%)</span></div>`;
  html += `<div style="color:var(--td);margin-bottom:3px">场景: ${sel.scenario||''} · MCU: ${req.preferred_mcu||'auto'} · 成本: ${sel.cost_est||'?'}</div>`;
  if ((sel.adjustments||[]).length) {
    html += `<div style="color:var(--warn);margin-top:4px">📌 设计调整:</div>`;
    sel.adjustments.forEach(a => { html += `<div style="color:var(--t);padding-left:8px">• ${a}</div>`; });
  }
  if ((sel.warnings||[]).length) {
    html += `<div style="color:var(--err);margin-top:4px">⚠️ 注意:</div>`;
    sel.warnings.forEach(w => { html += `<div style="color:var(--warn);padding-left:8px">${w}</div>`; });
  }
  html += `<div style="margin-top:6px"><button class="btn-sm" onclick="applyTemplate('${sel.template||''}')">\u2190 应用模板</button></div>`;
  html += '</div>';
  document.getElementById('sense5-result').innerHTML = html;
}

async function executeSense5() {
  const body = {...getSense5Input(), execute: true};
  if (!body.shi && !body.ting && !body.chu && !body.xiu && !body.wei) {
    document.getElementById('sense5-result').textContent = '请至少填写一项五感需求';
    return;
  }
  document.getElementById('sense5-result').innerHTML = '<span style="color:var(--a)">⬡ 无为启动中...</span>';
  const r = await api('/api/user_sense', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r.error) { document.getElementById('sense5-result').innerHTML = `<span style="color:var(--err)">${r.error}</span>`; return; }
  _curJobId = r.job_id;
  clearLog();
  logLine(`⬡ 五感无为流水线已启动 [${r.job_id}]`, 'ok');
  switchTab('logs');
  startSSE(r.job_id);
  refreshJobs();
  document.getElementById('sense5-result').innerHTML = `<span style="color:var(--a)">⬡ 已启动 [${r.job_id}] — 请查看实时日志</span>`;
}

function getSense5Input() {
  return {
    shi:  document.getElementById('s5-shi').value.trim(),
    ting: document.getElementById('s5-ting').value.trim(),
    chu:  document.getElementById('s5-chu').value.trim(),
    xiu:  document.getElementById('s5-xiu').value.trim(),
    wei:  document.getElementById('s5-wei').value.trim(),
  };
}

function applyTemplate(t) {
  if (!t) return;
  document.getElementById('f-circuit').value = t;
  document.querySelectorAll('.dna-card').forEach(c => c.classList.toggle('selected', c.dataset.name===t));
  switchTab('logs');
  logLine(`← 应用五感推荐模板: ${t}`, 'ok');
}

async function refreshWugan(circuit) {
  const c = circuit || document.getElementById('f-circuit').value.trim();
  const url = c ? `/api/wugan?circuit=${encodeURIComponent(c)}` : '/api/wugan';
  document.getElementById('wugan-content').innerHTML = '<span style="color:var(--td)">⬡ 六感感知中...</span>';
  const d = await api(url);
  if (d.error) { document.getElementById('wugan-content').innerHTML = `<span style="color:var(--err)">${d.error}</span>`; return; }
  const w = d.wugan || {};
  const score = w.score || 0;
  const lvl   = w.paoding_level || '族庖';
  const lvlColor = lvl==='庖丁'?'var(--a)': lvl==='良庖'?'var(--warn)':'var(--err)';
  const senses = d.senses || {};
  const barW  = Math.round(score * 1.6);
  let html = `<div style="margin-bottom:8px">`;
  html += `<div style="display:flex;justify-content:space-between;margin-bottom:4px">`;
  html += `<span style="font-size:13px;font-weight:bold;color:${lvlColor}">${lvl}</span>`;
  html += `<span style="font-size:18px;font-weight:bold;color:${score>=90?'var(--a)':score>=70?'var(--warn)':'var(--err)'}">${score}/100</span></div>`;
  html += `<div style="height:6px;background:var(--b);border-radius:3px;overflow:hidden">`;
  html += `<div style="width:${barW}px;height:100%;background:${score>=90?'var(--a)':score>=70?'var(--warn)':'var(--err)'};transition:width .5s"></div></div>`;
  html += `<div style="font-size:11px;color:var(--t);margin-top:6px">${w.verdict||''}</div>`;
  html += `<div style="font-size:10px;color:var(--a);margin-top:4px">${w.next_step||''}</div>`;
  html += `</div><div style="border-top:1px solid var(--b);padding-top:8px">`;
  const labels = {'视':'👁视','听':'👂听','触':'🤝触','嗅':'👃嗅','味':'👅味'};
  for (const [k,v] of Object.entries(senses)) {
    const s  = (v&&v.score)||0, m=(v&&v.max)||15;
    const pct= Math.round(s/m*100);
    html += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;font-size:11px">`;
    html += `<span style="width:30px;text-align:center">${labels[k]||k}</span>`;
    html += `<div style="flex:1;height:4px;background:var(--b);border-radius:2px">`;
    html += `<div style="width:${pct}%;height:100%;background:var(--a)"></div></div>`;
    html += `<span style="width:50px;text-align:right;color:var(--td)">${s}/${m}</span></div>`;
  }
  html += '</div>';
  document.getElementById('wugan-content').innerHTML = html;
}

async function callXinzhai() {
  const desc = document.getElementById('f-xinzhai').value.trim();
  if (!desc) return;
  document.getElementById('xinzhai-result').textContent = '心斋感知中...';
  const r = await api('/api/xinzhai', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify({description:desc})});
  if (r.error) { document.getElementById('xinzhai-result').textContent = '❌ ' + r.error; return; }
  const t = r.recommended || '未识别';
  const fields = (r.active_fields||[]).join('+')||'场域未明';
  const missing = (r.missing_elements||[]).join(' · ');
  document.getElementById('xinzhai-result').innerHTML =
    `<b style="color:var(--a)">气聚于</b> ${fields}<br>`
    + `<b>推荐:</b> ${t} — ${r.reason||''}<br>`
    + (missing ? `<b style="color:var(--warn)">虚(缺):</b> ${missing}<br>` : '')
    + `<span style="color:var(--td)">${r.wu_note||''}</span>`;
  if (t !== '未识别') {
    document.getElementById('f-circuit').value = t;
    document.getElementById('f-ask').value = desc;
    document.querySelectorAll('.dna-card').forEach(c => c.classList.toggle('selected', c.dataset.name===t));
  }
}

// ── 感知仪表盘 (intent + guardian) ── 全局函数 ────────────
var _intentData = null;
async function loadIntent(force) {
  force = !!force;
  document.getElementById('intent-loading').style.display='block';
  document.getElementById('intent-content').style.display='none';
  const url = force ? '/api/intent?force=1' : '/api/intent';
  const d = await api(url);
  if (d.error) {
    document.getElementById('intent-loading').textContent = '感知失败: ' + d.error;
    return;
  }
  _intentData = d;
  document.getElementById('i-focus').textContent = d.user_focus || '未检测到活动';
  document.getElementById('i-project').textContent = d.active_project
    ? d.active_project.split('\\').pop() + '  (扫描' + d.files_found + '个文件,耗时' + d.scan_duration_s + 's)'
    : '扫描' + d.files_found + '个文件';
  document.getElementById('i-template').textContent = d.primary_template;
  document.getElementById('i-conf').textContent = Math.round(d.primary_confidence * 100) + '% 置信';
  const reqs = d.circuit_requirements || {};
  document.getElementById('i-reqs').innerHTML = Object.entries(reqs)
    .map(([k,v]) => '<b>' + k + '</b>: ' + v).join('<br>');
  document.getElementById('i-action').textContent = d.recommended_action;
  document.getElementById('i-cmd').textContent = d.recommended_cmd;
  document.getElementById('i-scan-info').textContent =
    '扫描于 ' + new Date(d.timestamp * 1000).toLocaleTimeString();
  const trace = (d.decision_trace || []).slice(0,6);
  document.getElementById('i-trace').innerHTML = trace.length
    ? trace.map(function(t){return '['+t.template+'] '+t.file+' — w='+t.weight;}).join('<br>')
    : '无溯源数据';
  document.getElementById('intent-loading').style.display='none';
  document.getElementById('intent-content').style.display='block';
  if (d.primary_template) loadGuardian(d.primary_template);
}
async function loadGuardian(tpl) {
  var template = tpl || (_intentData && _intentData.primary_template) || '';
  if (!template) return;
  const d = await api('/api/guardian?template=' + encodeURIComponent(template));
  if (d.error) {
    document.getElementById('i-verdict').textContent = '风险分析失败: ' + d.error;
    return;
  }
  document.getElementById('i-verdict').innerHTML =
    d.verdict + '  <span style="color:var(--td);font-size:10px">风险分: ' + d.risk_score + '/100</span>';
  const fl = d.findings || [];
  document.getElementById('i-risks').innerHTML = fl.length
    ? fl.map(function(f){
        var c = f.severity==='CRITICAL'?'var(--err)':f.severity==='HIGH'?'var(--warn)':'var(--td)';
        return '<span style="color:'+c+'">['+f.severity+']</span> '+f.title+'<br>'
          +'<span style="color:var(--td);padding-left:12px">↑ '+f.fix_hint+'</span>';
      }).join('<br>')
    : '<span style="color:var(--a)">✓ 零风险</span>';
}
function runFromIntent() {
  if (!_intentData) return;
  var t = _intentData.primary_template;
  if (!t) return;
  document.getElementById('f-circuit').value = t;
  document.getElementById('f-mode').value = 'full';
  switchTab('logs');
  submitJob();
}

// 启动
(async () => {
  await loadTemplates();
  // 快速轮询状态直到缓存就绪
  async function pollStatus(retries) {
    const s = await api('/api/status');
    const badge = document.getElementById('agent-badge');
    if (s.warming) {
      badge.textContent = 'Agent 检测中...'; badge.className = 'badge off';
      document.getElementById('sb-agent').textContent = 'Agent: 检测中';
      if (retries > 0) setTimeout(() => pollStatus(retries - 1), 1500);
      return;
    }
    if (s.agent && s.agent.available) {
      badge.textContent = 'Agent :9904 ✓'; badge.className = 'badge';
      document.getElementById('sb-agent').textContent = 'Agent: 在线';
    } else {
      badge.textContent = 'Agent ✗'; badge.className = 'badge off';
      document.getElementById('sb-agent').textContent = 'Agent: 离线';
    }
  }
  pollStatus(8);
  refreshJobs();
  setInterval(refreshJobs, 5000);
  setInterval(() => pollStatus(1), 65000); // re-check after TTL
})();
</script>
</body></html>"""


# ─────────────────────────────────────────────────────────────
# 启动入口
# ─────────────────────────────────────────────────────────────
def main(port: int = 9906):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        from flask import Flask  # noqa: check import
    except ImportError:
        print("Flask未安装, 请运行: pip install flask")
        sys.exit(1)

    app = create_app()
    print(f"\n{'='*60}")
    print(f"  ⬡ PCBBrain — 老庄六感·用户五感·JLCPCB·MCP v9")
    print(f"{'='*60}")
    print(f"  面B Web UI:      http://localhost:{port}/")
    print(f"  面A REST API:    http://localhost:{port}/api/")
    print(f"  用户五感:      POST /api/user_sense  (视/听/触/嗅/味→PCB)")
    print(f"  老庄无感:      GET  /api/wugan        (0-100分·庚丁境界)")
    print(f"  心斋以气听:   POST /api/xinzhai      (意图场域→DNA)")
    print(f"  无为流水线:   POST /api/wuwei        (自动闭环)")
    print(f"  AI顾问:        POST /api/recommend   (自然语言→DNA)")
    print(f"  LLM对话:       POST /api/chat         (Ollama本地)")
    print(f"  嘉立创EDA:     POST /api/open_lceda")
    print(f"  JLCPCB BOM:   GET  /api/jlcpcb/bom?template=xxx")
    print(f"  JLCPCB成本:   GET  /api/jlcpcb/cost?template=xxx")
    print(f"  JLCPCB导出:   POST /api/jlcpcb/export")
    print(f"  MCP工具:       GET  /api/mcp/tools")
    print(f"  MCP服务:       python pcb_mcp.py  →  :9907")
    print(f"  Agent:        http://localhost:9904  (remote_agent)")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9906
    main(port)
