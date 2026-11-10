from typing import Any, Dict

from fle.env.tools import Tool

PATCH_FIELDS = ("amount", "tiles", "x1", "y1", "x2", "y2", "normal")


def _list(value: Any) -> list:
    """Lua arrays arrive as lists or as {"1": ..., "2": ...} dicts."""
    if isinstance(value, dict):
        return [value[k] for k in sorted(value, key=lambda k: int(k))]
    return list(value or [])


class GetResourceReserves(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(
        self, margin: float = 100, radius: float = 1000, max_cells: int = 20000
    ) -> Dict[str, Any]:
        """
        Resource patches near the factory, read from the game's resource entities.
        The factory area is the bounding box of the force's entities within
        `radius` tiles of the character, plus the character's position. Each
        patch with a tile within `margin` tiles of that area is followed to its
        full extent (connected tiles of one resource), up to `radius` tiles from
        the character.
        :param margin: Tiles around the factory area in which a patch must have a tile
        :param radius: Search radius around the character, in tiles
        :param max_cells: Bound on the search work (8x8-tile cells read); when it
            is reached, "truncated" is True and later patches are missing
        :return: {"area": {x1, y1, x2, y2}, "buildings": int, "margin", "radius",
            "truncated": bool, "patches": [{name, amount, tiles, x1, y1, x2, y2,
            infinite, normal, clipped}]}. amount is the sum of the tiles'
            amounts (for infinite resources such as crude oil, normal is the
            amount the game shows as 100% yield); clipped: the patch continues
            past the radius
        """
        response, _ = self.execute(
            self.player_index, float(margin), float(radius), int(max_cells)
        )
        if not isinstance(response, dict):
            raise Exception(
                f"Could not get resource reserves: "
                f"{self.get_error_message(str(response))}"
            )
        patches = []
        for p in _list(response.get("patches")):
            patch = {"name": str(p.get("name", "?"))}
            for key in PATCH_FIELDS:
                if p.get(key) is not None:
                    patch[key] = float(p[key])
            patch["tiles"] = int(patch.get("tiles", 0))
            patch["infinite"] = bool(p.get("infinite"))
            patch["clipped"] = bool(p.get("clipped"))
            patches.append(patch)
        area = response.get("area") or {}
        return {
            "area": {k: float(area[k]) for k in ("x1", "y1", "x2", "y2") if k in area},
            "buildings": int(response.get("buildings") or 0),
            "margin": float(response.get("margin") or margin),
            "radius": float(response.get("radius") or radius),
            "truncated": bool(response.get("truncated")),
            "patches": patches,
        }
