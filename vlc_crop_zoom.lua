-- VLC Crop & Zoom Pro Extension
-- Opens a dialog to crop a pixel region of the video and zoom into it.
-- Uses VLC's built-in crop and zoom variables applied to the video output.
--
-- Install:
--   Linux:   ~/.local/share/vlc/lua/extensions/vlc_crop_zoom.lua
--   Windows: %APPDATA%\vlc\lua\extensions\vlc_crop_zoom.lua
--   macOS:   ~/Library/Application Support/org.videolan.vlc/lua/extensions/vlc_crop_zoom.lua
--
-- Usage:
--   1. Open VLC and play a video
--   2. Tools > Extensions > Crop & Zoom Pro > click "Activate"  (or double-click)
--   3. The dialog will appear showing your video resolution
--   4. Enter crop coordinates (X, Y = top-left corner; W, H = region size)
--   5. Set zoom level (1.0 = no zoom, 2.0 = 2x zoom, etc.)
--   6. Click "Apply" - the video updates instantly in VLC
--   7. Click "Reset" to return to the original view

-- ============================================================================
-- DESCRIPTOR  (VLC calls descriptor() to get plugin metadata)
-- ============================================================================

function descriptor()
    return {
        title       = "Crop & Zoom Pro",
        version     = "1.1",
        author      = "Stonesetter",
        shortdesc   = "Crop and zoom video regions",
        description = "Crop any pixel region of the video and zoom into it using VLC's built-in filters. Play a video, open this extension, enter coordinates, and click Apply.",
        -- "input-listener" makes VLC automatically call input_changed() when media changes
        capabilities = {"input-listener"}
    }
end

-- ============================================================================
-- STATE
-- ============================================================================

local dlg        = nil   -- the dialog window
local lbl_status = nil   -- status label widget (updated live)
local txt_x      = nil   -- crop X input
local txt_y      = nil   -- crop Y input
local txt_w      = nil   -- crop width input
local txt_h      = nil   -- crop height input
local txt_zoom   = nil   -- zoom input

local vid_w = 1920       -- detected video width  (default 1920 until a video loads)
local vid_h = 1080       -- detected video height (default 1080 until a video loads)

-- ============================================================================
-- VLC LIFECYCLE CALLBACKS
-- ============================================================================

-- Called when user activates the extension from the menu
function activate()
    build_dialog()
    -- Immediately try to read the video dimensions if something is already playing
    refresh_dimensions()
end

-- Called when user deactivates the extension or VLC closes
function deactivate()
    do_reset()
    if dlg then
        dlg:delete()
        dlg = nil
    end
end

-- Called when the user clicks the X button on the dialog window
function close()
    vlc.deactivate()
end

-- Called automatically by VLC whenever the current media item changes
-- (requires "input-listener" in capabilities above)
function input_changed()
    refresh_dimensions()
end

-- ============================================================================
-- DIALOG UI
-- ============================================================================

function build_dialog()
    dlg = vlc.dialog("Crop & Zoom Pro")

    -- Row 1: live status line showing current video resolution
    lbl_status = dlg:add_label("Play a video, then use the controls below.", 1, 1, 4, 1)

    -- Row 2: section header
    dlg:add_label("__________ Crop Region (pixels) __________", 1, 2, 4, 1)

    -- Row 3: X and Y
    dlg:add_label("X (left edge):", 1, 3, 1, 1)
    txt_x = dlg:add_text_input("0", 2, 3, 1, 1)
    dlg:add_label("Y (top edge):", 3, 3, 1, 1)
    txt_y = dlg:add_text_input("0", 4, 3, 1, 1)

    -- Row 4: Width and Height
    dlg:add_label("Width:", 1, 4, 1, 1)
    txt_w = dlg:add_text_input("1920", 2, 4, 1, 1)
    dlg:add_label("Height:", 3, 4, 1, 1)
    txt_h = dlg:add_text_input("1080", 4, 4, 1, 1)

    -- Row 5: zoom header
    dlg:add_label("__________ Zoom __________", 1, 5, 4, 1)

    -- Row 6: zoom input
    dlg:add_label("Zoom level (e.g. 1.5, 2.0):", 1, 6, 2, 1)
    txt_zoom = dlg:add_text_input("1.0", 3, 6, 2, 1)

    -- Row 7: Apply / Reset buttons
    dlg:add_button("Apply", do_apply, 1, 7, 2, 1)
    dlg:add_button("Reset", do_reset, 3, 7, 2, 1)

    -- Row 8: quick-reference tip
    dlg:add_label("Tip: X=0 Y=0 crops from top-left. Zoom 1.0 = no zoom.", 1, 8, 4, 1)

    dlg:show()
