-- Function to check if an item is a module
local function is_module(item_name)
    local item_proto = prototypes.item[item_name]
    return item_proto and item_proto.type == "module"
end

-- How full the inventory is that the item would go into, e.g. "(input 100/100 items)"
local function get_inventory_info(entity, item_name)
    local inv, label
    local is_fuel = prototypes.item[item_name] and prototypes.item[item_name].fuel_value > 0
    if entity.type == "container" or entity.type == "logistic-container" then
        inv, label = entity.get_inventory(defines.inventory.chest), "chest"
    elseif entity.type == "lab" then
        inv, label = entity.get_inventory(defines.inventory.lab_input), "input"
    elseif entity.burner and is_fuel then
        inv, label = entity.get_fuel_inventory(), "fuel"
    elseif entity.type == "furnace" or entity.type == "assembling-machine" then
        inv, label = entity.get_inventory(defines.inventory.crafter_input), "input"
    end
    if not inv then
        return ""
    end
    local item_count, free_slots = 0, 0
    for i = 1, #inv do
        local stack = inv[i]
        if stack.valid_for_read then
            item_count = item_count + stack.count
        else
            free_slots = free_slots + 1
        end
    end
    return string.format("(%s inventory: %d items, %d of %d slots free)", label, item_count, free_slots, #inv)
end

-- Durability of one item of a tool (e.g. a science pack), or nil for other items
local function tool_max_durability(item_name)
    local prototype = prototypes.item[item_name]
    if prototype and prototype.type == "tool" then
        return prototype.get_durability()
    end
    return nil
end

-- Total durability of an item in an inventory: full items plus the part-used top item of each stack
local function inventory_durability(inventory, item_name, max_durability)
    local total = 0
    if not inventory then
        return 0
    end
    for slot = 1, #inventory do
        local stack = inventory[slot]
        if stack.valid_for_read and stack.name == item_name then
            total = total + (stack.count - 1) * max_durability + stack.durability
        end
    end
    return total
end

local function entity_durability(entity, item_name, max_durability)
    local total = 0
    for index = 1, entity.get_max_inventory_index() do
        total = total + inventory_durability(entity.get_inventory(index), item_name, max_durability)
    end
    return total
end

local function drain_entity_durability(entity, item_name, amount)
    for index = 1, entity.get_max_inventory_index() do
        local inventory = entity.get_inventory(index)
        if inventory then
            for slot = 1, #inventory do
                if amount <= 1e-9 then
                    return
                end
                local stack = inventory[slot]
                if stack.valid_for_read and stack.name == item_name then
                    local available = (stack.count - 1) * stack.prototype.get_durability() + stack.durability
                    local drained = math.min(amount, available)
                    stack.drain_durability(drained)
                    amount = amount - drained
                end
            end
        end
    end
end

storage.actions.insert_item = function(player_index, insert_item, count, x, y, target_name)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)
    local position = {x=x, y=y}
    local surface = player.surface

    if count <= 0 then
        error("\"Invalid count " .. tostring(count) .. ": the quantity must be greater than 0\"")
    end

    -- Check if player has enough items
    local item_count = player.get_item_count(insert_item)
    if item_count == 0 then
        error('\"No '..insert_item..' to insert from your inventory\"')
    end

    local closest_distance = math.huge
    local closest_entity = nil
    local area = {{position.x - 1, position.y - 1}, {position.x + 1, position.y + 1}}
    local buildings = nil

    if target_name then
        buildings = surface.find_entities_filtered{area = area, name=target_name}
    else
        buildings = surface.find_entities_filtered{area = area}
    end

    -- Function to get inventory fullness information
    --local function get_inventory_info(entity)
    --    if entity.get_inventory then
    --        local inv = entity.get_inventory(defines.inventory.chest)
    --        if inv then
    --            return string.format("(%d/%d)", #inv, #inv.get_bar())
    --        end
    --    end
    --    return ""
    --end

    local function fmt_pos(p)
        return string.format("(%s, %s)", p.x, p.y)
    end

    -- Can the item go into this entity? Returns ok, plus the reason when not.
    local function can_insert_item(entity, item_name)
        local item_prototype = prototypes.item[item_name]
        if not item_prototype then
            return false, item_name .. " is not an item"
        end
        if entity.type == "transport-belt" then
            -- All items that can be on ground can be on belts
            if item_prototype.has_flag("only-in-cursor") then
                return false, item_name .. " cannot be put on a belt"
            end
            return true
        elseif entity.type == "lab" then
            if item_prototype.type == "tool" then
                return true
            end
            return false, "a lab takes only science packs"
        elseif entity.type == "assembling-machine" then
            if is_module(item_name) then
                local module_inv = entity.get_module_inventory()
                if not module_inv or #module_inv == 0 then
                    return false, "it has no module slots"
                end
                if module_inv.is_full() then
                    return false, "its module slots are full"
                end
                return true
            end
            local recipe = entity.get_recipe()
            if not recipe then
                return false, "it has no recipe set"
            end
            for _, ingredient in pairs(recipe.ingredients) do
                if ingredient.name == item_name then
                    return true
                end
            end
            for _, product in pairs(recipe.products) do
                if product.name == item_name then
                    return true
                end
            end
            local names = {}
            for _, ingredient in pairs(recipe.ingredients) do
                table.insert(names, ingredient.name)
            end
            return false, item_name .. " is not an ingredient or product of its recipe " .. recipe.name ..
                " (ingredients: " .. table.concat(names, ", ") .. ")"
        elseif entity.type == "furnace" then
            if item_prototype.fuel_value > 0 then
                return true
            end
            -- Check furnace inventory for incompatible items (Factorio 2.0: crafter_input)
            local inventory = entity.get_inventory(defines.inventory.crafter_input)
            if inventory and not inventory.is_empty() then
                for i = 1, #inventory do
                    local stack = inventory[i]
                    if stack.valid_for_read and stack.name ~= item_name then
                        return false, "it already contains " .. stack.name .. " in its input slot"
                    end
                end
            end
            for _, recipe in pairs(prototypes.recipe) do
                if recipe.category == "smelting" then
                    for _, ingredient in pairs(recipe.ingredients) do
                        if ingredient.name == item_name then
                            return true
                        end
                    end
                end
            end
            return false, item_name .. " is neither a fuel nor a smelting ingredient"
        elseif entity.burner then
            if item_prototype.fuel_value > 0 then
                return true
            end
            return false, "it takes only fuel, and " .. item_name .. " is not a fuel"
        elseif entity.type == "container" or entity.type == "logistic-container" then
            return true  -- Containers can accept any item
        elseif entity.type == "beacon" then
            if not is_module(item_name) then
                return false, "a beacon takes only modules"
            end
            local module_inv = entity.get_module_inventory()
            if module_inv and module_inv.is_full() then
                return false, "its module slots are full"
            end
            return true
        end
        if entity.get_max_inventory_index() == 0 and entity.type ~= "transport-belt" then
            return false, "it has no inventory"
        end
        return true
    end

    -- Find the closest suitable building, and remember why the others were refused
    local refused = {}
    for _, building in ipairs(buildings) do
        if building.name ~= 'character' then
            local ok, reason = can_insert_item(building, insert_item)
            if ok then
                local distance = ((position.x - building.position.x) ^ 2 + (position.y - building.position.y) ^ 2) ^ 0.5
                if distance < closest_distance then
                    closest_distance = distance
                    closest_entity = building
                end
            elseif #refused < 3 then
                table.insert(refused, building.name .. " at " .. fmt_pos(building.position) .. ": " .. (reason or "it does not accept " .. insert_item))
            end
        end
    end

    if closest_entity == nil then
        local where = fmt_pos(position)
        if #refused > 0 then
            error("\"Cannot insert " .. insert_item .. " into " .. table.concat(refused, "; ") .. "\"")
        end
        if target_name then
            error("\"No " .. target_name .. " within 1 tile of " .. where .. "\"")
        end
        error("\"No entity within 1 tile of " .. where .. " to insert " .. insert_item .. " into\"")
    end

    -- Throw an error if the entity is out of the character's reach
    if not player.can_reach_entity(closest_entity) then
        error("\"Entity at ("..closest_entity.position.x..", "..closest_entity.position.y..") is too far away from your position of ("..player.position.x..", "..player.position.y.."), move closer.\"")
    end

    -- Function to insert items onto a transport belt - one at a time
    local function insert_on_belt(belt, item_name)
        local line1 = belt.get_transport_line(1)
        local line2 = belt.get_transport_line(2)

        -- Try first line
        if line1.can_insert_at_back() then
            if line1.insert_at_back({name = item_name, count = 1}) then
                return 1
            end
        end

        -- If first line failed, try second line
        if line2.can_insert_at_back() then
            if line2.insert_at_back({name = item_name, count = 1}) then
                return 1
            end
        end

        return 0  -- Could not insert on either line
    end

    -- Determine how many items can be inserted
    local insertable_count = math.min(count, item_count)

    -- Science packs are tools: the top item of a stack may be part-used. Insert
    -- adds full items and remove_item takes items by count, so measure the total
    -- durability on both sides to carry part-used packs over as they are.
    local max_durability = tool_max_durability(insert_item)
    local player_durability_before, entity_durability_before
    if max_durability then
        player_durability_before = inventory_durability(player.get_main_inventory(), insert_item, max_durability)
        entity_durability_before = entity_durability(closest_entity, insert_item, max_durability)
    end

   -- Attempt to insert items
    local inserted = 0
    if closest_entity.type == "transport-belt" then
        -- For transport belts, we need to use a different method
        -- game.print("Inserting ".. insertable_count.. " items onto transport belt...")
        inserted = insert_on_belt(closest_entity, insert_item)
    elseif closest_entity.type == "assembling-machine" then
        -- Check if inserting a module
        if is_module(insert_item) then
            local module_inv = closest_entity.get_module_inventory()
            if module_inv then
                inserted = module_inv.insert({name=insert_item, count=insertable_count})
            else
                error("\"Assembling machine does not support modules\"")
            end
        else
            local recipe = closest_entity.get_recipe()
            if recipe then
                local is_product = false
                for _, product in pairs(recipe.products) do
                    if product.name == insert_item then
                        is_product = true
                        break
                    end
                end

                if is_product then
                    -- Insert into output inventory
                    inserted = closest_entity.get_output_inventory().insert({name=insert_item, count=insertable_count})
                else
                    -- Insert into input inventory (Factorio 2.0: crafter_input)
                    inserted = closest_entity.get_inventory(defines.inventory.crafter_input).insert({name=insert_item, count=insertable_count})
                end
            else
                error("No recipe set for the assembling machine.")
            end
        end
    elseif closest_entity.type == "beacon" then
        -- Beacons only accept modules
        if is_module(insert_item) then
            local module_inv = closest_entity.get_module_inventory()
            if module_inv then
                inserted = module_inv.insert({name=insert_item, count=insertable_count})
            else
                error("\"Beacon does not have a module inventory\"")
            end
        else
            error("\"Beacons can only accept modules\"")
        end
    else
        -- For other entities, use the normal insert method
        inserted = closest_entity.insert{name=insert_item, count=insertable_count}
    end

    -- game.print("Inserted " .. inserted .. " items.")
    if inserted > 0 then
        -- Only remove successfully inserted items from player
        player.remove_item{name=insert_item, count=inserted}
        if max_durability then
            -- The entity gained full items; take back what the character's
            -- part-used items didn't have
            local lost = player_durability_before - inventory_durability(player.get_main_inventory(), insert_item, max_durability)
            local gained = entity_durability(closest_entity, insert_item, max_durability) - entity_durability_before
            drain_entity_durability(closest_entity, insert_item, gained - lost)
        end
        -- game.print("Successfully inserted " .. inserted .. " items.")
        return storage.utils.serialize_entity(closest_entity)
    else
        local reason
        if closest_entity.type == "transport-belt" then
            reason = "both lanes are full at the belt's input end"
        else
            local inventory_info = get_inventory_info(closest_entity, insert_item)
            if inventory_info ~= "" then
                reason = "no room for " .. insert_item .. " " .. inventory_info
            else
                reason = "the game accepted 0 of them"
            end
        end
        local error_msg = string.format(
            "\"Failed to insert %s into %s at %s (tried %d): %s\"",
            insert_item,
            closest_entity.name,
            fmt_pos(closest_entity.position),
            insertable_count,
            reason
        )
        error(error_msg)
    end
end