-- Move up to `count` items from the entity's inventories into the player's.
-- Each slot is moved with its state: for tools (science packs) the top item of a
-- stack may be part-used, and that partial durability goes with it, so the total
-- durability in the world is unchanged. Returns the number of items moved.
local function move_items_to_player(entity, player, item_name, count)
    local moved = 0
    for index = 1, entity.get_max_inventory_index() do
        local inventory = entity.get_inventory(index)
        if inventory then
            for slot = 1, #inventory do
                if moved >= count then
                    return moved
                end
                local stack = inventory[slot]
                if stack.valid_for_read and stack.name == item_name then
                    local is_tool = stack.prototype.type == "tool"
                    local taken = {
                        name = item_name,
                        count = math.min(count - moved, stack.count),
                        quality = stack.quality.name
                    }
                    if is_tool then
                        taken.durability = stack.durability
                    end
                    local inserted = player.insert(taken)
                    if inserted == 0 then
                        return moved
                    end
                    if inserted >= stack.count then
                        stack.clear()
                    else
                        stack.count = stack.count - inserted
                        if is_tool then
                            -- the part-used item went to the player; the rest are full
                            stack.durability = stack.prototype.get_durability(stack.quality)
                        end
                    end
                    moved = moved + inserted
                end
            end
        end
    end
    return moved
end

storage.actions.extract_item = function(player_index, extract_item, count, x, y, source_name)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}
    local surface = player.surface

    local function fmt_pos(p)
        return string.format("(%s, %s)", p.x, p.y)
    end

    -- Short list of what an entity holds, e.g. "iron-ore:4, coal:2" (or "nothing")
    local function contents_of(entity)
        local counts, order = {}, {}
        for index = 1, entity.get_max_inventory_index() do
            local inventory = entity.get_inventory(index)
            if inventory then
                for name, n in pairs(storage.utils.get_contents_compat(inventory)) do
                    if not counts[name] then table.insert(order, name) end
                    counts[name] = (counts[name] or 0) + n
                end
            end
        end
        local parts = {}
        for i, name in ipairs(order) do
            if i > 6 then
                table.insert(parts, "(" .. (#order - 6) .. " more)")
                break
            end
            table.insert(parts, name .. ":" .. counts[name])
        end
        return #parts > 0 and table.concat(parts, ", ") or "nothing"
    end

    local belt_types = {["transport-belt"] = true, ["underground-belt"] = true, ["splitter"] = true}

    -- Items of one kind on a belt's transport lines
    local function belt_count(belt, item_name)
        local n = 0
        for line = 1, belt.get_max_transport_line_index() do
            n = n + belt.get_transport_line(line).get_item_count(item_name)
        end
        return n
    end

    -- First validate the request
    if count <= 0 then
        error("\"Invalid count " .. tostring(count) .. ": the quantity must be greater than 0\"")
    end

    -- An entity source means that entity: look at its own tile first
    local exact = nil
    if source_name ~= nil then
        local here = surface.find_entities_filtered{position = position, name = source_name, limit = 1}
        exact = here[1]
    end

    -- Find all entities in range
    local search_radius = 10
    local area = {{position.x - search_radius, position.y - search_radius},
                  {position.x + search_radius, position.y + search_radius}}
    local buildings = nil

    if exact then
        buildings = {exact}
    elseif source_name ~= nil then
        buildings = surface.find_entities_filtered{
            area = area,
            name = source_name
        }
    else
        buildings = surface.find_entities_filtered{
            area = area
        }
    end

    -- Find the closest building with the item we want
    local closest_distance = math.huge
    local closest_entity = nil
    local belt_with_item = nil

    for _, building in ipairs(buildings) do
        if building.name ~= 'character' then
            if belt_types[building.type] then
                if not belt_with_item and belt_count(building, extract_item) > 0 then
                    belt_with_item = building
                end
            else
                local item_count = building.get_item_count(extract_item)
                if item_count > 0 then
                    local distance = ((position.x - building.position.x) ^ 2 +
                                    (position.y - building.position.y) ^ 2) ^ 0.5
                    if distance < closest_distance then
                        closest_distance = distance
                        closest_entity = building
                    end
                end
            end
        end
    end

    -- Error handling in priority order

    if #buildings == 0 then
        if source_name then
            error("\"No " .. source_name .. " within " .. search_radius .. " tiles of " .. fmt_pos(position) .. "\"")
        end
        error("\"No entity within " .. search_radius .. " tiles of " .. fmt_pos(position) .. "\"")
    end

    if not closest_entity then
        if exact and belt_types[exact.type] or (not exact and belt_with_item) then
            local belt = exact or belt_with_item
            error("\"extract_item takes items from entity inventories; " .. belt.name .. " at " .. fmt_pos(belt.position) ..
                " has no inventory (" .. belt_count(belt, extract_item) .. " " .. extract_item ..
                " on its lanes; items on belts are not extracted)\"")
        end
        if exact then
            error("\"" .. exact.name .. " at " .. fmt_pos(exact.position) .. " has no " .. extract_item ..
                " (it holds " .. contents_of(exact) .. ")\"")
        end
        local where = search_radius .. " tiles of " .. fmt_pos(position)
        if source_name then
            error("\"No " .. source_name .. " within " .. where .. " holds " .. extract_item .. "\"")
        else
            error("\"No entity within " .. where .. " holds " .. extract_item .. "\"")
        end
    end

    if not player.can_reach_entity(closest_entity) then
        error("\"" .. closest_entity.name .. " at ("..closest_entity.position.x..", "..closest_entity.position.y..") is too far away from your position of ("..player.position.x..","..player.position.y.."), move closer.\"")
    end

    -- Calculate how many items we can actually extract
    local available_count = closest_entity.get_item_count(extract_item)
    local extract_count = math.min(count, available_count)

    -- Move the items into the player's inventory (only what fits is removed)
    local number_extracted = move_items_to_player(closest_entity, player, extract_item, extract_count)

    if number_extracted > 0 then
        -- game.print("Extracted " .. number_extracted .. " " .. extract_item)
        return number_extracted
    else
        -- Nothing could be moved
        if not player.can_insert({name = extract_item, count = 1}) then
            error("\"Failed to extract " .. extract_item .. " from " .. closest_entity.name .. " at " ..
                fmt_pos(closest_entity.position) .. ": your inventory has no room for it\"")
        end
        error("\"Failed to extract " .. extract_item .. " from " .. closest_entity.name .. " at " ..
            fmt_pos(closest_entity.position) .. "\"")
    end
end
