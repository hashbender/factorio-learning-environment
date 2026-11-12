"""TransportBelt.inventory always holds both lanes (kept out of entities.py, whose class bodies are shown to agents)."""


def both_lanes(cls, v):
    """Both lanes are always present; an empty lane is an empty Inventory."""
    if v is None or isinstance(v, list):
        v = {}
    if isinstance(v, dict):
        v = dict(v)
        v["left"] = v.get("left") or {}
        v["right"] = v.get("right") or {}
    return v
