-- VLC Crop & Zoom Pro Extension
-- Opens a dialog to crop a pixel region of the video and zoom into it.
-- Uses VLC's built-in crop and zoom variables applied to the video output.
--
-- Install:
--   Linux:   ~/.local/share/vlc/lua/extensions/vlc_crop_zoom.lua
--   Windows: %APPDATA%\vlc\lua\extensions\vlc_crop_zoom.lua
--   macOS:   ~/Library/Application Support/org.videolan.vlc/lua/extensions/vlc_crop_zoom.lua
--
-- Activation (important - follow exactly):
--   1. Copy this file to the extensions folder (see paths above)
--   2. FULLY RESTART VLC (quit and reopen - not just stop/play)
--   3. Play a video
--   4. Go to Tools > Extensions  (NOT "Plugins and Extensions" - different menu)
--   5. Single-click "Crop & Zoom Pro" - the dialog opens
--      OR use the submenu: Tools > Extensions > Crop & Zoom Pro > [pick an action]
--
-- Dialog usage:
--   Enter X, Y (top-left corner of the region you want to keep)
--   Enter Width, Height (size of the region)
--   Enter Zoom (1.0 = no zoom, 2.0 = 2x, etc.)
--   Click Apply - video updates instantly inside VLC
--   Click Reset - returns to the original full view
--
-- Quick menu (Tools > Extensions > Crop & Zoom Pro submenu):
--   Open Dialog      - show the crop/zoom dialog
--   Reset View       - remove all crop and zoom instantly
--   Zoom In  +25%    - increase zoom by 0.25 each click
--   Zoom Out -25%    - decrease zoom by 0.25 each click
--   2x Zoom Center   - zoom 2x into the center of the video
--   4x Zoom Center   - zoom 4x into the center of the video

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
        -- "menu" adds a submenu under Tools > Extensions > Crop & Zoom Pro
        capabilities = {"input-listener", "menu"},
        -- These entries appear as: Tools > Extensions > Crop & Zoom Pro > [item]
        -- trigger_menu(id) below is called with the 1-based index of the clicked item
        menu = {
            "Open Dialog",
            "Reset View",
            "Zoom In  +25%",
            "Zoom Out -25%",
            "2x Zoom - Center",
            "4x Zoom - Center",
        }
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
local cur_zoom = 1.0     -- tracks current zoom so Zoom In/Out can increment it

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

-- Called when user picks an item from the Tools > Extensions > Crop & Zoom Pro submenu.
-- id is the 1-based index matching the menu table in descriptor().
function trigger_menu(id)
    if id == 1 then
        -- "Open Dialog" - create dialog if not already open
        if not dlg then
            build_dialog()
            refresh_dimensions()
        end
    elseif id == 2 then
        -- "Reset View"
        do_reset()
    elseif id == 3 then
        -- "Zoom In +25%"
        cur_zoom = math.min(16.0, cur_zoom + 0.25)
        apply_zoom_only(cur_zoom)
    elseif id == 4 then
        -- "Zoom Out -25%"
        cur_zoom = math.max(0.25, cur_zoom - 0.25)
        apply_zoom_only(cur_zoom)
    elseif id == 5 then
        -- "2x Zoom - Center"
        quick_zoom_center(2.0)
    elseif id == 6 then
        -- "4x Zoom - Center"
        quick_zoom_center(4.0)
    end
end

-- ============================================================================
-- DIALOG UI
-- ============================================================================

