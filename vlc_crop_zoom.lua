-- VLC Intelligent Crop & Zoom Plugin
-- Provides interactive crop/zoom UI with quality upscaling
-- Install: Copy to ~/.local/share/vlc/lua/extensions/ (Linux)
--          or %APPDATA%\VLC\lua\extensions\ (Windows)
--          or ~/Library/Application Support/VLC/lua/extensions/ (macOS)

local descriptor = {
    title = "Crop & Zoom Pro",
    version = "1.0",
    author = "Custom VLC",
    url = "http://www.videolan.org",
    shortdesc = "Advanced crop and zoom with intelligent upscaling",
    description = "Crop video regions and zoom with quality interpolation",
    capabilities = {"input-listener", "meta-fetcher"}
}

-- Plugin state
local cropState = {
    enabled = false,
    crop_x = 0,
    crop_y = 0,
    crop_w = 1920,
    crop_h = 1080,
    zoom_level = 1.0,
    upscale_method = "lanczos",  -- lanczos, spline, cubic
    original_w = 1920,
    original_h = 1080
}

local dialog = nil

-- ============================================================================
-- DIALOG MANAGEMENT
-- ============================================================================

function show_dialog()
    if dialog then
        vlc.deactivate()
        return
    end

    dialog = vlc.dialog("Crop & Zoom Pro")
    
    -- VIDEO PREVIEW / STATUS
    dialog:add_label("Video: Not playing", 1, 1, 2, 1)
    
    -- CROP CONTROLS
    dialog:add_label("<b>Crop Region:</b>", 1, 2, 2, 1)
    
    local crop_x = dialog:add_text_input("0", 1, 3, 1, 1)
    dialog:add_label("X offset", 2, 3, 1, 1)
    
    local crop_y = dialog:add_text_input("0", 1, 4, 1, 1)
    dialog:add_label("Y offset", 2, 4, 1, 1)
    
    local crop_w = dialog:add_text_input("1920", 1, 5, 1, 1)
    dialog:add_label("Width", 2, 5, 1, 1)
    
    local crop_h = dialog:add_text_input("1080", 1, 6, 1, 1)
    dialog:add_label("Height", 2, 6, 1, 1)
    
    -- ZOOM CONTROLS
    dialog:add_label("<b>Zoom Level:</b>", 1, 7, 2, 1)
    
    local zoom_slider = dialog:add_slider(1, 8, 1, 3, 1, 8)
    dialog:add_label("(1x - 8x)", 2, 7, 1, 1)
    
    local zoom_val = dialog:add_text_input("1.0", 1, 8, 1, 1)
    dialog:add_label("Zoom", 2, 8, 1, 1)
    
    -- UPSCALE METHOD
    dialog:add_label("<b>Upscale Method:</b>", 1, 9, 2, 1)
    
    local method_dropdown = dialog:add_dropdown(1, 10, 2, 1)
    method_dropdown:add_value("Lanczos (High Quality)", "lanczos")
    method_dropdown:add_value("Spline (Smooth)", "spline")
    method_dropdown:add_value("Cubic (Fast)", "cubic")
    method_dropdown:add_value("Nearest Neighbor (Pixelated)", "nearest")
    
    -- PREVIEW OPTIONS
    dialog:add_label("<b>Preview:</b>", 1, 11, 2, 1)
    
    local preview_check = dialog:add_check_button("Live preview", 1, 12, 2, 1)
    
    -- ACTION BUTTONS
    dialog:add_button("Apply Crop", function()
        apply_crop(
            tonumber(crop_x:get_text()) or 0,
            tonumber(crop_y:get_text()) or 0,
            tonumber(crop_w:get_text()) or 1920,
            tonumber(crop_h:get_text()) or 1080,
            tonumber(zoom_val:get_text()) or 1.0,
            method_dropdown:get_active()
        )
    end, 1, 13, 1, 1)
    
    dialog:add_button("Reset", function()
        reset_crop()
        crop_x:set_text("0")
        crop_y:set_text("0")
        crop_w:set_text(tostring(cropState.original_w))
        crop_h:set_text(tostring(cropState.original_h))
        zoom_val:set_text("1.0")
    end, 2, 13, 1, 1)
    
    -- Sync controls
    zoom_slider:add_callback(function(val)
        zoom_val:set_text(string.format("%.2f", val))
    end)
    
    zoom_val:add_callback(function(val)
        local zv = tonumber(val) or 1.0
        if zv >= 1 and zv <= 8 then
            zoom_slider:set_value(zv)
        end
    end)
end

-- ============================================================================
-- CROP OPERATIONS
-- ============================================================================

function apply_crop(x, y, w, h, zoom, method)
    cropState.crop_x = x
    cropState.crop_y = y
    cropState.crop_w = w
    cropState.crop_h = h
    cropState.zoom_level = zoom
    cropState.upscale_method = method
    cropState.enabled = true
    
    vlc.osd.message("Crop applied: (" .. x .. ", " .. y .. ") " .. w .. "x" .. h .. " @ " .. zoom .. "x zoom")
    
    -- Apply VLC's built-in crop filter
    local input = vlc.input.item()
    if input then
        apply_vlc_filters(x, y, w, h, zoom, method)
    end
end

function reset_crop()
    cropState.enabled = false
    cropState.crop_x = 0
    cropState.crop_y = 0
    cropState.crop_w = cropState.original_w
    cropState.crop_h = cropState.original_h
    cropState.zoom_level = 1.0
    
    -- Reset VLC filters
    vlc.var.set(vlc.object.vout(), "crop", "")
    vlc.var.set(vlc.object.vout(), "zoom", "1.0")
    
    vlc.osd.message("Crop reset")
end

-- ============================================================================
-- VLC FILTER INTEGRATION
-- ============================================================================

function apply_vlc_filters(x, y, w, h, zoom, method)
    local vout = vlc.object.vout()
    
    if not vout then
        vlc.osd.message("Error: No active video output")
        return
    end
    
    -- Apply crop filter (VLC format: WxH+X+Y)
    local crop_str = w .. "x" .. h .. "+" .. x .. "+" .. y
    vlc.var.set(vout, "crop", crop_str)
    
    -- Apply zoom
    local zoom_str = string.format("%.2f", zoom)
    vlc.var.set(vout, "zoom", zoom_str)
    
    -- TODO: Apply custom upscaling filter (Phase 2)
    -- This would call external upscaler or use libavfilter
    
    vlc.osd.message("Filters applied: crop=" .. crop_str .. " zoom=" .. zoom_str)
end

-- ============================================================================
-- EVENT LISTENERS
-- ============================================================================

function input_changed()
    local input = vlc.input.item()
    if input then
        -- Get video dimensions from the input
        local meta = input:metas()
        cropState.original_w = tonumber(meta.width) or 1920
        cropState.original_h = tonumber(meta.height) or 1080
        vlc.osd.message("Video detected: " .. cropState.original_w .. "x" .. cropState.original_h)
    end
end

-- ============================================================================
-- ACTIVATION
-- ============================================================================

function activate()
    show_dialog()
end

function deactivate()
    reset_crop()
    if dialog then
        dialog:delete()
        dialog = nil
    end
end

-- Register input listener
vlc.input.add_callback(input_changed)

return descriptor
