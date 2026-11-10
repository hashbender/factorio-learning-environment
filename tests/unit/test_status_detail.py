"""status_detail: the concrete reason behind an entity's status (no server).

serialize.lua's storage.utils.status_detail runs in Lua (lupa) against stub
entities; the Python side shows it in get_entity's repr and the observation."""

from pathlib import Path

import pytest

from fle.env.entities import (
    AssemblingMachine,
    Dimensions,
    EntityStatus,
    Lab,
    Position,
    TileDimensions,
)
from fle.env.gym_env.observation_formatter import TreeObservationFormatter as T

SERIALIZE_LUA = Path(__file__).resolve().parents[2] / "fle/env/mods/serialize.lua"

STUB_LUA = """
defines = {
    entity_status = {working = 1, normal = 2, no_power = 3, low_power = 4, no_fuel = 5,
        not_plugged_in_electric_network = 6, no_recipe = 7, no_ingredients = 8,
        no_input_fluid = 9, no_minable_resources = 10, fluid_ingredient_shortage = 11,
        full_output = 12, full_burnt_result_output = 13, item_ingredient_shortage = 14,
        missing_required_fluid = 15, missing_science_packs = 16, waiting_for_source_items = 17,
        waiting_for_space_in_destination = 18, low_input_fluid = 19},
    flow_precision_index = {five_seconds = 0},
    direction = {north = 0, east = 4, south = 8, west = 12},
    inventory = {furnace_source = 2, assembling_machine_input = 2, lab_input = 2},
    wire_connector_id = {}, wire_type = {}, entity_status_diode = {},
}
game = {tick = 1}
storage = {utils = {}}
storage.utils.get_contents_compat = function(inv)
    local out = {}
    for name, count in pairs(inv.items) do out[name] = count end
    return out
end
function inv(items)
    return {items = items, get_item_count = function(name) return items[name] or 0 end}
end
function surface(found)
    return {find_entities_filtered = function(f)
        local out = {}
        for _, e in ipairs(found) do
            if (f.type == nil and e.type ~= "item-entity") or f.type == e.type then table.insert(out, e) end
        end
        return out
    end}
end
"""


@pytest.fixture(scope="module")
def lua():
    lupa = pytest.importorskip("lupa")
    rt = lupa.LuaRuntime()
    rt.execute(STUB_LUA)
    rt.execute(SERIALIZE_LUA.read_text())
    return rt


def detail(lua, entity_src):
    return lua.eval(f"storage.utils.status_detail({entity_src})")


def assembler(status, ingredients, items, fluids="{}"):
    return f"""{{type = "assembling-machine", status = {status},
        get_recipe = function() return {{ingredients = {ingredients}}} end,
        get_inventory = function() return inv({items}) end, fluidbox = {fluids}}}"""


def test_item_shortage_lists_have_and_need_per_craft(lua):
    ing = '{{type = "item", name = "iron-plate", amount = 1}, {type = "item", name = "copper-cable", amount = 3}}'
    text = detail(lua, assembler(14, ing, '{["copper-cable"] = 1}'))
    assert (
        text == "missing iron-plate (0 of 1 per craft), copper-cable (1 of 3 per craft)"
    )


def test_item_shortage_is_capped(lua):
    ing = (
        "{"
        + ", ".join(
            f'{{type = "item", name = "item-{i}", amount = 2}}' for i in range(6)
        )
        + "}"
    )
    text = detail(lua, assembler(14, ing, "{}"))
    assert text.count("per craft") == 4 and text.endswith(", (2 more)")


def test_fluid_shortage(lua):
    ing = '{{type = "fluid", name = "petroleum-gas", amount = 100}, {type = "item", name = "coal", amount = 1}}'
    fluids = '{{name = "petroleum-gas", amount = 12.5}}'
    text = detail(lua, assembler(11, ing, "{coal = 5}", fluids))
    assert text == "missing petroleum-gas (12.5 of 100 per craft)"


def test_power(lua):
    assert (
        detail(lua, "{status = 3, electric_network_id = 7}")
        == "no power (electric network 7)"
    )
    assert (
        detail(lua, "{status = 4, electric_network_id = 2}")
        == "low power (electric network 2)"
    )
    assert (
        detail(lua, "{status = 3}") == "no power (not connected to an electric network)"
    )
    assert detail(lua, "{status = 6}") == "not connected to an electric network"


def test_full_output_names_the_items(lua):
    src = '{status = 12, get_output_inventory = function() return inv({["iron-gear-wheel"] = 100}) end}'
    assert detail(lua, src) == "output full (iron-gear-wheel 100)"


