# craft_item

The craft tool allows you to create items and entities in Factorio by crafting them from their component materials. This document explains how to use the tool effectively and covers important considerations.

## Basic Usage

To craft an item, use the `craft_item` function with a Prototype and optional quantity:

```python
# Craft a single iron chest
craft_item(Prototype.IronChest)

# Craft multiple items
craft_item(Prototype.CopperCable, quantity=20)
```

## Key Features

### Automatic Resource Management

- The tool automatically checks if you have the required resources in your inventory
- For items requiring intermediate resources, it will attempt to craft those first

### Recursive Crafting

The tool supports recursive crafting of intermediate components. For example:

- If you try to craft an electronic circuit but lack copper cable
- The tool will first attempt to craft the required copper cable
- Then proceed with crafting the electronic circuit

The whole recipe tree is worked out before anything is crafted. Intermediates you already hold are used first, and each intermediate is counted once across the tree, so an intermediate that two parts of a recipe use (such as the iron gear wheels a lab needs directly and inside its transport belts) is crafted in the total amount needed. Only the intermediates the recipe needs are crafted. If an item that can't be crafted by hand (a raw resource, a smelted plate, a machine-only or not yet unlocked intermediate) is short, nothing is crafted and the error lists the total still needed of each one, e.g. `still missing ingredients - iron-plate x36, copper-plate x15`.

### Technology Requirements

- Some items require specific technologies to be researched before they can be crafted
- The tool will check technology prerequisites and notify you if research is needed
- You cannot craft items that require unresearched technologies

## Important Considerations

- Raw resources like iron ore and copper ore cannot be crafted. These must be mined using mining tools instead. Attempting to craft raw resources will result in an error.
- Crafting if your inventory is full will also result in an error.

## Examples

### Basic Crafting

```python
# Craft 5 iron chests (requires 8 iron plates each)
craft_item(Prototype.IronChest, quantity=5)

# Craft 20 copper cables (requires 10 copper plates)
craft_item(Prototype.CopperCable, quantity=20)
```
