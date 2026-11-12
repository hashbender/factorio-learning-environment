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

    -- Items on a belt's lanes, e.g. "L iron-ore:3, R coal:1" (or "nothing")
    local function lanes_of(belt)
        local parts = {}
        for line = 1, belt.get_max_transport_line_index() do
            local label = (line % 2 == 1) and "L" or "R"
            for name, n in pairs(storage.utils.get_contents_compat(belt.get_transport_line(line))) do
                table.insert(parts, label .. " " .. name .. ":" .. n)
            end
        end
        return #parts > 0 and table.concat(parts, ", ") or "nothing"
    end

    -- Take up to `count` items off a belt's lanes into the character (only what fits)
    local function take_from_belt(belt)
        local where = belt.name .. " at " .. fmt_pos(belt.position)
        local on_belt = belt_count(belt, extract_item)
        if on_belt == 0 then
            error("\"" .. where .. " has no " .. extract_item .. " on its lanes (it carries " .. lanes_of(belt) .. ")\"")
        end
        if not player.can_reach_entity(belt) then
            error("\"" .. where .. " is too far away from your position of (" .. player.position.x .. "," ..
                player.position.y .. "), move closer.\"")
        end
        local room = on_belt
        local ok, insertable = pcall(function()
            return player.get_main_inventory().get_insertable_count(extract_item)
        end)
        if ok and type(insertable) == "number" then
            room = insertable
        end
        local want = math.min(count, on_belt, room)
        if want <= 0 then
            error("\"Failed to extract " .. extract_item .. " from " .. where .. ": your inventory has no room for it\"")
        end
        local taken = 0
        for line = 1, belt.get_max_transport_line_index() do
            if taken >= want then
                break
            end
            taken = taken + belt.get_transport_line(line).remove_item({name = extract_item, count = want - taken})
        end
        if taken == 0 then
            error("\"Failed to extract " .. extract_item .. " from " .. where .. "\"")
        end
        local inserted = player.insert({name = extract_item, count = taken})
        if inserted < taken then
            -- should not happen after the room check; never lose items
            belt.surface.spill_item_stack{position = player.position, stack = {name = extract_item, count = taken - inserted}}
        end
        return inserted
    end

    -- First validate the request
    if count <= 0 then
        error("\"Invalid count " .. tostring(count) .. ": the quantity must be greater than 0\"")
    end

    -- The source is the entity that occupies the position (for an Entity source: the
    -- entity of that name there). A tile (x, y) spans [x, x + 1) x [y, y + 1), so a
    -- position on the edge shared by two adjacent entities belongs to the one on its
    -- right / below; a position on an entity's outer edge still selects it when nothing
    -- else covers it. Items never come from a neighbouring entity.
    local skip_types = {["character"] = true, ["entity-ghost"] = true, ["tile-ghost"] = true}
    local function footprint(e)
        local box = e.bounding_box
        return math.floor(box.left_top.x), math.floor(box.left_top.y),
            math.ceil(box.right_bottom.x), math.ceil(box.right_bottom.y)
    end
    local function inside(e)
        local l, t, r, b = footprint(e)
        return position.x >= l and position.x < r and position.y >= t and position.y < b
    end
    local function on_edge(e)
        local l, t, r, b = footprint(e)
        return position.x >= l and position.x <= r and position.y >= t and position.y <= b
    end
    local function distance(e)
        return ((position.x - e.position.x) ^ 2 + (position.y - e.position.y) ^ 2) ^ 0.5
    end
    local function closest(list, accept)
        local best, best_distance = nil, math.huge
        for _, e in ipairs(list) do
            if e.valid and not skip_types[e.type] and accept(e) then
                local d = distance(e)
                if d < best_distance then
                    best, best_distance = e, d
                end
            end
        end
        return best
    end

    local near = surface.find_entities_filtered{
        area = {{position.x - 1, position.y - 1}, {position.x + 1, position.y + 1}},
        name = source_name,
        force = player.force
    }
    local source = closest(near, inside) or closest(near, on_edge)

    if not source then
        -- Name what is nearby, so the caller can address it
        local search_radius = 10
        local around = surface.find_entities_filtered{
            area = {{position.x - search_radius, position.y - search_radius},
                    {position.x + search_radius, position.y + search_radius}},
            name = source_name,
            force = player.force
        }
        local holders = {}
        for _, e in ipairs(around) do
            if e.valid and not skip_types[e.type] then
                local n = belt_types[e.type] and belt_count(e, extract_item) or e.get_item_count(extract_item)
                if n > 0 then
                    table.insert(holders, {e = e, n = n, d = distance(e)})
                end
            end
        end
        table.sort(holders, function(a, b) return a.d < b.d end)
        local what = source_name or "entity"
        local msg = "No " .. what .. " at " .. fmt_pos(position) .. ": extract_item takes items only from the entity" ..
            " that occupies the given position"
        if #holders > 0 then
            local parts = {}
            for i = 1, math.min(3, #holders) do
                local h = holders[i]
                table.insert(parts, string.format("%s at %s (%d %s, %.1f tiles away)", h.e.name, fmt_pos(h.e.position),
                    h.n, extract_item, h.d))
            end
            msg = msg .. ". Nearest that hold " .. extract_item .. ": " .. table.concat(parts, "; ")
        else
            msg = msg .. ". Nothing within " .. search_radius .. " tiles holds " .. extract_item
        end
        error("\"" .. msg .. "\"")
    end

    -- A belt: take the items off its lanes, as a player can
    if belt_types[source.type] then
        return take_from_belt(source)
    end

    if source.get_item_count(extract_item) == 0 then
        error("\"" .. source.name .. " at " .. fmt_pos(source.position) .. " has no " .. extract_item ..
            " (it holds " .. contents_of(source) .. ")\"")
    end
    local closest_entity = source

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
