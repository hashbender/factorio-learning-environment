storage.actions.set_entity_recipe = function(player_index, recipe_name, x, y)
    local player = storage.agent_characters[player_index]
    local surface = player.surface
    --local position = player.position
    local closest_distance = math.huge
    local closest_building = nil

    -- Iterate through all crafting machines in the area
    local area = {{x - 1, y - 1}, {x + 1, y + 1}}
    local buildings = surface.find_entities_filtered{area = area, type = {"assembling-machine", "inserter"}}

    -- The entity on the given position comes first: a chest next to an
    -- inserter must not set the inserter's filter
    for _, here in ipairs(surface.find_entities_filtered{position = {x, y}}) do
        if here.type == "assembling-machine" or here.type == "inserter" then
            buildings = {here}
            break
        elseif here.type ~= "character" and here.type ~= "resource" and here.type ~= "item-entity" then
            error("\"" .. here.name .. " at (" .. here.position.x .. ", " .. here.position.y ..
                ") has no recipe or filter to set (only assembling machines and inserters do)\"")
        end
    end

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
            -- Assembling machine: the same checks as the recipe picker in the game
            local recipe = player.force.recipes[recipe_name]
            local where = closest_building.name .. " at (" .. closest_building.position.x .. ", " .. closest_building.position.y .. ")"
            if not recipe then
                error("\"There is no recipe called " .. recipe_name .. "\"")
            end
            if not recipe.enabled then
                error("\"Recipe " .. recipe_name .. " is not unlocked yet (research needed)\"")
            end
            if not closest_building.prototype.crafting_categories[recipe.category] then
                local categories = {}
                for category in pairs(closest_building.prototype.crafting_categories) do
                    table.insert(categories, category)
                end
                table.sort(categories)
                error("\"" .. where .. " cannot craft " .. recipe_name .. " (recipe category " .. recipe.category ..
                    "; it crafts: " .. table.concat(categories, ", ") .. ")\"")
            end
            local current = closest_building.get_recipe()
            if not (current and current.name == recipe_name) then
                closest_building.set_recipe(recipe_name)
            end
            serialized = storage.utils.serialize_entity(closest_building)
        end

        local entity_json = helpers.table_to_json(serialized)
        -- game.print(entity_json)
        return serialized
    else
        local others = {}
        for _, e in ipairs(surface.find_entities_filtered{area = area}) do
            if e.type ~= "character" and #others < 3 then
                table.insert(others, e.name)
            end
        end
        local found = #others > 0 and (" (found: " .. table.concat(others, ", ") .. ")") or ""
        error("\"No assembling machine or inserter within 1 tile of (" .. x .. ", " .. y .. ")" .. found .. "\"")
    end
end

