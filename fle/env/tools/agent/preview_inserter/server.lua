-- What an inserter would take from and drop into if built at `position` facing
-- `direction` (the arrows the game shows while placing one). Builds nothing and
-- needs no item in the inventory. `direction` is a Factorio 2.0 direction
-- (0, 4, 8, 12), mapped as place_entity maps it.
local function round_half(v)
    return math.floor(v * 2 + 0.5) / 2
end

local function vec(v)
    if not v then return nil end
    return {x = v.x or v[1] or 0, y = v.y or v[2] or 0}
end

-- Rotate a vector given for a north-facing entity to `dir`
local function rotate(v, dir)
    if dir == defines.direction.east then return {x = -v.y, y = v.x} end
    if dir == defines.direction.south then return {x = -v.x, y = -v.y} end
    if dir == defines.direction.west then return {x = v.y, y = -v.x} end
    return {x = v.x, y = v.y}
end

-- The belt or inventory entity at a point that an inserter can use (as the
-- observation's pickup_target / drop_target), else nil
local function target_at(surface, point)
    for _, e in pairs(surface.find_entities_filtered{position = point, limit = 5}) do
        if e.valid and e.type ~= "character" and (e.type == "transport-belt" or e.type == "underground-belt"
            or e.type == "splitter" or e.type == "loader" or e.type == "loader-1x1"
            or (e.get_max_inventory_index() or 0) > 0) then
            return e
        end
    end
    return nil
end

storage.actions.preview_inserter = function(player_index, entity, direction, x, y)
    local player = storage.agent_characters[player_index]
    local prototype = prototypes.entity[entity]
    if prototype == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error("\"" .. name .. " isn't a valid entity prototype. Did you make a typo?\"")
    end
    if prototype.type ~= "inserter" then
        error("\"" .. entity .. " is not an inserter\"")
    end

    local entity_direction = storage.utils.get_entity_direction(entity, direction or 0)
    -- a 1x1 entity is built at the centre of the tile
    local position = {x = math.floor(x) + 0.5, y = math.floor(y) + 0.5}
    local result = {position = position}
    for _, side in ipairs({"pickup", "drop"}) do
        local offset = vec(prototype["inserter_" .. side .. "_position"])
        if not offset then error("\"" .. entity .. " has no " .. side .. " position\"") end
        local r = rotate(offset, entity_direction)
        local point = {x = position.x + r.x, y = position.y + r.y}
        result[side .. "_position"] = {x = round_half(point.x), y = round_half(point.y)}
        local target = target_at(player.surface, point)
        if target then
            result[side .. "_target"] = "\"" .. target.name .. "\""
            result[side .. "_target_position"] = {x = target.position.x, y = target.position.y}
        end
    end
    return result
end