def test_no_recipe_and_no_fuel(lua):
    assert detail(lua, "{status = 7}") == "no recipe set"
    assert (
        detail(lua, "{status = 5, burner = {inventory = inv({})}}")
        == "no fuel (fuel slot empty)"
    )


def test_waiting_for_space_names_the_drop_target(lua):
    src = """{status = 18, drop_position = {x = 3.5, y = 4.5},
        drop_target = {valid = true, name = "iron-chest", position = {x = 3.5, y = 4.5}}}"""
    assert detail(lua, src) == "waiting for space in iron-chest at (3.5, 4.5)"


def test_waiting_for_space_on_the_ground(lua):
    src = """{status = 18, drop_position = {x = 1.2, y = -0.3},
        surface = surface({{type = "item-entity", valid = true,
            stack = {valid_for_read = true, name = "iron-ore"}}})}"""
    assert (
        detail(lua, src)
        == "waiting for space in (1, -0.5): no entity there, iron-ore on the ground"
    )


def test_waiting_for_source_items(lua):
    src = """{status = 17, pickup_position = {x = 0.5, y = 1.5}, surface = surface({
        {type = "wooden-chest", valid = true, name = "wooden-chest", position = {x = 0.5, y = 1.5}}})}"""
    assert detail(lua, src) == "waiting for items from wooden-chest at (0.5, 1.5)"


def test_no_minable_resources_gives_the_mining_area(lua):
    src = """{status = 10, position = {x = 10, y = 20}, quality = "normal",
        prototype = {get_mining_drill_radius = function() return 2.49 end}}"""
    assert (
        detail(lua, src)
        == "no minable resources in the mining area (7.5, 17.5) to (12.5, 22.5)"
    )


def test_missing_science_packs(lua):
    src = """{status = 16, get_inventory = function() return inv({["automation-science-pack"] = 3}) end,
        force = {current_research = {name = "logistics-2", research_unit_ingredients = {
            {name = "automation-science-pack", amount = 1}, {name = "logistic-science-pack", amount = 1}}}}}"""
    assert detail(lua, src) == "missing logistic-science-pack (0 of 1) for logistics-2"


def test_no_detail_for_working_or_errors(lua):
    assert detail(lua, "{status = 1}") is None
    # an accessor that raises: no detail, no error
    assert (
        detail(lua, "setmetatable({}, {__index = function() error('x') end})") is None
    )


def _machine(**extra):
    return AssemblingMachine(
        name="assembling-machine-1",
        position=Position(x=1.5, y=1.5),
        energy=0,
        dimensions=Dimensions(width=3, height=3),
        tile_dimensions=TileDimensions(tile_width=3, tile_height=3),
        health=100,
        **extra,
    )


def test_repr_and_observation_show_the_detail():
    m = _machine(
        status=EntityStatus.ITEM_INGREDIENT_SHORTAGE,
        status_detail="missing iron-plate (0 of 1 per craft)",
    )
    assert "status_detail='missing iron-plate (0 of 1 per craft)'" in repr(m)
    assert "status_detail=missing iron-plate (0 of 1 per craft)" in T.format_entities(
        [m.__dict__]
    )


def test_no_detail_is_not_shown():
    m = _machine(status=EntityStatus.WORKING)
    assert "status_detail" not in repr(m)
    assert "status_detail" not in T.format_entities([m.__dict__])


def test_lab_repr_shows_the_detail():
    lab = Lab(
        name="lab",
        position=Position(x=1.5, y=1.5),
        energy=0,
        dimensions=Dimensions(width=3, height=3),
        tile_dimensions=TileDimensions(tile_width=3, tile_height=3),
        health=100,
        status=EntityStatus.MISSING_SCIENCE_PACKS,
        status_detail="missing logistic-science-pack (0 of 1) for logistics-2",
    )
    assert "status_detail='missing logistic-science-pack" in repr(lab)


def test_drill_with_nothing_to_mine_still_builds():
    # get_entities drops empty values, so an exhausted drill has no resources key
    from fle.env.entities import BurnerMiningDrill

    drill = BurnerMiningDrill(
        name="burner-mining-drill",
        position=Position(x=1, y=1),
        drop_position=Position(x=1, y=-0.3),
        energy=0,
        dimensions=Dimensions(width=2, height=2),
        tile_dimensions=TileDimensions(tile_width=2, tile_height=2),
        health=100,
        status=EntityStatus.NO_MINABLE_RESOURCES,
        status_detail="no minable resources in the mining area (0, 0) to (2, 2)",
    )
    assert drill.resources == []
    # get_entity keeps the empty Lua table, which arrives as {}
    assert BurnerMiningDrill(**{**drill.__dict__, "resources": {}}).resources == []
    assert "status_detail='no minable resources" in repr(drill)
