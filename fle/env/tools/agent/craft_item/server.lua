storage.actions.craft_item = function(player_index, entity, count)
    -- Ensure we have a valid character, recreating if necessary
    local player = storage.utils.ensure_valid_character(player_index)

    local function calculate_crafting_ticks(recipe, crafts_count)
        -- energy_required is in seconds, multiply by 60 to get standard ticks
        -- storage.elapsed_ticks should always represent standard 60 ticks/second
        local ticks_per_craft = (recipe.energy or 0.5) * 60
        return math.ceil(ticks_per_craft * crafts_count)
    end

    local function check_inventory_space(player, item_name, count)
        -- Get the prototype of the item
        local item_prototype = prototypes.item[item_name]
        if not item_prototype then
            return false, "Invalid item prototype"
        end

        -- Calculate how many slots this would need
        local stack_size = item_prototype.stack_size
        local slots_needed = math.ceil(count / stack_size)

        -- Check if player has enough free inventory slots
        local inventory = player.get_main_inventory()
        if not inventory then
            return false, "Cannot access player inventory"
        end

        -- Count free slots and partially filled slots of the same item
        local available_slots = 0
        for i = 1, #inventory do
            local stack = inventory[i]
            if not stack.valid_for_read then
                -- Empty slot
                available_slots = available_slots + 1
            elseif stack.name == item_name and stack.count < stack_size then
                -- Partially filled slot of the same item
                available_slots = available_slots + 1
            end
        end

        if available_slots < slots_needed then
            return false, "Inventory is full - requires " .. slots_needed .. " slots but only " .. available_slots .. " available"
        end

        return true
    end


    local function get_missing_ingredients(player, recipe, count)
        local missing_ingredients = {}
        local crafts_needed = math.ceil(count / recipe.products[1].amount)
        for _, ingredient in pairs(recipe.ingredients) do
            local count_that_player_has = player.get_item_count(ingredient.name)
            local needed = ingredient.amount * crafts_needed
            if count_that_player_has < needed then
                local difference = needed - count_that_player_has
                missing_ingredients[ingredient.name] = difference
            end
        end
        return missing_ingredients
    end

    local function get_required_technology(recipe_name, force)
        for _, tech in pairs(force.technologies) do
            -- Factorio 2.0: effects are on the technology prototype
            local effects = tech.prototype and tech.prototype.effects
            if effects then
                for _, effect in pairs(effects) do
                    if effect.type == "unlock-recipe" and effect.recipe == recipe_name then
                        return tech.name
                    end
                end
            end
        end
        return nil
    end

    local function can_craft_recipe(player, recipe_name)
        local recipe = player.force.recipes[recipe_name]
        if not recipe then
            return false, "recipe for " .. recipe_name .. " doesn't exist, it is a raw resource that must be gathered first"
        end
        if not recipe.enabled then
            local required_tech = get_required_technology(recipe_name, player.force)
            local tech_message = required_tech and string.format(" (requires %s technology)", required_tech) or ""
            return false, "recipe for " .. recipe_name .. " is not unlocked yet" .. tech_message .. ". You need to research the technology first"
        end
        -- Factorio 2.0: Check if the recipe category is one the character can craft
        -- Note: 'player' here is actually the character entity (returned by ensure_valid_character)
        local can_hand_craft = false
        local proto = player.prototype
        if proto then
            local cats = proto.crafting_categories
            if cats then
                can_hand_craft = cats[recipe.category] or false
            else
                -- Character prototype exists but has no crafting_categories
                -- Fallback: allow "crafting" category only
                can_hand_craft = (recipe.category == "crafting")
            end
        else
            -- No prototype - fallback
            can_hand_craft = (recipe.category == "crafting")
        end
        if not can_hand_craft then
            return false, "Item " .. recipe_name .. " cannot be crafted (category: " .. tostring(recipe.category) .. "). Recipe requires a crafting machine or smelting in a furnace"
        end
        return true, recipe
    end

    local function update_production_stats(force, recipe, crafts_count)
        -- Factorio 2.0: production_statistics is now a method requiring surface parameter
        local surface = game.surfaces[1]
        local stats = force.get_item_production_statistics(surface)
        local craft_stats = {crafted_count = crafts_count, inputs = {}, outputs = {}}
        for _, ingredient in pairs(recipe.ingredients) do
            craft_stats.inputs[ingredient.name] = ingredient.amount * crafts_count
            stats.on_flow(ingredient.name, -ingredient.amount * crafts_count)
        end
        for _, product in pairs(recipe.products) do
            if product.type == "item" then
                stats.on_flow(product.name, product.amount * crafts_count)
                craft_stats.outputs[product.name] = product.amount * crafts_count
            end
        end
        table.insert(storage.crafted_items, craft_stats)
    end

    -- Plan the whole recipe tree before crafting anything. Every intermediate is counted once across the tree:
    -- what you already hold is used first, and an intermediate crafted for one branch (or the extra copper cable of
    -- an odd count) is available to the next branch. So crafting a lab makes the gears the belts need as well as
    -- the gears the lab needs. If anything that can't be hand-crafted is short, the result lists the total still
    -- needed of each such item and nothing is crafted.
    local MAX_PLAN_STEPS = 500

    local function plan_craft(player, recipe, crafts)
        local avail = {}          -- items not yet reserved by the plan (starts as the inventory)
        local steps = {}          -- {name, recipe, crafts} in the order to craft them
        local short, short_order = {}, {}
        local too_big = false

        local function have(name)
            if avail[name] == nil then avail[name] = player.get_item_count(name) end
            return avail[name]
        end

        local function add_short(name, amount, reason)
            if not short[name] then
                short[name] = {amount = 0, reason = reason}
                table.insert(short_order, name)
            end
            short[name].amount = short[name].amount + amount
        end

        local need
        local function craft_into(name, rec, n, path)
            for _, ingredient in pairs(rec.ingredients) do
                need(ingredient.name, ingredient.amount * n, path)
            end
            table.insert(steps, {name = name, recipe = rec, crafts = n})
            if #steps > MAX_PLAN_STEPS then too_big = true end
        end

        need = function(name, amount, path)
            if too_big then return end
            local held = have(name)
            local take = math.min(held, amount)
            avail[name] = held - take
            local rest = amount - take
            if rest <= 0 then return end
            if path[name] then
                add_short(name, rest, "its recipe needs itself")
                return
            end
            local ok, rec_or_err = can_craft_recipe(player, name)
            if not ok then
                add_short(name, rest, rec_or_err)
                return
            end
            local rec = rec_or_err
            local per_craft = rec.products[1].amount
            local n = math.ceil(rest / per_craft)
            path[name] = true
            craft_into(name, rec, n, path)
            path[name] = nil
            avail[name] = (avail[name] or 0) + n * per_craft - rest
        end

        craft_into(recipe.name, recipe, crafts, {[recipe.name] = true})
        return steps, short, short_order, too_big
    end

    local function shortage_text(short, short_order)
        local parts = {}
        for _, name in ipairs(short_order) do
            local s = short[name]
            local part = name .. " x" .. s.amount
            local r = s.reason or ""
            -- raw resources and smelted plates need no explanation; machine-only or locked intermediates do
            if not (r:find("raw resource", 1, true) or r:find("category: smelting", 1, true)) then
                part = part .. " (" .. r .. ")"
            end
            table.insert(parts, part)
        end
        return table.concat(parts, ", ")
    end

    -- Slot use of the whole plan, step by step, before anything is crafted: each step's ingredients
    -- leave the inventory (freeing the slots they no longer need) and its product goes in (filling
    -- its part-filled stacks first, then free slots). Returns nil when every step fits, else the
    -- step's item name and how many more free slots it would need.
    local function plan_slots_short(player, steps)
        local inventory = player.get_main_inventory()
        if not inventory then return nil end
        local free, held_slots = 0, {}
        for i = 1, #inventory do
            local stack = inventory[i]
            if not stack.valid_for_read then
                free = free + 1
            else
                held_slots[stack.name] = (held_slots[stack.name] or 0) + 1
            end
        end
        local cnt, slots = {}, {}
        local function track(name)
            if cnt[name] == nil then
                cnt[name] = player.get_item_count(name)
                slots[name] = held_slots[name] or 0
            end
        end
        local function stack_size(name)
            local proto = prototypes.item[name]
            return proto and proto.stack_size or 1
        end
        for _, step in ipairs(steps) do
            for _, ingredient in pairs(step.recipe.ingredients) do
                track(ingredient.name)
                cnt[ingredient.name] = cnt[ingredient.name] - ingredient.amount * step.crafts
                local keep = math.ceil(math.max(cnt[ingredient.name], 0) / stack_size(ingredient.name))
                if keep < slots[ingredient.name] then
                    free = free + slots[ingredient.name] - keep
                    slots[ingredient.name] = keep
                end
            end
            track(step.name)
            cnt[step.name] = cnt[step.name] + step.crafts * step.recipe.products[1].amount
            local need = math.ceil(cnt[step.name] / stack_size(step.name))
            if need > slots[step.name] then
                free = free - (need - slots[step.name])
                slots[step.name] = need
            end
            if free < 0 then
                return step.name, -free
            end
        end
        return nil
    end

    -- Undo one step whose product did not all fit: take back what went in and return the
    -- ingredients (they held those slots a moment ago). Nothing is lost; if the game still
    -- refuses some ingredient, it is spilled at the character's feet and that is said.
    local function undo_step(player, step, inserted)
        if inserted > 0 then
            player.remove_item({name = step.name, count = inserted})
        end
        local spilled = {}
        for _, ingredient in pairs(step.recipe.ingredients) do
            local want = ingredient.amount * step.crafts
            local back = player.insert({name = ingredient.name, count = want})
            if back < want then
                player.surface.spill_item_stack{position = player.position,
                                                stack = {name = ingredient.name, count = want - back}}
                table.insert(spilled, ingredient.name .. " x" .. (want - back))
            end
        end
        return spilled
    end

    local function attempt_craft(player, entity_name, count)
        local can_craft, recipe_or_error = can_craft_recipe(player, entity_name)
        if not can_craft then
            return 0, recipe_or_error
        end

        local recipe = recipe_or_error
        local crafts_needed = math.ceil(count / recipe.products[1].amount)
        local actual_craft_count = crafts_needed * recipe.products[1].amount

        local steps, short, short_order, too_big = plan_craft(player, recipe, crafts_needed)
        if too_big then
            return 0, "the recipe tree needs more than " .. MAX_PLAN_STEPS .. " separate crafts; craft fewer at a time"
        end
        if next(short) then
            return 0, "still missing ingredients - " .. shortage_text(short, short_order) ..
                " (the total still needed after using what you hold and crafting every intermediate that can be " ..
                "hand-crafted). Nothing was crafted"
        end

        if storage.fast then
            local can_insert, error_msg = check_inventory_space(player, entity_name, actual_craft_count)
            if not can_insert then
                return 0, error_msg
            end
            local short_at, short_slots = plan_slots_short(player, steps)
            if short_at then
                return 0, "Inventory is full - crafting " .. short_at .. " on the way needs " .. short_slots ..
                    " more free slot" .. (short_slots == 1 and "" or "s") .. ". Nothing was crafted"
            end

            local crafted = 0
            for i, step in ipairs(steps) do
                -- the plan guarantees the ingredients; check anyway so a surprise never eats items
                for _, ingredient in pairs(step.recipe.ingredients) do
                    local want = ingredient.amount * step.crafts
                    if player.get_item_count(ingredient.name) < want then
                        return 0, "still missing ingredients - " .. ingredient.name .. " x" ..
                            (want - player.get_item_count(ingredient.name)) .. " (while crafting " .. step.name .. ")"
                    end
                end
                for _, ingredient in pairs(step.recipe.ingredients) do
                    player.remove_item({name = ingredient.name, count = ingredient.amount * step.crafts})
                end
                local made = step.crafts * step.recipe.products[1].amount
                local inserted = player.insert({name = step.name, count = made})
                if inserted < made then
                    -- never consume ingredients and lose the product: undo this step and stop
                    local spilled = undo_step(player, step, inserted)
                    local msg = "Inventory is full - no room for " .. made .. " " .. step.name ..
                        " (only " .. inserted .. " fit); that step was undone"
                    if #spilled > 0 then
                        msg = msg .. " (" .. table.concat(spilled, ", ") .. " spilled at your feet)"
                    end
                    if i == 2 then
                        msg = msg .. ". The craft step before it was done: its items are in your inventory"
                    elseif i > 2 then
                        msg = msg .. ". The " .. (i - 1) .. " craft steps before it were done: their items are in your inventory"
                    end
                    return 0, msg
                end
                storage.elapsed_ticks = storage.elapsed_ticks + calculate_crafting_ticks(step.recipe, step.crafts)
                if i == #steps then
                    crafted = inserted
                    update_production_stats(player.force, step.recipe, inserted)
                else
                    update_production_stats(player.force, step.recipe, made)
                end
            end
            return crafted, nil
        else
            -- Slow crafting: the game's crafting queue makes the intermediates itself
            local crafted = player.begin_crafting{count=count, recipe=entity_name}
            if crafted == 0 then
                return 0, "unable to begin crafting - check prerequisites and inventory space"
            end
            update_production_stats(player.force, recipe, crafted)
            return crafted, nil
        end
    end

    -- Main crafting logic
    local total_crafted = 0
    local final_error = nil

    while total_crafted < count do
        local remaining = count - total_crafted
        local crafted_amount, error_msg = attempt_craft(player, entity, remaining)

        if crafted_amount > 0 then
            total_crafted = total_crafted + crafted_amount
            if not storage.fast then
                break
            end
        else
            final_error = error_msg
            break
        end
    end

    if total_crafted >= count or (not storage.fast and total_crafted > 0) then
        return count
    elseif total_crafted > 0 then
        error(string.format("\"Successfully crafted %dx but failed to craft %dx %s because %s\"",
            total_crafted, count - total_crafted, entity, final_error))
    else
        error(string.format("\"Failed to craft %dx %s because %s\"",
            count, entity, final_error))
    end
end
