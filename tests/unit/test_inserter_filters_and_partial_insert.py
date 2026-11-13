"""An inserter's filter is part of the Inserter (serialize.lua sends use_filters and the set slots) and
shows in its repr; set_entity_recipe no longer stores the filter item as a `recipe` on an inserter.
insert_item reports a partial insert in the returned entity's warnings and still returns it (no exception). Server-free.
"""

from pathlib import Path

from fle.env.entities import Chest, Inserter, Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.insert_item.client import InsertItem
from fle.env.tools.agent.set_entity_recipe.client import SetEntityRecipe

ROOT = Path(__file__).resolve().parents[2]

BASE = {
    "name": "fast-inserter",
    "position": {"x": 0.5, "y": 0.5},
    "direction": 0,
    "energy": 0.0,
    "dimensions": {"width": 1, "height": 1},
    "tile_dimensions": {"tile_width": 1, "tile_height": 1},
    "health": 150.0,
    "drop_position": {"x": 0.5, "y": -0.5},
    "pickup_position": {"x": 0.5, "y": 1.5},
}


def test_filters_from_the_game():
    ins = Inserter(**BASE, use_filters=True, filters=["iron-plate"])
    assert ins.filters == ["iron-plate"]
    assert "filters=['iron-plate']" in repr(ins)
    # a Lua list can arrive keyed by index
    assert Inserter(**BASE, use_filters=True, filters={"1": "coal", "2": "stone"}).filters == ["coal", "stone"]
    # filtering on with no slot set (an empty Lua table is not sent)
    on = Inserter(**BASE, use_filters=True)
    assert on.filters == [] and "filters=[]" in repr(on)


def test_no_filter_no_change_in_repr():
    off = Inserter(**BASE, use_filters=False)
    assert off.filters is None and "filters" not in repr(off)
    old = Inserter(**BASE)  # as before r22 (no use_filters key)
    assert old.filters is None and "filters" not in repr(old)
    assert "use_filters" not in repr(Inserter(**BASE, use_filters=True))


def test_serialize_reads_the_filter_back():
    src = (ROOT / "fle/env/mods/serialize.lua").read_text()
    block = src[src.index('if entity.type == "inserter" then\n        serialized.pickup_position'):]
    block = block[: block.index("local burner = entity.burner")]
    assert "entity.use_filters" in block and "entity.get_filter(i)" in block and "filter_slot_count" in block


def test_set_entity_recipe_on_an_inserter_keeps_no_recipe():
    tool = SetEntityRecipe.__new__(SetEntityRecipe)
    tool.player_index = 1
    resp = dict(BASE, use_filters=True, filters=["iron-plate"])
    tool.execute = lambda *a: (resp, 0)
    tool.clean_response = lambda r: dict(r)
    ins = Inserter(**BASE)
    out = tool(ins, Prototype.IronPlate)
    assert isinstance(out, Inserter) and out.filters == ["iron-plate"]
    assert not hasattr(out, "recipe") or getattr(out, "recipe", None) is None


def _chest_resp(**extra):
    return {
        "name": "iron-chest",
        "position": {"x": 3.5, "y": 4.5},
        "direction": 0,
        "energy": 0.0,
        "dimensions": {"width": 1, "height": 1},
        "tile_dimensions": {"tile_width": 1, "tile_height": 1},
        "health": 200.0,
        "inventory": {"coal": 12},
        **extra,
    }


def _insert_tool(resp):
    tool = InsertItem.__new__(InsertItem)
    tool.player_index = 1
    tool.execute = lambda *a: (resp, 0)
    tool.clean_response = lambda r: dict(r)
    tool.get_position = lambda p: (p.x, p.y)
    return tool


def _chest():
    return Chest(**{k: v for k, v in _chest_resp().items() if k != "inventory"}, prototype=Prototype.IronChest)


def test_partial_insert_is_reported_and_returns_the_chest():
    tool = _insert_tool(_chest_resp(fle_inserted=12, fle_short_reason='"no room for more (chest inventory: 1 items)"'))
    out = tool(Prototype.Coal, _chest(), quantity=64)
    assert isinstance(out, Chest)
    assert "fle_inserted" not in (out.model_extra or {}) and "fle_short_reason" not in (out.model_extra or {})
    note = ("insert_item: 12 of 64 coal went in; no room for more (chest inventory: 1 items); "
            "the other 52 were not inserted")
    assert out.warnings == [note]
    assert note in repr(out)


def test_held_fewer_keeps_earlier_warnings():
    tool = _insert_tool(_chest_resp(warnings=["not connected"], fle_inserted=5, fle_short_reason='"you held only 5"'))
    out = tool(Prototype.Coal, _chest(), quantity=10)
    assert out.warnings == ["not connected", "insert_item: 5 of 10 coal went in; you held only 5; the other 5 were not inserted"]


def test_full_insert_says_nothing():
    tool = _insert_tool(_chest_resp())
    out = tool(Prototype.Coal, _chest(), quantity=12)
    assert isinstance(out, Chest) and out.warnings == []


def test_server_sends_the_count_only_when_short():
    src = (ROOT / "fle/env/tools/agent/insert_item/server.lua").read_text()
    assert "if inserted < count and type(serialized) == \"table\" then" in src
    assert "serialized.fle_inserted = inserted" in src
