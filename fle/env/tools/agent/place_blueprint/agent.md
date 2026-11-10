# place_blueprint

## Overview

The `place_blueprint` tool places a saved blueprint as ghosts, as the game does when a player places a blueprint. A ghost is only a plan: it is built only by construction robots, as in the game. Building ghosts needs:
- the `construction-robotics` research (it unlocks the roboport, construction robot, storage chest and passive provider chest recipes)
- a roboport (`Prototype.Roboport`) placed and powered from an electric network
- construction robots (`Prototype.ConstructionRobot`) in the roboport (`insert_item`)
- the item for each ghost in the roboport network's storage: storage, passive provider, active provider or buffer chests (`Prototype.StorageChest`, `Prototype.PassiveProviderChest`...) within a roboport's logistic area (25 tiles from it in each direction)
- the ghost within a roboport's construction area (55 tiles from it in each direction)

The robots take the items from storage and charge at the roboports. There is no personal roboport (no tool equips armor).

## Function Signature

```python
def place_blueprint(name: str, position: Position, direction: Direction = Direction.UP, force_build: bool = False) -> dict
```

### Parameters

- `name`: a saved blueprint
- `position`: the centre of the placement; it snaps to the tile grid
- `direction`: `Direction.UP` (as saved), `Direction.RIGHT`, `Direction.DOWN` or `Direction.LEFT` (turned clockwise)
- `force_build`: as shift-click in the game: ghosts are also placed over trees and rocks, which are marked for deconstruction

### Returns

A dict: `placement_id`, `ghosts_placed`, `ghosts` (count by name), `items_needed` (for the placed ghosts), `already_built` (the same entity already there), `refused_count`, `refused` (up to 20: `name`, `x`, `y`, `reason` naming what is in the way), `obstacles_marked_for_deconstruction`, `center`

## Key Behaviors

- Parts that collide with something are not placed; the rest are
- No reach is needed; the map must exist there (generated or charted)
- Ghosts are not returned by `get_entities`; `get_construction_status` counts them and says why they are not being built
- `place_entity` on a ghost of the same entity at its position builds it with the ghost's direction and recipe, using one item from your inventory. Placing any other entity removes the ghosts under it
- `mark_for_deconstruction` on ghosts removes them

## Error Handling

The tool raises an error if:
- no blueprint has that name
- part of the placement is in a part of the map that has not been generated or charted
