-- Throw cliff explosives at a position, as a player does: one item from the inventory,
-- the target within the capsule's throw range of the character, and every cliff within
-- the explosion's radius of the target destroyed. The item is used up even if no cliff
-- is in the radius.
storage.actions.throw_cliff_explosives = function(player_index, x, y)
    local player = storage.utils.ensure_valid_character(player_index)
    local surface = player.surface
    local item_name = "cliff-explosives"

    local item = prototypes.item[item_name]
    local action = item and item.capsule_action
    if action == nil or action.type ~= "destroy-cliffs" then
        error("\"cliff-explosives can't be thrown in this game\"")
    end
    local range = (action.attack_parameters and action.attack_parameters.range) or 10
    local radius = action.radius or 1.5

    local dx, dy = player.position.x - x, player.position.y - y
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance > range then
        error("\"The target (" .. x .. ", " .. y .. ") is too far away to throw cliff-explosives. The player position is " ..
              player.position.x .. ", " .. player.position.y .. ", the distance is " ..
              string.format("%.2f", distance) .. " and the max throw range is " .. range .. ". Move closer.\"")
    end

    if player.get_item_count(item_name) < 1 then
        error("\"No cliff_explosives in inventory. Current inventory: " ..
              storage.utils.format_inventory_for_error(player) .. "\"")
    end

    player.remove_item{name = item_name, count = 1}

    local destroyed = {}
    local cliffs = surface.find_entities_filtered{position = {x, y}, radius = radius, type = "cliff"}
    for _, cliff in ipairs(cliffs) do
        if cliff.valid then
            table.insert(destroyed, {x = cliff.position.x, y = cliff.position.y})
            cliff.destroy{do_cliff_correction = true}
        end
    end
    pcall(function()
        surface.create_entity{name = "ground-explosion", position = {x, y}}
    end)

    return {destroyed = #destroyed, cliffs = destroyed, x = x, y = y}
end