end

-- ============================================================================
-- ACTIONS
-- ============================================================================

-- Apply the crop and zoom values to the currently playing video
function do_apply()
    local vout = vlc.object.vout()
    if not vout then
        set_status("ERROR: No video playing. Start a video first.")
        vlc.osd.message("Crop & Zoom: No video output found")
        return
    end

    -- Read and validate inputs
    local x    = math.max(0, tonumber(txt_x:get_text())    or 0)
    local y    = math.max(0, tonumber(txt_y:get_text())    or 0)
    local w    = math.max(1, tonumber(txt_w:get_text())    or vid_w)
    local h    = math.max(1, tonumber(txt_h:get_text())    or vid_h)
    local zoom = tonumber(txt_zoom:get_text()) or 1.0
    zoom = math.max(0.1, math.min(16.0, zoom))   -- clamp to sane range

    -- VLC crop geometry string format:  WxH+X+Y
    --   W, H = size of the region to keep
    --   X, Y = offset from top-left corner
    local crop_str = w .. "x" .. h .. "+" .. x .. "+" .. y

    -- Apply to vout (zoom must be a number, not a string)
    vlc.var.set(vout, "crop", crop_str)
    vlc.var.set(vout, "zoom", zoom)

    local msg = "Crop: " .. crop_str .. "  Zoom: " .. string.format("%.2f", zoom) .. "x"
    set_status(msg)
    vlc.osd.message(msg)
end

-- Remove crop and zoom, restore original view
function do_reset()
    local vout = vlc.object.vout()
    if vout then
        vlc.var.set(vout, "crop", "")   -- empty string removes the crop
        vlc.var.set(vout, "zoom", 1.0)
    end

    -- Reset input fields to full-frame defaults
    if txt_x    then txt_x:set_text("0") end
    if txt_y    then txt_y:set_text("0") end
    if txt_w    then txt_w:set_text(tostring(vid_w)) end
    if txt_h    then txt_h:set_text(tostring(vid_h)) end
    if txt_zoom then txt_zoom:set_text("1.0") end

    set_status("Reset. Video: " .. vid_w .. "x" .. vid_h)
    vlc.osd.message("Crop & Zoom reset")
end

-- ============================================================================
-- HELPERS
-- ============================================================================

-- Read the actual video resolution from the vout and update the UI
function refresh_dimensions()
    local vout = vlc.object.vout()
    if vout then
        local w = vlc.var.get(vout, "video-width")
        local h = vlc.var.get(vout, "video-height")
        if w and h and w > 0 and h > 0 then
            vid_w = w
            vid_h = h
            -- Pre-fill width/height fields with actual video size
            if txt_w then txt_w:set_text(tostring(vid_w)) end
            if txt_h then txt_h:set_text(tostring(vid_h)) end
            set_status("Video: " .. vid_w .. "x" .. vid_h .. "  —  Set crop region below, then click Apply.")
        end
    end
end

-- Update the status label safely (it may not exist yet on first load)
function set_status(msg)
    if lbl_status then
        lbl_status:set_text(msg)
    end
end
