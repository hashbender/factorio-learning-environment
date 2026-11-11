"""get_entities with an inventory that comes back as a list (no server; execute stubbed).

Regression: the list branch extended the list it was iterating
(`for inv in inv_list: inv_list += inv`), so any entity whose inventory came
back as a non-empty list made get_entities loop forever and grow memory.
"""

import threading

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.get_entities.client import GetEntities


def _tool(response):
    tool = object.__new__(GetEntities)
    tool.player_index = 1
    tool.execute = lambda *args: (response, 0)
    return tool


def _chest(inventory):
    return {
        "name": "wooden-chest",
        "position": {"x": 0.5, "y": 0.5},
        "direction": 0,
        "health": 100,
        "status": "normal",
        "energy": 0,
        "dimensions": {"width": 1, "height": 1},
        "tile_dimensions": {"tile_width": 1, "tile_height": 1},
        "inventory": inventory,
    }


def _call_with_timeout(tool, seconds=10, **kwargs):
    result = {}

    def run():
        result["value"] = tool(**kwargs)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    assert not t.is_alive(), "get_entities did not return (endless loop)"
    return result["value"]


def test_list_of_inventory_dicts_returns_and_merges():
    # Lua-style list {"1": {...}, "2": {...}} -> clean_response turns it into a list of dicts.
    response = [_chest({"1": {"iron-plate": 5}, "2": {"iron-plate": 3, "coal": 2}})]
    entities = _call_with_timeout(
        _tool(response), entities={Prototype.WoodenChest}, position=Position(x=0, y=0)
    )
    assert len(entities) == 1
    inv = entities[0].inventory
    assert inv["iron-plate"] == 8
    assert inv["coal"] == 2


def test_dict_inventory_unchanged():
    response = [_chest({"iron-plate": 5, "coal": 0})]
    entities = _call_with_timeout(
        _tool(response), entities={Prototype.WoodenChest}, position=Position(x=0, y=0)
    )
    assert len(entities) == 1
    assert entities[0].inventory["iron-plate"] == 5
