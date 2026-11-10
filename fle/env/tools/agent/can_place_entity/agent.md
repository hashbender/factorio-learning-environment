# can_place_entity

`can_place_entity(entity, direction, position)` asks the game whether an entity can be built at a position and direction, like the green or red outline the game shows while placing one. It uses the same build check as `place_entity` and takes the same `direction` and `position`.

It builds nothing, needs no item in your inventory, takes no game time, leaves you where you are and works at any distance.

```python
check = can_place_entity(Prototype.StoneFurnace, Direction.UP, Position(x=10, y=4))
print(check)
# PlacementCheck(can_place=True, entity=stone-furnace, position=(10.0, 4.0), direction=UP, fits=True, in_reach=True, in_inventory=3)
if check:
    place_entity(Prototype.StoneFurnace, Direction.UP, Position(x=10, y=4))
```

## Return value

A `PlacementCheck`. Used in an `if`, it is True exactly when `can_place` is True.

- `fits`: the game's build check for the entity at `position` facing `direction` (True or False)
- `position`: the position the entity would be built at
- `reason`: when it does not fit, what the game refuses it for, with positions (None when `can_place` is True)
- `blocked_by`: the entities and tiles in the way, each with `kind` ("entity" or "tile"), `name` and `position`; at most five are listed, `blocked_count` is the total
- `in_reach`, `distance`, `reach`: whether the position is within your reach, as `place_entity` requires
- `in_inventory`: how many of the entity you hold
- `can_place`: `fits` and `in_reach` and `in_inventory > 0`, so `place_entity` would build it now

## What `reason` reports

- an entity in the way: `blocked by pipe at (9.5, 3.5)`
- a tile the entity cannot stand on: `blocked by water at (9, 3)` (a tile is named by its x, y)
- a cliff, tree or rock in the way, by name and position
- a position off the known map: `tile (140, -62) is in a part of the map that has not been generated or charted`
- an entity with a placement rule of its own: `pumpjack must be placed on a resource it can mine (crude-oil); there is none under this position`, `offshore-pump must be placed at the edge of water, facing the water`
- it fits but `place_entity` would still refuse: `fits, but out of reach (distance 14.2, reach 10)`, `fits, but no stone-furnace in your inventory`

```python
check = can_place_entity(Prototype.TransportBelt, Direction.RIGHT, Position(x=9.5, y=3.5))
print(check)
# PlacementCheck(can_place=False, entity=transport-belt, position=(9.5, 3.5), direction=RIGHT, fits=False, reason='blocked by pipe at (9.5, 3.5)', blocked_by=[pipe at (9.5, 3.5)], in_reach=True, in_inventory=40)
```

The check is for one entity on the map as it is now; it does not take into account anything you have not built yet.
