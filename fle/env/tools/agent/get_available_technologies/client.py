from typing import List

from fle.env.entities import AvailableTechnology, Ingredient
from fle.env.tools import Tool


def _as_list(value) -> list:
    if isinstance(value, dict):  # an empty or integer-keyed Lua table
        return [value[k] for k in sorted(value, key=lambda k: int(k))]
    return list(value or [])


def _text(value) -> str:
    return str(value).strip('"')


class GetAvailableTechnologies(Tool):
    def __init__(self, connection, game_state):
        super().__init__(connection, game_state)

    def __call__(self) -> List[AvailableTechnology]:
        """
        List the technologies that can be researched right now: enabled, not yet
        researched, and with every prerequisite researched (as the game's technology
        screen shows them), sorted by name.
        :return: For each technology its name, science packs per unit, unit count and
            seconds per unit, or for a trigger technology the action that completes it
        """
        response, elapsed = self.execute(self.player_index)

        if isinstance(response, str):
            raise Exception(
                f"Could not list available technologies - {response.replace(chr(34), '').strip()}"
            )

        technologies = []
        for entry in _as_list(response):
            trigger = entry.get("trigger")
            technologies.append(
                AvailableTechnology(
                    name=_text(entry["name"]),
                    ingredients=[
                        Ingredient(name=_text(i["name"]), count=int(i["count"]))
                        for i in _as_list(entry.get("ingredients"))
                    ],
                    unit_count=int(entry.get("unit_count") or 0),
                    unit_time=float(entry.get("unit_time") or 0),
                    trigger=_text(trigger) if trigger else None,
                )
            )
        return technologies
