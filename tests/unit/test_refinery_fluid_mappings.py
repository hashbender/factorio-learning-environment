"""Oil refinery fluid connection points per recipe. Server-free (Lua via lupa).

Expected points are the pipe connections of a Factorio 2.0.73 oil refinery
facing north at (3.5, -32.5): outputs at x = 1.5, 3.5, 5.5 hold heavy oil,
light oil and petroleum gas for both advanced oil processing and coal
liquefaction.
"""

from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

MAPPINGS_LUA = (
    Path(__file__).resolve().parents[2]
    / "fle/env/mods/recipe_fluid_connection_mappings.lua"
)

RECIPES = {
    "advanced-oil-processing": (
        [("water", "fluid"), ("crude-oil", "fluid")],
        ["heavy-oil", "light-oil", "petroleum-gas"],
    ),
    "coal-liquefaction": (
        [("coal", "item"), ("heavy-oil", "fluid"), ("steam", "fluid")],
        ["heavy-oil", "light-oil", "petroleum-gas"],
    ),
}


def _mappings(recipe_name, direction):
    lua = lupa.LuaRuntime()
    lua.execute(
        "defines = {direction = {north = 0, east = 4, south = 8, west = 12}}\n"
        "storage = {utils = {}}"
    )
    lua.execute(MAPPINGS_LUA.read_text())
    ingredients, products = RECIPES[recipe_name]
    make = lua.eval(
        "function(name, ingredients, products, direction) "
        "  local r = {name = name, ingredients = {}, products = {}} "
        "  for i = 1, #ingredients, 2 do "
        "    table.insert(r.ingredients, {name = ingredients[i], type = ingredients[i + 1]}) end "
        "  for _, p in ipairs(products) do table.insert(r.products, {name = p, type = 'fluid'}) end "
        "  local e = {position = {x = 3.5, y = -32.5}, direction = direction} "
        "  return storage.utils.get_refinery_fluid_mappings(e, r) end"
    )
    flat = lua.table_from([v for pair in ingredients for v in pair])
    result = make(recipe_name, flat, lua.table_from(products), direction)
    return {
        side: {
            p.type.strip('"'): (p.x, p.y)
            for p in (result[side][i] for i in range(1, len(result[side]) + 1))
        }
        for side in ("inputs", "outputs")
    }


@pytest.mark.parametrize("recipe", ["advanced-oil-processing", "coal-liquefaction"])
def test_outputs_facing_north(recipe):
    assert _mappings(recipe, 0)["outputs"] == {
        "heavy-oil": (1.5, -35.5),
        "light-oil": (3.5, -35.5),
        "petroleum-gas": (5.5, -35.5),
    }


def test_coal_liquefaction_inputs_facing_north():
    assert _mappings("coal-liquefaction", 0)["inputs"] == {
        "heavy-oil": (2.5, -29.5),
        "steam": (4.5, -29.5),
    }


def test_coal_liquefaction_outputs_rotate_with_the_refinery():
    # facing south the north side becomes the south side, mirrored
    assert _mappings("coal-liquefaction", 8)["outputs"] == {
        "heavy-oil": (5.5, -29.5),
        "light-oil": (3.5, -29.5),
        "petroleum-gas": (1.5, -29.5),
    }
