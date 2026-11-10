storage.actions.inspect_inventory = function(player_index, is_character_inventory, x, y, entity, all_players)
    local position = {x=x, y=y}
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface
    local is_fast = storage.fast
    local automatic_close = True

    local function get_player_inventory_items(player)

       local inventory = player.get_main_inventory()
       if not inventory or not inventory.valid then
           return nil
       end

       local item_counts = storage.utils.get_contents_compat(inventory)
       return item_counts
    end

    local function get_inventory()
       local closest_distance = math.huge
       local closest_entity = nil

       local area = {{position.x - 2, position.y - 2}, {position.x + 2, position.y + 2}}
       local buildings
       if entity and entity ~= "" then
           buildings = surface.find_entities_filtered({ area = area, force = "player", name = entity })
       else
           buildings = surface.find_entities_filtered({ area = area, force = "player" })
       end
       local what = (entity and entity ~= "") and entity or "entity"
       local where = "(" .. position.x .. ", " .. position.y .. ")"
       -- game.print("Found "..#buildings.. " "..entity)
       for _, building in ipairs(buildings) do
           -- with only a position, take the nearest entity that has an inventory
           if building.name ~= 'character' and (what ~= "entity" or building.get_max_inventory_index() > 0) then
               local distance = ((position.x - building.position.x) ^ 2 + (position.y - building.position.y) ^ 2) ^ 0.5
               if distance < closest_distance then
                   closest_distance = distance
                   closest_entity = building
               end
           end
       end
       
       if closest_entity == nil then
           error("\"No " .. what .. " within 2 tiles of " .. where .. "\"")
       end
       if not closest_entity or not closest_entity.valid then
           error("\"The " .. what .. " near " .. where .. " is no longer valid\"")
       end

       if not is_fast then
           player.opened = closest_entity
           script.on_nth_tick(60, function()
               if automatic_close == True then
                   if closest_entity and closest_entity.valid then
                       player.opened = nil
                   end
                   automatic_close = False
               end
           end)
       end

       -- Factorio 2.0: unified crafter_input/crafter_output for furnaces, assemblers, rocket silos
       if closest_entity.type == "furnace" or closest_entity.type == "assembling-machine" or closest_entity.type == "rocket-silo" then
           if not closest_entity or not closest_entity.valid then
               error("\"The " .. what .. " near " .. where .. " is no longer valid\"")
           end
           local source = storage.utils.get_contents_compat(closest_entity.get_inventory(defines.inventory.crafter_input))
           local output = storage.utils.get_contents_compat(closest_entity.get_inventory(defines.inventory.crafter_output))
           for k, v in pairs(output) do
               source[k] = (source[k] or 0) + v
           end
           -- a burner furnace's fuel is part of what it holds
           local fuel = storage.utils.get_contents_compat(closest_entity.get_fuel_inventory())
           for k, v in pairs(fuel) do
               source[k] = (source[k] or 0) + v
           end
           return source
       end
       if closest_entity.type == "lab" then
           if not closest_entity or not closest_entity.valid then
               error("\"The " .. what .. " near " .. where .. " is no longer valid\"")
           end
           return storage.utils.get_contents_compat(closest_entity.get_inventory(defines.inventory.lab_input))
       end
       -- Note: centrifuge is now handled by the unified assembling-machine block above
       if not closest_entity or not closest_entity.valid then
           error("\"The " .. what .. " near " .. where .. " is no longer valid\"")
       end
       return storage.utils.get_contents_compat(closest_entity.get_inventory(defines.inventory.chest))
    end

    local player = storage.agent_characters[player_index]
    if not player then
       error("Player not found")
    end

    if all_players then
        local all_inventories = {}
        for _, p in pairs(storage.agent_characters) do
            local inventory_items = get_player_inventory_items(p)
            if inventory_items then
                table.insert(all_inventories, inventory_items)
            else
                table.insert(all_inventories, {})
            end
        end
        return dump(all_inventories)
    end

    if is_character_inventory then
       local inventory_items = get_player_inventory_items(player)
       if inventory_items then
           return dump(inventory_items)
       else
           error("Could not get player inventory")
       end
    else
       local inventory_items = get_inventory()
       if inventory_items then
           return dump(inventory_items)
       else
           error("Could not get inventory of entity at "..x..", "..y)
       end
    end
end