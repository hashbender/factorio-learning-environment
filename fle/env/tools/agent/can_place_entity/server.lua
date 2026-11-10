-- Would the game let this entity be built at this position and direction?
-- The answer is the game's own build check (the one place_entity uses), with what
-- is in the way when it says no. Builds nothing, needs no item in the inventory,
-- takes no game time and leaves the character where it is.
-- `direction` is a Factorio 2.0 direction (0, 4, 8, 12), mapped as place_entity maps it.
local MAX_LISTED = 5

local function quoted(s)
    return "\"" .. tostring(s) .. "\""
end

-- Where the game puts the centre of an entity `size` tiles wide asked for at `v`
local function snap(v, size)
    if size % 2 == 1 then
        return math.floor(v) + 0.5
    end
    return math.floor(v + 0.5)
end

local function mask_layers(prototype)
    local ok, layers = pcall(function() return prototype.collision_mask.layers end)
    if ok and type(layers) == "table" then return layers end
    return nil
end

local function masks_collide(a, b)
    if not a or not b then return true end
    for layer in pairs(a) do
        if b[layer] then return true end
    end
    return false
end

storage.actions.can_place_entity = function(player_index, entity, direction, x, y)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface

    -- The item and the entity it builds usually share a name, but not always
    local item_name = entity
    if prototypes.entity[entity] == nil then
        local item = prototypes.item and prototypes.item[entity]
        if item and item.place_result then
            entity = item.place_result.name
        end
    end
    local prototype = prototypes.entity[entity]
    if prototype == nil then
        local name = entity:gsub(" ", "_"):gsub("-", "_")
        error(quoted(name .. " isn't a valid entity prototype. Did you make a typo?"))
    end

    local entity_direction = storage.utils.get_entity_direction(entity, direction or 0)
    local turned = entity_direction == defines.direction.east or entity_direction == defines.direction.west

    -- Footprint in tiles, turned for an east or west facing entity
    local box = prototype.collision_box
    local tile_w = prototype.tile_width or math.ceil(math.abs(box.right_bottom.x - box.left_top.x))
    local tile_h = prototype.tile_height or math.ceil(math.abs(box.right_bottom.y - box.left_top.y))
    if turned then tile_w, tile_h = tile_h, tile_w end
    local position = {x = snap(x, tile_w), y = snap(y, tile_h)}
    local left, top = math.floor(position.x - tile_w / 2 + 0.01), math.floor(position.y - tile_h / 2 + 0.01)
    local right, bottom = left + tile_w - 1, top + tile_h - 1

    local result = {
        position = position,
        footprint = {left = left, top = top, right = right, bottom = bottom},
        blocked_by = {},
        blocked_count = 0,
    }

    -- Reach and inventory: what place_entity also requires
    local dx, dy = player.position.x - x, player.position.y - y
    local distance = math.sqrt(dx * dx + dy * dy)
    local reach = player.reach_distance or player.build_distance
    result.distance = math.floor(distance * 100 + 0.5) / 100
    result.reach = reach
    result.in_reach = distance <= reach
    result.in_inventory = player.get_item_count(item_name)

    local function finish(fits, reason)
        result.fits = fits
        if reason then result.reason = quoted(reason) end
        result.can_place = fits and result.in_reach and result.in_inventory > 0
        return result
    end

    -- Charted, like the in-game map: nothing is known about an uncharted chunk
    for ty = top, bottom do
        for tx = left, right do
            local chunk = {x = math.floor(tx / 32), y = math.floor(ty / 32)}
            if not player.force.is_chunk_charted(surface, chunk) then
                return finish(false, "tile (" .. tx .. ", " .. ty .. ") is outside the charted map")
            end
        end
    end

    -- The game's build check. place_entity moves the character out of the way of
    -- what it builds, so when the character stands in the footprint the check is
    -- made with it stepped aside, and it is put back.
    local function game_check()
        return storage.utils.can_place_entity(player, entity, position, entity_direction) and true or false
    end
    local fits = game_check()
    if not fits then
        local p = player.position
        if p.x > left - 1 and p.x < right + 2 and p.y > top - 1 and p.y < bottom + 2 then
            local home = {x = p.x, y = p.y}
            player.teleport({x = right + 3.5, y = bottom + 3.5})
            local ok, answer = pcall(game_check)
            player.teleport(home)
            if not ok then error(answer) end
            fits = answer
        end
    end
    if fits then
        return finish(true, nil)
    end

    -- What is in the way: entities and tiles the entity's collision mask collides with
    local own_layers = mask_layers(prototype)
    local function add(kind, name, bx, by)
        result.blocked_count = result.blocked_count + 1
        if #result.blocked_by < MAX_LISTED then
            table.insert(result.blocked_by, {kind = quoted(kind), name = quoted(name), x = bx, y = by})
        end
    end
    local area = {{left + 0.01, top + 0.01}, {right + 0.99, bottom + 0.99}}
    local never = {["character"] = true, ["item-entity"] = true, ["corpse"] = true, ["character-corpse"] = true,
                   ["entity-ghost"] = true, ["tile-ghost"] = true, ["highlight-box"] = true,
                   ["flying-text"] = true, ["resource"] = true}
    for _, other in pairs(surface.find_entities_filtered{area = area}) do
        if other.valid and not never[other.type] and masks_collide(own_layers, mask_layers(other.prototype)) then
            add("entity", other.name, other.position.x, other.position.y)
        end
    end
    for ty = top, bottom do
        for tx = left, right do
            local tile = surface.get_tile(tx, ty)
            if tile and tile.valid then
                local collides = false
                if own_layers then
                    for layer in pairs(own_layers) do
                        local ok, hit = pcall(tile.collides_with, layer)
                        if ok and hit then collides = true; break end
                    end
                else
                    collides = string.find(tile.name, "water", 1, true) ~= nil
                end
                if collides then add("tile", tile.name, tx, ty) end
            end
        end
    end

    if result.blocked_count > 0 then
        local parts = {}
        for _, b in ipairs(result.blocked_by) do
            table.insert(parts, string.sub(b.name, 2, -2) .. " at (" .. b.x .. ", " .. b.y .. ")")
        end
        local more = result.blocked_count - #result.blocked_by
        local text = "blocked by " .. table.concat(parts, ", ")
        if more > 0 then text = text .. " and " .. more .. " more" end
        return finish(false, text)
    end

    -- Nothing collides: the entity has a placement rule of its own
    if prototype.type == "mining-drill" then
        local names = {}
        for name, resource in pairs(prototypes.entity) do
            if resource.type == "resource" and prototype.resource_categories
                and prototype.resource_categories[resource.resource_category] then
                table.insert(names, name)
            end
        end
        table.sort(names)
        return finish(false, entity .. " must be placed on a resource it can mine ("
            .. table.concat(names, ", ") .. "); there is none under this position")
    end
    if prototype.type == "offshore-pump" then
        return finish(false, entity .. " must be placed at the edge of water, facing the water")
    end
    return finish(false, "the game does not allow " .. entity .. " at this position; no colliding entity or tile was found")
end
