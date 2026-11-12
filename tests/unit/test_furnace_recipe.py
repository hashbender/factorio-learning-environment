"""Furnace.recipe is a Recipe, as AssemblingMachine.recipe is (no server).

Regression: Furnace declared no recipe field and entities allow extra fields, so the
recipe the game reports stayed a plain dict: `furnace.recipe.name` raised
"'dict' object has no attribute 'name'".
"""

from fle.env.entities import (
    AssemblingMachine,
    ElectricFurnace,
    Furnace,
    Position,
    Recipe,
)
from fle.env.game_types import Prototype

# as serialize_recipe sends it (after the client's cleanup)
SMELT = {
    "name": "iron-plate",
    "category": "smelting",
    "enabled": True,
    "energy": 3.2,
    "ingredients": [{"name": "iron-ore", "amount": 1, "type": "item"}],
    "products": [{"name": "iron-plate", "amount": 1, "type": "item", "probability": 1}],
}

COMMON = dict(
    position=Position(x=0, y=0),
    dimensions={"width": 2, "height": 2},
    tile_dimensions={"tile_width": 2, "tile_height": 2},
    health=200,
    energy=0,
)


def test_furnace_recipe_is_a_recipe():
    f = Furnace(name="stone-furnace", prototype=Prototype.StoneFurnace, recipe=SMELT, **COMMON)
    assert isinstance(f.recipe, Recipe)
    assert f.recipe.name == "iron-plate"
    assert f.recipe.ingredients[0].name == "iron-ore"
    assert f.recipe.products[0].name == "iron-plate"


def test_electric_furnace_recipe_is_a_recipe():
    f = ElectricFurnace(
        name="electric-furnace", prototype=Prototype.ElectricFurnace, recipe=SMELT, **COMMON
    )
    assert f.recipe.name == "iron-plate"


def test_idle_furnace_has_no_recipe():
    f = Furnace(name="stone-furnace", prototype=Prototype.StoneFurnace, **COMMON)
    assert f.recipe is None


def test_dict_style_reads_still_work():
    f = Furnace(name="stone-furnace", prototype=Prototype.StoneFurnace, recipe=SMELT, **COMMON)
    assert f.recipe["name"] == "iron-plate"
    assert f.recipe.get("category") == "smelting"
    assert f.recipe.get("nope", 7) == 7
    try:
        f.recipe["nope"]
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")


def test_same_type_as_assembling_machine():
    am = AssemblingMachine.model_fields["recipe"].annotation
    assert Furnace.model_fields["recipe"].annotation == am


def test_printed_furnace_is_unchanged():
    """The recipe stays out of the printed furnace (it was not shown before either)."""
    f = Furnace(name="stone-furnace", prototype=Prototype.StoneFurnace, recipe=SMELT, **COMMON)
    assert "recipe" not in repr(f)
    assert "furnace_source" in repr(f)
