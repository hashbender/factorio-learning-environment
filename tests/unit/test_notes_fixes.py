"""Fixes from agents' notes: recipe counts from the game's `amount`; pickup_entity on an
underground belt takes only its linked partner and never raises after a pickup;
extract_item with a group or None; inspect_inventory(None); can_place_entity over an
entity of the same name. Server-free."""

import pytest

from fle.env import entities as ent
from fle.env.entities import (
    AssemblingMachine,
    BeltGroup,
    Ingredient,
    PipeGroup,
    Position,
    Product,
    Recipe,
    TransportBelt,
)
from fle.env.game_types import Prototype
from fle.env.tools.agent.extract_item.client import ExtractItem
from fle.env.tools.agent.inspect_inventory.client import InspectInventory
from fle.env.tools.agent.pickup_entity.client import PickedUp, PickupEntity

from tests.unit.test_can_place_entity_reasons import _blockers, _run


# --- N1: recipe counts -----------------------------------------------------------


def test_recipe_from_game_data_keeps_the_amounts():
    r = Recipe(**{
        "name": "electronic-circuit",
        "ingredients": [{"name": "copper-cable", "amount": 3, "type": "item"},
                        {"name": "iron-plate", "amount": 1, "type": "item"}],
        "products": [{"name": "electronic-circuit", "amount": 1, "type": "item", "probability": 1}],
    })
    assert [(i.name, i.count) for i in r.ingredients] == [("copper-cable", 3), ("iron-plate", 1)]
    assert r.products[0].count == 1


def test_fluid_amounts_and_explicit_counts():
    assert Ingredient(name="water", amount=100.0, type="fluid").count == 100
    assert Product(name="petroleum-gas", amount=45, type="fluid").count == 45
    assert Ingredient(name="iron-plate", count=2, amount=7).count == 2  # count wins
    assert Ingredient(name="iron-plate").count == 1


def test_a_machine_recipe_from_the_game_has_the_right_counts():
    recipe = {"name": "engine-unit", "energy": 10,
              "ingredients": [{"name": "steel-plate", "amount": 1}, {"name": "iron-gear-wheel", "amount": 1},
                              {"name": "pipe", "amount": 2}],
              "products": [{"name": "engine-unit", "amount": 1}]}
    field = AssemblingMachine.model_fields["recipe"]
    from pydantic import TypeAdapter
    r = TypeAdapter(field.annotation).validate_python(recipe)
    assert {i.name: i.count for i in r.ingredients}["pipe"] == 2


# --- N2: pickup_entity on underground belts ----------------------------------------


def _picker(partner, answers):
    tool = PickupEntity.__new__(PickupEntity)
    tool.player_index = 1
    tool.check_reach = True
    calls = []

    def execute(*args):
        calls.append(args)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a, 0

    tool.execute = execute
    tool.get_error_message = lambda m: str(m)
    tool._underground_partner = lambda name, x, y: partner
    return tool, calls


def _ug(x, y):
    return ent.UndergroundBelt.model_construct(
        name="underground-belt", position=Position(x=x, y=y), is_input=True,
        output_position=Position(x=x, y=y - 1), direction=ent.Direction.UP)


def test_a_linked_pair_is_picked_up_both_ends_and_says_so():
    tool, calls = _picker((6.5, 36.5), [1, 1])
    r = tool(_ug(6.5, 40.5))
    assert r and r == True  # noqa: E712
    assert [(c[1], c[2]) for c in calls] == [(6.5, 40.5), (6.5, 36.5)]
    assert "underground-belt at (6.5, 40.5) and its paired underground-belt at (6.5, 36.5)" in repr(r)


def test_an_unpaired_end_is_picked_up_alone_and_the_tile_in_front_is_not_touched():
    tool, calls = _picker(None, [1])
    r = tool(_ug(6.5, 40.5))
    assert r and len(calls) == 1 and (calls[0][1], calls[0][2]) == (6.5, 40.5)


def test_no_raise_after_a_successful_pickup_when_the_partner_fails():
    tool, calls = _picker((6.5, 36.5), [1, "too far away"])
    r = tool(_ug(6.5, 40.5))
    assert r and "was not picked up: too far away" in repr(r)


# --- N3: extract_item sources -------------------------------------------------------


def _extractor():
    tool = ExtractItem.__new__(ExtractItem)
    tool.player_index = 1
    tool.get_position = lambda p: (p.x, p.y)
    tool.get_error_message = lambda m: str(m)
    taken = []

    def execute(player, name, quantity, x, y, source_name):
        taken.append((x, y, quantity))
        return min(quantity, 3), 0

    tool.execute = execute
    return tool, taken


@pytest.mark.parametrize("source", [None, "group"])
def test_extract_from_none_or_a_non_belt_group_says_what_source_takes(source):
    tool, _ = _extractor()
    if source == "group":
        source = PipeGroup.model_construct(id=1, position=Position(x=0, y=0), pipes=[])
    with pytest.raises(TypeError, match="source must be an Entity, a Position or a BeltGroup"):
        tool(Prototype.IronPlate, source, 5)


def test_extract_from_a_belt_group_takes_from_its_belts_that_carry_the_item():
    tool, taken = _extractor()
    belts = [
        TransportBelt.model_construct(name="transport-belt", position=Position(x=x, y=0.5),
                                      inventory={"left": {"iron-plate": 2} if x != 1.5 else {}, "right": {}})
        for x in (0.5, 1.5, 2.5, 3.5)
    ]
    group = BeltGroup.model_construct(id=1, position=Position(x=0, y=0), belts=belts, inputs=[], outputs=[])
    assert tool(Prototype.IronPlate, group, 5) == 5
    assert [(x, q) for x, _, q in taken] == [(0.5, 5), (2.5, 2)]


# --- N5: inspect_inventory(None) ------------------------------------------------------


def test_inspect_inventory_with_explicit_none_raises_and_no_argument_is_mine():
    tool = InspectInventory.__new__(InspectInventory)
    tool.player_index = 1
    seen = []
    tool.execute = lambda *a: (seen.append(a) or {}, 0)
    with pytest.raises(ValueError, match="inspect_inventory\\(None\\)"):
        tool(None)
    try:
        tool()
    except Exception:
        pass
    assert seen and seen[0][1] is True  # the character's own inventory was asked for


# --- N6: can_place_entity over an entity of the same name -------------------------------


def test_can_place_names_a_same_name_entity_the_game_would_turn():
    setup = """
    table.insert(world, {valid = true, name = "transport-belt", type = "transport-belt",
        position = {x = 2.5, y = 2.5}, prototype = prototypes.entity["transport-belt"]})
    local check = storage.utils.can_place_entity
    storage.utils.can_place_entity = function(p, entity, position, direction)
        if entity == "transport-belt" and position.x == 2.5 and position.y == 2.5 then return true end
        return check(p, entity, position, direction)
    end
    """
    _, r = _run("transport-belt", 0, 2.5, 2.5, setup)
    assert not r.fits and not r.can_place
    assert _blockers(r) == [("entity", "transport-belt", 2.5, 2.5)]
    assert "already stands at (2.5, 2.5)" in r.reason
