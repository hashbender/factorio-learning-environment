-- connect_entities

local MAX_SERIALIZATION_ITERATIONS = 1000  -- Maximum iterations for serializing belt groups
local MAX_PLACEMENT_ATTEMPTS = 50  -- Maximum attempts to find placeable positions
local MAX_PATH_LENGTH = 1000  -- Maximum number of path points to process
local MAX_STRAIGHT_SECTIONS = 100
local MAX_UNDERGROUND_SEGMENTS = 50

-- Wire reach values for different electric pole types
local wire_reach = {
    ['small-electric-pole'] = 7.5,
    ['medium-electric-pole'] = 9,
    ['big-electric-pole'] = 30,
    ['substation'] = 18
}

local default_connect_types = {
    ['pipe-to-ground'] = 'pipe',
    ['underground-belt'] = 'transport-belt',
    ['express-underground-belt'] = 'express-transport-belt',
    ['fast-underground-belt'] = 'fast-transport-belt',
}

local underground_ranges = {
    ['pipe-to-ground'] = 8,
    ['underground-belt'] = 4,
    ['fast-underground-belt'] = 4,
    ['express-underground-belt'] = 4
}

local function is_within_pole_range(position, pole)
    local dx = position.x - pole.position.x
    local dy = position.y - pole.position.y
    local wire_reach = wire_reach[pole.name] or 4
    return (dx * dx + dy * dy) <= wire_reach * wire_reach
end

local function get_electric_network_at_position(position)
    -- Get all electric poles near the position
    local nearby_poles = game.surfaces[1].find_entities_filtered{
        position = position,
        radius = 9, -- Maximum pole reach is 9 for medium poles
        type = "electric-pole"
    }

    -- Check if any pole's wire reaches this position
    for _, pole in pairs(nearby_poles) do
        if is_within_pole_range(position, pole) then
            return pole.electric_network_id
        end
    end
    return nil
end

local function are_positions_in_same_network(pos1, pos2)
    local network1 = get_electric_network_at_position(pos1)
    local network2 = get_electric_network_at_position(pos2)
    return network1 and network2 and network1 == network2
end

local function is_position_saturated(position, reach)
    -- Get nearby poles
    local nearby_poles = game.surfaces[1].find_entities_filtered{
        position = position,
        radius = 9,
        type = "electric-pole"
    }

    -- Check each corner of a 1x1 tile centered on the position
    local corners = {
        {x = position.x - reach/2, y = position.y - reach/2},
        {x = position.x - reach/2, y = position.y + reach/2},
        {x = position.x + reach/2, y = position.y + reach/2},
        {x = position.x + reach/2, y = position.y - reach/2}
    }

    -- For each corner, check if it's within range of any existing pole
    for _, corner in pairs(corners) do
        local corner_covered = false
        for _, pole in pairs(nearby_poles) do
            if is_within_pole_range(corner, pole) then
                corner_covered = true
                break
            end
        end
        if not corner_covered then
            return false -- Found an uncovered corner
        end
    end

    return true -- All corners are covered
end


function get_step_size(connection_type)
    return wire_reach[connection_type] or 1
end

function math.round(x)
    return x >= 0 and math.floor(x + 0.5) or math.ceil(x - 0.5)
end

local function has_valid_fluidbox(entity)
    -- Factorio 2.0: fluidbox methods are on the LuaFluidBox object, not individual elements
    -- Also: get_fluid_system_id -> get_fluid_segment_id
    return entity.fluidbox and #entity.fluidbox > 0 and entity.fluidbox[1] and entity.fluidbox.get_fluid_segment_id
end

-- The fluid segment ids of every fluid box of an entity (a refinery's or chemical plant's matching fluid
-- need not be in box 1)
local function fluid_segment_ids(entity)
    local ids = {}
    if not (entity and entity.valid and entity.fluidbox) then return ids end
    for i = 1, #entity.fluidbox do
        local ok, id = pcall(entity.fluidbox.get_fluid_segment_id, i)
        if ok and id then ids[id] = true end
    end
    return ids
end

local function are_fluidboxes_connected(entity1, entity2)
    local ids2 = fluid_segment_ids(entity2)
    for id in pairs(fluid_segment_ids(entity1)) do
        if ids2[id] then return true end
    end
    return false
end

-- Calculate maximum possible underground sections based on inventory
local function calculate_max_underground_sections(player, underground_type)
    local available_count = 0
    for _, inv in pairs({defines.inventory.character_main}) do
        if player.get_inventory(inv) then
            available_count = available_count + player.get_inventory(inv).get_item_count(underground_type)
        end
    end
    -- Each underground section requires 2 entities (entrance and exit)
    return math.floor(available_count / 2)
end

-- Helper function to check if an entity type is an underground variant
local function is_underground_type(entity_type)
    return underground_ranges[entity_type] ~= nil
end

-- Modified split_section_into_underground_segments to respect inventory limits
local function split_section_into_underground_segments(section, path, range, max_segments)
    local segments = {}

    -- Add margin of 1 at start and end of section
    local effective_start = section.start_index + 1
    local effective_end = section.end_index - 1

    -- Check if section is still long enough after adding margins
    if effective_end - effective_start < 2 then
        return segments  -- Return empty segments if section is too short
    end

    local current_start = effective_start
    local segment_count = 0
    local iteration_count = 0
    local MAX_ITERATIONS = math.min(section.length * 2, MAX_UNDERGROUND_SEGMENTS) -- Prevent excessive iterations


    while current_start + 1 < effective_end and segment_count < max_segments do
        iteration_count = iteration_count + 1
        if iteration_count > MAX_ITERATIONS then
            -- game.print("Warning: Maximum iterations reached while splitting underground segments")
            break
        end
        -- Calculate end index for this segment
        local end_index = math.min(current_start + range, effective_end)

        -- Only create segment if there's at least 1 tile gap between entrance and exit
        if end_index > current_start then
            table.insert(segments, {
                entrance_index = current_start,
                exit_index = end_index,
                direction = section.direction
            })

            segment_count = segment_count + 1

            -- Move to position after the exit for next iteration
            current_start = end_index + 1
        else
            -- If we can't create a valid segment, move forward
            current_start = current_start + 1
        end
    end


    return segments
end

-- Find straight sections in path suitable for underground entities
local function find_straight_sections(path, min_length)
    local sections = {}
    local current_section = {
        start_index = 1,
        direction = nil,
        length = 0
    }

    for i = 1, #path - 1 do --Always start slightly into the path, and away from the end to prevent connection issues.
        local current_pos = path[i].position
        local next_pos = path[i + 1].position
        local dx = next_pos.x - current_pos.x
        local dy = next_pos.y - current_pos.y
        local current_direction = {dx = dx, dy = dy}

        -- Normalize direction
        if math.abs(dx) > math.abs(dy) then
            current_direction = {dx = dx/math.abs(dx), dy = 0}
        else
            current_direction = {dx = 0, dy = dy/math.abs(dy)}
        end

        if not current_section.direction then
            current_section.direction = current_direction
        end

        -- Check if we're still going in the same direction
        if current_section.direction.dx == current_direction.dx and
           current_section.direction.dy == current_direction.dy then
            current_section.length = current_section.length + 1
        else
            -- Direction changed, check if previous section was long enough
            if current_section.length >= min_length then
                table.insert(sections, {
                    start_index = current_section.start_index,
                    end_index = i,
                    direction = current_section.direction,
                    length = current_section.length
                })
            end
            -- Start new section
            current_section = {
                start_index = i,
                direction = current_direction,
                length = 1
            }
        end
    end

    -- Check final section
    if current_section.length >= min_length then
        table.insert(sections, {
            start_index = current_section.start_index,
            end_index = #path,
            direction = current_section.direction,
            length = current_section.length
        })
    end

    return sections
end

-- Helper function to serialize a belt group using proper BFS
local function serialize_belt_group(entity)
    if not entity or not entity.valid or entity.type ~= "transport-belt" then
        return nil
    end

    local serialized = {}
    local visited = {}
    local queue = {entity}
    local max_search = 500 -- Prevent infinite loops
    local search_count = 0

    while #queue > 0 and search_count < max_search do
        search_count = search_count + 1
        local current_belt = table.remove(queue, 1)
        
        if not current_belt or not current_belt.valid then
            goto continue
        end
        
        local belt_id = current_belt.unit_number
        if visited[belt_id] then
            goto continue
        end
        visited[belt_id] = true
        
        -- Serialize this belt
        table.insert(serialized, storage.utils.serialize_entity(current_belt))
        
        -- Add all neighboring belts to queue (both inputs and outputs)
        if current_belt.belt_neighbours then
            -- Add output belts
            if current_belt.belt_neighbours.outputs then
                for _, output_belt in pairs(current_belt.belt_neighbours.outputs) do
                    if output_belt and output_belt.valid and not visited[output_belt.unit_number] then
                        table.insert(queue, output_belt)
                    end
                end
            end
            -- Add input belts  
            if current_belt.belt_neighbours.inputs then
                for _, input_belt in pairs(current_belt.belt_neighbours.inputs) do
                    if input_belt and input_belt.valid and not visited[input_belt.unit_number] then
                        table.insert(queue, input_belt)
                    end
                end
            end
        end
        
        ::continue::
    end
    
    return serialized
end


local function are_poles_connected(entity1, entity2)
    if not (entity1 and entity2) then return false end
    if not (entity1.electric_network_id and entity2.electric_network_id) then return false end
    return entity1.electric_network_id == entity2.electric_network_id
end

local function is_placeable(position)
    local invalid_tiles = {
        ["water"] = true,
        ["deepwater"] = true,
        ["water-green"] = true,
        ["deepwater-green"] = true,
        ["water-shallow"] = true,
        ["water-mud"] = true,
    }

    local entities = game.surfaces[1].find_entities_filtered{
        position = position,
        -- Factorio 2.0: collision_mask expects a collision layer name string
        collision_mask = "player"
    }
    if #entities == 1 then
        if entities[1].name == "character" then
            return not invalid_tiles[game.surfaces[1].get_tile(position.x, position.y).name]
        end
    end
    return #entities == 0 and not invalid_tiles[game.surfaces[1].get_tile(position.x, position.y).name]
end

local function find_placeable_neighbor(pos, previous_pos)
    local directions = {
        {dx = 0, dy = -1},  -- up
        {dx = 1, dy = 0},   -- right
        {dx = 0, dy = 1},   -- down
        {dx = -1, dy = 0}   -- left
    }

    if previous_pos then
        local desired_dx = pos.x - previous_pos.x
        local desired_dy = pos.y - previous_pos.y
        table.sort(directions, function(a, b)
            local a_score = math.abs(a.dx - desired_dx) + math.abs(a.dy - desired_dy)
            local b_score = math.abs(b.dx - desired_dx) + math.abs(b.dy - desired_dy)
            return a_score < b_score
        end)
    end

    for _, dir in ipairs(directions) do
        local test_pos = {x = pos.x + dir.dx, y = pos.y + dir.dy}
        if is_placeable(test_pos) then
            return test_pos
        end
    end
    return nil
end


local function interpolate_manhattan(pos1, pos2)
    local interpolated = {}
    local dx = pos2.x - pos1.x
    local dy = pos2.y - pos1.y
    local manhattan_distance = math.abs(dx) + math.abs(dy)
    -- game.print("Distance3 "..manhattan_distance)
    if manhattan_distance > 2 then
        local steps = math.max(math.abs(dx), math.abs(dy))
        local x_step = math.floor((dx / steps)*2)/2
        local y_step = math.floor((dy / steps)*2)/2

        for i = 1, steps - 1 do
            local new_pos_x = {x = pos1.x + math.round(x_step * i), y = pos1.y}
            if is_placeable(new_pos_x) then
                table.insert(interpolated, {position = new_pos_x})
            else
                local neighbor = find_placeable_neighbor(new_pos_x, pos1)
                if neighbor then
                    table.insert(interpolated, {position = neighbor})
                end
            end

            local new_pos_y = {x = pos1.x + math.round(x_step * i), y = pos1.y + math.round(y_step * i)}
            if is_placeable(new_pos_y) then
                table.insert(interpolated, {position = new_pos_y})
            else
                local neighbor = find_placeable_neighbor(new_pos_y, pos1)
                if neighbor then
                    table.insert(interpolated, {position = neighbor})
                end
            end
        end
        --elseif math.abs(dx) == 1 and math.abs(dy) == 1 then
        --    local mid_pos = {x = pos2.x, y = pos1.y}
        --    if is_placeable(mid_pos) then
        --        table.insert(interpolated, {position = mid_pos})
        --    else
        --        mid_pos = {x = pos1.x, y = pos2.y}
        --        if is_placeable(mid_pos) then
        --            table.insert(interpolated, {position = mid_pos})
        --        else
        --            mid_pos = find_placeable_neighbor(mid_pos, pos1)
        --            if mid_pos then
        --                table.insert(interpolated, {position = mid_pos})
        --            end
        --        end
        --    end
        --end
        elseif math.abs(dx) == 1 and math.abs(dy) == 1 then --and math.abs(dx) <= 1.5 and math.abs(dy) <= 1.5 then
            -- Try first horizontal then vertical movement
            local mid_pos = {x = pos2.x, y = pos1.y}
            if is_placeable(mid_pos) then
                table.insert(interpolated, {position = mid_pos})
            else
                -- Try vertical then horizontal movement
                mid_pos = {x = pos1.x, y = pos2.y}
                if is_placeable(mid_pos) then
                    table.insert(interpolated, {position = mid_pos})
                else
                    -- If neither orthogonal position works, try to find a neighbor
                    local neighbor = find_placeable_neighbor(mid_pos, pos1)
                    if neighbor then
                        table.insert(interpolated, {position = neighbor})
                    end
                end
            end

    end

    return interpolated
end



-- A dry run places nothing; it records what would be placed and where
local function planned_key(connection_type, position)
    return connection_type .. ":" .. position.x .. ":" .. position.y
end

-- The direction an entity placed facing `game_dir` has in the tool API (place_entity,
-- place_layout): get_entity_direction maps API directions to game directions and is
-- not the identity for every entity (pipe-to-ground is turned round), so the dry run
-- reports the API direction, which builds the same entity when passed back.
local function api_direction(name, game_dir)
    local ok, out = pcall(function()
        for _, d in ipairs({0, 4, 8, 12}) do
            if storage.utils.get_entity_direction(name, d) == game_dir then return d end
        end
        return game_dir
    end)
    if ok and out then return out end
    return game_dir
