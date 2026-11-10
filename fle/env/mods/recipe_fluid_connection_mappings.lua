-- Helper function to get fluid type from ingredient/product
local function get_fluid_type(item)
    if item.type == "fluid" then
        return item.name
    end
    return nil
end

-- Helper function to get position offsets based on fluid type and recipe
local function get_refinery_position_offsets(fluid_type, recipe, is_input)
    -- Basic oil processing
    if #recipe.ingredients == 1 then
        if not is_input then
            return 2, -3  -- Top right
        else
            return 1, 3 -- Bottom right
        end
    end

    -- game.print(serpent.block(recipe.ingredients))
    -- Advanced oil processing
    if #recipe.ingredients == 2 and recipe.ingredients[2].name == "crude-oil" then
        if is_input then
            if fluid_type == "crude-oil" then
                return 1, 3  -- South side (for north-facing refinery)
            else
                return -1, 3   -- South side (water)
            end
        else
            -- For north-facing refinery, outputs are on north side (y = -3)
            -- From left to right: heavy-oil (-2), light-oil (0), petroleum-gas (+2)
            if fluid_type == "heavy-oil" then
                return -2, -3     -- North side, left
            elseif fluid_type == "light-oil" then
                return 0, -3      -- North side, middle
            else
                return 2, -3      -- North side, right (petroleum-gas)
            end
        end
    end

    -- Coal liquefaction
    if #recipe.ingredients == 3 and recipe.ingredients[3].name == "steam" then
        if is_input then
            if fluid_type == "steam" then
                return 1, 3  -- Top left
            else
                return -1, 3   -- Top right (heavy oil)
            end
        else
            -- Same output ports as advanced oil processing: the products (heavy oil,
            -- light oil, petroleum gas) fill the north-side boxes from left to right
            if fluid_type == "heavy-oil" then
                return -2, -3     -- North side, left
            elseif fluid_type == "light-oil" then
                return 0, -3      -- North side, middle
            else
                return 2, -3      -- North side, right (petroleum-gas)
            end
        end
    end
    return 0,0
end

-- Helper function to get chemical plant position offsets
-- For a chemical plant whose entity.direction is north (Factorio 2.0 prototype):
--   Inputs are on the north side (y - 1.5)
--   Outputs are on the south side (y + 1.5)
-- Used only when the game's own pipe connections can't be read (see
-- get_chemical_plant_fluid_mappings).
local function get_chemical_plant_position_offsets(index, total, is_input)
    if is_input then
        if total == 1 then
            return -1, -1.5  -- North side for single input
        else
            -- For two inputs, space them out on north side
            return -1 + (index - 1) * 2, -1.5
        end
    else
        -- Outputs are on the south side
        return -1, 1.5
    end
end

-- Helper function to rotate coordinates based on entity direction
local function rotate_coordinates(x_offset, y_offset, direction)
    if direction == defines.direction.north then
        return x_offset, y_offset
    elseif direction == defines.direction.south then
        return -x_offset, -y_offset
    elseif direction == defines.direction.east then
        return -y_offset, x_offset
    elseif direction == defines.direction.west then
        return y_offset, -x_offset
    end
end

storage.utils.get_refinery_fluid_mappings = function(entity, recipe)
    if not entity or not recipe then return nil end
    if not entity.position then return nil end

    local x, y = entity.position.x, entity.position.y
    local input_points = {}
    local output_points = {}

    -- Map inputs
    for _, ingredient in pairs(recipe.ingredients) do
        if ingredient.type == "fluid" then
            local x_offset, y_offset = get_refinery_position_offsets(ingredient.name, recipe, true)
            local rotated_x, rotated_y = rotate_coordinates(x_offset, y_offset, entity.direction)
            table.insert(input_points, {
                x = x + rotated_x,
                y = y + rotated_y,
                type = "\""..ingredient.name.."\""
            })
        end
    end

    -- Map outputs
    for _, product in pairs(recipe.products) do
        if product.type == "fluid" then
            local x_offset, y_offset = get_refinery_position_offsets(product.name, recipe, false)
            local rotated_x, rotated_y = rotate_coordinates(x_offset, y_offset, entity.direction)
            table.insert(output_points, {
                x = x + rotated_x,
                y = y + rotated_y,
                type = "\""..product.name.."\""
            })
        end
    end

    return {
        inputs = input_points,
        outputs = output_points
    }
