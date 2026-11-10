# preview_inserter

`preview_inserter(entity, direction, position)` shows what an inserter would take from and drop into if it were placed at `position` facing `direction` (the same `direction` as `place_entity`), like the arrows the game shows while placing one. It builds nothing and needs no inserter in the inventory.

It returns an `InserterPreview`:

- `position`: the tile centre the inserter would be built at
- `pickup_position`, `drop_position`: where it would take items from and drop them
- `pickup_target`, `drop_target`: the entity at each of those positions that an inserter can use (a belt, or an entity with an inventory such as a chest, furnace, assembler or lab), or None when there is nothing there
- `pickup_target_position`, `drop_target_position`: that entity's position

```python
preview = preview_inserter(Prototype.BurnerInserter, Direction.RIGHT, Position(x=10.5, y=4.5))
print(preview)
# InserterPreview(position=(10.5, 4.5), direction=RIGHT, pickup_position=(9.5, 4.5), pickup_target=transport-belt at (9.5, 4.5), drop_position=(11.5, 4.5), drop_target=stone-furnace at (12.0, 5.0))
```

The inserter returned by `place_entity` and `get_entity` has the same `pickup_position`, `drop_position`, `pickup_target` and `drop_target` fields.