end
storage.utils.connect_api_direction = api_direction

local UNDERGROUND_NAMES = {["pipe-to-ground"] = true, ["underground-belt"] = true,
    ["fast-underground-belt"] = true, ["express-underground-belt"] = true}

local function record_planned(counter_state, connection_type, position, dir, is_underground_exit)
    if not counter_state.planned then counter_state.planned = {} end
    if not counter_state.planned_at then counter_state.planned_at = {} end
    counter_state.planned_at[planned_key(connection_type, position)] = true
    local entry = {
        name = "\"" .. connection_type .. "\"",
        x = position.x,
        y = position.y,
        direction = api_direction(connection_type, dir or 0)
    }
    if UNDERGROUND_NAMES[connection_type] then
        entry.type = is_underground_exit and "\"output\"" or "\"input\""
    end
    table.insert(counter_state.planned, entry)
end

-- Nothing is built from items the character does not hold
local function require_item(player, name, position)
    local inventory = player.get_inventory(defines.inventory.character_main)
    if not inventory or inventory.get_item_count(name) < 1 then
        error("\"No " .. name .. " in your inventory to place at (" .. position.x .. ", " .. position.y .. ")\"", 0)
    end
end

local function place_at_position(player, connection_type, current_position, dir, serialized_entities, dry_run, counter_state, is_underground_exit)

    local is_electric_pole = wire_reach[connection_type] ~= nil
    local placement_position = current_position
    local existing_entity = nil

    for _, entity in pairs(serialized_entities) do
        if entity.position.x == placement_position.x and entity.position.y == placement_position.y then
            return
        end
    end

    -- A route can pass the same tile twice (its first and last tile). The real pass
    -- finds the entity it has just placed there and places nothing more; the dry pass
    -- counts the tile once, so the count is the number of entities the real pass places.
    if dry_run and counter_state.planned_at
        and counter_state.planned_at[planned_key(connection_type, placement_position)] then
        return
    end

    if is_electric_pole then
        if is_position_saturated(current_position, wire_reach[connection_type]) then

            return -- No need to place another pole
        end

        placement_position = game.surfaces[1].find_non_colliding_position(connection_type, current_position, 2, 0.1)
        if not placement_position then
            error("Cannot find suitable position to place " .. connection_type)
        end
    else
        local entities = game.surfaces[1].find_entities_filtered{
            position = current_position,
            type = {"beam", "resource", "player"},
            invert=true

        }
        for _, entity in pairs(entities) do
            if entity.name == connection_type then
                existing_entity = entity
                break
            end
        end
    end

    if existing_entity then
        -- game.print("Existing entity "..existing_entity.name)
        -- Get the existing network ID before any modifications
        --local existing_network_id = has_valid_fluidbox(existing_entity) and existing_entity.fluidbox[1].get_fluid_system_id()

        -- Update direction if needed
        if existing_entity.name ~= connection_type then
            if existing_entity.direction ~= dir then
                existing_entity.direction = dir
            end
        end

        -- (Pipes next to each other join their fluid networks by themselves in
        -- Factorio 2.0; LuaEntity.connect_neighbour no longer exists.)

        -- Update or add to serialized list
        for i, serialized in ipairs(serialized_entities) do
            if serialized.position.x == current_position.x and serialized.position.y == current_position.y then
                serialized_entities[i] = storage.utils.serialize_entity(existing_entity)
                return existing_entity
            end
        end
        table.insert(serialized_entities, storage.utils.serialize_entity(existing_entity))
        return existing_entity

    else
        -- For underground entities, we need to set the correct type (input/output)
        local entity_variant = {
            name = connection_type,
            position = placement_position,
            direction = dir,
            force = player.force,
            type = is_underground_exit and "output" or "input",
            move_stuck_players=true
        }
        -- We can just teleport away here to avoid collision as we dont adhere by distance rules in connect_entities
        player.teleport({placement_position.x+2, placement_position.y+2})
        local can_place
        if connection_type == 'pipe' or connection_type == 'pipe-to-ground' or connection_type == 'underground-pipe' then
            -- Use permissive surface check for pipe placement to allow tight spaces
            can_place = game.surfaces[1].can_place_entity({
                name = connection_type,
                position = placement_position,
                direction = dir,
                force = player.force
            })
        else
            can_place = storage.utils.can_place_entity(player, connection_type, placement_position, dir)
        end

        --local can_place = storage.utils.avoid_entity(1, connection_type, placement_position, dir)
        --if not can_build then
        --    error("Cannot place the entity at the specified position: x="..position.x..", y="..position.y)
        --end
        --local player_position = player.position
       -- player.teleport({placement_position.x, placement_position.y})
        --local can_place = storage.actions.can_place_entity(1, connection_type, dir, placement_position.x, placement_position.y)--game.surfaces[1].can_place_entity(entity_variant)
        --player.teleport(player_position)

        --local can_place = storage.utils.avoid_entity(1, connection_type, placement_position, dir)
        rendering.draw_circle{only_in_alt_mode=true, width = 0.25, color = {r = 0, g = 1, b = 0}, surface = player.surface, radius = 0.5, filled = false, target = placement_position, time_to_live = 12000}

        if dry_run and can_place == false then
            -- Define the area where the entity will be placed
            local target_area = {
                {x = placement_position.x - 1 / 2, y = placement_position.y - 1 / 2},
                {x = placement_position.x + 1 / 2, y = placement_position.y + 1 / 2}
            }

            -- Name what is in the way
            local entities = player.surface.find_entities_filtered{area = target_area}
            error(storage.utils.connect_blockage_message(connection_type, placement_position, entities))
        end


        -- Place entity
        if can_place and not dry_run then
            require_item(player, connection_type, placement_position)
            local placed_entity = game.surfaces[1].create_entity(entity_variant)
            if placed_entity then
                player.remove_item({name = connection_type, count = 1})
                counter_state.place_counter = counter_state.place_counter + 1
                table.insert(serialized_entities, storage.utils.serialize_entity(placed_entity))
                return placed_entity
            end
        
        elseif can_place and dry_run then
            counter_state.place_counter = counter_state.place_counter + 1
            record_planned(counter_state, connection_type, placement_position, dir, is_underground_exit)
            return nil

        else
            -- game.print("Avoiding entity at " .. placement_position.x.. ", " .. placement_position.y)
            -- storage.utils.avoid_entity(player.index, connection_type, placement_position, dir)

            -- error("Cannot place entity")
            --local entities = player.surface.find_entities_filtered{position=placement_position, radius=0.5, type = {"beam", "resource", "player"}, invert=true}
            --local can_place = #entities == 0
            --if can_place then
            --    local tile = player.surface.get_tile(placement_position.x, placement_position.y)
            --    if is_water_tile(tile.name) then
            --        can_place = false
            --    end
            --end
            --
            --if can_place then
            --    local placed_entity = player.surface.create_entity({
            --        name = connection_type,
            --        position = placement_position,
            --        direction = dir,
            --        force = player.force
            --    })
            --
            --    if placed_entity then
            --        player.remove_item({name = connection_type, count = 1})
            --        counter_state.place_counter = counter_state.place_counter + 1
            --        table.insert(serialized_entities, storage.utils.serialize_entity(placed_entity))
            --        return placed_entity
            --    end
            --
            --end
        end
    end

    -- Check inventory
    local has_item = false
    for _, inv in pairs({defines.inventory.character_main}) do
        if player.get_inventory(inv) then
            local count = player.get_inventory(inv).get_item_count(connection_type)
            if count > 0 then
                has_item = true
                break
            end
        end
    end
    if not has_item then
        error("\"No " .. connection_type .. " in your inventory to place at (" .. placement_position.x .. ", " .. placement_position.y .. ")\"")
    end

    -- We can just teleport away here to avoid collision as we dont adhere by distance rules in connect_entities
    player.teleport({placement_position.x+2, placement_position.y+2})
    local can_place
    if connection_type == 'pipe' or connection_type == 'pipe-to-ground' or connection_type == 'underground-pipe' then
        -- Use permissive surface check for pipe placement to allow tight spaces
        can_place = game.surfaces[1].can_place_entity({
            name = connection_type,
            position = placement_position,
            direction = dir,
            force = player.force
        })
    else
        can_place = storage.utils.can_place_entity(player, connection_type, placement_position, dir)
    end
    --local player_position = player.position
    --player.teleport({placement_position.x, placement_position.y})
    --local can_place = storage.actions.can_place_entity(1, connection_type, dir, placement_position.x, placement_position.y)--game.surfaces[1].can_place_entity(entity_variant)
    --player.teleport(player_position)

    --local can_place = storage.utils.avoid_entity(1, connection_type, placement_position, dir)
    rendering.draw_circle{only_in_alt_mode=true, width = 0.25, color = {r = 0, g = 1, b = 0}, surface = player.surface, radius = 0.5, filled = false, target = placement_position, time_to_live = 12000}

    if dry_run and can_place == false then
        local target_area = {
                {x = placement_position.x - 1 / 2, y = placement_position.y - 1 / 2},
                {x = placement_position.x + 1 / 2, y = placement_position.y + 1 / 2}
            }

        -- Name what is in the way
        local entities = player.surface.find_entities_filtered{area = target_area}
        error(storage.utils.connect_blockage_message(connection_type, placement_position, entities))
    end


    -- Place entity
    if can_place and not dry_run then
        require_item(player, connection_type, placement_position)
        local placed_entity = game.surfaces[1].create_entity({
            name = connection_type,
            position = placement_position,
            direction = dir,
            force = player.force,
            move_stuck_players=true
        })

        if placed_entity then
            player.remove_item({name = connection_type, count = 1})
            counter_state.place_counter = counter_state.place_counter + 1
            table.insert(serialized_entities, storage.utils.serialize_entity(placed_entity))
            return placed_entity
        end
    
    elseif can_place and dry_run then
        counter_state.place_counter = counter_state.place_counter + 1
        record_planned(counter_state, connection_type, placement_position, dir, is_underground_exit)
        return nil

    else
        -- game.print("Avoiding entity at " .. placement_position.x.. ", " .. placement_position.y)
        -- storage.utils.avoid_entity(player.index, connection_type, placement_position, dir)

        -- error("Cannot place entity")
        --local entities = player.surface.find_entities_filtered{position=placement_position, radius=0.5, type = {"beam", "resource", "player"}, invert=true}
        --local can_place = #entities == 0
        --if can_place then
        --    local tile = player.surface.get_tile(placement_position.x, placement_position.y)
        --    if is_water_tile(tile.name) then
        --        can_place = false
        --    end
        --end
        --
        --if can_place then
        --    local placed_entity = player.surface.create_entity({
        --        name = connection_type,
        --        position = placement_position,
        --        direction = dir,
        --        force = player.force
        --    })
        --
        --    if placed_entity then
        --        player.remove_item({name = connection_type, count = 1})
        --        counter_state.place_counter = counter_state.place_counter + 1
        --        table.insert(serialized_entities, storage.utils.serialize_entity(placed_entity))
        --        return placed_entity
        --    end
        --
        --end
    end
end

local function table_contains(tbl, element)
    for _, value in ipairs(tbl) do
        if value == element then
            return true
        end
    end
    return false
end

