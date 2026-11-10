# place_tile

## Overview

The `place_tile` tool places one tile from a tile item on the tile that contains a position, as a player builds tiles: landfill (`Prototype.Landfill`) turns a water tile into land, and stone brick, concrete, hazard concrete and refined concrete pave a land tile. One item is used per tile.

## Function Signature

```python
def place_tile(tile: Prototype, position: Position) -> Position
```

### Parameters

- `tile`: Prototype of the tile item, e.g. `Prototype.Landfill`
- `position`: a position on the tile to build on

### Returns

- The Position of the centre of the tile that was placed

## Usage Example

```python
# Fill the water tile at (10.5, 20.5)
move_to(Position(x=8, y=20))
placed = place_tile(Prototype.Landfill, Position(x=10.5, y=20.5))
print(f"Landfill placed at {placed}")
```

## Key Behaviors

- The tile must be within your build distance (10 tiles from the centre of the tile)
- Landfill can only be placed on water tiles; stone brick and concrete can't be placed on water
- Building over a stone path or concrete tile returns the item of the tile it replaces to your inventory
- Fish on the tile are removed; any other entity whose collision is blocked by the new tile stops the placement

## Error Handling

The tool raises an error, and uses no item, if:
- the item isn't in your inventory
- the item can't be placed as a tile
- the tile is out of build distance
- the tile underneath doesn't allow the item (e.g. landfill on grass)
- the tile is already that tile
