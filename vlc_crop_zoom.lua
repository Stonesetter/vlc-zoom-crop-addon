-- VLC Crop & Zoom Pro Extension  (v2.0)
-- Crop any pixel region and zoom into it — all inside VLC, no external tools.
--
-- How it works:
--   VLC's "crop" variable selects a rectangular region of the video.
--   VLC's "zoom" variable is a pixel-scale factor (2.0 = each pixel drawn 2x).
--   To "zoom into" the video you must set BOTH together:
--     crop a smaller centre region  +  zoom up so it fills the window.
--   e.g. 2x zoom on 1920x1080 → crop centre 960x540, zoom=2.0 → fills window.
--
-- Install:
--   Linux:   ~/.local/share/vlc/lua/extensions/vlc_crop_zoom.lua
--   Windows: %APPDATA%\vlc\lua\extensions\vlc_crop_zoom.lua
--   macOS:   ~/Library/Application Support/org.videolan.vlc/lua/extensions/vlc_crop_zoom.lua
--
-- Activate:
--   1. Copy this file to the extensions folder above
--   2. FULLY RESTART VLC (quit and reopen)
--   3. Play a video
--   4. Tools > Extensions > "Crop & Zoom Pro" (single-click to open dialog)

-- ============================================================================
-- DESCRIPTOR
-- ============================================================================

