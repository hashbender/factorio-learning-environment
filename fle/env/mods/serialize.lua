-- Library for serializing items in Factorio
-- Based on code from playerManager and trainTeleports
-- Updated for Factorio 2.0

-- Factorio 2.0 API method names (no backwards compatibility needed)
local supports_bar = "supports_bar"
local get_bar = "get_bar"
local set_bar = "set_bar"

-- Version helper function (kept for potential future use)
local function version_to_table(version)
    local t = {}
    for p in string.gmatch(version, "%d+") do
        t[#t + 1] = tonumber(p)
    end
    return t
end

-- Always returns true for Factorio 2.0 as all modern features are supported
local function version_ge(comp)
    return true  -- Factorio 2.0 supports all features
end

local has_create_grid = version_ge("1.1.7")

-- Add this helper function at the top level
local function is_fluid_handler(entity_type)
    return entity_type == "boiler" or
           entity_type == "offshore-pump" or
           entity_type == "pump" or
           entity_type == "generator" or
           entity_type == "oil-refinery" or
    	   entity_type == "chemical-plant"
           --entity_type == "pipe" or
           --entity_type == "pipe-to-ground"
end

local recursive_serialize = {}

local function serialize_equipment_grid(grid)
    local serialized = {}
    local processed = {}
    for y = 0, grid.height - 1 do
        for x = 0, grid.width - 1 do
            local equipment = grid.get({x, y})
            if equipment ~= nil then
                local pos = equipment.position
                local combined_pos = pos.x + pos.y * grid.width + 1
                if not processed[combined_pos] then
                    processed[combined_pos] = true
                    local entry = {
                        n = equipment.name,
                        p = {pos.x, pos.y},
                    }
                    if equipment.shield > 0 then entry.s = equipment.shield end
                    if equipment.energy > 0 then entry.e = equipment.energy end
                    -- TODO: Test with Industrial Revolution
                    if equipment.burner then
                        local burner = equipment.burner
                        entry.i = recursive_serialize.serialize_inventory(burner.inventory)
                        entry.r = recursive_serialize.serialize_inventory(burner.burnt_result_inventory)
                        if burner.curently_burning then
                            entry.b = {}
                            recursive_serialize.serialize_item_stack(burner.curently_burning, entry.b)
                            entry.f = burner.remaining_burning_fuel
                        end
                    end
                    table.insert(serialized, entry)
                end
            end
        end
    end
    return serialized
end

recursive_serialize.serialize_item_stack = function(slot, entry)
    if
        slot.is_blueprint
        or slot.is_blueprint_book
        or slot.is_upgrade_item
        or slot.is_deconstruction_item
        or slot.is_item_with_tags
    then
        local call_success, call_return = pcall(slot.export_stack)
        if not call_success then
            print("Error: '" .. call_return .. "' thrown exporting '" .. slot.name .. "'")
        else
            entry.e = call_return
        end

        return
    end

    entry.n = slot.name
    entry.c = slot.count
    if slot.health < 1 then entry.h = slot.health end
    if slot.durability then entry.d = slot.durability end
    if slot.type == "ammo" then entry.a = slot.ammo end
    if slot.is_item_with_label then
        local label = {}
        if slot.label then label.t = slot.label end
        if slot.label_color then label.c = slot.label_color end
        label.a = slot.allow_manual_label_change
        entry.l = label
    end

    if slot.grid then
        entry.g = serialize_equipment_grid(slot.grid)
    end

    if slot.is_item_with_inventory then
        local sub_inventory = slot.get_inventory(defines.inventory.item_main)
        entry.i = recursive_serialize.serialize_inventory(sub_inventory)
    end
end

recursive_serialize.deserialize_item_stack = function(slot, entry)
    if entry.e then
        local success = slot.import_stack(entry.e)
        if success == 1 then
            print("Error: import of '" .. entry.e .. "' succeeded with errors")
        elseif success == -1 then
            print("Error: import of '" .. entry.e .. "' failed")
        end

        return
    end

    local item_stack = {
        name = entry.n,
        count = entry.c,
    }
    if entry.h then item_stack.health = entry.h end
    if entry.d then item_stack.durability = entry.d end
    if entry.a then item_stack.ammo = entry.a end

    local call_success, call_return = pcall(slot.set_stack, item_stack)
    if not call_success then
        print("Error: '" .. call_return .. "' thrown setting stack ".. serpent.line(entry))

    elseif not call_return then
        print("Error: Failed to set stack " .. serpent.line(entry))

    else
        if entry.l then
            -- TODO test this with AAI's unit-remote-control
            local label = entry.l
            if label.t then slot.label = label.t end
            if label.c then slot.label_color = label.c end
            slot.allow_manual_label_change = label.a
        end
        if entry.g then
            if slot.grid then
                recursive_serialize.deserialize_equipment_grid(slot.grid, entry.g)
            elseif slot.type == "item-with-entity-data" and has_create_grid then
                slot.create_grid()
                recursive_serialize.deserialize_equipment_grid(slot.grid, entry.g)
            else
                print("Error: Attempt to deserialize equipment grid on an unsupported entity")
            end
        end
        if entry.i then
            local sub_inventory = slot.get_inventory(defines.inventory.item_main)
            recursive_serialize.deserialize_inventory(sub_inventory, entry.i)
        end
    end
end

recursive_serialize.deserialize_inventory = function(inventory, serialized)
    if serialized.b and inventory[supports_bar]() then
        inventory[set_bar](serialized.b)
    end

    local last_slot_index = 0
    for _, entry in ipairs(serialized.i) do
        local base_index = entry.s or last_slot_index + 1

        local repeat_count = entry.r or 0
        for offset = 0, repeat_count do
            -- XXX what if the inventory is smaller on this instance?
            local index = base_index + offset
            local slot = inventory[index]
            if entry.f then
                local call_success, call_return = pcall(inventory.set_filter, index, entry.f)
                if not call_success then
                    print("Error: '" .. call_return .. "' thrown setting filter " .. entry.f)

                elseif not call_return then
                    print("Error: Failed to set filter " .. entry.f)
                end
            end

            if entry.n or entry.e then
                recursive_serialize.deserialize_item_stack(slot, entry)
            end
        end
        last_slot_index = base_index + repeat_count
    end
end


recursive_serialize.deserialize_equipment_grid = function(grid, serialized)
    grid.clear()
    for _, entry in ipairs(serialized) do
        local equipment = grid.put({
            name = entry.n,
            position = entry.p,
        })
        if equipment then
            if entry.s then equipment.shield = entry.s end
            if entry.e then equipment.energy = entry.e end
            if entry.i then
                local burner = equipment.burner
                if entry.b then recursive_serialize.deserialize_item_stack(burner.currently_burning, entry.b) end
                if entry.f then burner.remaining_burning_fuel = entry.f end
                recursive_serialize.deserialize_inventory(burner.burnt_result_inventory, entry.r)
                recursive_serialize.deserialize_inventory(burner.inventory, entry.i)
            end
        end
    end
end

local function serialize_fluidbox(fluidbox)
    local serialized = {
        length = #fluidbox,
    }
    if fluidbox.owner and fluidbox.owner.name then
        serialized[fluidbox.owner] = fluidbox.owner.name
    end

    -- Serialize each fluid box
    serialized.fluidboxes = {}
    for i = 1, #fluidbox do
        local box = fluidbox[i]
        local prototype = fluidbox.get_prototype(i)
        local connections = fluidbox.get_connections(i)
        local filter = fluidbox.get_filter(i)
        -- Factorio 2.0: get_flow removed, get_fluid_system_id -> get_fluid_segment_id
        local locked_fluid = fluidbox.get_locked_fluid(i)
        local fluid_segment_id = fluidbox.get_fluid_segment_id(i)

        local serialized_box = {
            prototype = prototype and prototype.object_name or nil,
            capacity = fluidbox.get_capacity(i),
            connections = {},
            filter = filter,
            flow = 0,  -- Factorio 2.0: get_flow no longer exists
            locked_fluid = locked_fluid,
            fluid_system_id = fluid_segment_id,
        }

        -- Serialize fluid
        if box then
            serialized_box.fluid = {
                name = box.name,
                amount = box.amount,
                temperature = box.temperature,
            }
        end

        -- Serialize connections (check validity of connection owner)
        for _, connection in pairs(connections) do
            if connection.owner and connection.owner.valid and connection.owner.name then
                table.insert(serialized_box.connections, "\""..connection.owner.name .. "\"")
            end
        end

        serialized.fluidboxes[i] = serialized_box
    end

    return serialized
end

-- Helper function to get relative direction of neighbor
local function get_neighbor_direction(entity, neighbor)
    local dx = neighbor.position.x - entity.position.x
    local dy = neighbor.position.y - entity.position.y

    -- Determine primary direction based on which delta is larger
    if math.abs(dx) > math.abs(dy) then
        return dx > 0 and defines.direction.east or defines.direction.west
    else
        return dy > 0 and defines.direction.south or defines.direction.north
    end
end

-- Helper function to expand a bounding box by a given amount
local function expand_box(box, amount)
    return {
        left_top = {
            x = box.left_top.x - amount,
            y = box.left_top.y - amount
        },
        right_bottom = {
            x = box.right_bottom.x + amount,
            y = box.right_bottom.y + amount
        }
    }
end

local function serialize_neighbours(entity)
    local neighbours = {}

    -- Get entity's prototype collision box
    local prototype = prototypes.entity[entity.name]
    local collision_box = prototype.collision_box

    -- Create a slightly larger search box
    local search_box = expand_box(collision_box, 0.707) -- Expand by 0.5 tiles

    -- Convert to world coordinates
    local world_box = {
        left_top = {
            x = entity.position.x + search_box.left_top.x,
            y = entity.position.y + search_box.left_top.y
        },
        right_bottom = {
            x = entity.position.x + search_box.right_bottom.x,
            y = entity.position.y + search_box.right_bottom.y
        }
    }

    -- Find entities within the expanded collision box
    local nearby = entity.surface.find_entities_filtered{
        area = world_box
    }

    -- Process each nearby entity
    for _, neighbor in pairs(nearby) do
        -- Skip if invalid, same entity, or no unit number
        if neighbor.valid and neighbor.unit_number and neighbor.unit_number ~= entity.unit_number then
            table.insert(neighbours, {
                unit_number = neighbor.unit_number,
                direction = get_neighbor_direction(entity, neighbor),
                name = "\""..neighbor.name.."\"",
                position = neighbor.position
                --type = neighbor.type
            })
        end
    end

    return neighbours
end

local function add_burner_inventory(serialized, burner)
    local fuel_inventory = burner.inventory
    if fuel_inventory and #fuel_inventory > 0 then
        serialized.fuel_inventory = {}
        serialized.remaining_fuel = 0
        for i = 1, #fuel_inventory do
            local item = fuel_inventory[i]
            if item and item.valid_for_read then

                table.insert(serialized.fuel_inventory, {name = "\""..item.name.."\"", count = item.count})
                serialized.remaining_fuel = serialized.remaining_fuel + item.count
            end
        end
    end
end

local function get_entity_direction(entity, direction)

    -- If direction is nil then return north
    if direction == nil then
        return defines.direction.north
    end

    local prototype = prototypes.entity[entity]
    -- if prototype is nil (e.g because the entity is a ghost or player character) then return the direction as is
    if prototype == nil then
        return direction
    end

    local cardinals = {
        defines.direction.north,
        defines.direction.east,
        defines.direction.south,
        defines.direction.west
    }
    -- Factorio 2.0 uses 16 directions: north=0, east=4, south=8, west=12
    -- The direction parameter comes from entity.direction
    if prototype and (prototype.name == "boiler" or prototype.type == "generator" or prototype.name == "heat-exchanger") then
        if direction == defines.direction.north then
            return defines.direction.north
        elseif direction == defines.direction.east then
            return defines.direction.east
        elseif direction == defines.direction.south then
            return defines.direction.south
        else
            return defines.direction.west
        end
    elseif prototype and prototype.name == "offshore-pump" then
        if direction == defines.direction.south then
            return defines.direction.north
        elseif direction == defines.direction.west then
            return defines.direction.east
        elseif direction == defines.direction.north then
            return defines.direction.south
        else
            return defines.direction.west
        end
    elseif prototype and prototype.name == "oil-refinery" then
        if direction == defines.direction.north then
            return defines.direction.north
        elseif direction == defines.direction.east then
            return defines.direction.east
        elseif direction == defines.direction.south then
            return defines.direction.south
        else
            return defines.direction.west
        end
    elseif prototype and prototype.name == "chemical-plant" then
        -- Like the oil refinery and assembling machines: the plant faces the
        -- requested direction (it used to face the opposite one, so the reported
        -- direction and rotate_entity's result never matched the request)
        if direction == defines.direction.north then
            return defines.direction.north
        elseif direction == defines.direction.east then
            return defines.direction.east
        elseif direction == defines.direction.south then
            return defines.direction.south
        else
            return defines.direction.west
        end
    elseif prototype and prototype.type == "transport-belt" or prototype.type == "splitter"  then
        if direction == defines.direction.north then
            return defines.direction.north
        elseif direction == defines.direction.west then
            return defines.direction.west
        elseif direction == defines.direction.south then
            return defines.direction.south
        else
            return defines.direction.east
        end
    elseif prototype and prototype.type == "inserter" then
        if direction == defines.direction.north then
            return defines.direction.south
        elseif direction == defines.direction.east then
            return defines.direction.west
        elseif direction == defines.direction.south then
            return defines.direction.north
        else
            return defines.direction.east
        end
    elseif prototype.type == "mining-drill" then
        if direction == defines.direction.east then
            return cardinals[2]
        elseif direction == defines.direction.south then
            return cardinals[3]
        elseif direction == defines.direction.west then
            return cardinals[4]
        else
            return cardinals[1]
        end
    elseif prototype.type == "underground-belt" then
        if direction == defines.direction.east then
            return defines.direction.east
        elseif direction == defines.direction.south then
            return defines.direction.south
        elseif direction == defines.direction.west then
            return defines.direction.west
        else
            return defines.direction.north
        end
    elseif prototype.type == "pipe-to-ground" then
        if direction == defines.direction.east then
            return defines.direction.west
        elseif direction == defines.direction.south then
            return defines.direction.north
        elseif direction == defines.direction.west then
            return defines.direction.east
        else
            return defines.direction.south
        end
    elseif prototype.type == "assembling-machine" then
        if direction == defines.direction.north then
            return defines.direction.north
        elseif direction == defines.direction.east then
            return defines.direction.east
        elseif direction == defines.direction.south then
            return defines.direction.south
        else
            return defines.direction.west
        end
    elseif prototype.type == "storage-tank" then
        if direction == defines.direction.north then
            return defines.direction.north
        elseif direction == defines.direction.east then
            return defines.direction.east
        elseif direction == defines.direction.south then
            return defines.direction.south
        else
            return defines.direction.west
        end
    else
        return direction
    end
    return direction
end

local function get_inverse_entity_direction(entity, factorio_direction)
    local prototype = prototypes.entity[entity]

    if not factorio_direction then
        return 0  -- Assuming 0 is the default direction in your system
    end

    if prototype and prototype.name == "offshore-pump" then
        if factorio_direction == defines.direction.west then
            return defines.direction.east
        elseif factorio_direction == defines.direction.east then
            return defines.direction.west
        elseif factorio_direction == defines.direction.south then
            return defines.direction.north
        else
            return defines.direction.south
        end
    end
    --game.print("Getting inverse direction: " .. entity .. " with direction: " .. factorio_direction)
    if prototype and prototype.type == "inserter" then
        if factorio_direction == defines.direction.south then
            return defines.direction.north
        elseif factorio_direction == defines.direction.west then
            return defines.direction.east
        elseif factorio_direction == defines.direction.north then
            return defines.direction.south
        elseif factorio_direction == defines.direction.east then
            return defines.direction.west
        else
            return -1
        end
    else
        --game.print("Returning direction: " .. math.floor(factorio_direction / 2) .. ', '.. factorio_direction)
        -- For other entity types, convert Factorio's direction to 0-3 range
        return factorio_direction
    end
end

-- An assembling machine's fluid ports as the game has them. For each fluid box
-- with an input or output role, the target tile of each pipe connection (the
-- tile a pipe must occupy), typed with the fluid of the box (its filter, or the
-- recipe's fluid ingredient or product in order). Returns {all, inputs, outputs}.
local function read_assembler_fluid_ports(entity)
    local fluidbox = entity.fluidbox
    local recipe = entity.get_recipe()
    local fluid_in, fluid_out = {}, {}
    if recipe then
        for _, item in pairs(recipe.ingredients or {}) do
            if item.type == "fluid" then table.insert(fluid_in, item.name) end
        end
        for _, item in pairs(recipe.products or {}) do
            if item.type == "fluid" then table.insert(fluid_out, item.name) end
        end
    end
    local all, inputs, outputs = {}, {}, {}
    local n_in, n_out = 0, 0
    for i = 1, #fluidbox do
        local proto = fluidbox.get_prototype(i)
        if type(proto) == "table" and proto.object_name == nil then
            proto = proto[1]
        end
        local role = proto and proto.production_type
        local connections = fluidbox.get_pipe_connections(i)
        if role ~= "input" and role ~= "output" then
            local flow = connections[1] and connections[1].flow_direction
            if flow == "input" or flow == "output" then role = flow end
        end
        local filter = fluidbox.get_filter(i)
        local fluid = filter and filter.name
        if role == "input" then
            n_in = n_in + 1
            fluid = fluid or fluid_in[n_in]
        elseif role == "output" then
            n_out = n_out + 1
            fluid = fluid or fluid_out[n_out]
        end
        for _, connection in pairs(connections) do
            local target = connection.target_position
            if target and connection.connection_type ~= "underground" then
                table.insert(all, {x = target.x, y = target.y})
                local point = {x = target.x, y = target.y, type = "\"" .. (fluid or "") .. "\""}
                if role == "input" then
                    table.insert(inputs, point)
                elseif role == "output" then
                    table.insert(outputs, point)
                end
            end
        end
    end
    return {all = all, inputs = inputs, outputs = outputs}
end

-- Helper function to check if a position is valid (not colliding with water or other impassable tiles)
local function is_valid_connection_point(surface, position)
    -- Get the tile at the position
    local tile = surface.get_tile(position.x, position.y)

    -- Check if the tile is water or other impassable tiles
    local invalid_tiles = {
        ["water"] = true,
        ["deepwater"] = true,
        ["water-green"] = true,
        ["deepwater-green"] = true,
        ["water-shallow"] = true,
        ["water-mud"] = true,
    }

    -- Return false if the tile is invalid, true otherwise
    return not invalid_tiles[tile.name]
end

storage.utils.entity_status_names = function(entity_status)
    local s = entity_status
    if not s then return '"normal"' end

    -- try direct lookup
    local name = defines.entity_status[s]
    if name then return '"' .. name .. '"' end

    -- fallback reverse lookup
    for k, v in pairs(defines.entity_status) do
        if v == s then return '"' .. k .. '"' end
    end

    return '"normal"'
end

storage.utils.get_entity_direction = get_entity_direction

storage.utils.serialize_recipe = function(recipe)
    local function serialize_number(num)
        if num == math.huge then
            return "inf"
        elseif num == -math.huge then
            return "-inf"
        else
            return tostring(num)
        end
    end
    if not recipe then return nil end

    local ingredients = {}
    for _, ingredient in pairs(recipe.ingredients) do
        table.insert(ingredients, {
            name = '"' .. ingredient.name .. '"',
            amount = serialize_number(ingredient.amount),
            type = '"' .. ingredient.type .. '"'
        })
    end

    local products = {}
    for _, product in pairs(recipe.products) do
        table.insert(products, {
            name = '"' .. product.name .. '"',
            amount = serialize_number(product.amount),
            type = '"' .. product.type .. '"',
            probability = product.probability and serialize_number(product.probability) or "1"
        })
    end

    return {
        name = '"' .. recipe.name .. '"',
        category = '"' .. recipe.category .. '"',
        enabled = recipe.enabled,
        energy = serialize_number(recipe.energy),
        ingredients = ingredients,
        products = products
    }
end

-- How much fluid one fluidbox holds: its prototype's volume. In Factorio 2.0
-- LuaFluidBox.get_capacity of a box that is part of a pipe segment returns the
-- whole segment's capacity, so it is only the fallback.
storage.utils.fluidbox_volume = function(fluidbox, index)
    local ok, volume = pcall(function() return fluidbox.get_prototype(index).volume end)
    if ok and volume then
        return volume
    end
    local ok_cap, capacity = pcall(function() return fluidbox.get_capacity(index) end)
    if ok_cap then
        return capacity
    end
    return nil
end

-- Electric network summaries, keyed by electric_network_id: what the power
-- pole GUI shows. Powers in W, energies in J.
--   production / consumption: the network's 5 s average flows
--   generator_max: the generators' rated maximum output
--   demand: the rated power of consumers that are working or waiting for
--     power (low or no power), plus the drain of the idle ones
--   satisfaction: consumption / demand, at most 1 (nil without demand)
--   accumulator_charge / accumulator_capacity, and counts of poles,
--   generators, accumulators, consumers and consumers with low or no power
-- Computed once per tick and surface (one get_entities call reuses it).
local electric_summary_cache = {tick = -1}
local WANTS_POWER = {working = true, low_power = true, no_power = true}
-- Entity types that can take or give electric power (Factorio 2.0); only these
-- are scanned. Unknown type names in a filter match nothing.
local ELECTRIC_TYPES = {"electric-pole", "generator", "solar-panel", "burner-generator", "accumulator",
    "assembling-machine", "furnace", "mining-drill", "inserter", "lab", "radar", "lamp", "roboport",
    "beacon", "rocket-silo", "pump", "offshore-pump", "electric-turret", "electric-energy-interface",
    "arithmetic-combinator", "decider-combinator", "selector-combinator", "programmable-speaker",
    "agricultural-tower", "lightning-attractor", "fusion-reactor", "fusion-generator"}

storage.utils.electric_network_summaries = function(surface, force)
    local cache = electric_summary_cache
    if cache.tick == game.tick and cache.surface == surface.index and cache.force == force.name then
        return cache.data
    end
    local status_names = {}
    for name, value in pairs(defines.entity_status) do
        status_names[value] = name
    end
    local five_seconds = defines.flow_precision_index.five_seconds
    local nets = {}
    local stats_read = {}
    for _, e in pairs(surface.find_entities_filtered{force = force, type = ELECTRIC_TYPES}) do
        local ok_id, id = pcall(function() return e.electric_network_id end)
        if ok_id and id then
            local n = nets[id]
            if not n then
                n = {id = id, production = 0, consumption = 0, demand = 0, generator_max = 0,
                     accumulator_charge = 0, accumulator_capacity = 0, poles = 0, generators = 0,
                     accumulators = 0, consumers = 0, low_power = 0, no_power = 0}
                nets[id] = n
            end
            local t = e.type
            if t == "electric-pole" then
                n.poles = n.poles + 1
                if not stats_read[id] then
                    stats_read[id] = true
                    local st = e.electric_network_statistics
                    for name, _ in pairs(st.output_counts) do
                        n.production = n.production + st.get_flow_count{name = name, category = "output",
                            precision_index = five_seconds, count = false} * 60
                    end
                    for name, _ in pairs(st.input_counts) do
                        n.consumption = n.consumption + st.get_flow_count{name = name, category = "input",
                            precision_index = five_seconds, count = false} * 60
                    end
                end
            elseif t == "generator" or t == "solar-panel" or t == "burner-generator" then
                n.generators = n.generators + 1
                local ok, max = pcall(function() return e.prototype.get_max_power_output(e.quality) end)
                if ok and max then
                    n.generator_max = n.generator_max + max * 60
                end
            elseif t == "accumulator" then
                n.accumulators = n.accumulators + 1
                n.accumulator_charge = n.accumulator_charge + e.energy
                n.accumulator_capacity = n.accumulator_capacity + e.electric_buffer_size
            else
                local ok_buf, buffer = pcall(function() return e.electric_buffer_size end)
                if ok_buf and buffer and buffer > 0 then
                    n.consumers = n.consumers + 1
                    local ok_s, status = pcall(function() return e.status end)
                    local status_name = ok_s and status and status_names[status] or nil
                    if status_name == "low_power" then
                        n.low_power = n.low_power + 1
                    elseif status_name == "no_power" then
                        n.no_power = n.no_power + 1
                    end
                    if WANTS_POWER[status_name] then
                        local ok_u, usage = pcall(function() return e.prototype.get_max_energy_usage(e.quality) end)
                        local ok_b, bonus = pcall(function() return e.consumption_bonus end)
                        local factor = 1 + ((ok_b and bonus) or 0)
                        if factor < 0.2 then factor = 0.2 end
                        if ok_u and usage then
                            n.demand = n.demand + usage * factor * 60
                        end
                    else
                        local ok_d, drain = pcall(function() return e.prototype.electric_energy_source_prototype.drain end)
                        if ok_d and drain then
                            n.demand = n.demand + drain * 60
                        end
                    end
                end
            end
        end
    end
    for _, n in pairs(nets) do
        if n.demand > 0 then
            n.satisfaction = math.min(1, n.consumption / n.demand)
        end
    end
    cache.tick, cache.surface, cache.force, cache.data = game.tick, surface.index, force.name, nets
    return nets
end

-- Status detail: the concrete reason behind an entity's status, as the game's
-- entity window shows it (ingredient and fuel slots, the electric network, the
-- drop or pickup target). Facts only. nil for statuses without one (working ...).
local DETAIL_LIST_CAP = 4

local function detail_num(v)
    if v == math.floor(v) then return tostring(math.floor(v)) end
    return string.format("%.1f", v)
end

local function detail_pos(p)
    return "(" .. detail_num(math.floor(p.x * 2 + 0.5) / 2) .. ", " .. detail_num(math.floor(p.y * 2 + 0.5) / 2) .. ")"
end

local function detail_capped(parts)
    local shown = {}
    for i = 1, math.min(#parts, DETAIL_LIST_CAP) do shown[i] = parts[i] end
    local s = table.concat(shown, ", ")
    if #parts > DETAIL_LIST_CAP then s = s .. ", (" .. (#parts - DETAIL_LIST_CAP) .. " more)" end
    return s
end

local function detail_contents(inventory)
    local parts = {}
    if inventory then
        for name, count in pairs(storage.utils.get_contents_compat(inventory)) do
            table.insert(parts, name .. " " .. detail_num(count))
        end
    end
    table.sort(parts)
    return parts
end

local function detail_fluid_amount(entity, name)
    local total = 0
    local fb = entity.fluidbox
    if fb then
        for i = 1, #fb do
            local f = fb[i]
            if f and f.name == name then total = total + f.amount end
        end
    end
    return total
end

-- Recipe ingredients of `kind` ("item" / "fluid") the machine has less of than one craft needs.
local function detail_missing_ingredients(entity, kind)
    local ok, recipe = pcall(function() return entity.get_recipe() end)
    if not ok or not recipe then return nil end
    local inv
    pcall(function()
        inv = entity.get_inventory(entity.type == "furnace" and defines.inventory.furnace_source
            or defines.inventory.assembling_machine_input)
    end)
    local parts = {}
    for _, ing in pairs(recipe.ingredients) do
        if ing.type == kind then
            local have
            if kind == "fluid" then
                have = detail_fluid_amount(entity, ing.name)
            else
                have = inv and inv.get_item_count(ing.name) or 0
            end
            if have < ing.amount then
                table.insert(parts, ing.name .. " (" .. detail_num(have) .. " of " .. detail_num(ing.amount) .. " per craft)")
            end
        end
    end
    if #parts == 0 then return nil end
    return "missing " .. detail_capped(parts)
end

local function detail_power(entity, what)
    local ok, id = pcall(function() return entity.electric_network_id end)
    if ok and id then return what .. " (electric network " .. id .. ")" end
    return what .. " (not connected to an electric network)"
end

-- What is at an inserter's or drill's drop / pickup position (the game's target first).
local function detail_target(entity, getter, pos, verb)
    local ok, target = pcall(getter)
    if not (ok and target and target.valid) and pos then
        for _, e in pairs(entity.surface.find_entities_filtered{position = pos, limit = 5}) do
            if e.valid and e ~= entity and e.type ~= "character" and e.type ~= "item-entity" then
                target = e
                break
            end
        end
    end
    if target and target.valid then
        return verb .. " " .. target.name .. " at " .. detail_pos(target.position)
    end
    if not pos then return nil end
    local text = verb .. " " .. detail_pos(pos) .. ": no entity there"
    local ground = entity.surface.find_entities_filtered{position = pos, type = "item-entity", limit = 1}[1]
    if ground and ground.valid and ground.stack and ground.stack.valid_for_read then
        text = text .. ", " .. ground.stack.name .. " on the ground"
    end
    return text
end

-- An inserter waiting for source items while its pickup belt holds items: the drop target
-- is not taking those items now (an inserter picks up from a belt only what its drop
-- target accepts). Names the items on the pickup belt and what the target holds of them,
-- or that they are not an ingredient of its recipe / research; plus what it is missing.
local BELT_TYPES = {["transport-belt"] = true, ["underground-belt"] = true, ["splitter"] = true,
    ["loader"] = true, ["loader-1x1"] = true, ["lane-splitter"] = true}

local function detail_belt_items(belt)
    local items, order = {}, {}
    local n = 2
    pcall(function() n = belt.get_max_transport_line_index() end)
    for i = 1, n do
        local ok, line = pcall(function() return belt.get_transport_line(i) end)
        if ok and line then
            for name, count in pairs(storage.utils.get_contents_compat(line)) do
                if not items[name] then table.insert(order, name) end
                items[name] = (items[name] or 0) + count
            end
        end
    end
    table.sort(order)
    return items, order
end

local function detail_uses(target)
    -- {name = true} for the target's recipe ingredients / current research packs, the
    -- input inventory, and the missing text; nil uses when unknown (no recipe)
    if target.type == "lab" then
        local inv = target.get_inventory(defines.inventory.lab_input)
        local tech = target.force and target.force.current_research
        if not tech then return nil, inv, nil, "no research" end
        local uses, parts = {}, {}
        for _, ing in pairs(tech.research_unit_ingredients) do
            uses[ing.name] = true
            local have = inv and inv.get_item_count(ing.name) or 0
            if have < ing.amount then
                table.insert(parts, ing.name .. " (" .. detail_num(have) .. " of " .. detail_num(ing.amount) .. ")")
            end
        end
        return uses, inv, (#parts > 0) and ("missing " .. detail_capped(parts)) or nil, tech.name
    end
    local ok, recipe = pcall(function() return target.get_recipe() end)
    local inv
    pcall(function()
        inv = target.get_inventory(target.type == "furnace" and defines.inventory.furnace_source
            or defines.inventory.assembling_machine_input)
    end)
    if not ok or not recipe then return nil, inv, nil, nil end
    local uses = {}
    for _, ing in pairs(recipe.ingredients) do uses[ing.name] = true end
    return uses, inv, detail_missing_ingredients(target, "item"), recipe.name
end

local function detail_not_taken(entity)
    local ok_t, belt = pcall(function() return entity.pickup_target end)
    if not (ok_t and belt and belt.valid and BELT_TYPES[belt.type]) then return nil end
    local ok_d, target = pcall(function() return entity.drop_target end)
    if not (ok_d and target and target.valid) then return nil end
    if not (target.type == "lab" or target.type == "assembling-machine" or target.type == "furnace") then
        return nil
    end
    local items, order = detail_belt_items(belt)
    if #order == 0 then return nil end
    local uses, inv, missing, what = detail_uses(target)
    local held, unused = {}, {}
    for _, name in ipairs(order) do
        if uses and not uses[name] then
            table.insert(unused, name)
        else
            table.insert(held, name .. " " .. detail_num(inv and inv.get_item_count(name) or 0))
        end
    end
    local belt_parts = {}
    for _, name in ipairs(order) do table.insert(belt_parts, name .. " " .. detail_num(items[name])) end
    local text = "; belt has " .. detail_capped(belt_parts) .. ", not taken now by " .. target.name .. " at "
        .. detail_pos(target.position) .. " ("
    local why = {}
    if #held > 0 then table.insert(why, "holds " .. detail_capped(held)) end
    if #unused > 0 then
        if target.type == "lab" then
            table.insert(why, detail_capped(unused) .. " not used by " .. (what or "the current research"))
        else
            table.insert(why, detail_capped(unused) .. " not in recipe " .. (what or "?"))
        end
    elseif uses == nil and what == "no research" then
        table.insert(why, "no research set")
    end
    if missing then table.insert(why, missing) end
    return text .. table.concat(why, "; ") .. ")"
end

local function detail_text(entity)
    local ok, s = pcall(function() return entity.status end)
    if not ok or not s then return nil end
    local S = defines.entity_status
    if s == S.item_ingredient_shortage then
        return detail_missing_ingredients(entity, "item")
    elseif s == S.fluid_ingredient_shortage or s == S.missing_required_fluid then
        return detail_missing_ingredients(entity, "fluid")
    elseif s == S.no_power then
        return detail_power(entity, "no power")
    elseif s == S.low_power then
        return detail_power(entity, "low power")
    elseif s == S.not_plugged_in_electric_network then
        return "not connected to an electric network"
    elseif s == S.full_output then
        local inv = entity.get_output_inventory()
        local parts = detail_contents(inv)
        if #parts == 0 then return "output full" end
        return "output full (" .. detail_capped(parts) .. ")"
    elseif s == S.full_burnt_result_output then
        local parts = detail_contents(entity.burner and entity.burner.burnt_result_inventory)
        return "burnt result full (" .. detail_capped(parts) .. ")"
    elseif s == S.no_recipe then
        return "no recipe set"
    elseif s == S.no_fuel then
        local parts = detail_contents(entity.burner and entity.burner.inventory)
        if #parts == 0 then return "no fuel (fuel slot empty)" end
        return "no fuel (fuel slot: " .. detail_capped(parts) .. ")"
    elseif s == S.waiting_for_space_in_destination then
        local ok_p, pos = pcall(function() return entity.drop_position end)
        return detail_target(entity, function() return entity.drop_target end, ok_p and pos or nil,
            "waiting for space in")
    elseif s == S.waiting_for_source_items then
        local ok_p, pos = pcall(function() return entity.pickup_position end)
        local text = detail_target(entity, function() return entity.pickup_target end, ok_p and pos or nil,
            "waiting for items from")
        local ok_n, extra = pcall(detail_not_taken, entity)
        if text and ok_n and extra then text = text .. extra end
        return text
    elseif s == S.no_minable_resources then
        local r
        pcall(function() r = entity.prototype.get_mining_drill_radius(entity.quality) end)
        if not r then pcall(function() r = entity.prototype.mining_drill_radius end) end
        if not r then return "no minable resources in the mining area" end
        local p = entity.position
        return "no minable resources in the mining area " .. detail_pos({x = p.x - r, y = p.y - r})
            .. " to " .. detail_pos({x = p.x + r, y = p.y + r})
    elseif s == S.missing_science_packs then
        local tech = entity.force.current_research
        if not tech then return nil end
        local inv = entity.get_inventory(defines.inventory.lab_input)
        local parts = {}
        for _, ing in pairs(tech.research_unit_ingredients) do
            local have = inv and inv.get_item_count(ing.name) or 0
            if have < ing.amount then
                table.insert(parts, ing.name .. " (" .. detail_num(have) .. " of " .. detail_num(ing.amount) .. ")")
            end
        end
        if #parts == 0 then return nil end
        return "missing " .. detail_capped(parts) .. " for " .. tech.name
    elseif s == S.no_input_fluid or s == S.low_input_fluid then
        local fb = entity.fluidbox
        local what = (s == S.no_input_fluid) and "no input fluid" or "low input fluid"
        if fb and #fb > 0 then
            local f = fb[1]
            local name = f and f.name
            if not name then
                local ok_f, filter = pcall(function() return fb.get_filter(1) end)
                name = ok_f and filter and filter.name or nil
            end
            if name then
                return what .. " (" .. name .. " " .. detail_num(f and f.amount or 0) .. ")"
            end
        end
        return nil
    end
    return nil
end

storage.utils.status_detail = function(entity)
    local ok, text = pcall(detail_text, entity)
    if ok and text then return text end
    return nil
end

-- The fluid networks (segment ids) of every fluid box of an entity, each once, in fluid box order. A machine's
-- own fluid box belongs to no segment (Factorio 2.0 returns nil for it): its network is the segment of what the
-- box is connected to (a pipe, a tank).
storage.utils.fluid_system_ids = function(entity)
    local ids, seen = {}, {}
    local fb = entity.fluidbox
    for i = 1, (fb and #fb or 0) do
        local here = {}
        local ok_s, id = pcall(fb.get_fluid_segment_id, i)
        if ok_s and id then
            table.insert(here, id)
        else
            local ok_c, conns = pcall(fb.get_connections, i)
            for _, other in pairs(ok_c and conns or {}) do
                local ok_o, oid = pcall(other.get_fluid_segment_id, 1)
                if ok_o and oid then table.insert(here, oid) end
            end
        end
        for _, x in ipairs(here) do
            if not seen[x] then seen[x] = true; table.insert(ids, x) end
        end
    end
    return ids
end

-- Why a connected steam engine / turbine has no steam: the boilers in the fluid network it is connected to
-- (followed through the connected fluid boxes, at most 400 entities) and their state
storage.utils.no_steam_detail = function(entity)
    local seen, queue, boilers, complete = {}, {entity}, {}, true
    seen[entity.unit_number or 0] = true
    local head = 1
    while head <= #queue do
        if head > 400 then complete = false; break end
        local e = queue[head]; head = head + 1
        if e.type == "boiler" then
            table.insert(boilers, e)
        else
            local fb = e.fluidbox
            for i = 1, (fb and #fb or 0) do
                local ok_c, conns = pcall(fb.get_connections, i)
                for _, other in pairs(ok_c and conns or {}) do
                    local o = other.owner
                    if o and o.valid and o.unit_number and not seen[o.unit_number] then
                        seen[o.unit_number] = true
                        table.insert(queue, o)
                    end
                end
            end
        end
    end
    local function where(b) return "(" .. b.position.x .. ", " .. b.position.y .. ")" end
    if #boilers == 0 then
        if complete then return "no steam: no boiler is connected to its steam input" end
        return "no steam in its input"
    end
    local parts = {}
    for _, b in ipairs(boilers) do
        if #parts >= 3 then break end
        local st = storage.utils.entity_status_names(b.status):sub(2, -2)
        if st == "no_fuel" then
            table.insert(parts, "boiler at " .. where(b) .. " has no fuel")
        else
            table.insert(parts, "boiler at " .. where(b) .. " is " .. st)
        end
    end
    local text = "no steam: " .. table.concat(parts, ", ")
    if #boilers > #parts then text = text .. " and " .. (#boilers - #parts) .. " more boilers" end
    return text
end

storage.utils.serialize_entity = function(entity)

    if entity == nil then
        return {}
    end

    -- Check if entity is still valid (hasn't been destroyed/removed)
    if not entity.valid then
        error("Cannot serialize entity: LuaEntity is no longer valid (entity may have been destroyed or removed)")
    end
    --game.print("Serializing entity: " .. entity.name .. " with direction: " .. entity.direction)
    local direction = entity.direction

    if direction ~= nil then
        direction = get_entity_direction(entity.name, entity.direction)
    else
        direction = 0
    end


    --game.print("Serialized direction: ", {skip=defines.print_skip.never})
    local s = entity.status  -- may be nil for some entities
    local name = s and defines.entity_status[s]
    
    if not name and s then
      -- robust reverse lookup
      for k, v in pairs(defines.entity_status) do
        if v == s then name = k; break end
      end
    end
    
    local serialized = {
        name = "\""..entity.name.."\"",
        position = entity.position,
        direction = direction,
        health = entity.health,
        energy = entity.energy,
        type = "\""..entity.type.."\"",
        status = storage.utils.entity_status_names(entity.status)
    }

    if entity.grid then
        serialized.grid = serialize_equipment_grid(entity.grid)
    end
    --game.print(serpent.line(entity.get_inventory(defines.inventory.turret_ammo)))
    serialized.warnings = storage.utils.get_issues(entity)

    -- Factorio 2.0 inventory indices overlap (fuel = chest = turret_ammo = 1,
    -- furnace_source = assembling_machine_input = lab_input = 2, furnace_result =
    -- assembling_machine_output = lab_modules = 3), so reading every define gives
    -- copies under wrong names. Name each inventory the entity really has after
    -- the game's own name (get_inventory_name), using FLE's field names where
    -- the entity classes expect them. Other inventories are listed only when not
    -- empty.
    local crafter_names = {
        crafter_input = "assembling_machine_input",
        crafter_output = "assembling_machine_output",
        crafter_modules = "assembling_machine_modules",
    }
    local fle_inventory_names = {
        ["furnace"] = {
            crafter_input = "furnace_source",
            crafter_output = "furnace_result",
            crafter_modules = "furnace_modules",
        },
        ["assembling-machine"] = crafter_names,
        ["rocket-silo"] = crafter_names,
        ["container"] = {chest = "inventory"},
        ["logistic-container"] = {chest = "inventory"},
        ["cargo-wagon"] = {cargo_wagon = "inventory"},
    }
    local always_listed = {
        fuel = true, burnt_result = true, inventory = true, turret_ammo = true,
        lab_input = true, lab_modules = true,
        furnace_source = true, furnace_result = true, furnace_modules = true,
        assembling_machine_input = true, assembling_machine_output = true,
        assembling_machine_modules = true,
    }
    local renames = fle_inventory_names[entity.type] or {}
    for index = 1, entity.get_max_inventory_index() do
        local inventory = entity.get_inventory(index)
        if inventory then
            local inv_name = entity.get_inventory_name(index)
            if inv_name then
                inv_name = renames[inv_name] or inv_name
                local contents = storage.utils.get_contents_compat(inventory)
                if always_listed[inv_name] or next(contents) ~= nil then
                    serialized[inv_name] = contents
                end
            end
        end
    end

    -- Add dimensions of the entity
    local prototype = prototypes.entity[entity.name]
    local collision_box = prototype.collision_box
    serialized.dimensions = {
        width = math.abs(collision_box.right_bottom.x - collision_box.left_top.x),
        height = math.abs(collision_box.right_bottom.y - collision_box.left_top.y),
    }
    serialized.neighbours = serialize_neighbours(entity)

    -- Add input and output locations if the entity is a transport belt
    if entity.type == "transport-belt" or entity.type == "underground-belt" then
        local x, y = entity.position.x, entity.position.y

        -- Initialize positions with default offsets based on belt direction
        local input_offset = {
            [defines.direction.north] = {x = 0, y = 1},
            [defines.direction.south] = {x = 0, y = -1},
            [defines.direction.east] = {x = -1, y = 0},
            [defines.direction.west] = {x = 1, y = 0}
        }

        local output_offset = {
            [defines.direction.north] = {x = 0, y = -1},
            [defines.direction.south] = {x = 0, y = 1},
            [defines.direction.east] = {x = 1, y = 0},
            [defines.direction.west] = {x = -1, y = 0}
        }

        -- Set input position based on upstream connections
        local input_pos = {x = x, y = y}
        if #entity.belt_neighbours["inputs"] > 0 then
            -- Use the position of the first connected input belt (check validity first)
            local input_belt = entity.belt_neighbours["inputs"][1]
            if input_belt and input_belt.valid then
                input_pos = {x = input_belt.position.x, y = input_belt.position.y}
            else
                -- Fallback to default offset if neighbor is invalid
                local offset = input_offset[entity.direction]
                input_pos.x = x + offset.x
                input_pos.y = y + offset.y
            end
        else
            -- No input connection, use default offset
            local offset = input_offset[entity.direction]
            input_pos.x = x + offset.x
            input_pos.y = y + offset.y
        end
        serialized.input_position = input_pos

        -- Set output position based on downstream connections
        local output_pos = {x = x, y = y}
        if #entity.belt_neighbours["outputs"] > 0 then
            -- Use the position of the first connected output belt (check validity first)
            local output_belt = entity.belt_neighbours["outputs"][1]
            if output_belt and output_belt.valid then
                output_pos = {x = output_belt.position.x, y = output_belt.position.y}
            else
                -- Fallback to default offset if neighbor is invalid
                local offset = output_offset[entity.direction]
                output_pos.x = x + offset.x
                output_pos.y = y + offset.y
            end
        else
            -- No output connection, use default offset
            local offset = output_offset[entity.direction]
            output_pos.x = x + offset.x
            output_pos.y = y + offset.y
        end
        serialized.output_position = output_pos

        -- Store the belt's own position
        serialized.position = {x = x, y = y}

        -- Handle belt contents and status
        local line1 = entity.get_transport_line(1)
        local line2 = entity.get_transport_line(2)

        -- Calculate if belt is full at the output
        local is_full = not line1.can_insert_at_back() and not line2.can_insert_at_back()

        serialized.belt_status = {
            status = is_full and "\"full_output\"" or "\"normal\""
        }

        -- Get and merge contents from both lines
        serialized.inventory = {}
        local line1_contents = storage.utils.get_contents_compat(line1)
        local line2_contents = storage.utils.get_contents_compat(line2)

        -- Set terminus and source flags based on connections
        serialized.is_terminus = #entity.belt_neighbours["outputs"] == 0
        serialized.is_source = #entity.belt_neighbours["inputs"] == 0

        serialized.inventory['left'] = {}
        serialized.inventory['right'] = {}

        -- Merge contents from both belt lines
        for item_name, count in pairs(line1_contents) do
            --serialized.inventory[item_name] = (serialized.inventory[item_name] or 0) + count
            serialized.inventory['left'][item_name] = (serialized.inventory[item_name] or 0) + count
        end
        for item_name, count in pairs(line2_contents) do
            --serialized.inventory[item_name] = (serialized.inventory[item_name] or 0) + count
            serialized.inventory['right'][item_name] = (serialized.inventory[item_name] or 0) + count
        end

        -- Add warning if belt is full
        if not serialized.warnings then
            serialized.warnings = {}
        end
        if is_full then
            table.insert(serialized.warnings, "Belt output is full")
        end

        -- Special handling for underground belts
        if entity.type == "underground-belt" then
            serialized.is_input = entity.belt_to_ground_type == "input"
            -- Check validity of underground belt neighbor before accessing properties
            local neighbour_valid = entity.neighbours ~= nil and entity.neighbours.valid
            if serialized.is_input then
                serialized.is_terminus = not neighbour_valid
            else
                serialized.is_source = not neighbour_valid
            end
            if neighbour_valid then
                serialized.connected_to = entity.neighbours.unit_number
            end
        end
    end

    serialized.id = entity.unit_number
    -- Power poles: the summary of the pole's electric network (what the pole's
    -- GUI shows). flow_rate is the network's consumption in W (5 s average);
    -- it used to be the energy consumed since the game started, in J.
    if entity.type == "electric-pole" then
        local ok, summaries = pcall(storage.utils.electric_network_summaries, entity.surface, entity.force)
        local summary = ok and summaries and entity.electric_network_id and summaries[entity.electric_network_id]
        if summary then
            serialized.flow_rate = summary.consumption
            serialized.network = summary
        else
            serialized.flow_rate = 0
        end
    end

    -- Add input and output positions if the entity is a splitter
    if entity.type == "splitter" then
        -- Initialize positions based on entity center
        local x, y = entity.position.x, entity.position.y

        -- Calculate the offset for left/right positions (0.5 tiles)
        local lateral_offset = 0.5

        if entity.direction == defines.direction.north then
            -- Input positions (south side)
            serialized.input_positions = {
                {x = x - lateral_offset, y = y + 1},
                {x = x + lateral_offset, y = y + 1}
            }
            -- Output positions (north side)
            serialized.output_positions = {
                {x = x - lateral_offset, y = y - 1},
                {x = x + lateral_offset, y = y - 1}
            }
        elseif entity.direction == defines.direction.south then
            -- Input positions (north side)
            serialized.input_positions = {
                {x = x + lateral_offset, y = y - 1},
                {x = x - lateral_offset, y = y - 1}
            }
            -- Output positions (south side)
            serialized.output_positions = {
                {x = x + lateral_offset, y = y + 1},
                {x = x - lateral_offset, y = y + 1}
            }
        elseif entity.direction == defines.direction.east then
            -- Input positions (west side)
            serialized.input_positions = {
                {x = x - 1, y = y - lateral_offset},
                {x = x - 1, y = y + lateral_offset}
            }
            -- Output positions (east side)
            serialized.output_positions = {
                {x = x + 1, y = y - lateral_offset},
                {x = x + 1, y = y + lateral_offset}
            }
        elseif entity.direction == defines.direction.west then
            -- Input positions (east side)
            serialized.input_positions = {
                {x = x + 1, y = y + lateral_offset},
                {x = x + 1, y = y - lateral_offset}
            }
            -- Output positions (west side)
            serialized.output_positions = {
                {x = x - 1, y = y + lateral_offset},
                {x = x - 1, y = y - lateral_offset}
            }
        end

        -- Get the contents of both output lines
        serialized.inventory = {
            storage.utils.get_contents_compat(entity.get_transport_line(1)),
            storage.utils.get_contents_compat(entity.get_transport_line(2))
        }
    end

    -- Add input and output locations if the entity is an inserter
    if entity.type == "inserter" then
        serialized.pickup_position = entity.pickup_position
        serialized.drop_position = entity.drop_position

        ---- round to the nearest 0.5
        serialized.pickup_position.x = math.round(serialized.pickup_position.x * 2 ) / 2
        serialized.pickup_position.y = math.round(serialized.pickup_position.y * 2 ) / 2
        serialized.drop_position.x = math.round(serialized.drop_position.x * 2 ) / 2
        serialized.drop_position.y = math.round(serialized.drop_position.y * 2 ) / 2

        -- if pickup_position is nil, compute it from the entity's position and direction
        if not serialized.pickup_position then
            --local direction = entity.direction
            local x, y = entity.position.x, entity.position.y
            if entity.direction == defines.direction.north then
                serialized.pickup_position = {x = x, y = y - 1}
            elseif entity.direction == defines.direction.south then
                serialized.pickup_position = {x = x, y = y + 1}
            elseif entity.direction == defines.direction.east then
                serialized.pickup_position = {x = x + 1, y = y}
            elseif entity.direction == defines.direction.west then
                serialized.pickup_position = {x = x - 1, y = y}
            end
        end

        -- What the inserter takes from and drops into, and what it holds. The game's
        -- pickup_target / drop_target first; when unset (e.g. not yet updated), the
        -- belt or inventory entity at that position. nil: ground or nothing usable.
        local function target_name(getter, pos)
            local ok, target = pcall(getter)
            if ok and target and target.valid then
                return target.name
            end
            if pos then
                for _, e in pairs(entity.surface.find_entities_filtered{position = pos, limit = 5}) do
                    -- only what an inserter can use: belts, or anything with an inventory
                    if e.valid and e ~= entity and (e.type == "transport-belt" or e.type == "underground-belt"
                        or e.type == "splitter" or e.type == "loader" or e.type == "loader-1x1"
                        or (e.get_max_inventory_index() or 0) > 0) and e.type ~= "character" then
                        return e.name
                    end
                end
            end
            return nil
        end
        local pickup_name = target_name(function() return entity.pickup_target end, serialized.pickup_position)
        local drop_name = target_name(function() return entity.drop_target end, serialized.drop_position)
        if pickup_name then serialized.pickup_target = "\""..pickup_name.."\"" end
        if drop_name then serialized.drop_target = "\""..drop_name.."\"" end
        local ok_held, held = pcall(function() return entity.held_stack end)
        if ok_held and held and held.valid_for_read then
            serialized.held_item = {name = "\""..held.name.."\"", count = held.count}
        end

        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end
    end

    -- Pipes and pipes-to-ground. Factorio 2.0 joins connected pipes into one
    -- fluid segment and has no per-pipe flow reading (LuaFluidBox.get_flow was
    -- removed), so no flow_rate is reported. What the game shows for a pipe:
    -- its fluid, the amount in this pipe out of its capacity, the temperature,
    -- and the segment it belongs to (contents = the whole segment's amount,
    -- including fluidboxes of machines on the segment).
    if entity.type == "pipe" or entity.type == "pipe-to-ground" then
        serialized.connections = {}
        for _, connection in pairs(entity.fluidbox.get_pipe_connections(1)) do
            table.insert(serialized.connections, connection.position)
        end
        local fluid_name = nil
        local contents_count = 0
        -- Factorio 2.0: get_fluid_system_contents -> get_fluid_segment_contents
        local segment_contents = entity.fluidbox.get_fluid_segment_contents(1)
        if segment_contents then
            for name, count in pairs(segment_contents) do
                contents_count = contents_count + count
                fluid_name = "\""..name.."\""
            end
        end
        serialized.contents = contents_count
        serialized.fluid = fluid_name
        -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id
        serialized.fluidbox_id = entity.fluidbox.get_fluid_segment_id(1)
        local own = entity.fluidbox[1]
        serialized.amount = own and own.amount or 0
        -- get_capacity(1) of a pipe is its whole segment's capacity in 2.0;
        -- the pipe itself holds its fluidbox prototype's volume
        serialized.capacity = storage.utils.fluidbox_volume(entity.fluidbox, 1)
        if own then
            serialized.temperature = own.temperature
            serialized.fluid = "\""..own.name.."\""
        end
    end

    -- Pumps and offshore pumps: fluid moved in the last tick, per second
    if entity.type == "pump" or entity.type == "offshore-pump" then
        local ok, pumped = pcall(function() return entity.pumped_last_tick end)
        if ok and pumped then
            serialized.flow_rate = pumped * 60
        end
    end

    -- Add input and output locations if the entity is a pump
    -- Factorio 2.0: get_connections returns LuaFluidBox[] (no position), and an
    -- unconnected pump has none. Read the pipe connections of the pump's single
    -- fluidbox instead; target_position is the tile a pipe connects from.
    if entity.type == "pump" then
        local ok, connections = pcall(function()
            return entity.fluidbox.get_pipe_connections(1)
        end)
        if ok and connections then
            for _, connection in pairs(connections) do
                local target = connection.target_position
                if target then
                    if connection.flow_direction == "input" then
                        serialized.input_position = {x = target.x, y = target.y}
                    elseif connection.flow_direction == "output" then
                        serialized.output_position = {x = target.x, y = target.y}
                    end
                end
            end
        end
    end

    -- Add the current research to the lab
    if entity.name == "lab" then
        if storage.agent_characters[1].force.current_research ~= nil then
            -- quoted like every other string field, so names with a hyphen
            -- (logistic-science-pack) parse
            serialized.research = "\"" .. storage.agent_characters[1].force.current_research.name .. "\""
        else
            serialized.research = nil
        end
    end

    -- Add input and output locations if the entity is a offshore pump
    if entity.type == "offshore-pump" then
        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end
    end


    if entity.name == "oil-refinery" then
        local x, y = entity.position.x, entity.position.y
        serialized.input_connection_points = {}
        serialized.output_connection_points = {}

        local recipe = entity.get_recipe()
        local mappings = storage.utils.get_refinery_fluid_mappings(entity, recipe)
        if mappings then
            serialized.input_connection_points = mappings.inputs
            serialized.output_connection_points = mappings.outputs
        end
    end

    if entity.name == "chemical-plant" then
        local x, y = entity.position.x, entity.position.y
        serialized.input_connection_points = {}
        serialized.output_connection_points = {}

        local recipe = entity.get_recipe()
        local mappings = storage.utils.get_chemical_plant_fluid_mappings(entity, recipe)
        if mappings then
            serialized.input_connection_points = mappings.inputs
            serialized.output_connection_points = mappings.outputs
        end

        -- Filter out any invalid connection points
        local filtered_input_points = {}
        for _, point in ipairs(serialized.input_connection_points) do
            if is_valid_connection_point(game.surfaces[1], point) then
                table.insert(filtered_input_points, point)
            end
        end
        serialized.input_connection_points = filtered_input_points

        -- Filter out any invalid connection points
        local filtered_output_points = {}
        for _, point in ipairs(serialized.output_connection_points) do
            if is_valid_connection_point(game.surfaces[1], point) then
                table.insert(filtered_output_points, point)
            end
        end
        serialized.output_connection_points = filtered_output_points

    end


    -- The fluids the set recipe takes and makes (MultiFluidHandler.input_fluids / output_fluids), from the
    -- recipe itself; both empty while no recipe is set
    if entity.name == "oil-refinery" or entity.name == "chemical-plant" then
        -- (their type is assembling-machine, so the fluid handler block below does not run for them)
        pcall(function()
            local ids = storage.utils.fluid_system_ids(entity)
            if #ids > 0 then serialized.fluid_systems = ids end
        end)
        pcall(function()
            local recipe = entity.get_recipe()
            if not recipe then return end
            local ins, outs = {}, {}
            for _, ing in pairs(recipe.ingredients or {}) do
                if ing.type == "fluid" then table.insert(ins, "\"" .. ing.name .. "\"") end
            end
            for _, prod in pairs(recipe.products or {}) do
                if prod.type == "fluid" then table.insert(outs, "\"" .. prod.name .. "\"") end
            end
            -- (an empty Lua table would be read back as a dict, not a list: left unset, the field stays [])
            if #ins > 0 then serialized.input_fluids = ins end
            if #outs > 0 then serialized.output_fluids = outs end
        end)
    end

    if entity.type == "storage-tank" then
        -- Get and filter connection points
        local connection_points = storage.utils.get_storage_tank_connection_points(entity)
        local filtered_points = {}

        -- Filter out invalid connection points (e.g., those in water)
        for _, point in ipairs(connection_points) do
            if is_valid_connection_point(entity.surface, point) then
                table.insert(filtered_points, point)
            end
        end

        -- Add connection points to serialized data
        serialized.connection_points = filtered_points

        -- Add fluid box information
        if entity.fluidbox and #entity.fluidbox > 0 then
            game.print("There is a fluidbox")
            local fluid = entity.fluidbox[1]
            if fluid then
                serialized.fluid = string.format("\"%s\"", fluid.name)
                serialized.fluid_amount = fluid.amount
                serialized.fluid_temperature = fluid.temperature
                -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id
                serialized.fluid_system_id = entity.fluidbox.get_fluid_segment_id(1)
            end
        end

        -- Add warning if some connection points were filtered
        if #filtered_points < #connection_points then
            if not serialized.warnings then
                serialized.warnings = {}
            end
            table.insert(serialized.warnings, "\"some connection points were filtered due to being blocked by water\"")
        end
    end


    if entity.type == "assembling-machine" and entity.name ~= "oil-refinery" and entity.name ~= "chemical-plant" then
        -- Read the ports from the game (LuaFluidBox.get_pipe_connections): the tile a
        -- pipe must occupy for each active fluid box. An assembling machine's fluid
        -- boxes are only active while its recipe uses a fluid, so a machine with no
        -- fluid recipe has no connection points. Inputs come first, then outputs.
        local ok, ports = pcall(read_assembler_fluid_ports, entity)
        if ok and ports then
            serialized.connection_points = ports.all
            -- connection_points is filtered for water with every other entity's below
            local function on_land(points)
                local kept = {}
                for _, point in ipairs(points) do
                    if is_valid_connection_point(entity.surface, point) then
                        table.insert(kept, point)
                    end
                end
                return kept
            end
            serialized.input_connection_points = on_land(ports.inputs)
            serialized.output_connection_points = on_land(ports.outputs)
        else
            serialized.connection_points = {}
        end
    end
    -- Add tile dimensions of the entity
    serialized.tile_dimensions = {
        tile_width = prototype.tile_width,
        tile_height = prototype.tile_height,
    }

    if entity.type == "mining-drill" then
        serialized.drop_position = {
            x = entity.drop_position.x,
            y = entity.drop_position.y
        }
        serialized.drop_position.x = math.round(serialized.drop_position.x * 2) / 2
        serialized.drop_position.y = math.round(serialized.drop_position.y * 2) / 2
        -- game.print("Mining drill drop position: " .. serpent.line(serialized.drop_position))

        -- Get the mining area
        local prototype = prototypes.entity[entity.name]
        local mining_area = 1
        if prototype.mining_drill_radius then
            mining_area = prototype.mining_drill_radius * 2
        end

        local position = entity.position

        -- Initialize resources table
        serialized.resources = {}

        -- Calculate the area to check based on mining drill radius
        local start_x = position.x - mining_area/2
        local start_y = position.y - mining_area/2
        local end_x = position.x + mining_area/2
        local end_y = position.y + mining_area/2

        local resources = game.surfaces[1].find_entities_filtered{
            area = {{start_x, start_y}, {end_x, end_y}},
            type = "resource",
        }

        for _, resource in pairs(resources) do
            -- Check resource validity before accessing properties
            if resource.valid then
                if not serialized.resources[resource.name] then
                    serialized.resources[resource.name] = {
                        name = "\""..resource.name.."\"",
                        count = 0,
                    }
                end

                -- Add the resource amount and position
                serialized.resources[resource.name].count = serialized.resources[resource.name].count + resource.amount
                -- Fluid wells (crude oil): amount is a yield (normal_resource_amount
                -- = 100%), so also report the fluid per second at this drill's base
                -- mining speed (no mining productivity)
                if resource.prototype.infinite_resource then
                    local mp = resource.prototype.mineable_properties
                    local per_second = (prototype.mining_speed or 1) * ((mp.products[1].amount or 1) / mp.mining_time)
                        * resource.amount / resource.prototype.normal_resource_amount
                    serialized.output_per_second = (serialized.output_per_second or 0) + per_second
                end
            end
        end
        if serialized.output_per_second then
            serialized.output_per_second = math.floor(serialized.output_per_second * 100 + 0.5) / 100
        end


        -- Convert resources table to array for consistent ordering
        local resources_array = {}
        for _, resource_data in pairs(serialized.resources) do
            table.insert(resources_array, resource_data)
        end
        serialized.resources = resources_array

        -- Add mining status
        if #resources_array == 0 then
            serialized.status = "\"no_minable_resources\""
            if not serialized.warnings then serialized.warnings = {} end
            table.insert(serialized.warnings, "\"nothing to mine\"")
        end

        -- Add burner info if applicable
        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end
    end

    -- Add recipes if the entity is a crafting machine
    if entity.type == "assembling-machine" or entity.type == "furnace" then
        if entity.get_recipe() then
            serialized.recipe = storage.utils.serialize_recipe(entity.get_recipe())
        end
    end

    -- Add fluid input point if the entity is a boiler
    if entity.type == "boiler" then
        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end

        --local direction = entity.direction
        local x, y = entity.position.x, entity.position.y

        if entity.direction == defines.direction.north then
            -- game.print("Boiler direction is north")
            serialized.connection_points = {{x = x - 2, y = y + 0.5}, {x = x + 2, y = y + 0.5}}
            serialized.steam_output_point = {x = x, y = y - 1.5}
        elseif entity.direction == defines.direction.south then
            -- game.print("Boiler direction is south")
            serialized.connection_points = {{x = x - 2, y = y - 0.5}, {x = x + 2, y = y - 0.5}}
            serialized.steam_output_point = {x = x, y = y + 1.5}
        elseif entity.direction == defines.direction.east then
            -- game.print("Boiler direction is east")
            serialized.connection_points = {{x = x - 0.5, y = y - 2}, {x = x - 0.5, y = y + 2}}
            serialized.steam_output_point = {x = x + 1.5, y = y}
        elseif entity.direction == defines.direction.west then
            -- game.print("Boiler direction is west")
            serialized.connection_points = {{x = x + 0.5, y = y - 2}, {x = x + 0.5, y = y + 2}}
            serialized.steam_output_point = {x = x - 1.5, y = y}
        end
    end

    if entity.type == "rocket-silo" then
        -- Basic rocket silo properties
        serialized.rocket_parts = 0  -- Will be updated with actual count
        serialized.rocket_progress = 0.0  -- Will be updated with actual progress
        -- Factorio 2.0: launch_count removed (no longer available on LuaEntity)

        -- Get part construction progress using the direct entity property (Factorio 2.0 compatible)
        serialized.rocket_parts = entity.rocket_parts or 0
        local parts_required = entity.prototype.rocket_parts_required or 100
        serialized.rocket_progress = (serialized.rocket_parts / parts_required) * 100.0

        -- Get input inventories for rocket components
        local rocket_inventory = {
            rocket_part = entity.get_inventory(defines.inventory.rocket_silo_input),
            result = entity.get_inventory(defines.inventory.rocket_silo_output)
        }

        -- Serialize the component inventories
        for name, inventory in pairs(rocket_inventory) do
            if inventory and not inventory.is_empty() then
                serialized[name .. "_inventory"] = storage.utils.get_contents_compat(inventory)
            end
        end

        -- The rocket's payload slot (defines.inventory.rocket_silo_rocket)
        pcall(function()
            local inv = entity.get_inventory(defines.inventory.rocket_silo_rocket)
            if inv and not inv.is_empty() then
                serialized.rocket_inventory = storage.utils.get_contents_compat(inv)
            end
        end)

        -- The silo's own state (entity.rocket_silo_status, by its defines name, e.g. "rocket_ready") and the
        -- entity status it means: a rocket that is ready waits to be launched, a launch in progress is launching
        local silo_state = nil
        pcall(function()
            local st = entity.rocket_silo_status
            for k, v in pairs(defines.rocket_silo_status) do
                if v == st then silo_state = k; break end
            end
        end)
        if silo_state then
            serialized.rocket_silo_status = "\"" .. silo_state .. "\""
            local launching = {launch_starting = true, engine_starting = true, arms_retract = true,
                rocket_flying = true, lights_blinking_close = true, doors_closing = true, launch_started = true}
            local raising = {create_rocket = true, lights_blinking_open = true, doors_opening = true,
                doors_opened = true, rocket_rising = true, arms_advance = true}
            if silo_state == "rocket_ready" then
                serialized.status = "\"waiting_to_launch_rocket\""
            elseif launching[silo_state] then
                serialized.status = "\"launching_rocket\""
            elseif raising[silo_state] then
                serialized.status = "\"preparing_rocket_for_launch\""
            end
        end
        if serialized.rocket_parts < parts_required and serialized.rocket_parts > 0
            and (silo_state == nil or silo_state == "building_rocket")
            and (entity.status == defines.entity_status.working or entity.status == defines.entity_status.normal) then
            serialized.status = "\"preparing_rocket_for_launch\""
        end

        -- Add warnings based on state
        if not serialized.warnings then
            serialized.warnings = {}
        end
        if serialized.status == "\"preparing_rocket_for_launch\"" and serialized.rocket_parts < parts_required
            and serialized.rocket_parts > 0 then
            table.insert(serialized.warnings, "\"waiting for rocket parts\"")
        elseif serialized.status == "\"waiting_to_launch_rocket\"" then
            table.insert(serialized.warnings, "\"ready to launch\"")
        end
    end

    -- Factorio 2.0: solar panels no longer have electric_output_flow_limit property
    -- Solar panel power output is now determined by prototype settings (performance_at_day/night)

    if entity.type == 'accumulator' then
        --serialized.energy_source = entity.energy_source
        --serialized.power_usage = entity.power_usage
        --serialized.emissions = entity.emissions
        serialized.energy = entity.energy
    end

    if entity.type == "generator" then
        serialized.connection_points = storage.utils.get_generator_connection_positions(entity)
        serialized.energy_generated_last_tick = entity.energy_generated_last_tick
        --serialized.power_production = entity.power_production
    end

    if entity.name == "pumpjack" then
        serialized.connection_points = storage.utils.get_pumpjack_connection_points(entity)
    end

    -- Add fuel and input ingredients if the entity is a furnace or burner
    if entity.type == "furnace" or entity.type == "burner" then
        local burner = entity.burner
        if burner then
            add_burner_inventory(serialized, burner)
        end
        local input_inventory = entity.get_inventory(defines.inventory.furnace_source)
        if input_inventory and #input_inventory > 0 then
            serialized.input_inventory = {}
            for i = 1, #input_inventory do
                local item = input_inventory[i]
                if item and item.valid_for_read then
                    table.insert(serialized.input_inventory, {name = "\""..item.name.."\"", count = item.count})
                end
            end
        end
    end

    -- Add fluid box if the entity is an offshore pump
    if entity.type == "offshore-pump" then
        serialized.connection_points = storage.utils.get_offshore_pump_connection_points(entity)
    end

    -- If entity has a fluidbox
    if entity.fluidbox then
        local fluid_box = entity.fluidbox
        if fluid_box and #fluid_box > 0 then
            serialized.fluid_box = {}
            for i = 1, #fluid_box do
                -- game.print("Fluid!")
                local fluid = fluid_box[i]
                if fluid then
                    -- index: the fluidbox number; capacity and type (input /
                    -- output / input-output) as the game reports them
                    local box = {index = i, name = "\""..fluid.name.."\"", amount = fluid.amount, temperature = fluid.temperature}
                    box.capacity = storage.utils.fluidbox_volume(fluid_box, i)
                    pcall(function()
                        box.type = "\""..fluid_box.get_prototype(i).production_type.."\""
                    end)
                    table.insert(serialized.fluid_box, box)
                end
            end
        end
    end

    -- Add fluid handler status check
    if is_fluid_handler(entity.type) then
        -- Check if the entity has a fluidbox
        if not entity.fluidbox or #entity.fluidbox == 0 then
            serialized.status = "\"not_connected\""
            if not serialized.warnings then
                serialized.warnings = {}
            end
            table.insert(serialized.warnings, "\"missing fluid connection\"")
        else
            -- Additional fluid-specific checks
            -- every fluid box's segment id (each id once, in fluid box order), whether or not the box holds
            -- fluid now; `fluid` is the first fluid found in any box
            local fluid_systems = {}
            local has_fluid = false
            local fluid_contents = nil
            fluid_systems = storage.utils.fluid_system_ids(entity)
            for i = 1, #entity.fluidbox do
                if entity.fluidbox[i] and not has_fluid then
                    has_fluid = true
                    fluid_contents =  "\""..entity.fluidbox[i].name.."\""
                end
            end
            serialized.fluid_systems = fluid_systems

            if not has_fluid then
                -- empty: NOT_CONNECTED only when no fluid box of it connects to anything; a connected but empty
                -- entity keeps the game's own status (e.g. no_input_fluid)
                local connected = false
                for i = 1, #entity.fluidbox do
                    local ok_c, conns = pcall(entity.fluidbox.get_connections, i)
                    if ok_c and conns and #conns > 0 then connected = true; break end
                end
                if not serialized.warnings then
                    serialized.warnings = {}
                end
                if not connected then
                    serialized.status = "\"not_connected\""
                    table.insert(serialized.warnings, "\"no fluid present in connections\"")
                elseif entity.type == "generator" then
                    local d = storage.utils.no_steam_detail(entity)
                    if d then serialized.status_detail = "\"" .. d .. "\"" end
                end
            else
                serialized.fluid = fluid_contents
            end
            --serialized.fluidbox = serialize_fluidbox(entity.fluidbox)
        end
    end

    if entity.electric_network_id then
        serialized.electrical_id = entity.electric_network_id
    end

    serialized.direction = get_inverse_entity_direction(entity.name, entity.direction) --api_direction_map[entity.direction]
    -- Post-process connection points if they exist
    if serialized.connection_points then
        local filtered_points = {}
        for _, point in ipairs(serialized.connection_points) do
            if is_valid_connection_point(game.surfaces[1], point) then
                table.insert(filtered_points, point)
            end
        end

        -- Update connection points or remove if all were filtered
        if #filtered_points > 0 then
            serialized.connection_points = filtered_points
        else
            serialized.connection_points = nil
        end

        -- Add warning if points were filtered
        if not serialized.warnings then
            serialized.warnings = {}
        end

        if serialized.connection_points ~= nil then
            if #filtered_points < #serialized.connection_points then
                table.insert(serialized.warnings, "\"some connection points were filtered due to being blocked by water\"")
            end
        end
    end

    -- Handle special case for boilers which have separate steam output points
    if serialized.steam_output_point then
        if not is_valid_connection_point(game.surfaces[1], serialized.steam_output_point) then
            serialized.steam_output_point = nil
            if not serialized.warnings then
                serialized.warnings = {}
            end
            table.insert(serialized.warnings, "\"steam output point was filtered due to being blocked by water\"")
        end
    end

    local detail = storage.utils.status_detail(entity)
    if detail and not serialized.status_detail then
        serialized.status_detail = "\"" .. detail .. "\""
    end

    return serialized
end
