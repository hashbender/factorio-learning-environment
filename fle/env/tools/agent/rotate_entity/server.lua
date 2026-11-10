storage.actions.rotate_entity = function(player_index, x, y, direction, entity, check_reach)
    local character = storage.agent_characters[player_index]
    local lua_player = game.players[player_index]  -- Get the actual LuaPlayer object
    local position = {x=x, y=y}
    local surface = character.surface

    local function table_contains(tbl, element)
        for _, value in ipairs(tbl) do
            if value == element then
                return true
            end
        end
        return false
    end

    local closest_distance = math.huge
    local closest_entity = nil
    local area = {{position.x - 0.5, position.y - 0.5}, {position.x + 0.5, position.y + 0.5}}
    local buildings = surface.find_entities_filtered{area = area, force = "player", name=entity}

    -- Find the closest building (skip rotatable check for assemblers, handled below)
    for _, building in ipairs(buildings) do
        if building.name ~= 'character' then
            local distance = ((position.x - building.position.x) ^ 2 + (position.y - building.position.y) ^ 2) ^ 0.5
            if distance < closest_distance then
                closest_distance = distance
                closest_entity = building
            end
        end
    end

    if closest_entity == nil then
        error("No entity to rotate at the given coordinates.")
    end

    -- A player can only rotate an entity within reach
    if check_reach ~= false and not character.can_reach_entity(closest_entity) then
        error("Entity at ("..closest_entity.position.x..", "..closest_entity.position.y..") is too far away from your position of ("..character.position.x..", "..character.position.y.."), move closer.")
    end

    -- Factorio 2.0 uses 16-direction system: 0 (north), 4 (east), 8 (south), 12 (west)
    local valid_directions = {0, 4, 8, 12}

    if not table_contains(valid_directions, direction) then
        error("Invalid direction " .. direction .. " provided. Please use 0 (north), 4 (east), 8 (south), or 12 (west).")
    end

    local target_direction = storage.utils.get_entity_direction(closest_entity.name, direction)

    -- Crafting machines (assembling machines, chemical plants, refineries): set the
    -- direction in place, as a player's rotate does, so the recipe, items, fluids and
    -- crafting progress stay. In Factorio 2.0 a machine without fluid boxes
    -- (assembling-machine-1, centrifuge) never takes a direction, and assembling
    -- machines 2 and 3 only take one while their recipe uses a fluid
    -- (fluid_boxes_off_when_no_fluid_recipe).
    if closest_entity.type == "assembling-machine" then
        if closest_entity.direction ~= target_direction then
            closest_entity.direction = target_direction
        end
        if closest_entity.direction ~= target_direction then
            local recipe = closest_entity.get_recipe()
            if #closest_entity.prototype.fluidbox_prototypes == 0 then
                error("Cannot rotate " .. closest_entity.name .. ": it has no fluid connections, so it always faces north.")
            elseif recipe then
                error("Cannot rotate " .. closest_entity.name .. ": its fluid connections are off because its recipe " .. recipe.name .. " uses no fluid. It takes a direction only while its recipe uses a fluid.")
            else
                error("Cannot rotate " .. closest_entity.name .. ": its fluid connections are off while it has no recipe. It takes a direction only while its recipe uses a fluid.")
            end
        end
    else
        -- For other entities, try direct assignment first (works for most entities)
        closest_entity.direction = target_direction

        -- If direction didn't change, try using the rotate() method
        if closest_entity.direction ~= target_direction then
            local current = closest_entity.direction
            local target = target_direction
            local rotations_needed = ((target - current + 16) % 16) / 4

            for i = 1, rotations_needed do
                if closest_entity.rotate then
                    closest_entity.rotate()
                end
            end
        end
    end

    -- Ensure the entity is properly aligned to the grid
    local entity_position = closest_entity.position
    local aligned_position = {
        x = math.floor(entity_position.x),
        y = math.floor(entity_position.y)
    }

    if entity_position.x ~= aligned_position.x or entity_position.y ~= aligned_position.y then
        closest_entity.teleport(aligned_position)
    end

    local serialized = storage.utils.serialize_entity(closest_entity)
    return serialized
end