-- Give the items LuaEntity.set_recipe removed from a machine to the character.
-- Factorio 2.0 returns an array of {name, count, quality}; 1.1 returned {name = count}.
-- Whatever doesn't fit in the character's inventory is spilled at its feet.
local function return_removed_items(player, removed)
    if type(removed) ~= "table" then return end
    for key, value in pairs(removed) do
        local stack
        if type(value) == "table" then
            stack = {name = value.name, count = value.count, quality = value.quality}
        else
            stack = {name = key, count = value}
        end
        if stack.name and stack.count and stack.count > 0 then
            local inserted = player.insert(stack)
            if inserted < stack.count then
                stack.count = stack.count - inserted
                player.surface.spill_item_stack{
                    position = player.position,
                    stack = stack,
                    enable_looted = true,
                    force = player.force,
                }
            end
        end
    end
end

storage.actions.set_entity_recipe = function(player_index, recipe_name, x, y)
    local player = storage.agent_characters[player_index]
    local surface = player.surface
    --local position = player.position
    local closest_distance = math.huge
    local closest_building = nil

    -- Iterate through all crafting machines in the area
    local area = {{x - 1, y - 1}, {x + 1, y + 1}}
    local buildings = surface.find_entities_filtered{area = area, type = {"assembling-machine", "inserter"}}

    -- Find the closest building
    for _, building in ipairs(buildings) do
        local distance = ((x - building.position.x) ^ 2 + (y - building.position.y) ^ 2) ^ 0.5
        if distance < closest_distance then
            closest_distance = distance
            closest_building = building
        end
    end

    -- If a closest building is found, handle based on its type
    if closest_building then
        local serialized

        -- A player can only set a recipe or filter on an entity within reach
        if not player.can_reach_entity(closest_building) then
            error("Entity at ("..closest_building.position.x..", "..closest_building.position.y..") is too far away from your position of ("..player.position.x..", "..player.position.y.."), move closer.")
        end

        -- Handle different entity types
        if closest_building.type == "inserter" then
            -- Factorio 2.0: all inserters can filter, enable filtering and set the filter
            closest_building.use_filters = true
            closest_building.set_filter(1, recipe_name)  -- Set first filter slot
            serialized = storage.utils.serialize_entity(closest_building)
        else
            -- Original assembling machine logic
            local recipe = player.force.recipes[recipe_name]
            if recipe and closest_building.get_recipe() ~= recipe then
                local removed = closest_building.set_recipe(recipe_name)
                -- Like a player changing the recipe in the GUI: the ingredients and
                -- products taken out of the machine go to the character, and what
                -- doesn't fit is spilled on the ground at the character
                return_removed_items(player, removed)
            end
            serialized = storage.utils.serialize_entity(closest_building)
        end

        local entity_json = helpers.table_to_json(serialized)
        -- game.print(entity_json)
        return serialized
    else
        error("No building found that could have its recipe or filter set.")
    end
end

