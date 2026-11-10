# get_map

`get_map` returns a text map of an area: one character per tile, with the x of every column and the y of every row, plus a legend. It reports what is on each tile, as the game screen shows it; it does not analyse the layout.

It only reads the map: it builds nothing, moves nothing, takes no game time and works at any distance from you. Tiles the map has not charted are shown as `?`, and nothing on them is reported.

## Basic Usage

```python
print(get_map())                                  # around you, radius 15 (31 x 31 tiles)
print(get_map(Position(x=20, y=-10), radius=8))   # 17 x 17 tiles around (20, -10)
print(get_map(left_top=Position(x=-20, y=5), right_bottom=Position(x=10, y=25)))   # a box, corners included
```

### Parameters

1. `position`: Position - Centre of the map (default: your position)
2. `radius`: int - Tiles from the centre to each edge, 1 to 31 (default: 15)
3. `left_top`, `right_bottom`: Position - Two opposite corners of a box, instead of `position` and `radius`. The tiles holding both corners are included.

The most one call returns is 64 x 64 tiles. A larger box raises an error that states the size asked for and this limit.

### Return Value

A string:
- a header line with the x range and y range, and the tile you are on;
- the x of each column, written top to bottom above the column (a `-` row for negative x, then one row per digit);
- one row per y, starting with that y, one character per tile;
- a legend of the symbols that appear, with entity names and counts.

x grows to the right and y grows downward. Tile `x, y` covers x to x+1 and y to y+1; its centre is `Position(x + 0.5, y + 0.5)`.

### Symbols

- An uppercase letter or digit per entity name (the legend gives the name and count). A multi-tile entity fills every tile of its footprint.
- `^ > v <`: a belt, pointing the way it moves items.
- `↑ → ↓ ←`: an inserter, pointing at the side it drops on.
- `=` pipe, `|` electric pole (the legend gives the names and counts).
- A lowercase letter per resource (the legend gives the name and tile count).
- `~` water, `#` cliff, `%` tree, `*` rock, `.` nothing on the tile, `?` not charted.
- `@` you, drawn only when the tile you are on holds no entity; the header always gives your tile.

Entities are drawn over resources, so a mining drill covers the ore under it. Letters are given per call: read them from that call's legend.

### Example

```
Map x -3..6, y 10..15 (10 x 6 tiles), one character per tile. The x of a column is written above it, top to bottom; each row starts with its y. x grows to the right, y grows downward. Tile x, y covers x to x+1 and y to y+1; its centre is Position(x + 0.5, y + 0.5).
You are on tile x=1, y=13.
   ---
   3210123456
10 ~~~.......
11 ~~..SS..ii
12 >>>→SS..ii
13 ..=.@..|ii
14 ..=...%...
15 ..=.....##
Legend:
  S stone-furnace (1)
  ^ > v < belt, pointing the way it moves items: transport-belt 3
  ↑ → ↓ ← inserter, pointing at the side it drops on: burner-inserter 1
  = pipe: pipe 3
  | electric pole: small-electric-pole 1
  i iron-ore (6 tiles)
  ~ water (5 tiles)
  # cliff (1)
  % tree (1)
  @ you
  . nothing on the tile
```
