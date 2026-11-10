-- Place one tile from a tile item (landfill, stone brick, concrete...) the way a player
-- builds it: the item must be in the inventory, the tile within build distance, and the
-- tile under it must satisfy the item's placement condition (PlaceAsTileResult). One item
-- is used per tile.
storage.actions.place_tile = function(player_index, item_name, x, y)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface

    local item = prototypes.item[item_name]
    if item == nil then
        error("\"" .. item_name .. " isn't an item that exists\"")
    end
    local result = item.place_as_tile_result
    if result == nil or result.result == nil then
        error("\"" .. item_name .. " can't be placed as a tile\"")
    end
    local tile_name = result.result.name

    local tx, ty = math.floor(x), math.floor(y)
    local cx, cy = tx + 0.5, ty + 0.5

    local reach = player.build_distance
    local dx, dy = player.position.x - cx, player.position.y - cy
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance > reach then
        error("\"The tile at (" .. cx .. ", " .. cy .. ") is too far away to build on. The player position is " ..
              player.position.x .. ", " .. player.position.y .. ", the distance is " ..
              string.format("%.2f", distance) .. " and the max distance is " .. reach .. ". Move closer.\"")
    end

    if player.get_item_count(item_name) < 1 then
        error("\"No " .. item_name .. " in inventory. Current inventory: " ..
              storage.utils.format_inventory_for_error(player) .. "\"")
    end

    local current = surface.get_tile(tx, ty)
    if current.name == tile_name then
        error("\"The tile at (" .. cx .. ", " .. cy .. ") is already " .. tile_name .. "\"")
    end

    -- The item's placement condition: the tiles it may go on (2.0 tile_condition), and the
    -- collision layers of the tile underneath that block it
    local allowed = true
    if result.tile_condition and #result.tile_condition > 0 then
        local listed = false
        for _, tile in pairs(result.tile_condition) do
            if tile.name == current.name then listed = true end
        end
        allowed = listed
    end
    if allowed and result.condition and result.condition.layers then
        local layers = current.prototype.collision_mask.layers
        for layer in pairs(result.condition.layers) do
            if layers[layer] then allowed = false end
        end
    end
    if result.invert then allowed = not allowed end
    if not allowed then
        error("\"Can't place " .. item_name .. " on " .. current.name .. " at (" .. cx .. ", " .. cy .. ")\"")
    end

    -- Entities in the way (other than fish, which a player's tile placement removes)
    local blocking = surface.find_entities_filtered{
        area = {{tx, ty}, {tx + 1, ty + 1}},
        type = {"fish", "character", "corpse", "particle", "projectile", "explosion", "smoke-with-trigger", "highlight-box", "flying-text"},
        invert = true,
    }
    for _, entity in ipairs(blocking) do
        local new_tile = prototypes.tile[tile_name]
        if entity.valid and entity.prototype.collision_mask and new_tile and new_tile.collision_mask then
            local entity_layers = entity.prototype.collision_mask.layers or {}
            for layer in pairs(new_tile.collision_mask.layers or {}) do
                if entity_layers[layer] then
                    error("\"Can't place " .. item_name .. " at (" .. cx .. ", " .. cy .. "): " .. entity.name ..
                          " at (" .. entity.position.x .. ", " .. entity.position.y .. ") is in the way\"")
                end
            end
        end
    end

    -- A player-built tile being replaced (e.g. stone path under concrete) goes back to the
    -- inventory, as when a player builds over it
    local returned = {}
    local mineable = current.prototype.mineable_properties
    if mineable and mineable.minable and mineable.products then
        for _, product in pairs(mineable.products) do
            if product.type == "item" then
                table.insert(returned, {name = product.name, count = product.amount or product.amount_min or 1})
            end
        end
    end

    surface.set_tiles({{name = tile_name, position = {tx, ty}}}, true, true, true, true)
    if surface.get_tile(tx, ty).name ~= tile_name then
        error("\"Could not place " .. item_name .. " at (" .. cx .. ", " .. cy .. ")\"")
    end
    player.remove_item{name = item_name, count = 1}
    for _, stack in ipairs(returned) do
        local inserted = player.insert(stack)
        if inserted < stack.count then
            surface.spill_item_stack{position = player.position, stack = {name = stack.name, count = stack.count - inserted},
                                     enable_looted = true, force = player.force}
        end
    end

    return {x = cx, y = cy}
end
