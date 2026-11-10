"""Tool error paths keep the real cause (no server: execute is stubbed)."""

import pytest

from fle.env.entities import Position
from fle.env.game_types import Prototype
from fle.env.tools.agent.extract_item.client import ExtractItem
from fle.env.tools.agent.insert_item.client import InsertItem
from fle.env.tools.agent.nearest.client import Nearest
from fle.env.tools.agent.set_entity_recipe.client import SetEntityRecipe

LUA = '[string "storage.actions.x = ..."]:12: '


def _tool(cls, response):
    tool = object.__new__(cls)
    tool.player_index = 1
    tool.execute = lambda *args: (response, 0)
    return tool


def test_extract_keeps_colons_and_target():
    msg = (
        LUA
        + '"stone-furnace at (1.5, 2.5) has no iron-plate (it holds iron-ore:4, coal:2)"'
    )
    tool = _tool(ExtractItem, msg)
    with pytest.raises(Exception) as e:
        tool(Prototype.IronPlate, Position(x=1.5, y=2.5), 5)
    assert "it holds iron-ore:4, coal:2" in str(e.value)
    assert "Could not extract iron-plate at (1.5, 2.5)" in str(e.value)


def test_extract_without_a_count_names_the_item():
    tool = _tool(ExtractItem, {})
    with pytest.raises(Exception) as e:
        tool(Prototype.IronPlate, Position(x=1.5, y=2.5), 5)
    assert str(e.value) != "Could not extract."
    assert "iron-plate" in str(e.value) and "(1.5, 2.5)" in str(e.value)


def test_insert_keeps_the_whole_reason():
    msg = (
        LUA
        + '"Cannot insert coal into lab at (3.5, 3.5): a lab takes only science packs"'
    )
    tool = _tool(InsertItem, msg)
    from fle.env.entities import Chest, Dimensions, TileDimensions

    chest = Chest(
        name="iron-chest",
        position=Position(x=3.5, y=3.5),
        energy=0,
        dimensions=Dimensions(width=1, height=1),
        tile_dimensions=TileDimensions(tile_width=1, tile_height=1),
        health=100,
    )
    with pytest.raises(Exception) as e:
        tool(Prototype.Coal, chest, 5)
    assert str(e.value) == (
        "Could not insert: Cannot insert coal into lab at (3.5, 3.5): "
        "a lab takes only science packs"
    )


def test_nearest_reports_server_reason():
    msg = (
        LUA + '"No iron-ore within 500 tiles (in x and y) of your position (0.0, 0.0)"'
    )
    tool = _tool(Nearest, msg)
    with pytest.raises(Exception) as e:
        tool(Prototype.IronOre)
    assert "within 500 tiles" in str(e.value)


def test_set_recipe_message_has_separator():
    msg = LUA + '"Recipe plastic-bar is not unlocked yet (research needed)"'
    tool = _tool(SetEntityRecipe, msg)
    from fle.env.entities import AssemblingMachine, Dimensions, TileDimensions

    am = AssemblingMachine(
        name="assembling-machine-1",
        position=Position(x=0.5, y=0.5),
        energy=0,
        dimensions=Dimensions(width=3, height=3),
        tile_dimensions=TileDimensions(tile_width=3, tile_height=3),
        health=100,
    )
    with pytest.raises(Exception) as e:
        tool(am, Prototype.PlasticBar)
    assert str(e.value) == (
        "Could not set recipe to plastic-bar: "
        "Recipe plastic-bar is not unlocked yet (research needed)"
    )
