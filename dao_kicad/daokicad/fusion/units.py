"""Units & layer helpers for the fusion layer.

KiCad's API speaks nanometres and a numeric ``BoardLayer`` enum; humans (and the
agent's natural-language intents) speak millimetres and names like ``F.Cu``.
These helpers translate both ways and tolerate the spellings people actually
use (``F.Cu``, ``F_Cu``, ``BL_F_Cu``, ``f.cu``).
"""
from __future__ import annotations


from kipy.geometry import Vector2, Angle
from kipy.util.board_layer import BoardLayer

NM_PER_MM = 1_000_000

# Canonical board layers we let the agent address by friendly name.
_LAYER_NAMES = [
    "F.Cu", "B.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu",
    "F.SilkS", "B.SilkS", "F.Mask", "B.Mask", "F.Paste", "B.Paste",
    "F.Adhes", "B.Adhes", "F.CrtYd", "B.CrtYd", "F.Fab", "B.Fab",
    "Edge.Cuts", "Margin", "User.Drawings", "User.Comments",
    "Dwgs.User", "Cmts.User",
]

# enum member names follow BL_<layer with . and dashes -> _>
def _enum_member(name: str) -> str:
    return "BL_" + name.replace(".", "_").replace("-", "_")


_NAME_TO_ID: dict[str, int] = {}
_ID_TO_NAME: dict[int, str] = {}
for _n in _LAYER_NAMES:
    _val = getattr(BoardLayer, _enum_member(_n), None)
    if _val is not None:
        _NAME_TO_ID[_n.lower()] = int(_val)
        _ID_TO_NAME.setdefault(int(_val), _n)
# common aliases
_ALIASES = {
    "f.silkscreen": "f.silks", "b.silkscreen": "b.silks",
    "top": "f.cu", "bottom": "b.cu", "gnd_layer": "f.cu",
    "silk": "f.silks", "courtyard": "f.crtyd", "edge": "edge.cuts",
}


def layer_id(name: str | int) -> int:
    """Resolve a layer name (any common spelling) or passthrough id to its id."""
    if isinstance(name, int):
        return name
    key = str(name).strip().lower()
    if key.startswith("bl_"):
        key = key[3:]
    key = key.replace("_", ".")
    key = _ALIASES.get(key, key)
    key = key.replace("silkscreen", "silks")
    if key in _NAME_TO_ID:
        return _NAME_TO_ID[key]
    # try BL_ enum directly
    val = getattr(BoardLayer, _enum_member(str(name)), None)
    if val is not None:
        return int(val)
    raise ValueError(f"未知层名: {name!r} (可用: {', '.join(sorted(_ID_TO_NAME.values()))})")


def layer_name(layer_id_: int) -> str:
    return _ID_TO_NAME.get(int(layer_id_), f"layer#{int(layer_id_)}")


def mm(value: float) -> int:
    """Millimetres → nanometres (KiCad's internal unit)."""
    return int(round(float(value) * NM_PER_MM))


def to_mm(nm: int) -> float:
    return round(int(nm) / NM_PER_MM, 6)


def vec_mm(x_mm: float, y_mm: float) -> Vector2:
    return Vector2.from_xy(mm(x_mm), mm(y_mm))


def vec_nm(x_nm: int, y_nm: int) -> Vector2:
    """Build a vector straight from nanometres (KiCad internal units)."""
    return Vector2.from_xy(int(x_nm), int(y_nm))


def angle_deg(deg: float) -> Angle:
    return Angle.from_degrees(float(deg))


def xy_mm(v: Vector2) -> tuple[float, float]:
    return (to_mm(v.x), to_mm(v.y))
