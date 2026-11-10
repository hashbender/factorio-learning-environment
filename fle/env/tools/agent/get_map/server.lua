-- A character grid of a box of the map: one character per tile.
-- Facts only: what entity, resource, water, cliff, tree or rock is on each tile.
-- Reads the map; changes nothing, takes no game time and has no reach rule.
-- Tiles in chunks the force has not charted are "?" and nothing on them is reported.
--
-- Inserters are returned as n / e / s / w (the side they drop on); the client
-- prints them as arrows. Those four letters are never used for a resource.
local MAX_SIDE = 64

storage.actions.get_map = function(player_index, x0, y0, x1, y1, radius)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface
    local force = player.force
    local px, py = math.floor(player.position.x), math.floor(player.position.y)

    x0, y0, x1, y1 = tonumber(x0), tonumber(y0), tonumber(x1), tonumber(y1)
    if x0 and y0 and x1 and y1 then
        x0, y0, x1, y1 = math.floor(x0), math.floor(y0), math.floor(x1), math.floor(y1)
        if x1 < x0 then x0, x1 = x1, x0 end
        if y1 < y0 then y0, y1 = y1, y0 end
    else
        radius = math.max(1, math.min(31, math.floor(tonumber(radius) or 15)))
        x0, y0, x1, y1 = px - radius, py - radius, px + radius, py + radius
    end
    local width, height = x1 - x0 + 1, y1 - y0 + 1
    if width > MAX_SIDE or height > MAX_SIDE then
        error("\"The map area is " .. width .. " x " .. height .. " tiles; the most one call returns is "
            .. MAX_SIDE .. " x " .. MAX_SIDE .. " tiles\"")
    end
    local area = {{x0, y0}, {x1 + 1, y1 + 1}}

    -- Charted chunks (what the in-game map shows)
    local chunk_charted = {}
    local function charted(tx, ty)
        local cx, cy = math.floor(tx / 32), math.floor(ty / 32)
        local key = cx .. "," .. cy
        if chunk_charted[key] == nil then
            chunk_charted[key] = force.is_chunk_charted(surface, {x = cx, y = cy}) and true or false
        end
        return chunk_charted[key]
    end

    local grid = {}
    local uncharted = 0
    for ty = y0, y1 do
        grid[ty] = {}
        for tx = x0, x1 do
            if charted(tx, ty) then
                grid[ty][tx] = "."
            else
                grid[ty][tx] = "?"
                uncharted = uncharted + 1
            end
        end
    end
    local function mark(tx, ty, ch, overwrite)
        local row = grid[ty]
        local cur = row and row[tx]
        if cur and cur ~= "?" and (overwrite or cur == ".") then
            row[tx] = ch
        end
    end

    -- Ground: water
    local water = 0
    for _, tile in pairs(surface.find_tiles_filtered{area = area}) do
        if string.find(tile.name, "water", 1, true) then
            local tx, ty = tile.position.x, tile.position.y
            if grid[ty] and grid[ty][tx] == "." then
                grid[ty][tx] = "~"
                water = water + 1
            end
        end
    end

    local function tiles_of(e)
        local box = e.bounding_box
        local lx, ly = math.floor(box.left_top.x + 0.01), math.floor(box.left_top.y + 0.01)
        local rx, ry = math.ceil(box.right_bottom.x - 0.01) - 1, math.ceil(box.right_bottom.y - 0.01) - 1
        return lx, ly, math.max(lx, rx), math.max(ly, ry)
    end
    local function visible(e)
        return charted(math.floor(e.position.x), math.floor(e.position.y))
    end

    -- First pass: what is there, so symbols are given in name order (the same
    -- set of names always gets the same symbols)
    local skip = {["resource"] = true, ["character"] = true, ["item-entity"] = true, ["corpse"] = true,
                  ["entity-ghost"] = true, ["tile-ghost"] = true, ["highlight-box"] = true,
                  ["flying-text"] = true, ["character-corpse"] = true}
    local resources, entities = {}, {}
    local resource_count, entity_count = {}, {}
    local belts, pipes, poles, inserters = {}, {}, {}, {}
    local trees, rocks, cliffs = 0, 0, 0
    for _, e in pairs(surface.find_entities_filtered{area = area}) do
        if e.valid and visible(e) then
            local t = e.type
            if t == "resource" then
                table.insert(resources, e)
                resource_count[e.name] = (resource_count[e.name] or 0) + 1
            elseif not skip[t] then
                table.insert(entities, e)
                if t == "tree" then
                    trees = trees + 1
                elseif t == "simple-entity" then
                    rocks = rocks + 1
                elseif t == "cliff" then
                    cliffs = cliffs + 1
                elseif t == "transport-belt" then
                    belts[e.name] = (belts[e.name] or 0) + 1
                elseif t == "pipe" then
                    pipes[e.name] = (pipes[e.name] or 0) + 1
                elseif t == "electric-pole" then
                    poles[e.name] = (poles[e.name] or 0) + 1
                elseif t == "inserter" then
                    inserters[e.name] = (inserters[e.name] or 0) + 1
                else
                    entity_count[e.name] = (entity_count[e.name] or 0) + 1
                end
            end
        end
    end

    local function sorted_keys(t)
        local keys = {}
        for k in pairs(t) do table.insert(keys, k) end
        table.sort(keys)
        return keys
    end
    local used = {}
    local function letter_for(name, pool, upper)
        for i = 1, #name do
            local c = string.sub(name, i, i)
            c = upper and string.upper(c) or string.lower(c)
            if string.find(pool, c, 1, true) and not used[c] then
                used[c] = true
                return c
            end
        end
        for i = 1, #pool do
            local c = string.sub(pool, i, i)
            if not used[c] then
                used[c] = true
                return c
            end
        end
        return "&"  -- more names than symbols: the legend lists what shares it
    end
    local resource_symbol, entity_symbol = {}, {}
    for _, name in ipairs(sorted_keys(resource_count)) do
        -- n, e, s, w are kept for inserters
        resource_symbol[name] = letter_for(name, "abcdfghijklmopqrtuvxyz", false)
    end
    for _, name in ipairs(sorted_keys(entity_count)) do
        entity_symbol[name] = letter_for(name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", true)
    end

    -- Resources, then entities over them
    for _, res in ipairs(resources) do
        mark(math.floor(res.position.x), math.floor(res.position.y), resource_symbol[res.name], false)
    end
    local arrows = {[defines.direction.north] = "^", [defines.direction.east] = ">",
                    [defines.direction.south] = "v", [defines.direction.west] = "<"}
    local occupied = {}
    for _, e in ipairs(entities) do
        local t = e.type
        local ch
        if t == "tree" then
            ch = "%"
        elseif t == "simple-entity" then
            ch = "*"
        elseif t == "cliff" then
            ch = "#"
        elseif t == "transport-belt" then
            ch = arrows[e.direction] or "+"
        elseif t == "pipe" then
            ch = "="
        elseif t == "electric-pole" then
            ch = "|"
        elseif t == "inserter" then
            -- the side it drops on
            local dx, dy = e.drop_position.x - e.position.x, e.drop_position.y - e.position.y
            if math.abs(dx) >= math.abs(dy) then
                ch = dx >= 0 and "e" or "w"
            else
                ch = dy >= 0 and "s" or "n"
            end
        else
            ch = entity_symbol[e.name]
        end
        local lx, ly, rx, ry = tiles_of(e)
        for ty = ly, ry do
            for tx = lx, rx do
                mark(tx, ty, ch, true)
                occupied[tx .. "," .. ty] = true
            end
        end
    end
    -- The character is drawn only on a tile with no entity, so it hides nothing
    local you_drawn = false
    if grid[py] and grid[py][px] and grid[py][px] ~= "?" and not occupied[px .. "," .. py] then
        grid[py][px] = "@"
        you_drawn = true
    end

    local rows = {}
    for ty = y0, y1 do
        table.insert(rows, "\"" .. table.concat(grid[ty], "", x0, x1) .. "\"")
    end
    local legend = {}
    local function add(symbol, text)
        table.insert(legend, {symbol = "\"" .. symbol .. "\"", text = "\"" .. text .. "\""})
    end
    local function counts(t)
        local parts = {}
        for _, name in ipairs(sorted_keys(t)) do table.insert(parts, name .. " " .. t[name]) end
        return table.concat(parts, ", ")
    end
    for _, name in ipairs(sorted_keys(entity_symbol)) do
        add(entity_symbol[name], name .. " (" .. entity_count[name] .. ")")
    end
    if next(belts) then add("^ > v <", "belt, pointing the way it moves items: " .. counts(belts)) end
    if next(inserters) then add("INSERTER", "inserter, pointing at the side it drops on: " .. counts(inserters)) end
    if next(pipes) then add("=", "pipe: " .. counts(pipes)) end
    if next(poles) then add("|", "electric pole: " .. counts(poles)) end
    for _, name in ipairs(sorted_keys(resource_symbol)) do
        add(resource_symbol[name], name .. " (" .. resource_count[name] .. " tiles)")
    end
    if water > 0 then add("~", "water (" .. water .. " tiles)") end
    if cliffs > 0 then add("#", "cliff (" .. cliffs .. ")") end
    if trees > 0 then add("%", "tree (" .. trees .. ")") end
    if rocks > 0 then add("*", "rock (" .. rocks .. ")") end
    if you_drawn then add("@", "you") end
    add(".", "nothing on the tile")
    if uncharted > 0 then add("?", "not charted (" .. uncharted .. " tiles)") end
    return {x0 = x0, y0 = y0, x1 = x1, y1 = y1, rows = rows, legend = legend,
            player_x = px, player_y = py}
end
