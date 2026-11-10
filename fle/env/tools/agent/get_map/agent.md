# get_map

`get_map` returns a text map of an area: one character per tile, with the x of every column and the y of every row, and a legend. It shows what is on each tile, as the game screen does; it does not analyse the layout.

It only reads the map: it builds nothing, moves nothing, takes no game time and works at any distance. Tiles in a part of the map that has not been generated or charted show as `?`, and nothing on them is reported.

```python
print(get_map())                                  # around you, radius 15 (31 x 31 tiles)
print(get_map(Position(x=20, y=-10), radius=8))   # 17 x 17 tiles around (20, -10)
print(get_map(left_top=Position(x=-20, y=5), right_bottom=Position(x=10, y=25)))   # a box, corner tiles included
```

- `position`, `radius`: centre (default: your position) and tiles from the centre to each edge, 1 to 31 (default 15).
- `left_top`, `right_bottom`: two opposite corners of a box, instead of `position` and `radius`.
- The most one call returns is 64 x 64 tiles; a larger box raises an error stating the size asked for and this limit.

It returns a `TileMap`; `print()` it for the text:

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

- An uppercase letter or digit stands for one entity name, given in that call's legend with its count. A multi-tile entity fills every tile of its footprint.
- A lowercase letter stands for one resource. Entities are drawn over resources, so a mining drill covers the ore under it.
- `@` is drawn only when the tile you are on holds no entity; the header always gives your tile.
- The `TileMap` also has `rows` (the grid rows without labels, top to bottom), `legend` (symbol to meaning), `x0`, `y0`, `x1`, `y1`, and `at(x, y)`: the character on the tile that holds (x, y), or None outside the map.
