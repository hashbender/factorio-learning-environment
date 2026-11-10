-- A character grid of the map around a position: one character per tile.
-- Facts only: what entity, resource, water, cliff, tree or rock is on each tile.
storage.actions.get_map = function(player_index, x, y, radius)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface
    radius = math.max(1, math.min(32, math.floor(tonumber(radius) or 15)))
    local cx = math.floor(tonumber(x) or player.position.x)
    local cy = math.floor(tonumber(y) or player.position.y)
    local x0, y0, x1, y1 = cx - radius, cy - radius, cx + radius, cy + radius
    local area = {{x0, y0}, {x1 + 1, y1 + 1}}

    local grid = {}
    for ty = y0, y1 do
        grid[ty] = {}
        for tx = x0, x1 do
            grid[ty][tx] = "."
        end
    end
    local function mark(tx, ty, ch, overwrite)
        local row = grid[ty]
        if row and row[tx] and (overwrite or row[tx] == ".") then
            row[tx] = ch
        end
    end

    -- Ground: water
    local water = 0
    for _, tile in pairs(surface.find_tiles_filtered{area = area}) do
        if string.find(tile.name, "water", 1, true) then
            mark(tile.position.x, tile.position.y, "~", true)
            water = water + 1
        end
    end

    -- Resources: a lowercase letter per resource
    local letters_used = {}
    local resource_symbol, resource_count = {}, {}
    local function letter_for(name, upper)
        local pool = upper and "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" or "abcdefghijklmnopqrstuvwxyz"
        for i = 1, #name do
            local c = string.sub(name, i, i)
            c = upper and string.upper(c) or string.lower(c)
            if string.find(pool, c, 1, true) and not letters_used[c] then
                letters_used[c] = true
                return c
            end
        end
        for i = 1, #pool do
            local c = string.sub(pool, i, i)
            if not letters_used[c] then
                letters_used[c] = true
                return c
            end
        end
        return "?"
    end
    for _, res in pairs(surface.find_entities_filtered{area = area, type = "resource"}) do
        local name = res.name
        if not resource_symbol[name] then
            resource_symbol[name] = letter_for(name, false)
            resource_count[name] = 0
        end
        resource_count[name] = resource_count[name] + 1
        mark(math.floor(res.position.x), math.floor(res.position.y), resource_symbol[name], false)
    end

    -- Entities (drawn over resources): belts as arrows, others an uppercase letter or digit per name
    local arrows = {[defines.direction.north] = "^", [defines.direction.east] = ">",
                    [defines.direction.south] = "v", [defines.direction.west] = "<"}
    local entity_symbol, entity_count = {}, {}
    local trees, rocks, cliffs, belts = 0, 0, 0, {}
    local entities = surface.find_entities_filtered{area = area}
    for _, e in pairs(entities) do
        local t = e.type
        if e.valid and t ~= "resource" and t ~= "character" and t ~= "item-entity"
            and t ~= "corpse" and t ~= "entity-ghost" and t ~= "highlight-box" and t ~= "flying-text" then
            local ch
            if t == "tree" then
                ch = "%"; trees = trees + 1
            elseif t == "simple-entity" then
                ch = "*"; rocks = rocks + 1
            elseif t == "cliff" then
                ch = "#"; cliffs = cliffs + 1
            elseif t == "transport-belt" then
                ch = arrows[e.direction] or "+"
                belts[e.name] = (belts[e.name] or 0) + 1
            else
                if not entity_symbol[e.name] then
                    entity_symbol[e.name] = letter_for(e.name, true)
                    entity_count[e.name] = 0
                end
                entity_count[e.name] = entity_count[e.name] + 1
                ch = entity_symbol[e.name]
            end
            local box = e.bounding_box
            local lx, ly = math.floor(box.left_top.x + 0.01), math.floor(box.left_top.y + 0.01)
            local rx, ry = math.ceil(box.right_bottom.x - 0.01) - 1, math.ceil(box.right_bottom.y - 0.01) - 1
            for ty = ly, math.max(ly, ry) do
                for tx = lx, math.max(lx, rx) do
                    mark(tx, ty, ch, true)
                end
            end
        end
    end
    mark(math.floor(player.position.x), math.floor(player.position.y), "@", true)

    local rows = {}
    for ty = y0, y1 do
        table.insert(rows, "\"" .. table.concat(grid[ty], "", x0, x1) .. "\"")
    end
    local legend = {}
    local function add(symbol, text)
        table.insert(legend, {symbol = "\"" .. symbol .. "\"", text = "\"" .. text .. "\""})
    end
    local names = {}
    for name in pairs(entity_symbol) do table.insert(names, name) end
    table.sort(names)
    for _, name in ipairs(names) do
        add(entity_symbol[name], name .. " (" .. entity_count[name] .. ")")
    end
    local belt_names = {}
    for name, n in pairs(belts) do table.insert(belt_names, name .. " " .. n) end
    table.sort(belt_names)
    if #belt_names > 0 then
        add("^>v<", "belts, pointing the way they move: " .. table.concat(belt_names, ", "))
    end
    local res_names = {}
    for name in pairs(resource_symbol) do table.insert(res_names, name) end
    table.sort(res_names)
    for _, name in ipairs(res_names) do
        add(resource_symbol[name], name .. " (" .. resource_count[name] .. " tiles)")
    end
    if water > 0 then add("~", "water (" .. water .. " tiles)") end
    if cliffs > 0 then add("#", "cliff (" .. cliffs .. ")") end
    if trees > 0 then add("%", "tree (" .. trees .. ")") end
    if rocks > 0 then add("*", "rock (" .. rocks .. ")") end
    add("@", "you")
    add(".", "nothing on the tile")
    return {x0 = x0, y0 = y0, x1 = x1, y1 = y1, rows = rows, legend = legend}
end
