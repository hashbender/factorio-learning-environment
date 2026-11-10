# can_place_entity

`can_place_entity(entity, direction, position)` asks the game whether an entity can be built at a position and direction, like the green or red outline the game shows while placing one. It uses the same build check as `place_entity` and takes the same `direction` and `position`.

It builds nothing, needs no item in your inventory, takes no game time, leaves you where you are and works at any distance. The check is for one entity on the map as it is now.

```python
check = can_place_entity(Prototype.TransportBelt, Direction.RIGHT, Position(x=9.5, y=3.5))
print(check)
# PlacementCheck(can_place=False, entity=transport-belt, position=(9.5, 3.5), direction=RIGHT, fits=False, reason='blocked by pipe at (9.5, 3.5)', blocked_by=[pipe at (9.5, 3.5)], in_reach=True, in_inventory=40)
if check:   # True exactly when can_place is True
    place_entity(Prototype.TransportBelt, Direction.RIGHT, Position(x=9.5, y=3.5))
```

The `PlacementCheck` has:

- `fits`: the game's build check for the entity at `position` (where it would be built) facing `direction`
- `reason`: why it does not fit, or why `place_entity` would still refuse (None when `can_place` is True)
- `blocked_by`: the entities and tiles in the way, each with `kind` ("entity" or "tile"), `name` and `position`; at most five are listed, `blocked_count` is the total
- `in_reach` (with `distance` and `reach`) and `in_inventory` (how many you hold): what `place_entity` also requires
- `can_place`: `fits` and `in_reach` and `in_inventory > 0`

`reason` texts:

- `blocked by pipe at (9.5, 3.5)`: an entity, cliff, tree or rock in the way, at its position
- `blocked by water at (9, 3)`: a tile the entity cannot stand on, by the tile's x, y
- `tile (140, -62) is in a part of the map that has not been generated or charted`
- `pumpjack must be placed on a resource it can mine (crude-oil); there is none under this position`
- `offshore-pump must be placed at the edge of water, facing the water`
- `fits, but out of reach (distance 14.2, reach 10)`, `fits, but no stone-furnace in your inventory`
