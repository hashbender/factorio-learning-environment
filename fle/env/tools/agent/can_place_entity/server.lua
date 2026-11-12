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

-- Fluids next to a pipe-like entity the game refused with nothing in the way: the game does not build a
-- fluid entity that would connect two different fluids. nil, or text naming the fluids and where they are.
local MIX_TYPES = {["pipe"] = true, ["pipe-to-ground"] = true, ["storage-tank"] = true, ["pump"] = true}
local function fluid_mix(surface, prototype, left, top, right, bottom, direction)
    if not MIX_TYPES[prototype.type] then return nil end
    local seen, names = {}, {}
    local function add(other)
        if not (other.valid and other.fluidbox) then return end
        for i = 1, #other.fluidbox do
            local f = other.fluidbox[i]
            if f and f.name and not seen[f.name] then
                seen[f.name] = other.name .. " at (" .. other.position.x .. ", " .. other.position.y .. ")"
                table.insert(names, f.name)
            end
        end
    end
    -- the four sides (not the corners: fluid boxes never connect diagonally)
    local ring = {{left - 1 + 0.01, top - 1 + 0.01}, {right + 1 + 0.99, bottom + 1 + 0.99}}
    for _, other in pairs(surface.find_entities_filtered{area = ring}) do
        local p = other.position
        local beside_x = p.x >= left and p.x <= right + 1
        local beside_y = p.y >= top and p.y <= bottom + 1
        if beside_x or beside_y then add(other) end
    end
    -- a pipe-to-ground also connects underground along its axis
    if prototype.type == "pipe-to-ground" then
        local vertical = direction == defines.direction.north or direction == defines.direction.south
        local cx, cy = left + 0.5, top + 0.5
        local line = vertical and {{cx - 0.4, cy - 11}, {cx + 0.4, cy + 11}} or {{cx - 11, cy - 0.4}, {cx + 11, cy + 0.4}}
        for _, other in pairs(surface.find_entities_filtered{area = line, type = "pipe-to-ground"}) do add(other) end
    end
    if #names < 2 then return nil end
    local parts = {}
    for k, n in ipairs(names) do
        if k > 3 then break end
        table.insert(parts, n .. " (" .. seen[n] .. ")")
    end
    return "it would connect fluid boxes holding different fluids: " .. table.concat(parts, ", ")
        .. "; the game does not join two fluids"
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

    -- The map must exist there: a charted or generated chunk (FLE worlds have no connected
    -- player, so the game charts nothing around the character; place_blueprint's rule)
    for ty = top, bottom do
        for tx = left, right do
            local chunk = {x = math.floor(tx / 32), y = math.floor(ty / 32)}
            if not (player.force.is_chunk_charted(surface, chunk) or surface.is_chunk_generated(chunk)) then
                return finish(false, "tile (" .. tx .. ", " .. ty .. ") is in a part of the map that has not been generated or charted")
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
    -- The game lets an entity be built over one of the same name (it turns or replaces it,
    -- e.g. a belt over a belt facing another way); place_entity does not, it fails with
    -- "entity already exists at the target position".
    local same = nil
    if fits then
        local ok, found = pcall(surface.find_entities_filtered,
            {area = {{position.x - 0.4, position.y - 0.4}, {position.x + 0.4, position.y + 0.4}}, name = entity})
        for _, other in pairs(ok and found or {}) do
            if other.valid and other.name == entity then same = other; break end
        end
    end
    if fits and same then
        result.blocked_count = 1
        table.insert(result.blocked_by, {kind = quoted("entity"), name = quoted(same.name), x = same.position.x, y = same.position.y})
        return finish(false, entity .. " already stands at (" .. same.position.x .. ", " .. same.position.y
            .. "); place_entity does not build over an entity of the same name (it does not turn or replace it)")
    end
    -- Nor over another entity the game would let it replace (e.g. a belt over an underground belt)
    if fits then
        local own = mask_layers(prototype)
        local never_here = {["character"] = true, ["item-entity"] = true, ["corpse"] = true, ["character-corpse"] = true,
                            ["entity-ghost"] = true, ["tile-ghost"] = true, ["highlight-box"] = true,
                            ["flying-text"] = true, ["resource"] = true}
        local area = {{left + 0.01, top + 0.01}, {right + 0.99, bottom + 0.99}}
        local ok_f, found_here = pcall(surface.find_entities_filtered, {area = area})
        for _, other in pairs(ok_f and found_here or {}) do
            if other.valid and not never_here[other.type] and masks_collide(own, mask_layers(other.prototype)) then
                result.blocked_count = 1
                table.insert(result.blocked_by, {kind = quoted("entity"), name = quoted(other.name), x = other.position.x, y = other.position.y})
                local what = other.name
                if other.type == "underground-belt" then what = what .. " (" .. other.belt_to_ground_type .. ")" end
                return finish(false, what .. " stands at (" .. other.position.x .. ", " .. other.position.y
                    .. ") in its footprint; place_entity does not build over or replace another entity")
            end
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
    local mix = fluid_mix(surface, prototype, left, top, right, bottom, entity_direction)
    if mix then return finish(false, "the game does not allow " .. entity .. " at this position: " .. mix) end
    return finish(false, "the game does not allow " .. entity .. " at this position; no colliding entity or tile was found")
end
