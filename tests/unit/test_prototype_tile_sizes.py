"""Prototype.WIDTH / HEIGHT vs Factorio 2.0 tile sizes. Server-free."""

import pytest

from fle.env.game_types import Prototype, prototype_by_name

# prototypes.entity[name].tile_width / tile_height (facing north) on a
# Factorio 2.0.73 headless server, base mod only
FACTORIO_2_0_TILE_SIZES = {
    "accumulator": (2, 2),
    "active-provider-chest": (1, 1),
    "arithmetic-combinator": (1, 2),
    "artillery-turret": (3, 3),
    "assembling-machine-1": (3, 3),
    "assembling-machine-2": (3, 3),
    "assembling-machine-3": (3, 3),
    "beacon": (3, 3),
    "big-electric-pole": (2, 2),
    "boiler": (3, 2),
    "buffer-chest": (1, 1),
    "bulk-inserter": (1, 1),
    "burner-inserter": (1, 1),
    "burner-mining-drill": (2, 2),
    "car": (2, 2),
    "cargo-wagon": (2, 5),
    "centrifuge": (3, 3),
    "chemical-plant": (3, 3),
    "constant-combinator": (1, 1),
    "curved-rail-a": (2, 4),
    "curved-rail-b": (2, 2),
    "decider-combinator": (1, 2),
    "electric-furnace": (3, 3),
    "electric-mining-drill": (3, 3),
    "express-splitter": (2, 1),
    "express-transport-belt": (1, 1),
    "express-underground-belt": (1, 1),
    "fast-inserter": (1, 1),
    "fast-splitter": (2, 1),
    "fast-transport-belt": (1, 1),
    "fast-underground-belt": (1, 1),
    "flamethrower-turret": (2, 3),
    "fluid-wagon": (2, 5),
    "gate": (1, 1),
    "gun-turret": (2, 2),
    "half-diagonal-rail": (2, 2),
    "heat-exchanger": (3, 2),
    "heat-pipe": (1, 1),
    "inserter": (1, 1),
    "iron-chest": (1, 1),
    "lab": (3, 3),
    "land-mine": (1, 1),
    "laser-turret": (2, 2),
    "locomotive": (2, 6),
    "long-handed-inserter": (1, 1),
    "medium-electric-pole": (1, 1),
    "nuclear-reactor": (5, 5),
    "offshore-pump": (1, 1),
    "oil-refinery": (5, 5),
    "passive-provider-chest": (1, 1),
    "pipe": (1, 1),
    "pipe-to-ground": (1, 1),
    "power-switch": (2, 2),
    "programmable-speaker": (1, 1),
    "pump": (1, 2),
    "pumpjack": (3, 3),
    "radar": (3, 3),
    "rail-chain-signal": (1, 1),
    "rail-signal": (1, 1),
    "requester-chest": (1, 1),
    "roboport": (4, 4),
    "rocket-silo": (9, 9),
    "small-electric-pole": (1, 1),
    "small-lamp": (1, 1),
    "solar-panel": (3, 3),
    "spidertron": (2, 2),
    "splitter": (2, 1),
    "steam-engine": (3, 5),
    "steam-turbine": (3, 5),
    "steel-chest": (1, 1),
    "steel-furnace": (2, 2),
    "stone-furnace": (2, 2),
    "stone-wall": (1, 1),
    "storage-chest": (1, 1),
    "storage-tank": (3, 3),
    "straight-rail": (2, 2),
    "substation": (2, 2),
    "tank": (2, 3),
    "train-stop": (2, 2),
    "transport-belt": (1, 1),
    "underground-belt": (1, 1),
    "wooden-chest": (1, 1),
}


@pytest.mark.parametrize("name", sorted(FACTORIO_2_0_TILE_SIZES))
def test_size_matches_factorio_2_0(name):
    prototype = prototype_by_name[name]
    assert (prototype.WIDTH, prototype.HEIGHT) == FACTORIO_2_0_TILE_SIZES[name]


def test_steam_engine_is_long_north_south():
    # 3 wide, 5 tall when facing north
    assert (Prototype.SteamEngine.WIDTH, Prototype.SteamEngine.HEIGHT) == (3, 5)


def test_offshore_pump_is_one_tile():
    assert (Prototype.OffshorePump.WIDTH, Prototype.OffshorePump.HEIGHT) == (1, 1)
