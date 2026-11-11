storage.actions.get_entity = function(player_index, entity, x, y)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x = x, y = y}

    if prototypes.entity[entity] == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error(name .. " isnt something that exists. Did you make a typo? ")
    end

    -- The tiles an entity occupies: its bounding box widened to whole tiles
    -- (collision boxes sit a little inside the tile edges).
    local function footprint(e)
        local box = e.bounding_box
        return math.floor(box.left_top.x), math.floor(box.left_top.y),
            math.ceil(box.right_bottom.x), math.ceil(box.right_bottom.y)
    end

    -- inside: the position is on one of the entity's tiles; a tile (x, y) spans
    -- [x, x + 1) x [y, y + 1), so a position on the edge shared by two adjacent
    -- entities belongs to the one on its right / below.
    -- on_edge: the position is on the entity's tiles or on their outer edge.
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
            if e.valid and e.name ~= 'character' and accept(e) then
                local d = distance(e)
                if d < best_distance then
                    best, best_distance = e, d
                end
            end
        end
        return best
    end

    -- An area one tile wider than the position on each side holds every entity
    -- whose footprint contains the position (and possibly its neighbours).
    local entities = player.surface.find_entities_filtered{
        area = {{position.x - 1, position.y - 1}, {position.x + 1, position.y + 1}},
        name = entity
    }

    local found = closest(entities, inside) or closest(entities, on_edge)
    if found ~= nil then
        return storage.utils.serialize_entity(found)
    end

    -- Nothing of this type covers the position: name the nearest ones.
    local search = 30
    local nearby = player.surface.find_entities_filtered{
        area = {{position.x - search, position.y - search}, {position.x + search, position.y + search}},
        name = entity
    }
    local candidates = {}
    for _, e in ipairs(nearby) do
        if e.valid and e.name ~= 'character' then
            table.insert(candidates, {entity = e, distance = distance(e)})
        end
    end
    table.sort(candidates, function(a, b) return a.distance < b.distance end)

    local function fmt(v) return string.format("%.1f", v) end
    local where = "(" .. fmt(position.x) .. ", " .. fmt(position.y) .. ")"
    local message = "Could not get " .. entity .. " at position " .. where .. ": no " .. entity ..
        " covers that position."
    if #candidates == 0 then
        message = message .. " There is no " .. entity .. " within " .. search .. " tiles."
    else
        local parts = {}
        for i = 1, math.min(3, #candidates) do
            local c = candidates[i]
            table.insert(parts, c.entity.name .. " at (" .. fmt(c.entity.position.x) .. ", " ..
                fmt(c.entity.position.y) .. ") " .. fmt(c.distance) .. " tiles away")
        end
        message = message .. " Nearest: " .. table.concat(parts, "; ") .. "."
    end
    error("\"" .. message .. "\"")
end