-- The game's path for a wide search box weaves between trees and rocks; snapped
-- to the tile grid, some tile of a long route then lands on a tree or rock and
-- the connection fails with a placement blockage. Rewrite the path as a chain of
-- adjacent tiles that follows the game's path and, at each step, takes whichever
-- of the two grid moves toward the next path point is buildable. Nothing is
-- removed from the map; if neither move is buildable the chain goes on and the
-- placement check reports the blockage as before.
local function buildable_tile_chain(surface, raw_path, entity_name)
    if type(raw_path) ~= "table" or #raw_path < 2 then
        return raw_path
    end
    local function tile(p)
        return {x = math.floor(p.x) + 0.5, y = math.floor(p.y) + 0.5}
    end
    local function buildable(p)
        return surface.can_place_entity{name = entity_name, position = p, force = "player"}
    end
    local current = tile(raw_path[1].position)
    local chain = {{position = current}}
    local guard = 0
    for i = 2, #raw_path do
        local target = tile(raw_path[i].position)
        while (current.x ~= target.x or current.y ~= target.y) and guard < 20000 do
            guard = guard + 1
            local dx, dy = target.x - current.x, target.y - current.y
            local step_x = dx ~= 0 and {x = current.x + (dx > 0 and 1 or -1), y = current.y} or nil
            local step_y = dy ~= 0 and {x = current.x, y = current.y + (dy > 0 and 1 or -1)} or nil
            local first, second = step_x, step_y
            if math.abs(dy) > math.abs(dx) then
                first, second = step_y, step_x
            end
            local next_tile
            if first and buildable(first) then
                next_tile = first
            elseif second and buildable(second) then
                next_tile = second
            else
                next_tile = first or second
            end
            chain[#chain + 1] = {position = next_tile}
            current = next_tile
        end
    end
    return chain
end

-- A pipe leg whose start and end are the same tile or side by side needs no
-- route: it is that tile, or those two tiles. The game's path search is not used
-- for it, because the start tile usually holds the pipe the previous leg ended
-- on (a search cannot start inside it) and the tiles beside existing pipes are
-- fenced off, so the search went round them and came back (a U-turn ring).
local function adjacent_pipe_leg(connection_types, start_position, end_position)
    if (default_connect_types[connection_types[1]] or connection_types[1]) ~= "pipe" then
        return nil
    end
    if #connection_types == 1 and connection_types[1] == "pipe-to-ground" then
        return nil
    end
    local function tile(p)
        return {x = math.floor(p.x) + 0.5, y = math.floor(p.y) + 0.5}
    end
    local first, last = tile(start_position), tile(end_position)
    local steps = math.abs(first.x - last.x) + math.abs(first.y - last.y)
    if steps == 0 then
        return {{position = first}}
    elseif steps == 1 then
        return {{position = first}, {position = last}}
    end
    return nil
end
storage.utils.adjacent_pipe_leg = adjacent_pipe_leg

-- ---------------------------------------------------------------------------
-- Electric poles: a near-straight line of poles from the source to the target.
-- Each pole goes as far along the line as its wire reaches, on a tile where it
-- can be built; the line only bends where tiles are blocked (trees, rocks,
-- water, cliffs, buildings). The game's walking path is used only as a guide
-- when the straight line cannot get through (e.g. a lake wider than the reach).
-- ---------------------------------------------------------------------------
local POLE_WIRE_REACH = {
    ['small-electric-pole'] = 7.5,
    ['medium-electric-pole'] = 9,
    ['big-electric-pole'] = 30,
    ['substation'] = 18
}
local POLE_SUPPLY = {
    ['small-electric-pole'] = 2.5,
    ['medium-electric-pole'] = 3.5,
    ['big-electric-pole'] = 2,
    ['substation'] = 9
}

local function prototype_number(name, getter)
    local ok, value = pcall(function()
        local proto = prototypes.entity[name]
        return getter(proto)
    end)
    if ok and type(value) == "number" and value > 0 then return value end
    return nil
end

storage.utils.pole_wire_reach = function(name)
    return prototype_number(name, function(p) return p.get_max_wire_distance() end)
        or POLE_WIRE_REACH[name] or 7.5
end

storage.utils.pole_supply_distance = function(name)
    return prototype_number(name, function(p) return p.get_supply_area_distance() end)
        or POLE_SUPPLY[name] or 2.5
end

-- 0.5 for poles one tile wide (centred on a tile), 0 for 2x2 poles (centred on a corner)
storage.utils.pole_grid_offset = function(name)
    local width = prototype_number(name, function(p)
        local box = p.collision_box
        return math.ceil(box.right_bottom.x - box.left_top.x)
    end)
    if not width then
        width = (name == 'big-electric-pole' or name == 'substation') and 2 or 1
    end
    return (width % 2 == 1) and 0.5 or 0
end

local function distance(a, b)
    local dx, dy = a.x - b.x, a.y - b.y
    return math.sqrt(dx * dx + dy * dy)
end

-- Plan the poles of one connection. Pure: the map is only seen through o.free.
--   o.start, o.goal       positions
--   o.reach               wire reach of the pole type placed
--   o.offset              pole_grid_offset of that type
--   o.free(p)             true if a pole can be built with its centre at p
--   o.start_reach         wire reach of the pole at o.start, or nil when there is none
--                         (then the first pole is built on or next to o.start)
--   o.goal_reach          wire reach of the pole at o.goal, or nil when o.goal is a
--                         place to power (then the last pole is built on or next to it)
--   o.guide               optional list of positions (a walking path) to follow
--                         instead of the straight line
-- Returns a list of pole positions in build order, or nil and a reason.
storage.utils.plan_pole_line = function(o)
    local reach = o.reach - 0.001
    local offset = o.offset or 0.5
    local function snap(v)
        if offset == 0.5 then return math.floor(v) + 0.5 end
        return math.floor(v + 0.5)
    end
    local function candidates(centre, r)
        local out = {}
        local x0, x1 = snap(centre.x - r) - 1, snap(centre.x + r) + 1
        local y0, y1 = snap(centre.y - r) - 1, snap(centre.y + r) + 1
        for x = x0, x1 do
            for y = y0, y1 do
                local c = {x = x, y = y}
                if distance(c, centre) <= r then out[#out + 1] = c end
            end
        end
        return out
    end
    local function fmt(p) return string.format("(%.1f, %.1f)", p.x, p.y) end
    local goal = o.goal
    local poles = {}
    local cur, link

    if o.start_reach then
        cur, link = o.start, math.min(reach, o.start_reach - 0.001)
    else
        -- first pole on the start tile, else the nearest buildable tile (nearer the goal on ties)
        local list = candidates(o.start, 3)
        table.sort(list, function(a, b)
            local da, db = distance(a, o.start), distance(b, o.start)
            if math.abs(da - db) > 1e-9 then return da < db end
            return distance(a, goal) < distance(b, goal)
        end)
        for _, c in ipairs(list) do
            if o.free(c) then cur = c; break end
        end
        if not cur then
            return nil, "No tile to build a pole on within 3 tiles of " .. fmt(o.start)
        end
        poles[1] = cur
        link = reach
    end

    -- how close the last pole must come to a goal that is not a pole
    local finish = 1.5
    local guide_at = 1
    local limit = math.ceil(distance(cur, goal)) + 20
    while #poles <= limit do
        if o.goal_reach then
            if distance(cur, goal) <= math.min(link, o.goal_reach - 0.001) then return poles end
        elseif distance(cur, goal) < 0.01 then
            return poles
        end

        -- the last pole: within wire reach of this one and on (or next to) the goal
        local end_r = o.goal_reach and math.min(reach, o.goal_reach - 0.001) or finish
        if distance(cur, goal) <= link + end_r then
            local list = {}
            for _, c in ipairs(candidates(goal, end_r)) do
                if distance(c, cur) <= link then list[#list + 1] = c end
            end
            table.sort(list, function(a, b) return distance(a, goal) < distance(b, goal) end)
            for _, c in ipairs(list) do
                if o.free(c) then
                    poles[#poles + 1] = c
                    return poles
                end
            end
            if not o.goal_reach and distance(cur, goal) <= finish then
                return poles  -- already next to the goal, its own tile is taken
            end
        end

        -- the next pole: the buildable tile within reach that gets closest to the aim
        local aim = goal
        if o.guide and guide_at <= #o.guide then
            -- the farthest guide point within reach, else the next one not reached yet
            local j = nil
            for k = guide_at, #o.guide do
                if distance(cur, o.guide[k]) <= link then j = k end
            end
            if j then
                aim = o.guide[j]
                guide_at = j + 1
            else
                aim = o.guide[guide_at]
            end
        end
        local list = candidates(cur, link)
        local scored = {}
        local here = distance(cur, aim)
        -- keep to the straight line from the first pole to the goal (no drift)
        local line_a, line_b = (o.guide and cur) or poles[1] or o.start, aim
        local lx, ly = line_b.x - line_a.x, line_b.y - line_a.y
        local llen = math.sqrt(lx * lx + ly * ly)
        local function off_line(c)
            if llen < 1e-9 then return 0 end
            return math.abs(lx * (line_a.y - c.y) - (line_a.x - c.x) * ly) / llen
        end
        for _, c in ipairs(list) do
            local d = distance(c, aim)
            if d < here - 0.5 or d < 0.01 then
                scored[#scored + 1] = {c = c, d = d, s = d + 0.5 * off_line(c)}
            end
        end
        table.sort(scored, function(a, b)
            if math.abs(a.s - b.s) > 1e-9 then return a.s < b.s end
            return distance(a.c, cur) > distance(b.c, cur)
        end)
        local nxt
        for _, s in ipairs(scored) do
            if o.free(s.c) then nxt = s.c; break end
        end
        if not nxt then
            return nil, "No placeable tile for a pole within wire reach (" .. o.reach .. ") of " .. fmt(cur)
                .. " that gets closer to " .. fmt(aim) .. ": the tiles toward it are blocked"
        end
        poles[#poles + 1] = nxt
        cur, link = nxt, reach
    end
    return nil, "Pole route did not reach " .. fmt(goal)
end

-- true if a pole/pipe of this name can be built at p (a character standing there
-- is moved aside when the entity is built, so it does not count)
local function buildable_at(surface, force, name, p, half)
    if surface.can_place_entity{name = name, position = p, force = force} then return true end
    local area = {{p.x - half + 0.01, p.y - half + 0.01}, {p.x + half - 0.01, p.y + half - 0.01}}
    local blockers = surface.find_entities_filtered{area = area}
    if #blockers == 0 then return false end
    for _, e in pairs(blockers) do
        if e.type ~= "character" and e.type ~= "resource" then return false end
    end
    local tile = surface.get_tile(p.x, p.y)
    local ok, water = pcall(function() return tile.collides_with("water_tile") end)
    if ok and water then return false end
    local name_ok, tile_name = pcall(function() return tile.name end)
    if name_ok and tile_name and tile_name:find("water") then return false end
    return true
end

local function pole_at(surface, p)
    local found = surface.find_entities_filtered{type = "electric-pole", position = p, radius = 0.5}
    local best, best_d
    for _, e in pairs(found) do
        local d = distance(e.position, p)
        if not best or d < best_d then best, best_d = e, d end
    end
    return best
end

local function connect_poles(player, source_x, source_y, target_x, target_y, raw_path, pole_name, dry_run)
    local surface = player.surface
    local start = {x = source_x, y = source_y}
    local goal = {x = target_x, y = target_y}
    local reach = storage.utils.pole_wire_reach(pole_name)
    local offset = storage.utils.pole_grid_offset(pole_name)
    local half = offset == 0.5 and 0.5 or 1

    local source_pole = pole_at(surface, start)
    if not source_pole then
        -- a source already on a pole: start from the pole that powers it
        local supplied = surface.find_entities_filtered{type = "electric-pole", position = start, radius = 3}
        local best, best_d
        for _, e in pairs(supplied) do
            local s = storage.utils.pole_supply_distance(e.name)
            if math.abs(e.position.x - start.x) <= s and math.abs(e.position.y - start.y) <= s then
                local d = distance(e.position, goal)
                if not best or d < best_d then best, best_d = e, d end
            end
        end
        source_pole = best
    end
    local target_pole = pole_at(surface, goal)

    local guide = nil
    if type(raw_path) == "table" and #raw_path > 0 then
        guide = {}
        for i = 1, #raw_path do
            local p = raw_path[i].position or raw_path[i]
            guide[#guide + 1] = {x = p.x, y = p.y}
        end
        guide[#guide + 1] = goal
    end

    local plan, why = storage.utils.plan_pole_line{
        start = source_pole and {x = source_pole.position.x, y = source_pole.position.y} or start,
        goal = target_pole and {x = target_pole.position.x, y = target_pole.position.y} or goal,
        reach = reach,
        offset = offset,
        free = function(p) return buildable_at(surface, player.force, pole_name, p, half) end,
        start_reach = source_pole and storage.utils.pole_wire_reach(source_pole.name) or nil,
        goal_reach = target_pole and storage.utils.pole_wire_reach(target_pole.name) or nil,
        guide = guide,
    }
    if not plan then error("\"" .. why .. "\"", 0) end

    local serialized_entities = {}
    local counter_state = {place_counter = 0}
    if dry_run then
        for _, p in ipairs(plan) do
            counter_state.place_counter = counter_state.place_counter + 1
            record_planned(counter_state, pole_name, p, 0)
        end
        return {entities = {}, connected = false, number_of_entities = counter_state.place_counter,
                planned = counter_state.planned}
    end

    local inventory = player.get_inventory(defines.inventory.character_main)
    local held = inventory and inventory.get_item_count(pole_name) or 0
    if held < #plan then
        error("\"You do not have enough " .. pole_name .. " in your inventory to complete this connection. Required number - "
            .. #plan .. ", Available in inventory - " .. held .. "\"", 0)
    end
    local connected = false
    for _, p in ipairs(plan) do
        local placed = surface.create_entity{name = pole_name, position = p, force = player.force, move_stuck_players = true}
        if not placed then
            error(storage.utils.connect_blockage_message(pole_name, p,
                surface.find_entities_filtered{area = {{p.x - half, p.y - half}, {p.x + half, p.y + half}}}), 0)
        end
        player.remove_item{name = pole_name, count = 1}
        counter_state.place_counter = counter_state.place_counter + 1
        table.insert(serialized_entities, storage.utils.serialize_entity(placed))
        if target_pole and target_pole.valid and placed.electric_network_id
            and placed.electric_network_id == target_pole.electric_network_id then
            connected = true
            break
        end
    end
    return {entities = serialized_entities, connected = connected,
            number_of_entities = counter_state.place_counter, planned = counter_state.planned}
end

-- ---------------------------------------------------------------------------
-- Pipes: a tile-by-tile route search, used when the route along the game's
-- walking path cannot be built (it can lead over cliffs, or round them for
-- hundreds of tiles). Pipes go on buildable tiles; with pipe-to-ground among the
-- connection types, an underground pair carries the pipe under anything up to the
-- pipe-to-ground's reach (cliffs, water, trees, buildings). Straight runs then use
-- the pipe-to-ground held beyond those, as the usual route does.
-- ---------------------------------------------------------------------------
local DIRS = {[0] = {0, -1}, [4] = {1, 0}, [8] = {0, 1}, [12] = {-1, 0}}
local DIR_LIST = {0, 4, 8, 12}

storage.utils.underground_pipe_reach = function(name)
    return prototype_number(name or "pipe-to-ground", function(p) return p.max_underground_distance end) or 10
end

-- Plan a pipe route. Pure: the map is only seen through o.free / o.has_underground.
--   o.start, o.goal      tile centres (always usable, they are the ends)
--   o.free(p)            true if a pipe (or pipe-to-ground) can be built on tile p
--   o.has_underground(p) true if tile p holds a pipe-to-ground (a tunnel must not pass one)
--   o.max_jump           tiles from an underground entrance to its exit (0 = none)
--   o.underground_budget pipe-to-ground held (for straight runs beyond the obstacle crossings)
--   o.max_expand, o.margin  search limits
-- Returns {placements = {{kind = "pipe"|"in"|"out", position = p, dir = travel dir}}, pipes, undergrounds}
-- or nil and a reason.
storage.utils.plan_pipe_route = function(o)
    local sx, sy = math.floor(o.start.x), math.floor(o.start.y)
    local gx, gy = math.floor(o.goal.x), math.floor(o.goal.y)
    local manhattan = math.abs(gx - sx) + math.abs(gy - sy)
    local margin = o.margin or (32 + math.floor(manhattan / 4))
    local x0, x1 = math.min(sx, gx) - margin, math.max(sx, gx) + margin
    local y0, y1 = math.min(sy, gy) - margin, math.max(sy, gy) + margin
    local max_jump = o.max_jump or 0
    local max_expand = o.max_expand or 400000
    local free_cache = {}
    local function tkey(x, y) return (x + 1048576) * 2097152 + (y + 1048576) end
    local function centre(x, y) return {x = x + 0.5, y = y + 0.5} end
    local function is_end(x, y) return (x == sx and y == sy) or (x == gx and y == gy) end
    local function free(x, y)
        if is_end(x, y) then return true end
        local k = tkey(x, y)
        local v = free_cache[k]
        if v == nil then
            v = o.free(centre(x, y)) and true or false
            free_cache[k] = v
        end
        return v
    end
    local function h(x, y) return math.abs(gx - x) + math.abs(gy - y) end
    local W = 1.5  -- weighted search: near-shortest routes, few tiles searched

    -- binary heap of {f, h, key}
    local heap = {}
    local function push(f, hh, key)
        local n = #heap + 1
        heap[n] = {f, hh, key}
        while n > 1 do
            local p = math.floor(n / 2)
            local a, b = heap[p], heap[n]
            if a[1] < b[1] or (a[1] == b[1] and a[2] <= b[2]) then break end
            heap[p], heap[n] = b, a
            n = p
        end
    end
    local function pop()
        local top = heap[1]
        local last = heap[#heap]
        heap[#heap] = nil
        if #heap > 0 then
            heap[1] = last
            local n = 1
            while true do
                local l, r, m = 2 * n, 2 * n + 1, n
                if l <= #heap and (heap[l][1] < heap[m][1] or (heap[l][1] == heap[m][1] and heap[l][2] < heap[m][2])) then m = l end
                if r <= #heap and (heap[r][1] < heap[m][1] or (heap[r][1] == heap[m][1] and heap[r][2] < heap[m][2])) then m = r end
                if m == n then break end
                heap[m], heap[n] = heap[n], heap[m]
                n = m
            end
        end
        return top
    end

    -- state: tile + arrival direction + how it was reached (0 step, 1 underground exit, 2 start)
    local function skey(x, y, d, fl) return (tkey(x, y) * 16 + (d or 16) / 4) * 4 + fl end
    local nodes = {}
    local closed = {}
    local start_key = skey(sx, sy, nil, 2)
    nodes[start_key] = {x = sx, y = sy, d = nil, fl = 2, g = 0}
    push(W * h(sx, sy), h(sx, sy), start_key)
    local expanded = 0
    local found = nil
    local function relax(key, x, y, d, fl, g, parent, jump)
        local n = nodes[key]
        if n and n.g <= g then return end
        nodes[key] = {x = x, y = y, d = d, fl = fl, g = g, parent = parent, jump = jump}
        push(g + W * h(x, y), h(x, y), key)
    end
    while #heap > 0 do
        local top = pop()
        local key = top[3]
        if not closed[key] then
            closed[key] = true
            local n = nodes[key]
            if n.x == gx and n.y == gy and n.fl ~= 1 then found = key; break end
            expanded = expanded + 1
            if expanded > max_expand then break end
            -- one tile on
            for _, nd in ipairs(DIR_LIST) do
                local ok = true
                if n.fl == 1 and nd ~= n.d then ok = false end
                if n.d and (nd + 8) % 16 == n.d then ok = false end
                if ok then
                    local v = DIRS[nd]
                    local x, y = n.x + v[1], n.y + v[2]
                    if x >= x0 and x <= x1 and y >= y0 and y <= y1 and free(x, y) then
                        local g = n.g + 1 + ((n.d and nd ~= n.d) and 0.5 or 0)
                        relax(skey(x, y, nd, 0), x, y, nd, 0, g, key, false)
                    end
                end
            end
            -- under an obstacle: an entrance here, the exit up to max_jump tiles on, straight
            if max_jump >= 2 and n.fl == 0 and not is_end(n.x, n.y) then
                local v = DIRS[n.d]
                local blocked = false
                for k = 1, max_jump do
                    local x, y = n.x + v[1] * k, n.y + v[2] * k
                    if x < x0 or x > x1 or y < y0 or y > y1 then break end
                    if k >= 2 and blocked and not (x == gx and y == gy) and not (x == sx and y == sy) and free(x, y) then
                        relax(skey(x, y, n.d, 1), x, y, n.d, 1, n.g + k + 10, key, true)
                    end
                    if o.has_underground and o.has_underground(centre(x, y)) then break end
                    if not free(x, y) then blocked = true end
                end
            end
        end
    end
    if not found then
        local why = expanded > max_expand and ("the search gave up after " .. max_expand .. " tiles")
            or ("no buildable route within " .. margin .. " tiles of the straight line")
        if max_jump < 2 then
            why = why .. " (without pipe-to-ground, every tile of the route must be buildable)"
        else
            why = why .. " (pipe-to-ground crosses at most " .. (max_jump - 1) .. " blocked tiles)"
        end
        return nil, why
    end

    -- the route, start to goal
    local seq = {}
    local k = found
    while k do
        local n = nodes[k]
        table.insert(seq, 1, n)
        k = n.parent
    end
    local placements = {}
    for i, n in ipairs(seq) do
        placements[i] = {kind = "pipe", position = centre(n.x, n.y), dir = n.d, jump = n.jump}
        if n.jump then
            placements[i - 1].kind = "in"
            placements[i - 1].dir = n.d
            placements[i].kind = "out"
        end
    end
    local crossings = 0
    for _, p in ipairs(placements) do if p.kind == "in" then crossings = crossings + 1 end end

    -- straight runs: underground pairs with the pipe-to-ground left over, each at up
    -- to max_jump tiles, back to back. Runs a pair would cover had there been enough
    -- pipe-to-ground stay surface pipe and are counted (short_pairs).
    local budget = (o.underground_budget or 0) - 2 * crossings
    local short_pairs = 0
    if max_jump >= 2 then
        local out = {placements[1]}
        local i = 2
        local n = #placements
        while i <= n do
            local p = placements[i]
            local m_best = nil
            if p.kind == "pipe" and i < n and not p.jump then
                local d = p.dir
                local m = i
                while m + 1 <= n - 1 and m + 1 - i <= max_jump do
                    local q = placements[m + 1]
                    if q.kind ~= "pipe" or q.jump or q.dir ~= d then break end
                    m = m + 1
                end
                -- the exit's next tile must carry on in the same direction
                while m > i do
                    local after = placements[m + 1]
                    if after and not after.jump and after.dir == d and m - i >= 3 then break end
                    m = m - 1
                end
                local clear = true
                if o.has_underground then
                    for t = i + 1, m - 1 do
                        if o.has_underground(placements[t].position) then clear = false; break end
                    end
                end
                if m - i >= 3 and clear then m_best = m end
            end
            if m_best and budget >= 2 then
                out[#out + 1] = {kind = "in", position = p.position, dir = p.dir}
                out[#out + 1] = {kind = "out", position = placements[m_best].position, dir = p.dir}
                budget = budget - 2
                i = m_best + 1
            elseif m_best then
                short_pairs = short_pairs + 1
                for t = i, m_best do out[#out + 1] = placements[t] end
                i = m_best + 1
            else
                out[#out + 1] = p
                i = i + 1
            end
        end
        placements = out
    end
    local pipes, undergrounds = 0, 0
    for _, p in ipairs(placements) do
        if p.kind == "pipe" then pipes = pipes + 1 else undergrounds = undergrounds + 1 end
    end
    return {placements = placements, pipes = pipes, undergrounds = undergrounds, expanded = expanded,
            short_pairs = short_pairs}
end

-- plan_pipe_route, using no more pipe-to-ground than o.underground_budget (the number
-- held): when the obstacle crossings alone need more, a route of plain pipes is
-- planned instead. Only when there is none is the plan with the crossings returned
-- (the item check then names the pipe-to-ground it needs).
storage.utils.plan_pipe_route_within_held = function(o)
    local plan, why = storage.utils.plan_pipe_route(o)
    if plan and plan.undergrounds > (o.underground_budget or 0) and (o.max_jump or 0) > 0 then
        local plain_opts = {}
        for k, v in pairs(o) do plain_opts[k] = v end
        plain_opts.max_jump = 0
        plain_opts.underground_budget = 0
        local plain = storage.utils.plan_pipe_route(plain_opts)
        if plain then
            -- what the route with its crossings and full tunnels would have used
            plain.wanted_undergrounds = plan.undergrounds + 2 * plan.short_pairs
            return plain
        end
    end
    return plan, why
end

local function is_pipe_route(connection_types)
    if (default_connect_types[connection_types[1]] or connection_types[1]) ~= "pipe" then return false end
    for _, t in ipairs(connection_types) do
        if t == "pipe" then return true end
    end
    return false
end

local function connect_pipes_by_tiles(player_index, source_x, source_y, target_x, target_y, connection_types, dry_run)
    local player = storage.agent_characters[player_index]
    local surface = player.surface
    local function tile(x, y) return {x = math.floor(x) + 0.5, y = math.floor(y) + 0.5} end
    local start, goal = tile(source_x, source_y), tile(target_x, target_y)
    local underground = nil
    for _, t in ipairs(connection_types) do
        if t == "pipe-to-ground" then underground = t end
    end
    local inventory = player.get_inventory(defines.inventory.character_main)
    local function held(name) return inventory and inventory.get_item_count(name) or 0 end

    local near_ends = function(p)
        return (math.abs(p.x - start.x) + math.abs(p.y - start.y) <= 1)
            or (math.abs(p.x - goal.x) + math.abs(p.y - goal.y) <= 1)
    end
    local function segment_of(e)
        local ok, id = pcall(function() return e.fluidbox.get_fluid_segment_id(1) end)
        if ok then return id end
        return nil
    end
    local own_segments = {}
    for _, p in pairs({start, goal}) do
        for _, e in pairs(surface.find_entities_filtered{name = {"pipe", "pipe-to-ground"}, position = p, radius = 1.1}) do
            local id = segment_of(e)
            if id then own_segments[id] = true end
        end
    end
    local route = {
        start = start,
        goal = goal,
        free = function(p)
            if not buildable_at(surface, player.force, "pipe", p, 0.5) then return false end
            if near_ends(p) then return true end
            -- a tile beside a pipe of another fluid system would join the two
            for _, v in pairs(DIRS) do
                local other = surface.find_entity("pipe", {x = p.x + v[1], y = p.y + v[2]})
                if other then
                    local id = segment_of(other)
                    if not (id and own_segments[id]) then return false end
                end
            end
            return true
        end,
        has_underground = function(p)
            return #surface.find_entities_filtered{name = "pipe-to-ground", position = p, radius = 0.4} > 0
        end,
        max_jump = underground and storage.utils.underground_pipe_reach(underground) or 0,
        underground_budget = underground and held(underground) or 0,
    }
    local plan, why = storage.utils.plan_pipe_route_within_held(route)
    if not plan then
        error("\"No pipe route from (" .. start.x .. ", " .. start.y .. ") to (" .. goal.x .. ", " .. goal.y .. "): " .. why .. "\"", 0)
    end
    if not dry_run then
        local short = {}
        if held("pipe") < plan.pipes then short[#short + 1] = "pipe " .. plan.pipes .. " (you hold " .. held("pipe") .. ")" end
        if plan.undergrounds > 0 and held(underground) < plan.undergrounds then
            short[#short + 1] = underground .. " " .. plan.undergrounds .. " (you hold " .. held(underground) .. ")"
        end
        if #short > 0 then
            error("\"You do not have enough items in your inventory to complete this connection. Required: "
                .. table.concat(short, ", ") .. "\"", 0)
        end
    end
    local serialized_entities = {}
    local counter_state = {place_counter = 0}
    for _, p in ipairs(plan.placements) do
        if p.kind == "pipe" then
            place_at_position(player, "pipe", p.position, 0, serialized_entities, dry_run, counter_state, false)
        else
            local d = p.kind == "in" and p.dir or (p.dir + 8) % 16
            place_at_position(player, underground, p.position, storage.utils.get_entity_direction(underground, d),
                serialized_entities, dry_run, counter_state, p.kind == "out")
        end
    end
    local answer = {entities = serialized_entities, connected = not dry_run,
            number_of_entities = counter_state.place_counter, planned = counter_state.planned}
    -- fewer tunnels than the route has room for: the pipe-to-ground it would have used
    local wanted = plan.wanted_undergrounds or (plan.undergrounds + 2 * (plan.short_pairs or 0))
    if underground and wanted > plan.undergrounds then
        answer.underground_wanted = wanted
        answer.underground_used = plan.undergrounds
    end
    return answer
end

-- ---------------------------------------------------------------------------
-- Pipe-to-ground alone: a straight line of pipe-to-ground pairs, back to back, from
-- the start tile to the end tile (the same x or the same y), with no pipes. Each
-- exit is at most `reach` tiles past its entrance (the game's max_underground_distance);
-- the line uses as few pairs as that allows, of near-equal length.
-- Pure: o.start, o.goal (tile centres), o.reach, o.crosses(p, axis): true if tile p holds a
-- pipe-to-ground on the line's axis (a pair must not span one: the game would pair with it).
-- Returns {placements = {{kind = "in"|"out", position, dir = travel dir}}, pipes, undergrounds}
-- or nil and a reason.
-- ---------------------------------------------------------------------------
storage.utils.plan_pipe_to_ground_line = function(o)
    local sx, sy = math.floor(o.start.x), math.floor(o.start.y)
    local gx, gy = math.floor(o.goal.x), math.floor(o.goal.y)
    local function at(x, y) return "(" .. (x + 0.5) .. ", " .. (y + 0.5) .. ")" end
    if sx ~= gx and sy ~= gy then
        return nil, "Prototype.UndergroundPipe alone connects two tiles in a straight line (the same x or the same y): "
            .. at(sx, sy) .. " and " .. at(gx, gy) .. " are not"
    end
    local d = math.abs(gx - sx) + math.abs(gy - sy)
    if d == 0 then
        return nil, "Prototype.UndergroundPipe alone needs two different tiles: both ends are " .. at(sx, sy)
    end
    local ux = (gx > sx and 1) or (gx < sx and -1) or 0
    local uy = (gy > sy and 1) or (gy < sy and -1) or 0
    local dir = (ux == 1 and 4) or (ux == -1 and 12) or (uy == 1 and 8) or 0
    local reach = o.reach or 10
    local tiles = d + 1
    local pairs_needed = math.ceil(tiles / (reach + 1))
    local placements = {}
    local first = 0
    for k = 1, pairs_needed do
        local span = math.ceil((tiles - first) / (pairs_needed - k + 1))
        local last = first + span - 1
        for t = first + 1, last - 1 do
            if o.crosses and o.crosses({x = sx + ux * t + 0.5, y = sy + uy * t + 0.5}, dir % 8) then
                return nil, "a pipe-to-ground at " .. at(sx + ux * t, sy + uy * t) .. " lies on the line between "
                    .. at(sx + ux * first, sy + uy * first) .. " and " .. at(sx + ux * last, sy + uy * last)
                    .. " in the same axis: the pair would connect to it"
            end
        end
        placements[#placements + 1] = {kind = "in", position = {x = sx + ux * first + 0.5, y = sy + uy * first + 0.5}, dir = dir}
        placements[#placements + 1] = {kind = "out", position = {x = sx + ux * last + 0.5, y = sy + uy * last + 0.5}, dir = dir}
        first = last + 1
    end
    return {placements = placements, pipes = 0, undergrounds = #placements}
end

local function is_pipe_to_ground_only(connection_types)
    return #connection_types == 1 and connection_types[1] == "pipe-to-ground"
end

local function connect_pipe_to_ground_line(player_index, source_x, source_y, target_x, target_y, dry_run)
    local player = storage.agent_characters[player_index]
    local surface = player.surface
    local function tile(x, y) return {x = math.floor(x) + 0.5, y = math.floor(y) + 0.5} end
    local plan, why = storage.utils.plan_pipe_to_ground_line{
        start = tile(source_x, source_y),
        goal = tile(target_x, target_y),
        reach = storage.utils.underground_pipe_reach("pipe-to-ground"),
        crosses = function(p, axis)
            for _, e in pairs(surface.find_entities_filtered{name = "pipe-to-ground", position = p, radius = 0.4}) do
                if e.direction % 8 == axis then return true end
            end
            return false
        end,
    }
    if not plan then
        error("\"" .. why .. "\"", 0)
    end
    local serialized_entities = {}
    local counter_state = {place_counter = 0}
    for _, p in ipairs(plan.placements) do
        local d = p.kind == "in" and p.dir or (p.dir + 8) % 16
        place_at_position(player, "pipe-to-ground", p.position, storage.utils.get_entity_direction("pipe-to-ground", d),
            serialized_entities, dry_run, counter_state, p.kind == "out")
    end
    return {entities = serialized_entities, connected = not dry_run,
            number_of_entities = counter_state.place_counter, planned = counter_state.planned}
end

-- ---------------------------------------------------------------------------
-- Belts: a tile-by-tile route search, used when the game's walking path gives no
-- buildable route (its path search treats belts already on the map as walls, so a
-- belt line could not cross another one). Belts go on buildable tiles that no belt
-- already on the map feeds into. With an underground belt among the connection types,
-- an underground pair carries the line under anything in its way (other belts,
-- buildings, water) up to the underground belt's reach. Belts already on the map are
-- not changed: a pair never spans, or stands inside, a tunnel of the same underground
-- belt on the same axis (the game would re-pair it).
-- ---------------------------------------------------------------------------
local BELT_TIERS = {"transport-belt", "fast-transport-belt", "express-transport-belt"}
local UNDERGROUND_BELT_TIERS = {"underground-belt", "fast-underground-belt", "express-underground-belt"}
local UNDERGROUND_BELT_OF = {["transport-belt"] = "underground-belt",
    ["fast-transport-belt"] = "fast-underground-belt", ["express-transport-belt"] = "express-underground-belt"}
local BELT_DIRECTION_NAMES = {[0] = "UP", [4] = "RIGHT", [8] = "DOWN", [12] = "LEFT"}

storage.utils.underground_belt_reach = function(name)
    return prototype_number(name, function(p) return p.max_underground_distance end)
        or ({["underground-belt"] = 5, ["fast-underground-belt"] = 7, ["express-underground-belt"] = 9})[name] or 5
end

-- Plan a belt route. Pure: the map is only seen through the callbacks.
--   o.start, o.goal          tile centres (always usable: they are the ends)
--   o.start_open, o.goal_open  true if that end tile is empty, so an underground belt may stand there
--   o.free(p)                true if a belt can be built on tile p
--   o.has_underground(p)     true if tile p holds an underground belt of the route's name (a tunnel must not pass one)
--   o.can_jump(a, b, d)      optional: false if an underground pair from a to b (direction d) may not be built
--   o.max_jump               tiles from an underground entrance to its exit (0 = no underground belts)
--   o.max_expand, o.margin   search limits
-- Returns {placements = {{kind = "belt"|"in"|"out", position = p, dir = d}}, belts, undergrounds}, where d is
-- the direction the entity faces (items leave it that way), or nil, a reason and the blocked tile nearest the
-- goal that the search reached (nil if it reached none).
storage.utils.plan_belt_route = function(o)
    local sx, sy = math.floor(o.start.x), math.floor(o.start.y)
    local gx, gy = math.floor(o.goal.x), math.floor(o.goal.y)
    local manhattan = math.abs(gx - sx) + math.abs(gy - sy)
    local margin = o.margin or (32 + math.floor(manhattan / 4))
    local x0, x1 = math.min(sx, gx) - margin, math.max(sx, gx) + margin
    local y0, y1 = math.min(sy, gy) - margin, math.max(sy, gy) + margin
    local max_jump = o.max_jump or 0
    local max_expand = o.max_expand or 200000
    local function tkey(x, y) return (x + 1048576) * 2097152 + (y + 1048576) end
    local function centre(x, y) return {x = x + 0.5, y = y + 0.5} end
    local function h(x, y) return math.abs(gx - x) + math.abs(gy - y) end
    local is_start = function(x, y) return x == sx and y == sy end
    local is_goal = function(x, y) return x == gx and y == gy end
    local free_cache = {}
    local nearest_block = nil
    local function free(x, y)
        if is_start(x, y) or is_goal(x, y) then return true end
        local k = tkey(x, y)
        local v = free_cache[k]
        if v == nil then
            v = o.free(centre(x, y)) and true or false
            free_cache[k] = v
            if not v and (not nearest_block or h(x, y) < nearest_block.h) then
                nearest_block = {x = x, y = y, h = h(x, y)}
            end
        end
        return v
    end
    local W = 1.5  -- weighted search: near-shortest routes, few tiles searched

    local heap = {}
    local function less(a, b) return a[1] < b[1] or (a[1] == b[1] and a[2] < b[2]) end
    local function push(f, hh, key)
        local n = #heap + 1
        heap[n] = {f, hh, key}
        while n > 1 do
            local p = math.floor(n / 2)
            if not less(heap[n], heap[p]) then break end
            heap[p], heap[n] = heap[n], heap[p]
            n = p
        end
    end
    local function pop()
        local top = heap[1]
        local last = heap[#heap]
        heap[#heap] = nil
        if #heap > 0 then
            heap[1] = last
            local n = 1
            while true do
                local l, r, m = 2 * n, 2 * n + 1, n
                if l <= #heap and less(heap[l], heap[m]) then m = l end
                if r <= #heap and less(heap[r], heap[m]) then m = r end
                if m == n then break end
                heap[m], heap[n] = heap[n], heap[m]
                n = m
            end
        end
        return top
    end

    -- state: tile + arrival direction + how it was reached (0 belt step, 1 underground exit, 2 start)
    local function skey(x, y, d, fl) return (tkey(x, y) * 16 + (d or 16) / 4) * 4 + fl end
    local nodes = {}
    local closed = {}
    local start_key = skey(sx, sy, nil, 2)
    nodes[start_key] = {x = sx, y = sy, d = nil, fl = 2, g = 0}
    push(W * h(sx, sy), h(sx, sy), start_key)
    local expanded = 0
    local found = nil
    -- a route never comes back to a tile it has used (the last 16 tiles are checked;
    -- the turn and tunnel rules can otherwise make a short loop the cheapest way)
    local function on_route(key, x, y)
        local steps = 0
        while key and steps < 16 do
            local m = nodes[key]
            if m.x == x and m.y == y then return true end
            key = m.parent
            steps = steps + 1
        end
        return false
    end
    local function relax(key, x, y, d, fl, g, parent, jump)
        local n = nodes[key]
        if n and n.g <= g then return end
        if on_route(parent, x, y) then return end
        nodes[key] = {x = x, y = y, d = d, fl = fl, g = g, parent = parent, jump = jump}
        push(g + W * h(x, y), h(x, y), key)
    end
    local function in_box(x, y) return x >= x0 and x <= x1 and y >= y0 and y <= y1 end
    while #heap > 0 do
        local key = pop()[3]
        if not closed[key] then
            closed[key] = true
            local n = nodes[key]
            if is_goal(n.x, n.y) then found = key; break end
            expanded = expanded + 1
            if expanded > max_expand then break end
            -- one tile on (an underground exit sends the items straight on)
            for _, nd in ipairs(DIR_LIST) do
                if not (n.fl == 1 and nd ~= n.d) and not (n.d and (nd + 8) % 16 == n.d) then
                    local v = DIRS[nd]
                    local x, y = n.x + v[1], n.y + v[2]
                    if in_box(x, y) and free(x, y) then
                        relax(skey(x, y, nd, 0), x, y, nd, 0, n.g + 1 + ((n.d and nd ~= n.d) and 0.5 or 0), key, false)
                    end
                end
            end
            -- under an obstacle: an entrance on this tile, fed straight from behind (or the
            -- start tile, if empty), the exit up to max_jump tiles on in the same direction
            local jump_dirs = nil
            if max_jump >= 2 then
                if n.fl == 0 then jump_dirs = {n.d}
                elseif n.fl == 2 and o.start_open then jump_dirs = DIR_LIST end
            end
            for _, jd in ipairs(jump_dirs or {}) do
                local v = DIRS[jd]
                local blocked = false
                for k = 1, max_jump do
                    local x, y = n.x + v[1] * k, n.y + v[2] * k
                    if not in_box(x, y) then break end
                    if k >= 2 and blocked and not is_start(x, y) and (o.goal_open or not is_goal(x, y))
                        and free(x, y)
                        and (not o.can_jump or o.can_jump(centre(n.x, n.y), centre(x, y), jd)) then
                        relax(skey(x, y, jd, 1), x, y, jd, 1, n.g + k + 6, key, true)
                    end
                    if o.has_underground and o.has_underground(centre(x, y)) then break end
                    if not free(x, y) then blocked = true end
                end
            end
        end
    end
    local at = nearest_block and centre(nearest_block.x, nearest_block.y) or nil
    if not found then
        if expanded > max_expand then
            return nil, "the search gave up after " .. max_expand .. " tiles", at
        end
        return nil, "no route within " .. margin .. " tiles of the straight line", at
    end

    local seq = {}
    local used = {}
    local k = found
    while k do
        local n = nodes[k]
        if used[tkey(n.x, n.y)] then
            return nil, "no route found that does not cross itself", at
        end
        used[tkey(n.x, n.y)] = true
        table.insert(seq, 1, n)
        k = n.parent
    end
    local placements = {}
    local belts, undergrounds = 0, 0
    for i, n in ipairs(seq) do
        local nxt = seq[i + 1]
        local kind, dir = "belt", (nxt and nxt.d) or n.d or 0
        if n.jump then kind, dir = "out", n.d end
        if nxt and nxt.jump then kind, dir = "in", nxt.d end
        placements[i] = {kind = kind, position = centre(n.x, n.y), dir = dir}
        if kind == "belt" then belts = belts + 1 else undergrounds = undergrounds + 1 end
    end
    return {placements = placements, belts = belts, undergrounds = undergrounds, expanded = expanded}
end

-- plan_belt_route, using no more underground belts than o.underground_budget (the number
-- held) when a route without them exists; otherwise the route with them (the item check
-- then names what it needs).
storage.utils.plan_belt_route_within_held = function(o)
    local plan, why, at = storage.utils.plan_belt_route(o)
    if plan and plan.undergrounds > (o.underground_budget or 0) and (o.max_jump or 0) > 0 then
        local plain_opts = {}
        for k, v in pairs(o) do plain_opts[k] = v end
        plain_opts.max_jump = 0
        local plain = storage.utils.plan_belt_route(plain_opts)
        if plain then return plain end
    end
    return plan, why, at
end

local function is_belt_route(connection_types)
    for _, t in ipairs(connection_types) do
        if not (t:find("belt") or t:find("splitter")) then return false end
    end
    return #connection_types > 0
end

-- The belt on the map whose output is tile p (a new belt there would join its line), if any
storage.utils.belt_feeding_tile = function(surface, p)
    local area = {{p.x - 1.5, p.y - 1.5}, {p.x + 1.5, p.y + 1.5}}
    for _, e in pairs(surface.find_entities_filtered{area = area, type = {"transport-belt", "underground-belt", "splitter"}}) do
        local v = DIRS[e.direction]
        if v then
            local outs = {}
            if e.type == "transport-belt" or (e.type == "underground-belt" and e.belt_to_ground_type == "output") then
                outs = {{e.position.x + v[1], e.position.y + v[2]}}
            elseif e.type == "splitter" then
                local px, py = -v[2] * 0.5, v[1] * 0.5
                outs = {{e.position.x + px + v[1], e.position.y + py + v[2]},
                        {e.position.x - px + v[1], e.position.y - py + v[2]}}
            end
            for _, q in ipairs(outs) do
                if math.abs(q[1] - p.x) < 0.1 and math.abs(q[2] - p.y) < 0.1 then return e end
            end
        end
    end
    return nil
end

local function describe_belt_block(surface, force, name, p)
    local function at(e) return "(" .. e.position.x .. ", " .. e.position.y .. ")" end
    if buildable_at(surface, force, name, p, 0.5) then
        local feeder = storage.utils.belt_feeding_tile(surface, p)
        if feeder then
            return "the " .. feeder.name .. " at " .. at(feeder) .. " facing "
                .. (BELT_DIRECTION_NAMES[feeder.direction] or tostring(feeder.direction))
                .. " outputs onto this tile (a belt there would join that line)"
        end
    end
    local area = {{p.x - 0.49, p.y - 0.49}, {p.x + 0.49, p.y + 0.49}}
    local names = {}
    for _, e in pairs(surface.find_entities_filtered{area = area}) do
        local t = e.valid and e.type
        if t and t ~= "character" and t ~= "resource" and t ~= "item-entity" and t ~= "corpse" and #names < 3 then
            local s = e.name
            if t == "transport-belt" or t == "underground-belt" or t == "splitter" then
                s = s .. " facing " .. (BELT_DIRECTION_NAMES[e.direction] or tostring(e.direction))
                if t == "underground-belt" then s = s .. " (" .. e.belt_to_ground_type .. ")" end
            end
            table.insert(names, s)
        end
    end
    if #names > 0 then return "blocked by " .. table.concat(names, ", ") end
    local tile = surface.get_tile(p.x, p.y)
    return "the tile there (" .. (tile and tile.valid and tile.name or "unknown") .. ") does not allow it"
end

local function connect_belts_by_tiles(player_index, source_x, source_y, target_x, target_y, connection_types, dry_run)
    local player = storage.agent_characters[player_index]
    local surface = player.surface
    local force = player.force
    local function tile(x, y) return {x = math.floor(x) + 0.5, y = math.floor(y) + 0.5} end
    local start, goal = tile(source_x, source_y), tile(target_x, target_y)
    local inventory = player.get_inventory(defines.inventory.character_main)
    local function held(name) return inventory and inventory.get_item_count(name) or 0 end

    -- the surface belt (the cheapest tier listed) and the underground belt of the route
    local listed = {}
    for _, t in ipairs(connection_types) do listed[t] = true end
    local plain = nil
    for _, t in ipairs(BELT_TIERS) do if listed[t] and not plain then plain = t end end
    local underground = nil
    local listed_undergrounds = {}
    for _, t in ipairs(UNDERGROUND_BELT_TIERS) do
        if listed[t] then table.insert(listed_undergrounds, t) end
    end
    if #listed_undergrounds > 0 then
        local matching = plain and UNDERGROUND_BELT_OF[plain]
        if matching and listed[matching] and held(matching) >= 2 then underground = matching end
        for _, t in ipairs(listed_undergrounds) do
            if not underground and held(t) >= 2 then underground = t end
        end
        if not underground then
            underground = (matching and listed[matching]) and matching or listed_undergrounds[1]
        end
    end
    plain = plain or default_connect_types[underground] or "transport-belt"
    local reach = underground and storage.utils.underground_belt_reach(underground) or 0

    local function inside_tunnel(t, vertical)
        local area = vertical and {{t.x - 0.4, t.y - reach - 0.5}, {t.x + 0.4, t.y + reach + 0.5}}
            or {{t.x - reach - 0.5, t.y - 0.4}, {t.x + reach + 0.5, t.y + 0.4}}
        for _, u in pairs(surface.find_entities_filtered{name = underground, area = area}) do
            local w = u.neighbours
            if w and w.valid then
                local a, b = u.position, w.position
                if vertical and math.abs(a.x - t.x) < 0.1 and math.abs(b.x - t.x) < 0.1
                    and (a.y - t.y) * (b.y - t.y) < 0 then return true end
                if not vertical and math.abs(a.y - t.y) < 0.1 and math.abs(b.y - t.y) < 0.1
                    and (a.x - t.x) * (b.x - t.x) < 0 then return true end
            end
        end
        return false
    end
    local function open(p)
        return buildable_at(surface, force, underground or plain, p, 0.5)
    end
    local under_cache = {}

    local route = {
        start = start,
        goal = goal,
        start_open = underground ~= nil and open(start),
        goal_open = underground ~= nil and open(goal),
        free = function(p)
            if not buildable_at(surface, force, plain, p, 0.5) then return false end
            return storage.utils.belt_feeding_tile(surface, p) == nil
        end,
        has_underground = underground and function(p)
            local k = p.x .. "," .. p.y
            if under_cache[k] == nil then
                under_cache[k] = #surface.find_entities_filtered{name = underground, position = p, radius = 0.4} > 0
            end
            return under_cache[k]
        end or nil,
        can_jump = underground and function(a, b, d)
            local vertical = (d == 0 or d == 8)
            return not inside_tunnel(a, vertical) and not inside_tunnel(b, vertical)
        end or nil,
        max_jump = reach,
        underground_budget = underground and held(underground) or 0,
    }
    local plan, why, blocked = storage.utils.plan_belt_route_within_held(route)
    if not plan then
        local msg = "Failed to find a path. No belt route from (" .. start.x .. ", " .. start.y .. ") to ("
            .. goal.x .. ", " .. goal.y .. "): " .. why .. "."
        if blocked then
            msg = msg .. " The blocked tile nearest the target that the search reached: cannot place " .. plain
                .. " at (" .. blocked.x .. ", " .. blocked.y .. "): " .. describe_belt_block(surface, force, plain, blocked) .. "."
        end
        if underground then
            msg = msg .. " Underground belts: " .. underground .. " allowed (an exit at most " .. reach
                .. " tiles past its entrance, so at most " .. (reach - 1) .. " tiles crossed; you hold "
                .. held(underground) .. ")."
        else
            msg = msg .. " Underground belts: not allowed (connection_type has no underground belt)."
        end
        error("\"" .. msg .. "\"", 0)
    end

    local serialized_entities = {}
    local counter_state = {place_counter = 0}
    -- as the walking-path route does: a belt of the route's names already at the start
    -- is turned to face along the route (a dry run reports it instead)
    local placements = plan.placements
    if #placements > 1 then
        local initial_dir = placements[1].dir
        local here = surface.find_entities_filtered{position = {x = source_x, y = source_y}, name = connection_types, force = "player"}
        local source_belt = here[1]
        if source_belt and source_belt.valid and source_belt.type == "transport-belt" and source_belt.direction ~= initial_dir then
            if dry_run then
                counter_state.would_turn = {name = "\"" .. source_belt.name .. "\"", x = source_belt.position.x,
                    y = source_belt.position.y, from = source_belt.direction, to = initial_dir}
            else
                source_belt.direction = initial_dir
                table.insert(serialized_entities, storage.utils.serialize_entity(source_belt))
            end
        end
    end
    local first_belt = nil
    for _, p in ipairs(placements) do
        local name = p.kind == "belt" and plain or underground
        local placed = place_at_position(player, name, p.position, storage.utils.get_entity_direction(name, p.dir),
            serialized_entities, dry_run, counter_state, p.kind == "out")
        if placed and placed.valid and placed.type == "transport-belt" and not first_belt then first_belt = placed end
    end
    if not dry_run and first_belt then
        -- the whole belt line, as the walking-path route returns it, plus what was placed
        local group = serialize_belt_group(first_belt)
        if group then
            local seen = {}
            for _, s in ipairs(group) do seen[tostring(s.name) .. ":" .. tostring(s.position and s.position.x) .. ":" .. tostring(s.position and s.position.y)] = true end
            for _, s in ipairs(serialized_entities) do
                if not seen[tostring(s.name) .. ":" .. tostring(s.position and s.position.x) .. ":" .. tostring(s.position and s.position.y)] then table.insert(group, s) end
            end
            serialized_entities = group
        end
    end
    return {entities = serialized_entities, connected = not dry_run, number_of_entities = counter_state.place_counter,
            planned = counter_state.planned, would_turn = counter_state.would_turn}
end

local function connect_entities(player_index, source_x, source_y, target_x, target_y, path_handle, connection_types, dry_run)
    local counter_state = {place_counter = 0}
    local player = storage.agent_characters[player_index]
    local last_placed_entity = nil

    local start_position = {x = math.floor(source_x*2)/2, y = math.floor(source_y*2)/2}
    local end_position = {x = target_x, y = target_y}


    local raw_path = storage.paths[path_handle]
    local path = adjacent_pipe_leg(connection_types, start_position, end_position)

    if not path then
        if not raw_path or type(raw_path) ~= "table" or #raw_path == 0 then
            error("\"No path found\"")
        end

        -- Pipes: follow the game's path tile by tile, choosing buildable tiles
        if (default_connect_types[connection_types[1]] or connection_types[1]) == "pipe" then
            raw_path = buildable_tile_chain(player.surface, raw_path, "pipe")
        end

        path = storage.utils.normalise_path(raw_path, start_position, end_position)
    end

    if #path == 0 then
        error(string.format(
            "\"Could not connect entities from (%.1f, %.1f) to (%.1f, %.1f): no placeable positions in normalized path\"",
            source_x,
            source_y,
            target_x,
            target_y
        ))
    end

    -- Get default and underground connection types
    local default_connection_type = default_connect_types[connection_types[1]] or connection_types[1]
    local underground_type = nil
    for _, type in ipairs(connection_types) do
        if is_underground_type(type) then
            underground_type = type
            break
        end
    end

    --rendering.clear()

    rendering.draw_circle{only_in_alt_mode=true, width = 1, color = {r = 1, g = 0, b = 0}, surface = player.surface, radius = 0.5, filled = false, target = start_position, time_to_live = 60000}
    rendering.draw_circle{only_in_alt_mode=true, width = 1, color = {r = 0, g = 1, b = 0}, surface = player.surface, radius = 0.5, filled = false, target = end_position, time_to_live = 60000}

    for i = 1, #path - 1 do
        rendering.draw_line{only_in_alt_mode=true, surface = player.surface, from = path[i].position, to =  path[i + 1].position, color = {1, 0, 1}, width = 2,  dash_length=0.25, gap_length = 0.25}
    end
    -- (a leg built without the search may have no path from it: "not_found")
    for i = 1, (type(raw_path) == "table" and #raw_path or 0) - 1 do
        rendering.draw_line{only_in_alt_mode=true, surface = player.surface, from = raw_path[i].position, to =  raw_path[i + 1].position, color = {1, 1, 0}, width = 0,  dash_length=0.2, gap_length = 0.2}
    end


    local last_position = start_position
    local step_size = wire_reach[default_connection_type] or 1
    local is_electric_pole = wire_reach[default_connection_type] ~= nil


    -- (No walking time is counted here: the client walks the character along the
    -- route with move_to, in game time, before the real call builds it.)

    local serialized_entities = {}

    -- Get source and target entities
    local source_entity = storage.utils.get_closest_entity(player, {x = source_x, y = source_y})
    local target_entity = storage.utils.get_closest_entity(player, {x = target_x, y = target_y})


    if #connection_types == 1 and connection_types[1] == 'pipe-to-ground' then
        
        -- Calculate the direction from start to end.
        -- Factorio 2.0: get_direction returns 0, 4, 8, 12 - pass directly to get_entity_direction
        local dir = storage.utils.get_direction(start_position, end_position)
        local entrance_dir = storage.utils.get_entity_direction(underground_type, dir)

        -- Place the underground entrance at the start position.
        place_at_position(player, underground_type, start_position, entrance_dir,
                          serialized_entities, dry_run, counter_state, false)

        local exit_dir
        if underground_type == "pipe-to-ground" then
          -- For pipe-to-ground, rotate the direction 180° for the exit.
          -- Factorio 2.0: rotate 180° by adding 8 and mod 16
          exit_dir = storage.utils.get_entity_direction(underground_type, (dir + 8) % 16)
        else
          exit_dir = storage.utils.get_entity_direction(underground_type, dir)
        end
        
        -- Place the underground exit at the end position.
        place_at_position(player, underground_type, end_position, exit_dir,
                          serialized_entities, dry_run, counter_state, true)
        
        return {
          entities = serialized_entities,
          connected = true,
          number_of_entities = counter_state.place_counter,
          planned = counter_state.planned
        }
    end


    if underground_type then
        -- Calculate maximum possible underground sections based on inventory
        local max_underground_sections = calculate_max_underground_sections(player, underground_type)

        -- Find straight sections suitable for underground entities
        local range = underground_ranges[underground_type]
        if underground_type == "pipe-to-ground" then
            -- the game's reach: an exit up to max_underground_distance tiles past its entrance
            range = storage.utils.underground_pipe_reach(underground_type)
        end
        local straight_sections = find_straight_sections(path, 4)

        -- Track remaining underground sections we can create
        local remaining_sections = max_underground_sections




        local current_index = 1
        for _, section in ipairs(straight_sections) do

            if remaining_sections <= 0 then
                break
            end

            -- Place regular entities up to the section
            while current_index < section.start_index do
                local current_pos = path[current_index].position
                local next_pos = path[current_index + 1].position
                -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
                local dir = storage.utils.get_direction(current_pos, next_pos)
                place_at_position(player, default_connection_type, current_pos,
                        storage.utils.get_entity_direction(default_connection_type, dir),
                        serialized_entities, dry_run, counter_state, false)
                current_index = current_index + 1
            end

            -- Place initial surface entity for direction change
            local margin_pos = path[section.start_index].position
            local margin_next_pos = path[section.start_index + 1].position
            local margin_dir = storage.utils.get_direction(margin_pos, margin_next_pos)
            -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
            place_at_position(player, default_connection_type, margin_pos,
                    storage.utils.get_entity_direction(default_connection_type, margin_dir),
                    serialized_entities, dry_run, counter_state, false)

            -- Split the section into multiple underground segments, limited by remaining_sections
            local segments = split_section_into_underground_segments(section, path, range, remaining_sections)

            -- Update remaining_sections count
            remaining_sections = remaining_sections - #segments

            for i, segment in ipairs(segments) do
                -- Place underground entrance
                local entrance_pos = path[segment.entrance_index].position
                local exit_pos = path[segment.exit_index].position
                local dir = storage.utils.get_direction(entrance_pos, exit_pos)

                -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
                local entity_dir = storage.utils.get_entity_direction(underground_type, dir)

                place_at_position(player, underground_type, entrance_pos,
                        entity_dir,
                        serialized_entities, dry_run, counter_state, false)

                -- Adjust direction for pipe-to-ground exit (rotate 180°)
                if underground_type == 'pipe-to-ground' then
                    entity_dir = storage.utils.get_entity_direction(underground_type, (dir + 8) % 16)
                end

                place_at_position(player, underground_type, exit_pos,
                        entity_dir,
                        serialized_entities, dry_run, counter_state, true)

                -- Update current_index to after the exit
                current_index = segment.exit_index + 1
            end
            -- Place final surface entity for direction change if we had segments
            if #segments > 0 then
                local final_margin_pos = path[section.end_index].position
                local final_prev_pos = path[section.end_index - 1].position
                local final_dir = storage.utils.get_direction(final_prev_pos, final_margin_pos)
                -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
                place_at_position(player, default_connection_type, final_margin_pos,
                        storage.utils.get_entity_direction(default_connection_type, final_dir),
                        serialized_entities, dry_run, counter_state, false)
            end

            -- If we've used all available underground sections, use regular entities for the rest
            if remaining_sections <= 0 then
                break
            end

        end

        -- Place remaining regular entities to finish the connection
        while current_index < #path do
            local current_pos = path[current_index].position
            local next_pos = path[current_index + 1].position
            -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
            local dir = storage.utils.get_direction(current_pos, next_pos)
            place_at_position(player, default_connection_type, current_pos,
                    storage.utils.get_entity_direction(default_connection_type, dir),
                    serialized_entities, dry_run, counter_state, false)
            current_index = current_index + 1
        end

        -- After underground segment placement
        if current_index == #path and not path[#path].has_entity then
            local final_pos = path[#path].position
            -- a one-tile leg has no previous tile
            local prev_pos = (path[#path-1] or path[#path]).position
            -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
            local dir = storage.utils.get_direction(prev_pos, final_pos)
            place_at_position(player, default_connection_type, final_pos,
                    storage.utils.get_entity_direction(default_connection_type, dir),
                    serialized_entities, dry_run, counter_state, false)
        end
    else
        -- Handle source belt orientation if it exists
        if not is_electric_pole and not table_contains(connection_types, 'pipe') then
            local source_pos = {x = source_x, y = source_y}
            local entities = game.surfaces[1].find_entities_filtered{
                position = source_pos,
                name = connection_types,
                force = "player"
            }

            if #entities > 0 and #path > 1 then
                -- Calculate initial direction based on first two points in path
                local initial_dir = storage.utils.get_direction(path[1].position, path[2].position)
                --local entity_dir = storage.utils.get_entity_direction('pipe', initial_dir/2)

                -- Update source belt direction if needed
                local source_belt = entities[1]
                if source_belt and source_belt.valid and source_belt.direction ~= initial_dir then
                    if dry_run then
                        -- a dry run turns nothing; it reports the belt the real call would turn
                        counter_state.would_turn = {
                            name = "\"" .. source_belt.name .. "\"",
                            x = source_belt.position.x,
                            y = source_belt.position.y,
                            from = source_belt.direction,
                            to = initial_dir
                        }
                    else
                        source_belt.direction = initial_dir
                        table.insert(serialized_entities, storage.utils.serialize_entity(source_belt))
                    end
                end
            end
        end

        if is_electric_pole then
            -- Place poles until we achieve connectivity
            local last_pole = source_entity

            for i = 1, #path, step_size do
                local current_pos = path[i].position
                local dir = storage.utils.get_direction(current_pos, path[math.min(i + step_size, #path)].position)
                -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
                local entity_dir = storage.utils.get_entity_direction(default_connection_type, dir)

                -- Place the pole
                local placed_entity = place_at_position(player, default_connection_type, current_pos, entity_dir, serialized_entities, dry_run, counter_state)

                if not dry_run then
                    -- Get the newly placed pole
                    local current_pole = placed_entity or storage.utils.get_closest_entity(player, current_pos)

                    -- Check if we've achieved connectivity to the target
                    if are_poles_connected(current_pole, target_entity) then
                        break  -- Stop placing poles once we have connectivity
                    end

                    last_pole = current_pole
                end
            end

            -- If we haven't achieved connectivity yet, place one final pole at the target
            if not dry_run and last_pole and target_entity and not are_poles_connected(last_pole, target_entity) then
                local final_dir = storage.utils.get_direction(path[#path].position, end_position)
                -- game.print("Placing final pole at "..serpent.line(end_position))
                -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
                place_at_position(player, default_connection_type, end_position,
                        storage.utils.get_entity_direction(default_connection_type, final_dir),
                        serialized_entities, dry_run, counter_state)
            end
        else
            if table_contains(connection_types, 'pipe') then
                place_at_position(player, 'pipe', start_position, 0, serialized_entities, dry_run, counter_state)
            end

            for i = 1, #path-1, step_size do
                local dir = storage.utils.get_direction(path[i].position, path[math.min(i + step_size, #path)].position)
                -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
                local placed = place_at_position(player, default_connection_type, path[i].position,
                        storage.utils.get_entity_direction(default_connection_type, dir),
                        serialized_entities, dry_run, counter_state)
                if placed then
                    last_placed_entity = placed
                end
            end

            -- Handle final placement
            if table_contains(connection_types, 'pipe') then
                local preemptive_target = {
                    x = (target_x + path[#path].position.x)/2,
                    y = (target_y + path[#path].position.y)/2
                }

                -- Place intermediate and final pipes
                place_at_position(player, 'pipe', path[#path].position,
                        storage.utils.get_direction(path[#path].position, preemptive_target),
                        serialized_entities, dry_run, counter_state)

                place_at_position(player, 'pipe', preemptive_target,
                        storage.utils.get_direction(path[#path].position, preemptive_target),
                        serialized_entities, dry_run, counter_state)

                place_at_position(player, 'pipe', end_position,
                        storage.utils.get_direction(preemptive_target, end_position),
                        serialized_entities, dry_run, counter_state)
            else
                local last_path_index = #path
                local second_to_last_index = math.max(1, last_path_index - 1)
                local final_dir = storage.utils.get_direction(
                        path[second_to_last_index].position,
                        path[last_path_index].position
                )

                -- Factorio 2.0: get_direction returns 0/4/8/12 - pass directly
                local final_entity = place_at_position(player, default_connection_type, end_position,
                        storage.utils.get_entity_direction(default_connection_type, final_dir),
                        serialized_entities, dry_run, counter_state)
                        

                if final_entity then
                    last_placed_entity = final_entity
                end

                -- After all belts are placed, serialize the entire belt group if we're not in dry run
                if not dry_run and last_placed_entity and last_placed_entity.valid and default_connection_type:find("belt") then
                    -- Clear the existing serialized entities (which only contain individual placements)
                    local individual_count = #serialized_entities
                    serialized_entities = {}
                    
                    -- Find the full belt network by checking from source position
                    local source_belt = game.surfaces[1].find_entity(default_connection_type, start_position)
                    local group_data = nil
                    
                    if source_belt and source_belt.valid then
                        group_data = serialize_belt_group(source_belt)
                    else
                        group_data = serialize_belt_group(last_placed_entity)
                    end
                    
                    if group_data then
                        for _, serialized in ipairs(group_data) do
                            table.insert(serialized_entities, serialized)
                        end
                    else
                        -- Restore individual entities if group serialization failed
                        for i = 1, individual_count do
                            serialized_entities[i] = serialized_entities[i]
                        end
                    end
                end
            end
        end
    end

    -- Check final connectivity
    local is_connected = false
    if source_entity and target_entity then
        if is_electric_pole then
            is_connected = are_poles_connected(source_entity, target_entity)
        else
            is_connected = are_fluidboxes_connected(source_entity, target_entity)
        end
    end

    -- game.print("Connection status: " .. tostring(is_connected))


    return {
        entities = serialized_entities,
        connected = is_connected,
        number_of_entities = counter_state.place_counter,
        planned = counter_state.planned,
        would_turn = counter_state.would_turn
    }
end

-- "Cannot place pipe at (x, y): blocked by stone-furnace, cliff" (or the tile, when no entity is there)
storage.utils.connect_blockage_message = function(connection_type, position, entities)
    local names = {}
    for _, entity in pairs(entities or {}) do
        local t = entity.valid and entity.type
        if t and t ~= "character" and t ~= "resource" and t ~= "item-entity" and t ~= "corpse" and #names < 3 then
            table.insert(names, entity.name)
        end
    end
    local cause
    if #names > 0 then
        cause = "blocked by " .. table.concat(names, ", ")
    else
        local tile = game.surfaces[1].get_tile(position.x, position.y)
        cause = "the tile there (" .. (tile and tile.valid and tile.name or "unknown") .. ") does not allow it"
    end
    return "\"Cannot connect: cannot place " .. connection_type .. " at (" .. position.x .. ", " .. position.y .. "): " .. cause .. "\""
end

storage.utils.normalise_path = function(original_path, start_position, end_position)
    local path = {}
    local seen = {}  -- To track seen positions
    if original_path == nil or #original_path < 1 or original_path == "not_found" then
        error("Failed to find a path.")
    end
    if math.ceil(start_position.x) == start_position.x then
        start_position.x = start_position.x + 0.5
        --start_position.y = start_position.y + 0.5
    end
    if math.ceil(start_position.y) == start_position.y then
        start_position.y = start_position.y + 0.5
    end

    if math.ceil(end_position.x) == end_position.x or math.ceil(end_position.y) == end_position.y then
        end_position.x = end_position.x + 0.5
        end_position.y = end_position.y + 0.5
    end

    --game.print(serpent.block(original_path))
    --for i = 1, #original_path do
    --    game.print(serpent.line(original_path[i]))
    --end

    if math.ceil(original_path[1].position.x) == original_path[1].position.x or math.ceil(original_path[1].position.y) == original_path[1].position.y then
        original_path[1].position.x = original_path[1].position.x + 0.5
        original_path[1].position.y = original_path[1].position.y + 0.5
    end

    -- Helper function to add unique positions
    local function add_unique(pos, prev_pos)
        local key = pos.x .. "," .. pos.y
        if not seen[key] then
            if is_placeable(pos) then
                table.insert(path, {position = pos})
                seen[key] = true
                return pos
            else
                local alt_pos = find_placeable_neighbor(pos, prev_pos)
                if alt_pos then
                    local alt_key = alt_pos.x .. "," .. alt_pos.y
                    if not seen[alt_key] then
                        table.insert(path, {position = alt_pos})
                        seen[alt_key] = true
                        return alt_pos
                    end
                end
            end
        end
        return nil
    end

    -- Add start position first
    local previous_pos = add_unique(start_position, nil) or start_position

    -- Process each segment of the path
    local current_pos = previous_pos
    for i = 1, #original_path do
        local target_pos = original_path[i].position
        local interpolated = interpolate_manhattan(current_pos, target_pos)

        -- Add interpolated positions
        for _, point in ipairs(interpolated) do
            local new_pos = add_unique(point.position, current_pos)
            if new_pos then
                current_pos = new_pos
            end
        end

        -- Add the target position
        local new_pos = add_unique(target_pos, current_pos)
        if new_pos then
            current_pos = new_pos
        end
    end

    -- Finally interpolate to end position if it's different from the last position
    if current_pos.x ~= end_position.x or current_pos.y ~= end_position.y then
        local interpolated = interpolate_manhattan(current_pos, end_position)
        for _, point in ipairs(interpolated) do
            local new_pos = add_unique(point.position, current_pos)
            if new_pos then
                current_pos = new_pos
            end
        end
        add_unique(end_position, current_pos)
    end

    return path
end

-- Helper function to check if two positions are adjacent
local function are_positions_adjacent(pos1, pos2)
    local dx = math.abs(pos1.x - pos2.x)
    local dy = math.abs(pos1.y - pos2.y)
    return (dx <= 1 and dy <= 1) and not (dx == 0 and dy == 0)
end

-- Helper function to validate belt direction compatibility
local function are_belt_directions_compatible(dir1, dir2, pos1, pos2)
    -- Convert positions to vectors
    local dx = pos2.x - pos1.x
    local dy = pos2.y - pos1.y

    -- Check if the belts are pointing in compatible directions
    -- This is a simplified check - you may need to adjust based on your specific needs
    if dir1 == dir2 then
        -- Same direction - check if it matches position delta
        local expected_dir = storage.utils.get_direction(pos1, pos2)
        return dir1 == expected_dir
    else
        -- Different directions - check if they form a valid turn
        -- Add more sophisticated turn validation if needed
        return are_positions_adjacent(pos1, pos2)
    end
end


-- Helper function to check if two positions are connected by belts
local function are_positions_belt_connected(start_pos, end_pos, connection_type)
    -- Find belt at start position - try multiple belt types if connection_type is nil
    local belt_types = {"transport-belt", "fast-transport-belt", "express-transport-belt"}
    if connection_type then
        belt_types = {connection_type}
    end
    
    local start_belt = nil
    for _, belt_type in ipairs(belt_types) do
        start_belt = game.surfaces[1].find_entity(belt_type, start_pos)
        if start_belt then
            break
        end
    end
    
    if not start_belt then
        return false
    end
    
    -- Use BFS to find if there's a path to end position
    local visited = {}
    local queue = {start_belt}
    local max_search = 200 -- Prevent infinite loops
    local search_count = 0
    
    while #queue > 0 and search_count < max_search do
        search_count = search_count + 1
        local current_belt = table.remove(queue, 1)
        
        if not current_belt or not current_belt.valid then
            goto continue
        end
        
        local pos_key = current_belt.position.x .. "," .. current_belt.position.y
        if visited[pos_key] then
            goto continue
        end
        visited[pos_key] = true
        
        -- Check if we reached the target
        local dx = math.abs(current_belt.position.x - end_pos.x)
        local dy = math.abs(current_belt.position.y - end_pos.y)
        if dx < 0.1 and dy < 0.1 then
            return true
        end
        
        -- Add neighboring belts to queue
        if current_belt.belt_neighbours then
            -- Add output belts
            if current_belt.belt_neighbours.outputs then
                for _, output_belt in pairs(current_belt.belt_neighbours.outputs) do
                    if output_belt and output_belt.valid then
                        table.insert(queue, output_belt)
                    end
                end
            end
            -- Add input belts  
            if current_belt.belt_neighbours.inputs then
                for _, input_belt in pairs(current_belt.belt_neighbours.inputs) do
                    if input_belt and input_belt.valid then
                        table.insert(queue, input_belt)
                    end
                end
            end
        end
        
        ::continue::
    end
    
    return false
end

-- Helper function to check if two positions are connected by electric poles
local function are_positions_pole_connected(start_pos, end_pos, connection_type)
    -- Find pole at start position - try multiple pole types if connection_type is nil
    local pole_types = {"small-electric-pole", "medium-electric-pole", "big-electric-pole", "substation"}
    if connection_type then
        pole_types = {connection_type}
    end
    
    local start_pole = nil
    for _, pole_type in ipairs(pole_types) do
        start_pole = game.surfaces[1].find_entity(pole_type, start_pos)
        if start_pole then
            break
        end
    end
    
    if not start_pole then
        return false
    end
    
    -- Use electric network ID for faster checking
    if start_pole.electric_network_id then
        local end_pole = nil
        for _, pole_type in ipairs(pole_types) do
            end_pole = game.surfaces[1].find_entity(pole_type, end_pos)
            if end_pole then
                break
            end
        end
        
        if end_pole and end_pole.electric_network_id then
            return start_pole.electric_network_id == end_pole.electric_network_id
        end
    end
    
    return false
end

-- Helper function to check if two positions are connected by pipes
local function are_positions_pipe_connected(start_pos, end_pos, connection_type)
    -- Find pipe at start position - try multiple pipe types if connection_type is nil
    local pipe_types = {"pipe", "pipe-to-ground"}
    if connection_type then
        pipe_types = {connection_type}
    end
    
    local start_pipe = nil
    for _, pipe_type in ipairs(pipe_types) do
        start_pipe = game.surfaces[1].find_entity(pipe_type, start_pos)
        if start_pipe then
            break
        end
    end
    
    if not start_pipe then
        return false
    end
    
    -- Use fluid system ID for checking pipe connections
    if has_valid_fluidbox(start_pipe) then
        local end_pipe = nil
        for _, pipe_type in ipairs(pipe_types) do
            end_pipe = game.surfaces[1].find_entity(pipe_type, end_pos)
            if end_pipe then
                break
            end
        end
        
        if end_pipe and has_valid_fluidbox(end_pipe) then
            -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id
            return start_pipe.fluidbox.get_fluid_segment_id(1) == end_pipe.fluidbox.get_fluid_segment_id(1)
        end
    end

    return false
end

-- Helper function to serialize pipe group from a starting pipe using improved BFS
local function serialize_pipe_group(entity)
    if not entity or not entity.valid or (entity.type ~= "pipe" and entity.type ~= "pipe-to-ground") then
        return nil
    end

    if not has_valid_fluidbox(entity) then
        return nil
    end

    local serialized = {}
    local visited = {}
    local queue = {entity}
    local max_search = 200
    local search_count = 0
    -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id
    local system_id = entity.fluidbox.get_fluid_segment_id(1)

    while #queue > 0 and search_count < max_search do
        search_count = search_count + 1
        local current_pipe = table.remove(queue, 1)

        if not current_pipe or not current_pipe.valid then
            goto continue
        end

        local pipe_id = current_pipe.unit_number
        if visited[pipe_id] then
            goto continue
        end
        visited[pipe_id] = true

        -- Serialize current pipe
        table.insert(serialized, storage.utils.serialize_entity(current_pipe))

        -- Find all connected pipes in the same fluid system
        local all_pipes = game.surfaces[1].find_entities_filtered{
            position = current_pipe.position,
            radius = 10,
            type = {"pipe", "pipe-to-ground"}
        }

        for _, pipe in pairs(all_pipes) do
            if pipe.valid and has_valid_fluidbox(pipe) and not visited[pipe.unit_number] then
                -- Factorio 2.0: get_fluid_system_id -> get_fluid_segment_id
                if pipe.fluidbox.get_fluid_segment_id(1) == system_id then
                    table.insert(queue, pipe)
                end
            end
        end
        
        ::continue::
    end
    
    return serialized
end

-- Helper function to serialize pole group from a starting pole using improved logic
local function serialize_pole_group(entity)
    if not entity or not entity.valid or entity.type ~= "electric-pole" then
        return nil
    end
    
    local serialized = {}
    local visited = {}
    
    if entity.electric_network_id then
        -- Find all poles in the same electric network within a reasonable search area
        -- This prevents searching the entire map for very large networks
        local search_areas = {
            {position = entity.position, radius = 50},  -- Close area first
            {position = entity.position, radius = 100}, -- Medium area if needed
        }
        
        local network_id = entity.electric_network_id
        
        for _, area in ipairs(search_areas) do
            local nearby_poles = game.surfaces[1].find_entities_filtered{
                position = area.position,
                radius = area.radius,
                type = "electric-pole"
            }
            
            for _, pole in pairs(nearby_poles) do
                if pole.valid and pole.electric_network_id == network_id then
                    local pole_id = pole.unit_number
                    if not visited[pole_id] then
                        visited[pole_id] = true
                        table.insert(serialized, storage.utils.serialize_entity(pole))
                    end
                end
            end
            
            -- If we found poles in the first area, we likely have the full local network
            if #serialized > 1 then
                break
            end
        end
    end
    
    return serialized
end

-- Function to validate belt connectivity
local function validate_belt_connectivity(path)
    if not path or #path < 2 then
        return false, "Invalid path length"
    end

    -- Check each segment of the path
    for i = 1, #path - 1 do
        local current_pos = path[i].position
        local next_pos = path[i + 1].position

        -- Check if positions are adjacent or properly spaced
        if not are_positions_adjacent(current_pos, next_pos) then
            return false, "Could not create a belt at position " ..
                   current_pos.x .. "," .. current_pos.y
        end

        -- Calculate directions for current and next position
        local current_dir = storage.utils.get_direction(current_pos, next_pos)
        local next_dir = i < #path - 1 and
                        storage.utils.get_direction(next_pos, path[i + 2].position) or
                        current_dir

        -- Check direction compatibility
        if not are_belt_directions_compatible(current_dir, next_dir, current_pos, next_pos) then
            return false, "Invalid belt turn detected at position " ..
                   current_pos.x .. "," .. current_pos.y
        end

        -- Check if position is placeable - BUT allow existing belts of the same type
        local entities_at_pos = game.surfaces[1].find_entities_filtered{
            position = current_pos,
            radius = 0.1
        }
        
        for _, existing_entity in pairs(entities_at_pos) do
            if existing_entity and existing_entity.valid then
                -- If there's already a belt of the same type, that's okay
                -- Also ignore character entities and resource entities (they don't block belt placement)
                if not existing_entity.name:find("belt") and 
                   existing_entity.name ~= "character" and
                   existing_entity.type ~= "resource" then
                    return false, "Cannot place belt at position " ..
                           current_pos.x .. "," .. current_pos.y .. " (blocked by " .. existing_entity.name .. ")"
                end
            end
        end
    end

    -- Check final position - same logic for existing belts
    local final_pos = path[#path].position
    local final_entities = game.surfaces[1].find_entities_filtered{
        position = final_pos,
        radius = 0.1
    }
    
    for _, existing_final in pairs(final_entities) do
        if existing_final and existing_final.valid then
            -- Ignore character entities, existing belts, and resource entities
            if not existing_final.name:find("belt") and 
               existing_final.name ~= "character" and
               existing_final.type ~= "resource" then
                return false, "Cannot place belt at final position (blocked by " .. existing_final.name .. ")"
            end
        end
    end

    return true, nil
end

-- Modify the connect_entities function to include validation
local function connect_entities_with_validation(player_index, source_x, source_y, target_x, target_y, path_handle, connection_types, dry_run)
    local path = storage.paths[path_handle]
    local pole_type = wire_reach[connection_types[1]] and connection_types[1] or nil
    -- (pipes without a path, handle -1: an existing connection is still found, then
    -- the tile-by-tile route is used)
    if path == nil and not pole_type and not is_pipe_route(connection_types) then
        error("No path found")
    end
    
    -- Check for existing connections first
    
    for _,connection_type in pairs(connection_types) do
        if wire_reach[connection_type] then
            -- Check if positions are already connected by electric poles
            if are_positions_pole_connected(
                {x = source_x, y = source_y},
                {x = target_x, y = target_y},
                connection_type
            ) then
                -- Positions are already connected - return existing pole group
                local start_pole = nil
                local pole_types = {"small-electric-pole", "medium-electric-pole", "big-electric-pole", "substation"}
                for _, pole_type in ipairs(pole_types) do
                    start_pole = game.surfaces[1].find_entity(pole_type, {x = source_x, y = source_y})
                    if start_pole then
                        break
                    end
                end
                
                if start_pole then
                    local group_data = serialize_pole_group(start_pole)
                    if group_data then
                        return {
                            entities = group_data,
                            connected = true,
                            number_of_entities = 0
                        }
                    end
                end
                -- Fallback: return empty connection result (existing connection)
                return {
                    entities = {},
                    connected = true,
                    number_of_entities = 0
                }
            end
        elseif connection_type == "pipe" or connection_type == "pipe-to-ground" then
            -- Check if positions are already connected by pipes
            if are_positions_pipe_connected(
                {x = source_x, y = source_y},
                {x = target_x, y = target_y},
                connection_type
            ) then
                -- Positions are already connected - return existing pipe group
                local start_pipe = nil
                local pipe_types = {"pipe", "pipe-to-ground"}
                for _, pipe_type in ipairs(pipe_types) do
                    start_pipe = game.surfaces[1].find_entity(pipe_type, {x = source_x, y = source_y})
                    if start_pipe then
                        break
                    end
                end
                
                if start_pipe then
                    local group_data = serialize_pipe_group(start_pipe)
                    if group_data then
                        return {
                            entities = group_data,
                            connected = true,
                            number_of_entities = 0
                        }
                    end
                end
                -- Fallback: return empty connection result (existing connection)
                return {
                    entities = {},
                    connected = true,
                    number_of_entities = 0
                }
            end
        elseif connection_type:find("belt") then
            -- Check if positions are already FULLY connected by belts
            if are_positions_belt_connected(
                {x = source_x, y = source_y},
                {x = target_x, y = target_y},
                connection_type
            ) then
                -- Positions are already connected - return existing group
                
                -- Positions are already connected - return existing belt group
                local start_belt = game.surfaces[1].find_entity(connection_type, {x = source_x, y = source_y})
                if start_belt then
                    local group_data = serialize_belt_group(start_belt)
                    if group_data then
                        return {
                            entities = group_data,
                            connected = true,
                            number_of_entities = 0
                        }
                    end
                end
                -- Fallback: return empty connection result (existing connection)
                return {
                    entities = {},
                    connected = true,
                    number_of_entities = 0
                }
            end
            
            -- Normalize path first
            local normalized_path = storage.utils.normalise_path(path,
                    {x = source_x, y = source_y},
                    {x = target_x, y = target_y})

            -- Validate connectivity
            local is_valid, error_message = validate_belt_connectivity(normalized_path)
            if not is_valid then
                error(error_message)
            end
            break
        end
    end

    -- Poles: a near-straight line at full wire reach (the game's path, if any, only guides it)
    if pole_type then
        return connect_poles(storage.agent_characters[player_index], source_x, source_y, target_x, target_y,
                             path, pole_type, dry_run)
    end

    if path == nil then
        error("No path found")
    end

    -- If validation passes or it's not a belt, proceed with normal connection
    return connect_entities(player_index, source_x, source_y, target_x, target_y,
                          path_handle, connection_types, dry_run)
end


-- Using the new shortest_path function.
-- Items the route places, per name (from the dry pass)
local function planned_counts(result)
    local counts = {}
    for _, p in pairs((result and result.planned) or {}) do
        local name = tostring(p.name):gsub('"', '')
        counts[name] = (counts[name] or 0) + 1
    end
    return counts
end

storage.actions.connect_entities = function(player_index, source_x, source_y, target_x, target_y, path_handle, connection_type_string, dry_run, number_of_connection_entities)

    local connection_types = {}
    for item in string.gmatch(connection_type_string, "([^,]+)") do
        table.insert(connection_types, item)
    end
    local player = storage.agent_characters[player_index]
    -- The checks below step the character aside; it is always put back where it
    -- stood (the client walks it along the route, in game time, before building).
    local home = player and player.valid and {x = player.position.x, y = player.position.y}
    local function go_home()
        if home and player.valid and (player.position.x ~= home.x or player.position.y ~= home.y) then
            local spot = player.surface.find_non_colliding_position("character", home, 5, 0.1) or home
            player.teleport(spot)
        end
    end

    -- One pass. A pipe route the game's walking path cannot give (no path, a path
    -- over cliffs, a timed-out search) is searched tile by tile instead.
    local function pass(dry, by_tiles)
        -- belts without a path (handle -1): the tile-by-tile route
        if path_handle == -1 and is_belt_route(connection_types) then
            return connect_belts_by_tiles(player_index, source_x, source_y, target_x, target_y, connection_types, dry), false
        end
        if is_pipe_to_ground_only(connection_types) then
            return connect_pipe_to_ground_line(player_index, source_x, source_y, target_x, target_y, dry), false
        end
        if by_tiles then
            return connect_pipes_by_tiles(player_index, source_x, source_y, target_x, target_y, connection_types, dry), true
        end
        local ok, answer = pcall(connect_entities_with_validation, player_index, source_x, source_y, target_x, target_y, path_handle, connection_types, dry)
        if ok then return answer, false end
        if is_pipe_route(connection_types) then
            local ok2, answer2 = pcall(connect_pipes_by_tiles, player_index, source_x, source_y, target_x, target_y, connection_types, dry)
            if ok2 then return answer2, true end
            local first = tostring(answer):gsub('^"', ''):gsub('"$', '')
            local second = tostring(answer2):gsub('^"', ''):gsub('"$', '')
            error("\"" .. first .. " A tile-by-tile search found no route either: " .. second .. "\"", 0)
        end
        error(answer, 0)
    end

    storage.connect_dry_run_only = true
    local ok, answer, by_tiles = pcall(pass, true, false)
    storage.connect_dry_run_only = nil
    if not ok or dry_run then
        go_home()
        if not ok then error(answer, 0) end
        return answer
    end

    -- Every item the route places must be in the inventory, per item
    local inventory = player.get_inventory(defines.inventory.character_main)
    local short = {}
    for name, count in pairs(planned_counts(answer)) do
        local have = inventory and inventory.get_item_count(name) or 0
        if have < count then
            table.insert(short, name .. ": required " .. count .. ", in inventory " .. have)
        end
    end
    if #short > 0 then
        go_home()
        table.sort(short)
        error("\"You do not have enough items in your inventory to complete this connection (" .. table.concat(short, "; ") .. "). Nothing was built.\"", 0)
    end

    local ok2, result = pcall(pass, false, by_tiles)
    go_home()
    if not ok2 then error(result, 0) end

    -- Every tile the dry pass planned must now hold its entity (no gaps)
    if not wire_reach[connection_types[1]] then
        local missing = {}
        for _, p in pairs(answer.planned or {}) do
            local name = tostring(p.name):gsub('"', '')
            if #player.surface.find_entities_filtered{name = name, position = {x = p.x, y = p.y}, radius = 0.5} == 0 then
                table.insert(missing, name .. " at (" .. p.x .. ", " .. p.y .. ")")
            end
        end
        if #missing > 0 then
            error("\"The connection was built with gaps: " .. #missing .. " planned entities are missing ("
                .. table.concat(missing, ", ", 1, math.min(#missing, 5)) .. ")\"", 0)
        end
    end
    return result
end
