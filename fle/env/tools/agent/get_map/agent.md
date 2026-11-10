# get_map

`get_map` returns a text map of the area around a position: one character per tile, plus a legend. It reports what is on each tile; it does not analyse the layout.

## Basic Usage

```python
print(get_map())                                  # around you, radius 15
print(get_map(Position(x=20, y=-10), radius=8))   # 17 x 17 tiles around (20, -10)
```

### Parameters

1. `position`: Position - Centre of the map (default: your position)
2. `radius`: int - Tiles from the centre to each edge, 1 to 32 (default: 15)

### Return Value

A string:
- a header line with the x range (left to right) and y range (top to bottom);
- one row per y, starting with that y, one character per tile;
- a legend.

### Symbols

- An uppercase letter or digit per entity name (the legend gives the name and count). A multi-tile entity fills all its tiles.
- `^ > v <`: belts, pointing the way they move.
- A lowercase letter per resource (the legend gives the name and tile count).
- `~` water, `#` cliff, `%` tree, `*` rock, `@` you, `.` nothing on the tile.

Entities are drawn over resources, so a mining drill covers the ore under it.