function descriptor()
    return {
        title       = "Crop & Zoom Pro",
        version     = "2.0",
        author      = "Stonesetter",
        shortdesc   = "Crop and zoom video regions",
        description = "Crop any pixel region of the video and zoom into it. "
                   .. "Includes quick-zoom buttons and manual crop entry.",
        capabilities = {"input-listener", "menu"},
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

local dlg        = nil   -- dialog window handle
local lbl_status = nil   -- status label widget
local txt_x      = nil   -- crop X input widget
local txt_y      = nil   -- crop Y input widget
local txt_w      = nil   -- crop width input widget
local txt_h      = nil   -- crop height input widget
local lbl_zoom   = nil   -- zoom display label (read-only, not a text input)

local vid_w    = 0       -- detected video width  (0 until a video plays)
local vid_h    = 0       -- detected video height
local cur_zoom = 1.0     -- current zoom level (1.0 = full frame, no zoom)

-- ============================================================================
-- VLC LIFECYCLE
-- ============================================================================

function activate()
    build_dialog()
    refresh_dimensions()
    update_dialog_fields(0, 0, vid_w, vid_h)
end

function deactivate()
    -- Reset crop/zoom, but guard against errors during VLC shutdown
    pcall(do_reset)
    if dlg then
        dlg:delete()
        dlg = nil
    end
end

function close()
    vlc.deactivate()
end

function input_changed()
    refresh_dimensions()
end

function trigger_menu(id)
    if id == 1 then
        if not dlg then
            build_dialog()
            refresh_dimensions()
            update_dialog_fields(0, 0, vid_w, vid_h)
        end
    elseif id == 2 then
        do_reset()
    elseif id == 3 then
        btn_zoom_in()
    elseif id == 4 then
        btn_zoom_out()
    elseif id == 5 then
        set_center_zoom(2.0)
    elseif id == 6 then
        set_center_zoom(4.0)
    end
end

-- ============================================================================
-- DIALOG
-- ============================================================================

function build_dialog()
    dlg = vlc.dialog("Crop & Zoom Pro")

    -- Row 1: status
    lbl_status = dlg:add_label(
        "Play a video, then use the controls below.", 1, 1, 4, 1)

    -- Row 2: quick zoom header
    dlg:add_label("── Quick Zoom ─────────────────────────", 1, 2, 4, 1)

    -- Row 3: quick zoom buttons
    dlg:add_button("  +  Zoom In  ",  btn_zoom_in,  1, 3, 1, 1)
    dlg:add_button("  -  Zoom Out ",  btn_zoom_out, 2, 3, 1, 1)
    dlg:add_button("  2x Center  ",   btn_zoom2,    3, 3, 1, 1)
    dlg:add_button("  4x Center  ",   btn_zoom4,    4, 3, 1, 1)

    -- Row 4: current zoom display
    lbl_zoom = dlg:add_label("Current zoom: 1.0x  (full frame)", 1, 4, 4, 1)

    -- Row 5: manual crop header
    dlg:add_label("── Manual Crop (pixels) ───────────────", 1, 5, 4, 1)

    -- Row 6: X and Y
    dlg:add_label("X:", 1, 6, 1, 1)
    txt_x = dlg:add_text_input("0", 2, 6, 1, 1)
    dlg:add_label("Y:", 3, 6, 1, 1)
    txt_y = dlg:add_text_input("0", 4, 6, 1, 1)

    -- Row 7: Width and Height
    dlg:add_label("Width:", 1, 7, 1, 1)
    txt_w = dlg:add_text_input("0", 2, 7, 1, 1)
    dlg:add_label("Height:", 3, 7, 1, 1)
    txt_h = dlg:add_text_input("0", 4, 7, 1, 1)

    -- Row 8: Apply Crop / Reset buttons
    dlg:add_button("  Apply Crop  ", do_apply_crop, 1, 8, 2, 1)
    dlg:add_button("  Reset All  ",  do_reset,      3, 8, 2, 1)

    -- Row 9: help text
    dlg:add_label(
        "Crop: enter the top-left X,Y and size W,H of the region to keep. "
     .. "Quick Zoom buttons zoom into the centre of the video.",
        1, 9, 4, 1)

    dlg:show()
end

-- ============================================================================
-- QUICK ZOOM  (centre-crop + proportional zoom — confirmed working pattern)
-- ============================================================================

--- Set zoom to an exact level by centre-cropping and scaling proportionally.
--- This is the pattern confirmed working for 2x and 4x:
---   crop = (vid_w/zoom) x (vid_h/zoom) centred  +  zoom = zoom
---   e.g. 2x on 1920x1080 → crop 960x540+480+270, zoom=2.0 → fills window.
function set_center_zoom(zoom)
    local vout = vlc.object.vout()
    if not vout then
        set_status("No video playing — start a video first.")
        return
    end
    refresh_dimensions()
    if vid_w == 0 or vid_h == 0 then
        set_status("Cannot detect video size — try again after video loads.")
        return
    end

    zoom = math.max(1.0, math.min(8.0, zoom))
    cur_zoom = zoom

    if zoom <= 1.0 then
        -- Full frame: remove crop, auto-fit
        vlc.var.set(vout, "crop", "")
        vlc.var.set(vout, "zoom", 0)
        update_dialog_fields(0, 0, vid_w, vid_h)
        set_status("Full view.  Video: " .. vid_w .. "x" .. vid_h)
        vlc.osd.message("Full view")
        return
    end

    -- Crop a proportional centre region
    local cw = math.floor(vid_w / zoom)
    local ch = math.floor(vid_h / zoom)
    -- Ensure even dimensions (some codecs need it)
    cw = cw - (cw % 2)
    ch = ch - (ch % 2)
    if cw < 2 then cw = 2 end
    if ch < 2 then ch = 2 end
    local cx = math.floor((vid_w - cw) / 2)
    local cy = math.floor((vid_h - ch) / 2)

    local crop_str = cw .. "x" .. ch .. "+" .. cx .. "+" .. cy
    vlc.var.set(vout, "crop", crop_str)
    vlc.var.set(vout, "zoom", zoom)

    update_dialog_fields(cx, cy, cw, ch)

    local msg = string.format("%.2fx zoom  (centre %dx%d)", zoom, cw, ch)
    set_status(msg)
    vlc.osd.message(msg)
end

-- Button callbacks (called from dialog buttons and trigger_menu)
function btn_zoom_in()
    set_center_zoom(cur_zoom + 0.25)
end

function btn_zoom_out()
    set_center_zoom(cur_zoom - 0.25)
end

function btn_zoom2()
    set_center_zoom(2.0)
end

function btn_zoom4()
    set_center_zoom(4.0)
end

-- ============================================================================
-- MANUAL CROP  (user-specified region, auto-compute zoom to fill window)
-- ============================================================================

function do_apply_crop()
    local vout = vlc.object.vout()
    if not vout then
        set_status("No video playing — start a video first.")
        return
    end
    refresh_dimensions()
    if vid_w == 0 or vid_h == 0 then
        set_status("Cannot detect video size — try again after video loads.")
        return
    end

    -- Read crop values from dialog fields
    local x = math.max(0, math.floor(tonumber(txt_x:get_text()) or 0))
    local y = math.max(0, math.floor(tonumber(txt_y:get_text()) or 0))
    local w = math.floor(tonumber(txt_w:get_text()) or vid_w)
    local h = math.floor(tonumber(txt_h:get_text()) or vid_h)

    -- Clamp to video bounds
    if x >= vid_w then x = 0 end
    if y >= vid_h then y = 0 end
    if w < 1 then w = vid_w end
    if h < 1 then h = vid_h end
    if x + w > vid_w then w = vid_w - x end
    if y + h > vid_h then h = vid_h - y end

    -- Ensure even dimensions (some codecs require it)
    w = w - (w % 2)
    h = h - (h % 2)
    if w < 2 then w = 2 end
    if h < 2 then h = 2 end

    -- Full frame? Just reset
    if x == 0 and y == 0 and w == vid_w and h == vid_h then
        do_reset()
        return
    end

    -- Apply the crop
    local crop_str = w .. "x" .. h .. "+" .. x .. "+" .. y
    vlc.var.set(vout, "crop", crop_str)

    -- Compute the zoom factor that fills the window with this crop.
    -- Use the smaller ratio so the entire crop region is visible (fit, no clip).
    -- This matches the pattern that works for 2x/4x centre zoom.
    local zoom_w = vid_w / w
    local zoom_h = vid_h / h
    local zoom   = math.min(zoom_w, zoom_h)
    zoom = math.max(1.0, zoom)

    vlc.var.set(vout, "zoom", zoom)
    cur_zoom = zoom

    -- Write computed values back to fields
    update_dialog_fields(x, y, w, h)

    local msg = string.format("Crop: %dx%d+%d+%d  (%.1fx)", w, h, x, y, zoom)
    set_status(msg)
    vlc.osd.message(msg)
end

-- ============================================================================
-- RESET
-- ============================================================================

function do_reset()
    local vout = vlc.object.vout()
    if vout then
        vlc.var.set(vout, "crop", "")
        vlc.var.set(vout, "zoom", 0)   -- 0 = auto-fit (VLC default)
    end

    cur_zoom = 1.0
    refresh_dimensions()
    update_dialog_fields(0, 0, vid_w, vid_h)

    local res = ""
    if vid_w > 0 and vid_h > 0 then
        res = "  Video: " .. vid_w .. "x" .. vid_h
    end
    set_status("Reset." .. res)
    vlc.osd.message("Crop & Zoom reset")
end

-- ============================================================================
-- HELPERS
-- ============================================================================

--- Detect video dimensions from the vout and store in vid_w / vid_h.
function refresh_dimensions()
    local vout = vlc.object.vout()
    if not vout then return end

    local w = vlc.var.get(vout, "video-width")
    local h = vlc.var.get(vout, "video-height")
    if w and h and w > 0 and h > 0 then
        vid_w = w
        vid_h = h
    end
end

--- Update all dialog fields to reflect the current state.
function update_dialog_fields(x, y, w, h)
    if txt_x then txt_x:set_text(tostring(x or 0)) end
    if txt_y then txt_y:set_text(tostring(y or 0)) end
    if txt_w then txt_w:set_text(tostring(w or vid_w)) end
    if txt_h then txt_h:set_text(tostring(h or vid_h)) end

    if lbl_zoom then
        if cur_zoom <= 1.0 then
            lbl_zoom:set_text("Current zoom: 1.0x  (full frame)")
        else
            lbl_zoom:set_text(
                "Current zoom: " .. string.format("%.2f", cur_zoom) .. "x")
        end
    end
end

--- Update the status label (safe to call even if dialog isn't open).
function set_status(msg)
    if lbl_status then
        lbl_status:set_text(msg)
    end
end
