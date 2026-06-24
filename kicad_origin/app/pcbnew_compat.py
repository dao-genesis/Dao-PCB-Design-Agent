"""
pcbnew_compat — KiCad SWIG `pcbnew` 模块的形似神似复刻 (30+ API)

目标: 让 `import pcbnew` 的老脚本 (如 pcb_brain) 无需修改即可在
      无 KiCad 安装的环境运行.

API 覆盖 (按使用频率排序):
    顶层函数:
        LoadBoard(path)               → BOARD
        SaveBoard(path, board)        → bool
        GetBoard()                    → BOARD (上次 LoadBoard 的)
        FromMM(mm) / ToMM(iu)         → IU 转换
        wxPoint(x, y) = VECTOR2I(x,y) → 坐标点
        Refresh()                     → no-op (GUI 刷新, 兼容只)
        IsRunningOnWxPython()         → False

    BOARD:
        GetFootprints()               → [FOOTPRINT]
        GetTracks()                   → [TRACK | VIA]
        GetNetsByName()               → {name: NETINFO}
        GetNetsByNetcode()            → {code: NETINFO}
        GetCopperLayerCount()         → int
        GetBoardEdgesBoundingBox()    → BOX2I
        GetTitle()                    → str
        Save(path)                    → bool
        Add(item)                     → None
        Remove(item)                  → None

    FOOTPRINT:
        GetReference() / SetReference(s)
        GetValue() / SetValue(s)
        GetPosition() / SetPosition(p)  ← VECTOR2I (IU)
        GetOrientation()              → EDA_ANGLE (度 * 10)
        SetOrientation(deg10)
        GetLayerName()                → "F.Cu" / "B.Cu"
        GetPads()                     → [PAD]
        GetFPID()                     → LIB_ID

    PAD:
        GetNumber() / GetName()       → str
        GetPosition()                 → VECTOR2I
        GetSize()                     → VECTOR2I (w, h)
        GetDrillSize()                → VECTOR2I
        GetNetCode()                  → int
        GetNetname()                  → str
        GetLayerName()                → str

    TRACK / VIA:
        GetStart() / GetEnd()         → VECTOR2I
        GetWidth()                    → IU
        GetLayerName()                → str
        GetNetCode() / GetNetname()
        IsVia() / IsTrack()

    NETINFO:
        GetNetCode() / GetNetname()

约定: 所有"位置/尺寸"在 SWIG pcbnew 里是 IU (整数 nm).
      我们用 VECTOR2I 包一层, .x/.y 持 IU, 提供 .ToMM() 便利.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from kicad_origin.origin.unit import IU_PER_MM, mm_to_iu, iu_to_mm
from kicad_origin.pcb.board import Board
from kicad_origin.pcb.footprint import Footprint as _Footprint
from kicad_origin.pcb.pad import Pad as _Pad
from kicad_origin.pcb.track import Segment as _Segment, Via as _Via
from kicad_origin.pcb.net import Net as _Net
from kicad_origin.pcb.geometry import Point as _Point


# ─────────────────────────────────────────────────────────────────────
# 全局: 最近 LoadBoard 的 board (供 GetBoard())
# ─────────────────────────────────────────────────────────────────────
_current_board: Optional["BOARD"] = None


# ─────────────────────────────────────────────────────────────────────
# 顶层: 单位 / 坐标
# ─────────────────────────────────────────────────────────────────────
def FromMM(mm: float) -> int:
    """mm → IU (整数 nm). KiCad 6+ 使用 1 IU = 1 nm."""
    return int(round(mm * IU_PER_MM))


def ToMM(iu: int) -> float:
    """IU → mm."""
    return iu / IU_PER_MM


class VECTOR2I:
    """KiCad 坐标点 (IU)."""

    __slots__ = ("x", "y")

    def __init__(self, x: int = 0, y: int = 0):
        self.x = int(x)
        self.y = int(y)

    def __repr__(self) -> str:
        return f"VECTOR2I({self.x}, {self.y})"

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, VECTOR2I):
            return NotImplemented
        return self.x == o.x and self.y == o.y

    def __iter__(self):
        return iter((self.x, self.y))

    def ToMM(self) -> tuple:
        return (ToMM(self.x), ToMM(self.y))

    @classmethod
    def from_mm(cls, x_mm: float, y_mm: float) -> "VECTOR2I":
        return cls(FromMM(x_mm), FromMM(y_mm))

    @classmethod
    def from_point(cls, p: _Point) -> "VECTOR2I":
        return cls(FromMM(p.x), FromMM(p.y))

    def to_point(self) -> _Point:
        return _Point(ToMM(self.x), ToMM(self.y))


# wxPoint 是 KiCad 早期别名, 现在 = VECTOR2I
wxPoint = VECTOR2I


# ─────────────────────────────────────────────────────────────────────
# BOX2I — 矩形
# ─────────────────────────────────────────────────────────────────────
class BOX2I:
    __slots__ = ("_orig", "_size")

    def __init__(self, origin: VECTOR2I, size: VECTOR2I):
        self._orig = origin
        self._size = size

    def GetOrigin(self) -> VECTOR2I: return self._orig
    def GetSize(self)   -> VECTOR2I: return self._size
    def GetWidth(self)  -> int:      return self._size.x
    def GetHeight(self) -> int:      return self._size.y
    def GetX(self)      -> int:      return self._orig.x
    def GetY(self)      -> int:      return self._orig.y
    def GetEnd(self)    -> VECTOR2I:
        return VECTOR2I(self._orig.x + self._size.x,
                        self._orig.y + self._size.y)


# ─────────────────────────────────────────────────────────────────────
# EDA_ANGLE — KiCad 7+ 用 EDA_ANGLE 类, 历史是度*10 整数
# ─────────────────────────────────────────────────────────────────────
class EDA_ANGLE:
    """简化角度. AsDegrees() / AsTenthsOfADegree()."""

    __slots__ = ("_deg",)

    def __init__(self, deg: float):
        self._deg = float(deg)

    def AsDegrees(self) -> float: return self._deg
    def AsTenthsOfADegree(self) -> int: return int(self._deg * 10)
    def AsRadians(self) -> float:
        import math
        return math.radians(self._deg)

    def __repr__(self) -> str:
        return f"EDA_ANGLE({self._deg}°)"


# ─────────────────────────────────────────────────────────────────────
# LIB_ID — "Lib:Name"
# ─────────────────────────────────────────────────────────────────────
class LIB_ID:
    __slots__ = ("_lib", "_name")

    def __init__(self, lib_id_str: str = ""):
        if ":" in lib_id_str:
            self._lib, self._name = lib_id_str.split(":", 1)
        else:
            self._lib, self._name = "", lib_id_str

    def GetLibNickname(self) -> str:  return self._lib
    def GetLibItemName(self) -> str:  return self._name
    def GetUniStringLibId(self) -> str:
        return f"{self._lib}:{self._name}" if self._lib else self._name
    def Format(self) -> str:          return self.GetUniStringLibId()


# ─────────────────────────────────────────────────────────────────────
# NETINFO
# ─────────────────────────────────────────────────────────────────────
class NETINFO_ITEM:
    __slots__ = ("_net",)

    def __init__(self, net: _Net):
        self._net = net

    def GetNetCode(self) -> int: return self._net.number
    def GetNetname(self) -> str: return self._net.name


# ─────────────────────────────────────────────────────────────────────
# PAD wrapper
# ─────────────────────────────────────────────────────────────────────
class PAD:
    __slots__ = ("_pad", "_parent_pos")

    def __init__(self, pad: _Pad, parent_pos: _Point):
        self._pad = pad
        self._parent_pos = parent_pos

    # 名/号
    def GetNumber(self) -> str: return self._pad.number
    def GetName(self)   -> str: return self._pad.number  # alias

    # 位置 (绝对 IU)
    def GetPosition(self) -> VECTOR2I:
        pp = self._pad.position
        return VECTOR2I.from_mm(self._parent_pos.x + pp.x,
                                self._parent_pos.y + pp.y)

    # 尺寸
    def GetSize(self) -> VECTOR2I:
        s = self._pad.size
        return VECTOR2I.from_mm(s.x, s.y)

    def GetDrillSize(self) -> VECTOR2I:
        d = self._pad.drill
        return VECTOR2I.from_mm(d, d)

    # 网络
    def GetNetCode(self) -> int: return self._pad.net_number
    def GetNetname(self) -> str: return self._pad.net_name

    # 层
    def GetLayerName(self) -> str:
        layers = self._pad.layers
        return layers[0] if layers else ""

    # 形状/类型
    def GetShape(self) -> str: return self._pad.shape
    def GetAttribute(self) -> str: return self._pad.type

    def __repr__(self) -> str:
        return f"PAD({self._pad.number} @ {self.GetPosition()})"


# ─────────────────────────────────────────────────────────────────────
# FOOTPRINT wrapper
# ─────────────────────────────────────────────────────────────────────
class FOOTPRINT:
    __slots__ = ("_fp",)

    def __init__(self, fp: _Footprint):
        self._fp = fp

    # 标识
    def GetReference(self) -> str: return self._fp.ref
    def SetReference(self, v: str) -> None: self._fp.ref = v
    def GetValue(self)     -> str: return self._fp.value
    def SetValue(self, v: str)     -> None: self._fp.value = v

    def GetFPID(self) -> LIB_ID: return LIB_ID(self._fp.lib_id)

    # 位置/方向
    def GetPosition(self) -> VECTOR2I:
        return VECTOR2I.from_point(self._fp.position)

    def SetPosition(self, p: Union[VECTOR2I, tuple, _Point]) -> None:
        if isinstance(p, VECTOR2I):
            self._fp.position = p.to_point()
        elif isinstance(p, _Point):
            self._fp.position = p
        elif isinstance(p, tuple) and len(p) >= 2:
            # 假定是 IU 整数 (与 SWIG 一致)
            if isinstance(p[0], (int,)) and abs(p[0]) > 10000:
                self._fp.position = _Point(ToMM(p[0]), ToMM(p[1]))
            else:
                self._fp.position = _Point(float(p[0]), float(p[1]))
        else:
            raise TypeError(f"无法识别的位置: {p!r}")

    def GetOrientation(self) -> EDA_ANGLE:
        return EDA_ANGLE(self._fp.rotation)

    def SetOrientation(self, deg10_or_angle: Union[int, float, EDA_ANGLE]) -> None:
        if isinstance(deg10_or_angle, EDA_ANGLE):
            self._fp.rotation = deg10_or_angle.AsDegrees()
        elif isinstance(deg10_or_angle, (int, float)):
            # KiCad 老 API 用 度 * 10
            v = float(deg10_or_angle)
            # 启发式: 若 |v| > 360 视为 deg10, 否则视为度
            self._fp.rotation = (v / 10.0) if abs(v) > 360 else v
        else:
            raise TypeError(f"未知方向格式: {deg10_or_angle!r}")

    # 层
    def GetLayerName(self) -> str: return self._fp.layer
    def IsFlipped(self)   -> bool: return self._fp.is_back_side

    # 焊盘
    def GetPads(self) -> List[PAD]:
        ppos = self._fp.position
        return [PAD(p, ppos) for p in self._fp.pads()]

    Pads = GetPads  # 别名 (有些版本叫 Pads())

    # 属性
    def GetField(self, name: str) -> str:
        return self._fp.get_property(name, "")

    def SetField(self, name: str, value: str) -> None:
        self._fp.set_property(name, value)

    def __repr__(self) -> str:
        return f"FOOTPRINT({self._fp.ref}={self._fp.lib_id})"


# ─────────────────────────────────────────────────────────────────────
# TRACK / VIA
# ─────────────────────────────────────────────────────────────────────
class TRACK:
    __slots__ = ("_seg",)

    def __init__(self, seg: _Segment):
        self._seg = seg

    def GetStart(self) -> VECTOR2I: return VECTOR2I.from_point(self._seg.start)
    def GetEnd(self)   -> VECTOR2I: return VECTOR2I.from_point(self._seg.end)
    def GetWidth(self) -> int:      return FromMM(self._seg.width)
    def GetLayerName(self) -> str:  return self._seg.layer
    def GetNetCode(self) -> int:    return self._seg.net
    def GetNetname(self)  -> str:   return ""  # segment 无法直接得名, 留给 board map
    def IsVia(self)   -> bool:      return False
    def IsTrack(self) -> bool:      return True
    def GetLength(self) -> int:     return FromMM(self._seg.length)


class VIA:
    __slots__ = ("_via",)

    def __init__(self, via: _Via):
        self._via = via

    def GetPosition(self) -> VECTOR2I: return VECTOR2I.from_point(self._via.position)
    def GetStart(self)    -> VECTOR2I: return self.GetPosition()
    def GetEnd(self)      -> VECTOR2I: return self.GetPosition()
    def GetWidth(self)    -> int:      return FromMM(self._via.size)
    def GetDrillValue(self) -> int:    return FromMM(self._via.drill)
    def GetNetCode(self)  -> int:      return self._via.net
    def GetLayerName(self) -> str:     return self._via.layer
    def TopLayer(self)    -> str:
        ls = self._via.layers; return ls[0] if ls else ""
    def BottomLayer(self) -> str:
        ls = self._via.layers; return ls[-1] if ls else ""
    def IsVia(self)   -> bool: return True
    def IsTrack(self) -> bool: return False


# ─────────────────────────────────────────────────────────────────────
# BOARD wrapper (主入口)
# ─────────────────────────────────────────────────────────────────────
class BOARD:
    """KiCad SWIG BOARD 形似复刻."""

    __slots__ = ("_board",)

    def __init__(self, board: Board):
        self._board = board

    # 元信息
    def GetTitle(self) -> str:           return self._board.title
    def GetFileName(self) -> str:        return str(self._board.path) if self._board.path else ""
    def GetCopperLayerCount(self) -> int: return self._board.copper_layer_count()

    # 元件
    def GetFootprints(self) -> List[FOOTPRINT]:
        return [FOOTPRINT(f) for f in self._board.footprints()]

    Footprints = GetFootprints  # alias

    def FindFootprintByReference(self, ref: str) -> Optional[FOOTPRINT]:
        f = self._board.footprint_by_ref(ref)
        return FOOTPRINT(f) if f else None

    # 走线/过孔
    def GetTracks(self) -> List[Any]:
        out: List[Any] = [TRACK(s) for s in self._board.segments()]
        out.extend(VIA(v) for v in self._board.vias())
        return out

    Tracks = GetTracks

    # 网络
    def GetNetsByName(self) -> Dict[str, NETINFO_ITEM]:
        return {n.name: NETINFO_ITEM(n) for n in self._board.nets()}

    def GetNetsByNetcode(self) -> Dict[int, NETINFO_ITEM]:
        return {n.number: NETINFO_ITEM(n) for n in self._board.nets()}

    def FindNet(self, name_or_code: Union[str, int]) -> Optional[NETINFO_ITEM]:
        if isinstance(name_or_code, str):
            n = self._board.net_by_name(name_or_code)
        else:
            n = self._board.net_by_number(name_or_code)
        return NETINFO_ITEM(n) if n else None

    # 几何
    def GetBoardEdgesBoundingBox(self) -> BOX2I:
        outline = self._board.board_outline()
        if outline is None:
            bb = self._board.bbox()
            if bb.empty:
                return BOX2I(VECTOR2I(0, 0), VECTOR2I(0, 0))
            return BOX2I(
                VECTOR2I.from_mm(bb.x_min, bb.y_min),
                VECTOR2I.from_mm(bb.width, bb.height),
            )
        return BOX2I(
            VECTOR2I.from_mm(outline.x_min, outline.y_min),
            VECTOR2I.from_mm(outline.width, outline.height),
        )

    def ComputeBoundingBox(self, *, edges_only: bool = False) -> BOX2I:
        return self.GetBoardEdgesBoundingBox()

    # 增删改
    def Add(self, item: Any) -> None:
        if isinstance(item, FOOTPRINT):
            self._board.add_footprint(item._fp)
        elif isinstance(item, TRACK):
            self._board.add_segment(item._seg)
        elif isinstance(item, VIA):
            self._board.add_via(item._via)
        else:
            raise TypeError(f"无法 Add 的类型: {type(item).__name__}")

    def Remove(self, item: Any) -> bool:
        uuid = ""
        if isinstance(item, FOOTPRINT):
            uuid = item._fp.uuid
        elif isinstance(item, TRACK):
            uuid = item._seg.uuid
        elif isinstance(item, VIA):
            uuid = item._via.uuid
        if not uuid:
            return False
        return self._board.remove_by_uuid(uuid) > 0

    # 持久化
    def Save(self, path: Optional[str] = None) -> bool:
        try:
            self._board.save(path)
            return True
        except Exception:
            return False

    def __repr__(self) -> str:
        return f"BOARD({self._board.title!r} fp={len(self._board.footprints())})"


# ─────────────────────────────────────────────────────────────────────
# 顶层函数
# ─────────────────────────────────────────────────────────────────────
def LoadBoard(path: Union[str, Path]) -> BOARD:
    """加载 .kicad_pcb 文件. 等同 pcbnew.LoadBoard(path)."""
    global _current_board
    b = Board.load(path)
    _current_board = BOARD(b)
    return _current_board


def SaveBoard(path: Union[str, Path], board: BOARD) -> bool:
    """保存 board 到 path. 等同 pcbnew.SaveBoard."""
    return board.Save(path)


def NewBoard(path: Union[str, Path] = None) -> BOARD:
    """新建空板. KiCad 9+ 提供. 等同 Board.empty + 包裹."""
    global _current_board
    b = Board.empty()
    if path:
        b.path = Path(path)
    _current_board = BOARD(b)
    return _current_board


def GetBoard() -> Optional[BOARD]:
    """返回最近一次 LoadBoard / NewBoard 的 board.

    在 KiCad GUI 内, 此函数返回当前打开的板; 在脚本里我们用最近 Load 的.
    """
    return _current_board


def Refresh() -> None:
    """GUI 刷新 — no-op."""
    pass


def IsRunningOnWxPython() -> bool:
    """是否在 KiCad GUI 进程中. 我们永远是脚本, 返回 False."""
    return False


# ─────────────────────────────────────────────────────────────────────
# 常量映射 (KiCad 用大量 PCB_* / F_Cu / B_Cu 整数常量)
# ─────────────────────────────────────────────────────────────────────
# 层 ID (KiCad pcbnew_swig 编号)
F_Cu      = 0
B_Cu      = 31
F_Mask    = 38
B_Mask    = 39
F_SilkS   = 36
B_SilkS   = 37
F_Paste   = 34
B_Paste   = 35
F_Fab     = 49
B_Fab     = 48
Edge_Cuts = 44


# ─────────────────────────────────────────────────────────────────────
# 自检
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        b = LoadBoard(sys.argv[1])
        print(f"board: {b}")
        print(f"  footprints: {len(b.GetFootprints())}")
        print(f"  tracks:     {len(b.GetTracks())}")
        print(f"  nets:       {len(b.GetNetsByName())}")
        print(f"  copper:     {b.GetCopperLayerCount()}")
        bbox = b.GetBoardEdgesBoundingBox()
        print(f"  bbox:       origin={bbox.GetOrigin()} size={bbox.GetSize()}")
        for fp in b.GetFootprints()[:3]:
            print(f"  fp: {fp.GetReference()} = {fp.GetValue()}")
            print(f"      pos={fp.GetPosition()} ({fp.GetPosition().ToMM()} mm)")
            print(f"      lib_id={fp.GetFPID().GetUniStringLibId()}")
    else:
        # 自检: 单位转换 + LoadBoard + GetFootprints + 改 ref + Save
        import tempfile
        b = NewBoard()
        assert FromMM(1.0) == 1_000_000, "1mm = 1e6 IU"
        assert ToMM(1_000_000) == 1.0
        v = VECTOR2I.from_mm(50.0, 30.0)
        assert v.x == 50_000_000 and v.y == 30_000_000
        assert v.ToMM() == (50.0, 30.0)
        # 注入 sys.modules + 真正 import pcbnew 看看
        from kicad_origin.app import install_pcbnew_compat
        install_pcbnew_compat()
        import pcbnew  # 应当拿到我们
        assert pcbnew.FromMM(2.5) == 2_500_000
        print("pcbnew_compat 自检 ✅")
        print(f"  pcbnew = {pcbnew.__name__}")
        print(f"  FromMM(2.5) = {pcbnew.FromMM(2.5)}")
        print(f"  IsRunningOnWxPython = {pcbnew.IsRunningOnWxPython()}")