end

-- Fluid names of the given type in a recipe's ingredient or product list, in order
local function fluid_names(list)
    local names = {}
    for _, item in pairs(list or {}) do
        if item.type == "fluid" then
            table.insert(names, item.name)
        end
    end
    return names
end

-- The chemical plant's connection points as the game has them: for each input
-- or output fluid box, the point between the plant's port tile and the tile a
-- pipe must occupy (LuaFluidBox.get_pipe_connections), typed with the fluid the
-- recipe puts in that box. Returns nil if the fluid boxes can't be read.
local function read_chemical_plant_fluid_mappings(entity, recipe)
    local fluid_inputs = fluid_names(recipe.ingredients)
    local fluid_outputs = fluid_names(recipe.products)
    local input_points, output_points = {}, {}
    local n_in, n_out = 0, 0
    for i = 1, #entity.fluidbox do
        local proto = entity.fluidbox.get_prototype(i)
        if type(proto) == "table" and proto.object_name == nil then
            proto = proto[1]
        end
        local production_type = proto and proto.production_type
        local connections = entity.fluidbox.get_pipe_connections(i)
        if production_type ~= "input" and production_type ~= "output" then
            local flow = connections[1] and connections[1].flow_direction
            if flow == "input" or flow == "output" then
                production_type = flow
            end
        end
        local filter = entity.fluidbox.get_filter(i)
        local fluid = filter and filter.name
        if production_type == "input" then
            n_in = n_in + 1
            fluid = fluid or fluid_inputs[n_in]
        elseif production_type == "output" then
            n_out = n_out + 1
            fluid = fluid or fluid_outputs[n_out]
        end
        if fluid and (production_type == "input" or production_type == "output") then
            for _, connection in pairs(connections) do
                if connection.position and connection.target_position then
                    local point = {
                        x = (connection.position.x + connection.target_position.x) / 2,
                        y = (connection.position.y + connection.target_position.y) / 2,
                        type = "\""..fluid.."\""
                    }
                    if production_type == "input" then
                        table.insert(input_points, point)
                    else
                        table.insert(output_points, point)
                    end
                end
            end
        end
    end
    if #input_points == 0 and #output_points == 0 then
        return nil
    end
    return {inputs = input_points, outputs = output_points}
end

-- Helper function to map connection points to fluid types for chemical plant
storage.utils.get_chemical_plant_fluid_mappings = function(entity, recipe)
    if not entity or not recipe then return nil end
    if not entity.position then return nil end

    if entity.valid then
        local ok, mappings = pcall(read_chemical_plant_fluid_mappings, entity, recipe)
        if ok and mappings then
            return mappings
        end
    end

    local x, y = entity.position.x, entity.position.y
    local input_points = {}
    local output_points = {}

    -- Count fluid inputs
    local fluid_inputs = {}
    for _, ingredient in pairs(recipe.ingredients) do
        if ingredient.type == "fluid" then
            table.insert(fluid_inputs, ingredient)
        end
    end

    -- Map inputs
    for i, ingredient in ipairs(fluid_inputs) do
        local x_offset, y_offset = get_chemical_plant_position_offsets(i, #fluid_inputs, true)
        local rotated_x, rotated_y = rotate_coordinates(x_offset, y_offset, entity.direction)
        table.insert(input_points, {
            x = x + rotated_x,
            y = y + rotated_y,
            type = "\""..ingredient.name.."\""
        })
    end

    -- Map outputs
    for _, product in pairs(recipe.products) do
        if product.type == "fluid" then
            local x_offset, y_offset = get_chemical_plant_position_offsets(1, 1, false)
            local rotated_x, rotated_y = rotate_coordinates(x_offset, y_offset, entity.direction)
            table.insert(output_points, {
                x = x + rotated_x,
                y = y + rotated_y,
                type = "\""..product.name.."\""
            })
        end
    end

    return {
        inputs = input_points,
        outputs = output_points
    }
end