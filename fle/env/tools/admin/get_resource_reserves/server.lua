-- Resource patches near the factory, from the game's resource entities.
-- The factory area is the bounding box of the force's entities within `radius`
-- tiles of the character, plus the character's position. Every patch with a
-- tile within `margin` tiles of that area is followed to its full extent
-- (connected resource tiles of one name, gaps under CELL tiles bridged), up to
-- `radius` tiles from the character. Per patch: name, total amount, tile
-- count, bounding box of its tiles, and whether it continues past the radius.
local CELL = 8

storage.actions.get_resource_reserves = function(player_index, margin, radius, max_cells)
    local player = storage.agent_characters[player_index]
    if not (player and player.valid) then
        error("\"No valid character\"")
    end
    local surface = player.surface
    margin = margin or 100
    radius = radius or 1000
    max_cells = max_cells or 20000
    local px, py = player.position.x, player.position.y

    local ax1, ay1, ax2, ay2 = px, py, px, py
    local buildings = 0
    for _, e in pairs(surface.find_entities_filtered{position = {px, py}, radius = radius, force = player.force}) do
        if e.valid and e.type ~= "character" then
            local p = e.position
            if p.x < ax1 then ax1 = p.x end
            if p.y < ay1 then ay1 = p.y end
            if p.x > ax2 then ax2 = p.x end
            if p.y > ay2 then ay2 = p.y end
            buildings = buildings + 1
        end
    end

    local function cell_of(v) return math.floor(v / CELL) end
    local r2 = radius * radius
    local function in_radius(cx, cy)
        -- nearest point of the cell to the character
        local x = math.max(cx * CELL, math.min(px, (cx + 1) * CELL))
        local y = math.max(cy * CELL, math.min(py, (cy + 1) * CELL))
        return (x - px) ^ 2 + (y - py) ^ 2 <= r2
    end

    -- seed cells: resource tiles near the factory area, per resource name
    local seeds = {}
    local seed_area = {{ax1 - margin, ay1 - margin}, {ax2 + margin, ay2 + margin}}
    for _, r in pairs(surface.find_entities_filtered{area = seed_area, type = "resource"}) do
        local p = r.position
        local key = r.name .. "|" .. cell_of(p.x) .. "|" .. cell_of(p.y)
        seeds[key] = {name = r.name, cx = cell_of(p.x), cy = cell_of(p.y)}
    end

    local visited = {}
    local patches = {}
    local cells_used = 0
    local truncated = false
    local seed_keys = {}
    for key in pairs(seeds) do table.insert(seed_keys, key) end
    table.sort(seed_keys)
    for _, key in ipairs(seed_keys) do
        local s = seeds[key]
        if not visited[key] then
            local patch = {name = s.name, amount = 0, tiles = 0, clipped = false}
            local queue = {{s.cx, s.cy}}
            visited[key] = true
            local head = 1
            while head <= #queue do
                local cx, cy = queue[head][1], queue[head][2]
                head = head + 1
                cells_used = cells_used + 1
                if cells_used > max_cells then
                    truncated = true
                    break
                end
                local found = surface.find_entities_filtered{
                    area = {{cx * CELL, cy * CELL}, {(cx + 1) * CELL, (cy + 1) * CELL}},
                    type = "resource", name = s.name,
                }
                local any = false
                for _, r in pairs(found) do
                    local p = r.position
                    -- the area test is inclusive of the far edge; count each tile in one cell only
                    if cell_of(p.x) == cx and cell_of(p.y) == cy then
                        any = true
                        patch.amount = patch.amount + r.amount
                        patch.tiles = patch.tiles + 1
                        if patch.x1 == nil or p.x < patch.x1 then patch.x1 = p.x end
                        if patch.y1 == nil or p.y < patch.y1 then patch.y1 = p.y end
                        if patch.x2 == nil or p.x > patch.x2 then patch.x2 = p.x end
                        if patch.y2 == nil or p.y > patch.y2 then patch.y2 = p.y end
                    end
                end
                if any then
                    for dx = -1, 1 do
                        for dy = -1, 1 do
                            local nx, ny = cx + dx, cy + dy
                            local nkey = s.name .. "|" .. nx .. "|" .. ny
                            if not visited[nkey] then
                                if in_radius(nx, ny) then
                                    visited[nkey] = true
                                    table.insert(queue, {nx, ny})
                                else
                                    patch.clipped = true
                                end
                            end
                        end
                    end
                end
            end
            if patch.tiles > 0 then
                local proto = prototypes.entity[s.name]
                patch.infinite = proto and proto.infinite_resource or false
                patch.normal = proto and proto.normal_resource_amount or nil
                table.insert(patches, patch)
            end
            if truncated then break end
        end
    end

    return {
        area = {x1 = ax1, y1 = ay1, x2 = ax2, y2 = ay2},
        buildings = buildings,
        margin = margin,
        radius = radius,
        count = #patches,
        patches = patches,
        truncated = truncated,
    }
end
