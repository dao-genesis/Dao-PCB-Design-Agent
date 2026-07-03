"""tools — KiCad 工具调用注册表 (把 KiCad 本源能力暴成 Agent 可调工具集)。

道法自然: 一个 AI IDE 的本源之二是「工具调用」——上游模型以 OpenAI function-call
形式请求工具, IDE 侧把这些调用**落到本体真实能力**上。Cursor/Windsurf 的工具是
read_file/edit/run_command…(见 devin-remote 的 `lsp_tools.js`); 我们专属于 KiCad,
故工具集是 **KiCad 本源原子**:

  * kicad_project_state  · 项目全貌 (板况/DRC/流程/产物/git/动作日志 一次拿全 — 眼睛)
  * kicad_board_summary  · 读活板摘要 (层数/元件/网/未连接)
  * kicad_eval           · 在活体内核进程内执行 pcbnew 代码 (通达全 7913 SWIG 面)
  * kicad_run_flow       · 跑全流程 (build→heal→route→fab), 真 DRC 裁决
  * kicad_native_list    · 列可用 native_* 本源原子层 (自省)
  * devin_ask            · 委派 Devin Cloud 会话 (云端 Agent 协同)

设计: 注册表与「处理器」解耦——`ToolRegistry(handlers)` 吃一组 name→callable, 供
CI 注入桩纯测; `default_registry(bridge)` 把工具接到真 bridge/native 能力。工具名
兼容 IDE 别名 (源 lsp_tools.js:5 ALIAS): 上游发别名 → 规范化为标准名。

反臆造: schema 的 parameters 与真实处理器签名对齐; 未注册工具调用返回明确 error,
不静默吞。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# ── IDE 别名 → KiCad 标准工具名 (源 lsp_tools.js:5 · 上游习惯用通用名) ──────
ALIAS: Dict[str, str] = {
    "eval": "kicad_eval",
    "run_command": "kicad_eval",
    "bash": "kicad_eval",
    "focus": "kicad_focus",
    "highlight": "kicad_focus",
    "select": "kicad_focus",
    "goto": "kicad_focus",
    "move": "kicad_move",
    "move_footprint": "kicad_move",
    "route": "kicad_route",
    "add_track": "kicad_route",
    "zone": "kicad_zone",
    "pour": "kicad_zone",
    "copper_pour": "kicad_zone",
    "delete": "kicad_delete",
    "remove": "kicad_delete",
    "clear": "kicad_delete",
    "ripup": "kicad_delete",
    "rip_up": "kicad_delete",
    "delete_tracks": "kicad_delete",
    "drc": "kicad_drc",
    "check": "kicad_drc",
    "run_drc": "kicad_drc",
    "save": "kicad_save",
    "save_board": "kicad_save",
    "summary": "kicad_board_summary",
    "read_board": "kicad_board_summary",
    "run_flow": "kicad_run_flow",
    "flow": "kicad_run_flow",
    "list_dir": "kicad_native_list",
    "ask": "devin_ask",
    "state": "kicad_project_state",
    "project_state": "kicad_project_state",
    "read_project": "kicad_project_state",
}


def normalize_name(name: str) -> str:
    """别名 → 标准名 (已是标准名则原样)。"""
    return ALIAS.get(name, name)


# ── KiCad 工具 schema (OpenAI function-call 格式) ─────────────────────────
KICAD_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "kicad_project_state",
            "description": (
                "读取整个 PCB 项目的实时全貌 (Agent 的眼睛): 板况(封装/走线/网/铜皮)"
                "、最近 DRC 结果、全流程报告、产物(gerber/钻孔/可投厂)、git 进度、"
                "最近动作日志。做任何改动前先看全貌, 避免盲人摸象。无副作用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_dir": {
                        "type": "string",
                        "description": "项目根目录 (缺省从活板文件自动反推)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_board_summary",
            "description": (
                "读取当前活体 KiCad 板 (live BOARD) 的摘要: 层数/元件数/网络数/"
                "未连接数/板框尺寸。无副作用。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_eval",
            "description": (
                "在活体内核进程内执行一段 pcbnew Python 代码 (可通达全部 SWIG 类/"
                "方法), 直改这块活着的板并回传真实回值。这是 KiCad 的通用工具原语——"
                "浇铜/加过孔/查坐标等皆经此。代码里 `board` 已绑定当前活板。"
                "常用 API: len(board.GetFootprints()) 数件 (无 GetFootprintCount); "
                "board.FindFootprintByReference('R1') 取件; pcbnew.ToMM/FromMM 单位。"
                "移件用 kicad_move, 跑 DRC 用 kicad_drc (pcbnew 无 DRC 类)。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 pcbnew Python 代码 (最后一表达式为回值)",
                    }
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_focus",
            "description": (
                "在 KiCad 画布上选中并缩放定位到给定元件 (参考号列表), 让用户实时"
                "看到你正指着哪个件——相当于把光标落到真实 PCB 上。讲解某件、定位"
                "问题、或改动前, 先调它高亮聚焦; 用户即刻在画布上看见。无破坏性副作用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "元件参考号列表, 如 [\"R2\", \"C11\", \"U1\"]",
                    }
                },
                "required": ["refs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_move",
            "description": (
                "移动/旋转活板上的一个封装 (相对偏移 dx_mm/dy_mm 或绝对坐标 "
                "x_mm/y_mm, 可附旋转), 画布即时刷新, 回传前后坐标供验证。"
                "比手写 kicad_eval 代码更稳、一次原子完成。改完记得 kicad_save。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "封装参考号, 如 R2"},
                    "dx_mm": {"type": "number", "description": "水平相对偏移 (mm, 右为正)"},
                    "dy_mm": {"type": "number", "description": "垂直相对偏移 (mm, 下为正)"},
                    "x_mm": {"type": "number", "description": "绝对 X (mm, 与 dx 互斥)"},
                    "y_mm": {"type": "number", "description": "绝对 Y (mm, 与 dy 互斥)"},
                    "rotate_deg": {"type": "number", "description": "附加旋转角 (度, 逆时针)"},
                },
                "required": ["ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_route",
            "description": (
                "在两个封装焊盘间布线 (须同网络): 自动直连或 L 形两段走线, "
                "画布即时刷新, 回传段数/长度。比手写 kicad_eval 建 PCB_TRACK 稳。"
                "布完可用 kicad_drc 裁决、kicad_save 落盘。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_ref": {"type": "string", "description": "起点封装参考号, 如 R1"},
                    "end_ref": {"type": "string", "description": "终点封装参考号, 如 R2"},
                    "start_pad": {"type": "string", "description": "起点焊盘号 (缺省第一个)"},
                    "end_pad": {"type": "string", "description": "终点焊盘号 (缺省第一个)"},
                    "width_mm": {"type": "number", "description": "线宽 (mm, 默 0.25)"},
                    "layer": {"type": "string", "description": "铜层名 (默 F.Cu)"},
                },
                "required": ["start_ref", "end_ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_zone",
            "description": (
                "在板框范围对指定网络铺铜并立即填充 (如 GND 地铜), 回传填充面积。"
                "铺完可用 kicad_drc 裁决、kicad_save 落盘。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "net": {"type": "string", "description": "网络名, 如 GND"},
                    "layer": {"type": "string", "description": "铜层名 (默 F.Cu)"},
                    "clearance_mm": {"type": "number", "description": "间距 (mm, 默 0.3)"},
                },
                "required": ["net"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_delete",
            "description": (
                "从活板删除布线图元 (拆线/清铜): kind 选 tracks(走线含过孔)/"
                "zones(铺铜)/all; 可按 net 和 layer 过滤只删某网/某层。回传各类"
                "删除数。重布前先拆旧线用它, 比手写 kicad_eval 遍历稳。删完可"
                "kicad_route 重布、kicad_drc 裁决、kicad_save 落盘。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["tracks", "zones", "all"],
                        "description": "删什么: tracks=走线+过孔, zones=铺铜, all=两者 (默 tracks)",
                    },
                    "net": {"type": "string", "description": "只删此网络名下的图元 (缺省全部网)"},
                    "layer": {"type": "string", "description": "只删此铜层上的图元, 如 F.Cu (缺省全部层)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_drc",
            "description": (
                "对活板跑真 kicad-cli DRC (先自动落盘): 回传违规数/未连接数与报告"
                "路径, 报告写进项目 out/ 供全貌感知拾取。改板后用它裁决, 比跑全流程快。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "out_dir": {"type": "string", "description": "报告输出目录 (缺省项目 out/)"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_save",
            "description": (
                "把活板保存到其自身 .kicad_pcb 文件 (Ctrl+S 内化为工具)。对板子做过"
                "改动后调它落盘, 无需触碰 GUI。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_run_flow",
            "description": (
                "跑 PCB 全流程 (build→place→heal→fanout→route→ground→fab), 以真 "
                "kicad-cli DRC 为唯一裁判, 产出可投厂工件。吃任一上游 (.net/.kicad_sch/"
                "spec)。耗时较长。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "上游文件路径 (.net/.kicad_sch) 或 spec 名"},
                    "out_dir": {"type": "string", "description": "工件输出目录"},
                    "route": {"type": "boolean", "description": "是否布线 (默 true)"},
                    "fab": {"type": "boolean", "description": "是否出 fab 工件 (默 true)"},
                },
                "required": ["source", "out_dir"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kicad_native_list",
            "description": "列出可用的 native_* 本源原子层 (自省 KiCad 能力面)。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "devin_ask",
            "description": (
                "把一个子任务委派给 Devin Cloud 会话 (云端 Agent 协同), 返回会话 id。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "委派给云端 Agent 的任务描述"}
                },
                "required": ["prompt"],
            },
        },
    },
]

_SCHEMA_BY_NAME: Dict[str, Dict[str, Any]] = {
    t["function"]["name"]: t for t in KICAD_TOOLS
}


class ToolRegistry:
    """工具注册表: name→handler(args)->result。与 schema 解耦, 便于注入桩。"""

    def __init__(self, handlers: Optional[Dict[str, Callable[..., Any]]] = None) -> None:
        self._handlers: Dict[str, Callable[..., Any]] = dict(handlers or {})

    def register(self, name: str, handler: Callable[..., Any]) -> None:
        self._handlers[normalize_name(name)] = handler

    def names(self) -> List[str]:
        return list(self._handlers.keys())

    def schemas(self) -> List[Dict[str, Any]]:
        """仅返回**已注册且有 schema**的工具定义 (供传给模型)。"""
        return [_SCHEMA_BY_NAME[n] for n in self._handlers if n in _SCHEMA_BY_NAME]

    def dispatch(self, name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """调用工具; 统一返回 {"ok":bool, "result"|"error":...}。"""
        std = normalize_name(name)
        handler = self._handlers.get(std)
        if handler is None:
            return {"ok": False,
                    "error": "未注册工具: %s (可用: %s)"
                             % (name, ", ".join(sorted(self._handlers)))}
        try:
            res = handler(**(args or {}))
        except TypeError as e:
            return {"ok": False, "error": "参数不符 (%s): %s" % (std, e)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        if isinstance(res, dict) and "ok" in res:
            return res
        return {"ok": True, "result": res}


# ── 本源原子层清单 (自省用; 与 kicad_origin/origin/native_*.py 对齐) ────────
NATIVE_ATOMS: List[str] = [
    "native_build", "native_lib", "native_libscan", "native_netlist",
    "native_schematic", "native_recipe", "native_place", "native_move",
    "native_group", "native_route", "native_track", "native_arc", "native_via",
    "native_fanout", "native_ripup", "native_zone", "native_zonefill",
    "native_stitch", "native_thermal", "native_stackup", "native_outline",
    "native_panel", "native_keepout", "native_ops", "native_drc", "native_bom",
    "native_assembly", "native_render", "native_audit", "native_courtyard",
    "native_dimension", "native_fiducial", "native_paste", "native_mask",
    "native_silk", "native_netclass", "native_diff", "native_flow", "native_live",
]


def default_registry(bridge: Any) -> ToolRegistry:
    """把 KiCad 工具接到真 bridge / native 能力。

    bridge 需暴露 live_summary / live_eval / new_session (见 DevinKiCadBridge)。
    kicad_run_flow 延迟导入 native_flow (KiCad 依赖) → 仅调用时才触碰。
    """
    reg = ToolRegistry()

    reg.register("kicad_project_state",
                 lambda project_dir="": bridge.project_state(project_dir or None))
    reg.register("kicad_board_summary", lambda: bridge.live_summary())
    reg.register("kicad_eval", lambda code: bridge.live_eval(code))
    reg.register("kicad_focus", lambda refs: bridge.live_focus(refs))
    reg.register("kicad_move",
                 lambda ref, dx_mm=0.0, dy_mm=0.0, x_mm=None, y_mm=None,
                 rotate_deg=0.0: bridge.live_move(
                     ref, dx_mm=dx_mm, dy_mm=dy_mm, x_mm=x_mm, y_mm=y_mm,
                     rotate_deg=rotate_deg))
    reg.register("kicad_route",
                 lambda start_ref, end_ref, start_pad="", end_pad="",
                 width_mm=0.25, layer="F.Cu": bridge.live_route(
                     start_ref, end_ref, start_pad=start_pad, end_pad=end_pad,
                     width_mm=width_mm, layer=layer))
    reg.register("kicad_zone",
                 lambda net, layer="F.Cu", clearance_mm=0.3: bridge.live_zone(
                     net, layer=layer, clearance_mm=clearance_mm))
    reg.register("kicad_delete",
                 lambda kind="tracks", net="", layer="": bridge.live_delete(
                     kind=kind, net=net, layer=layer))
    reg.register("kicad_drc", lambda out_dir="": bridge.live_drc(out_dir))
    reg.register("kicad_save", lambda: bridge.live_save())

    def _run_flow(source: str, out_dir: str, route: bool = True, fab: bool = True) -> Dict[str, Any]:
        from kicad_origin.origin import native_flow  # 延迟导入 (KiCad 依赖)
        board = native_flow.run_flow(source, out_dir, route=route, fab=fab)
        return {"ok": True, "result": {"out_dir": out_dir, "board": str(board)}}

    reg.register("kicad_run_flow", _run_flow)
    reg.register("kicad_native_list", lambda: {"ok": True, "result": list(NATIVE_ATOMS)})
    reg.register("devin_ask", lambda prompt: bridge.new_session(prompt))
    return reg