function build_dialog()
    dlg = vlc.dialog("Crop & Zoom Pro")

    -- Row 1: live status line showing current video resolution
    lbl_status = dlg:add_label("Play a video, then use the controls below.", 1, 1, 4, 1)

    -- Row 2: quick zoom section header
    dlg:add_label("── Quick Zoom ──────────────────────────────────", 1, 2, 4, 1)

    -- Row 3: quick zoom buttons (all four in one row)
    dlg:add_button("Zoom In  +25%",  btn_zoom_in,      1, 3, 1, 1)
    dlg:add_button("Zoom Out -25%",  btn_zoom_out,     2, 3, 1, 1)
    dlg:add_button("2×  Center",     btn_zoom2_center, 3, 3, 1, 1)
    dlg:add_button("4×  Center",     btn_zoom4_center, 4, 3, 1, 1)

    -- Row 4: crop section header
    dlg:add_label("── Crop Region (pixels) ────────────────────────", 1, 4, 4, 1)

    -- Row 5: X and Y
    dlg:add_label("X (left edge):", 1, 5, 1, 1)
    txt_x = dlg:add_text_input("0", 2, 5, 1, 1)
    dlg:add_label("Y (top edge):", 3, 5, 1, 1)
    txt_y = dlg:add_text_input("0", 4, 5, 1, 1)

    -- Row 6: Width and Height
    dlg:add_label("Width:", 1, 6, 1, 1)
    txt_w = dlg:add_text_input("1920", 2, 6, 1, 1)
    dlg:add_label("Height:", 3, 6, 1, 1)
    txt_h = dlg:add_text_input("1080", 4, 6, 1, 1)

    -- Row 7: zoom level section header
    dlg:add_label("── Manual Zoom ─────────────────────────────────", 1, 7, 4, 1)

    -- Row 8: zoom input
    dlg:add_label("Zoom level (e.g. 1.5, 2.0):", 1, 8, 2, 1)
    txt_zoom = dlg:add_text_input("1.0", 3, 8, 2, 1)

    -- Row 9: Apply / Reset buttons
    dlg:add_button("Apply", do_apply, 1, 9, 2, 1)
    dlg:add_button("Reset", do_reset, 3, 9, 2, 1)

    -- Row 10: quick-reference tip
    dlg:add_label("Tip: X=0 Y=0 starts at top-left.  Zoom 1.0 = no zoom.", 1, 10, 4, 1)

    dlg:show()
end

-- Button callbacks for the quick-zoom row in the dialog
function btn_zoom_in()
    cur_zoom = math.min(16.0, cur_zoom + 0.25)
    apply_zoom_only(cur_zoom)
end

function btn_zoom_out()
    cur_zoom = math.max(0.25, cur_zoom - 0.25)
    apply_zoom_only(cur_zoom)
end

function btn_zoom2_center()
    quick_zoom_center(2.0)
end

function btn_zoom4_center()
    quick_zoom_center(4.0)
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
    cur_zoom = zoom  -- keep state in sync for Zoom In/Out menu items

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

    cur_zoom = 1.0
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

-- Apply a zoom level without touching the crop region
function apply_zoom_only(zoom)
    local vout = vlc.object.vout()
    if not vout then
        vlc.osd.message("Crop & Zoom: No video playing")
        return
    end
    vlc.var.set(vout, "zoom", zoom)
    cur_zoom = zoom
    -- Update the dialog field if it's open
    if txt_zoom then txt_zoom:set_text(string.format("%.2f", zoom)) end
    local msg = "Zoom: " .. string.format("%.2f", zoom) .. "x"
    set_status(msg)
    vlc.osd.message(msg)
end

-- Crop to the center of the video and apply the given zoom level.
-- The crop region is sized so that zooming fills the original frame.
-- e.g. 2x zoom on 1920x1080 crops a 960x540 region from the center.
function quick_zoom_center(zoom)
    local vout = vlc.object.vout()
    if not vout then
        vlc.osd.message("Crop & Zoom: No video playing")
        return
    end
    refresh_dimensions()  -- make sure vid_w/vid_h are current

    -- Crop a region 1/zoom the size of the frame, centered
    local crop_w = math.floor(vid_w / zoom)
    local crop_h = math.floor(vid_h / zoom)
    local crop_x = math.floor((vid_w - crop_w) / 2)
    local crop_y = math.floor((vid_h - crop_h) / 2)

    local crop_str = crop_w .. "x" .. crop_h .. "+" .. crop_x .. "+" .. crop_y
    vlc.var.set(vout, "crop", crop_str)
    vlc.var.set(vout, "zoom", zoom)
    cur_zoom = zoom

    -- Update dialog fields if open
    if txt_x    then txt_x:set_text(tostring(crop_x)) end
    if txt_y    then txt_y:set_text(tostring(crop_y)) end
    if txt_w    then txt_w:set_text(tostring(crop_w)) end
    if txt_h    then txt_h:set_text(tostring(crop_h)) end
    if txt_zoom then txt_zoom:set_text(string.format("%.2f", zoom)) end

    local msg = zoom .. "x center zoom (" .. crop_w .. "x" .. crop_h .. ")"
    set_status(msg)
    vlc.osd.message(msg)
end

-- Update the status label safely (it may not exist yet on first load)
function set_status(msg)
    if lbl_status then
        lbl_status:set_text(msg)
    end
end
