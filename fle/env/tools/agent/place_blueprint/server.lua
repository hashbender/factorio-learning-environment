-- Place a saved blueprint as ghosts, as a player does (LuaItemStack.build_blueprint). Only
-- construction robots build the ghosts. Parts that collide with something are not placed;
-- each one is reported with what is in the way.
local function rotate(x, y, direction)
    if direction == 4 then return -y, x
    elseif direction == 8 then return -x, -y
    elseif direction == 12 then return y, -x end
    return x, y
end

local function fmt(v)
    return (v == math.floor(v)) and tostring(math.floor(v)) or tostring(v)
end

local function obstacle(surface, force, name, x, y, direction)
    local w, h = storage.utils.entity_footprint(name, direction)
    local area = {{x - w / 2 + 0.05, y - h / 2 + 0.05}, {x + w / 2 - 0.05, y + h / 2 - 0.05}}
    for _, e in ipairs(surface.find_entities_filtered{area = area}) do
        if e.valid and e.type ~= "character" and e.type ~= "resource" and e.type ~= "item-request-proxy" then
            local what = e.type == "entity-ghost" and ("a ghost of " .. e.ghost_name) or e.name
            return what .. " at (" .. fmt(e.position.x) .. ", " .. fmt(e.position.y) .. ")"
        end
    end
    for tx = math.floor(area[1][1]), math.floor(area[2][1]) do
        for ty = math.floor(area[1][2]), math.floor(area[2][2]) do
            local tile = surface.get_tile(tx, ty)
            if tile.valid and tile.collides_with("water_tile") then
                return tile.name .. " tile at (" .. tx .. ", " .. ty .. ")"
            end
        end
    end
    return "the game refused it here"
end

storage.actions.place_blueprint = function(player_index, name, x, y, direction, forced)
    local player = storage.utils.ensure_valid_character(player_index)
    local stack = storage.utils.get_blueprint_stack(name)
    local surface, force = player.surface, player.force
    direction = tonumber(direction) or 0
    if direction % 4 ~= 0 then
        error("\"A blueprint can face north, east, south or west only\"")
    end
    direction = direction % 16

    -- where each entity lands: blueprint positions are relative to the centre of its footprint,
    -- the centre snaps to a tile centre (odd size) or a tile corner (even size), then turns
    local _, ents, box = storage.utils.blueprint_info(name, stack, false)
    local cx, cy = (box[1] + box[3]) / 2, (box[2] + box[4]) / 2
    local bw, bh = box[3] - box[1], box[4] - box[2]
    if direction == 4 or direction == 12 then bw, bh = bh, bw end
    local ox = (math.floor(bw + 0.5) % 2 == 1) and (math.floor(x) + 0.5) or math.floor(x + 0.5)
    local oy = (math.floor(bh + 0.5) % 2 == 1) and (math.floor(y) + 0.5) or math.floor(y + 0.5)
    local expected = {}
    for _, e in ipairs(ents) do
        local rx, ry = rotate(e.position.x - cx, e.position.y - cy, direction)
        table.insert(expected, {name = e.name, x = ox + rx, y = oy + ry, direction = ((e.direction or 0) + direction) % 16})
    end

    -- ghosts can only go where the map exists: charted or generated chunks (FLE worlds have
    -- no connected player, so the game charts nothing around the character)
    for _, e in ipairs(expected) do
        local chunk = {math.floor(e.x / 32), math.floor(e.y / 32)}
        if not (force.is_chunk_charted(surface, chunk) or surface.is_chunk_generated(chunk)) then
            error("\"Cannot place blueprint " .. name .. ": (" .. fmt(e.x) .. ", " .. fmt(e.y) ..
                  ") is in a part of the map that has not been generated or charted\"")
        end
    end

    local w2, h2 = bw / 2 + 1, bh / 2 + 1
    local zone = {{ox - w2, oy - h2}, {ox + w2, oy + h2}}
    local marked_before = #surface.find_entities_filtered{area = zone, to_be_deconstructed = true}

    local ghosts = stack.build_blueprint{surface = surface, force = force, position = {x, y},
                                         direction = direction, skip_fog_of_war = false, raise_built = true,
                                         build_mode = forced and defines.build_mode.forced or defines.build_mode.normal}

    -- line the prediction up with the game's own placement if they differ
    local placed = {}
    for _, g in pairs(ghosts or {}) do
        if g.valid then table.insert(placed, g) end
    end
    if placed[1] then
        local g, best, bd = placed[1], nil, math.huge
        for _, e in ipairs(expected) do
            if e.name == g.ghost_name then
                local d = (e.x - g.position.x) ^ 2 + (e.y - g.position.y) ^ 2
                if d < bd then best, bd = e, d end
            end
        end
        if best and bd > 0.01 then
            local dx, dy = g.position.x - best.x, g.position.y - best.y
            for _, e in ipairs(expected) do e.x, e.y = e.x + dx, e.y + dy end
        end
    end

    local at = {}
    for _, g in ipairs(placed) do
        at[g.ghost_name .. "@" .. g.position.x .. "," .. g.position.y] = true
    end
    local counts, items, refused, record = {}, {}, {}, {}
    local refused_count, already = 0, 0
    for _, e in ipairs(expected) do
        if at[e.name .. "@" .. e.x .. "," .. e.y] then
            counts[e.name] = (counts[e.name] or 0) + 1
            local item, n = storage.utils.build_item(e.name)
            if item then items[item] = (items[item] or 0) + n end
            table.insert(record, {name = e.name, x = e.x, y = e.y})
        else
            local same = false
            for _, o in ipairs(surface.find_entities_filtered{position = {e.x, e.y}, force = force}) do
                if (o.name == e.name or (o.type == "entity-ghost" and o.ghost_name == e.name))
                   and math.abs(o.position.x - e.x) < 0.01 and math.abs(o.position.y - e.y) < 0.01 then
                    same = true
                end
            end
            if same then
                already = already + 1
            else
                refused_count = refused_count + 1
                if #refused < 20 then
                    table.insert(refused, {name = e.name, x = e.x, y = e.y,
                                           reason = "blocked by " .. obstacle(surface, force, e.name, e.x, e.y, e.direction)})
                end
            end
        end
    end

    local store = storage.utils.blueprint_store()
    local id = store.next_placement
    store.next_placement = id + 1
    if #record > 0 then
        table.insert(store.placements, {id = id, blueprint = name, x = ox, y = oy, ghosts = record})
        while #store.placements > storage.utils.PLACEMENTS_KEPT do table.remove(store.placements, 1) end
    end
    local marked = #surface.find_entities_filtered{area = zone, to_be_deconstructed = true} - marked_before
    return storage.utils.hex_json({placement_id = id, blueprint = name, ghosts_placed = #record, ghosts = counts,
                                   items_needed = items, already_built = already, refused_count = refused_count,
                                   refused = refused, obstacles_marked_for_deconstruction = math.max(marked, 0),
                                   center = {x = ox, y = oy}})
end
