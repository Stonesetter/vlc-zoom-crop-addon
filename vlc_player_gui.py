#!/usr/bin/env python3
"""
vlc_player_gui.py — Interactive VLC player with drag-to-crop and Shift+scroll zoom

Controls:
  Shift + scroll wheel    Zoom in / out (0.25x steps, centres on video)
  Zoom slider (toolbar)   Same as Shift+scroll but always reachable
  Click "Draw Crop Box"   Pauses video, shows a snapshot of the current frame.
                          Drag to draw the crop rectangle on the snapshot.
                          Press Enter or click Apply Crop to lock it in.
                          Press Esc to cancel without changing anything.
  Apply Crop button       Applies the drawn crop region to the live video.
  Reset All button        Removes crop and zoom, restores the original view.

Requirements:
  pip install python-vlc PyQt5
  VLC media player must also be installed on the system (provides libvlc).

  Ubuntu/Debian: sudo apt install vlc python3-pyqt5 && pip install python-vlc
  Windows:       Install VLC from videolan.org, then pip install python-vlc PyQt5
  macOS:         brew install --cask vlc && pip install python-vlc PyQt5

Run:
  python3 vlc_player_gui.py
  python3 vlc_player_gui.py /path/to/video.mp4
"""

import os
import sys
import time
import tempfile

import vlc
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QFileDialog, QFrame, QSizePolicy,
    QRubberBand,
)
from PyQt5.QtCore import Qt, QRect, QSize, QTimer, QEvent
from PyQt5.QtGui import QPixmap, QPainter


# =============================================================================
# EVENT CAPTURE OVERLAY
# A transparent widget placed on top of the video frame.
# On Linux/X11, VLC's embedded window sits below Qt's widget stack, so
# raising this overlay above it lets us intercept scroll (and other) events
# that VLC would otherwise swallow before Qt sees them.
# =============================================================================

class EventOverlay(QWidget):
    """
    Transparent overlay over the video frame used solely to capture mouse
    events (specifically Shift+scroll for zoom) before they reach VLC's
    embedded X11 sub-window.

    Raised above VLC's surface after VLC initialises (~1 s into playback).
    Fully transparent: passes click events through to VLC by calling
    ignore() so the user can interact with VLC normally.
    """

    def __init__(self, parent: QWidget, on_shift_scroll):
        super().__init__(parent)
        self._on_shift_scroll = on_shift_scroll
        # Transparent visually but NOT for mouse events
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

    def paintEvent(self, _event):
        pass  # completely invisible

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ShiftModifier:
            delta = event.angleDelta().y()
            step  = 0.25 if delta > 0 else -0.25
            self._on_shift_scroll(step)
            event.accept()
        else:
            event.ignore()   # let non-shift scrolls pass to VLC (volume etc.)

    def mousePressEvent(self, event):
        event.ignore()   # pass clicks through to VLC / parent

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()


# =============================================================================
# SNAPSHOT CROP PICKER
# Shown as a full overlay when user clicks "Draw Crop Box".
# Displays the frozen frame; user drags to choose the crop region.
# =============================================================================

class SnapshotCropPicker(QWidget):
    """
    Full-area overlay showing a snapshot of the current video frame.
    The user drags a rubber-band rectangle to choose the crop region.
    Enter confirms; Esc cancels.
    """

    def __init__(self, pixmap: QPixmap, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: black;")

        self._pixmap     = pixmap
        self._drag_start = None
        self._drag_end   = None
        self._dragging   = False
        self._final_rect = None   # QRect in widget coords after mouse release

        self._rubber = QRubberBand(QRubberBand.Rectangle, self)

        # Instruction banner
        self._hint = QLabel(
            "  Drag to draw crop box   |   Enter = Apply   |   Esc = Cancel  ",
            self
        )
        self._hint.setStyleSheet(
            "background: rgba(0,0,0,180); color: #FFE000; "
            "font-size: 13px; padding: 5px 10px; border-radius: 4px;"
        )
        self._hint.adjustSize()
        self._hint.move(12, 12)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ---- paint ---------------------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            x = (self.width()  - scaled.width())  // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

    # ---- mouse ---------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self._drag_end   = event.pos()
            self._dragging   = True
            self._final_rect = None
            self._rubber.setGeometry(QRect(self._drag_start, QSize()))
            self._rubber.show()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._drag_end = event.pos()
            self._rubber.setGeometry(
                QRect(self._drag_start, self._drag_end).normalized()
            )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._drag_end   = event.pos()
            self._dragging   = False
            self._final_rect = QRect(self._drag_start, self._drag_end).normalized()
            self._rubber.setGeometry(self._final_rect)

    # ---- keyboard ------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._confirm()
        elif event.key() == Qt.Key_Escape:
            self._cancel()

    # ---- coord conversion ----------------------------------------------------

    def get_video_crop(self):
        """
        Convert the rubber-band selection from widget-pixel coords to actual
        video-pixel coords, accounting for letterbox/pillarbox scaling.
        Returns (x, y, w, h) in video pixels, or None if the selection is too small.
        """
        if (not self._final_rect
                or self._final_rect.width()  < 5
                or self._final_rect.height() < 5):
            return None

        r  = self._final_rect
        iw = self._pixmap.width()
        ih = self._pixmap.height()
        ww = self.width()
        wh = self.height()

        # Scale used by paintEvent (KeepAspectRatio)
        scale = min(ww / iw, wh / ih)
        off_x = (ww - iw * scale) / 2
        off_y = (wh - ih * scale) / 2

        vx = max(0, int((r.x()     - off_x) / scale))
        vy = max(0, int((r.y()     - off_y) / scale))
        vw = max(1, int(r.width()            / scale))
        vh = max(1, int(r.height()           / scale))

        # Clamp to image bounds
        vw = min(vw, iw - vx)
        vh = min(vh, ih - vy)

        return (vx, vy, vw, vh)

    def _confirm(self):
        # window() walks up to the top-level QMainWindow (PlayerWindow).
        # parent() would only return video_frame (QFrame), which has no method.
        self.window()._on_crop_picker_confirm()

    def _cancel(self):
        self.window()._on_crop_picker_cancel()


# =============================================================================
# MAIN PLAYER WINDOW
# =============================================================================

class PlayerWindow(QMainWindow):

    # ---- Zoom is stored as an integer multiple of 0.25 to avoid float drift --
    # _zoom_steps = 4  →  1.00×
    # _zoom_steps = 8  →  2.00×  etc.
    _ZOOM_STEP   = 0.25
    _ZOOM_MIN    = 1.0     # 1.0 = no zoom (full frame)
    _ZOOM_MAX    = 8.0

    def __init__(self, initial_file: str = None):
        super().__init__()
        self.setWindowTitle("VLC Crop & Zoom")
        self.resize(1280, 780)

        # VLC setup
        args = ["--no-xlib"] if sys.platform.startswith("linux") else []
        self._vlc_instance = vlc.Instance(*args)
        self._player       = self._vlc_instance.media_player_new()

        # State
        self._vid_w           = 0      # detected after first tick
        self._vid_h           = 0
        self._zoom            = 1.0    # current zoom level
        self._pending_crop    = None   # (vx, vy, vw, vh) drawn but not applied
        self._snap_widget     = None   # SnapshotCropPicker when active
        self._overlay_raised  = False  # True once overlay has been raised over VLC

        self._build_ui()

        # Also keep the app-level event filter as a fallback (works on Windows/macOS)
        QApplication.instance().installEventFilter(self)

        # Poll timer: seek bar sync + dimension detection + overlay raising
        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        if initial_file and os.path.exists(initial_file):
            self._load_file(initial_file)

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        # ---- Video frame ----
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background: black;")
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_frame.setMinimumSize(640, 360)
        vbox.addWidget(self.video_frame, stretch=1)

        # Transparent event-capture overlay (child of video_frame, raised later)
        self._overlay = EventOverlay(self.video_frame, self._on_zoom_step)
        self._overlay.setGeometry(self.video_frame.rect())
        self._overlay.show()

        # Attach VLC renderer to the video frame's native window handle
        win_id = int(self.video_frame.winId())
        if sys.platform.startswith("linux"):
            self._player.set_xwindow(win_id)
        elif sys.platform == "win32":
            self._player.set_hwnd(win_id)
        elif sys.platform == "darwin":
            self._player.set_nsobject(win_id)

        # ---- Seek bar ----
        self.seek_bar = QSlider(Qt.Horizontal)
        self.seek_bar.setRange(0, 1000)
        self.seek_bar.sliderMoved.connect(
            lambda v: self._player.set_position(v / 1000.0)
        )
        vbox.addWidget(self.seek_bar)

        # ---- Status label ----
        self.lbl_status = QLabel(
            "Open a video to begin.  "
            "Shift+scroll = zoom  |  Draw Crop Box to select a region."
        )
        self.lbl_status.setStyleSheet("color: #bbb; font-size: 11px;")
        vbox.addWidget(self.lbl_status)

        # ---- Toolbar ----
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.btn_open  = QPushButton("Open File")
        self.btn_play  = QPushButton("Play / Pause")
        self.btn_crop  = QPushButton("Draw Crop Box")
        self.btn_apply = QPushButton("Apply Crop")
        self.btn_reset = QPushButton("Reset All")
        self.lbl_zoom  = QLabel("Zoom: 1.00×")
        self.lbl_zoom.setStyleSheet("min-width: 90px;")

        # Zoom slider (1.0× – 8.0× in 0.25× steps → 4 … 32 integer range)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(4, 32)
        self.zoom_slider.setValue(4)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.setToolTip("Zoom (1× – 8×)  |  also: Shift+scroll over video")
        self.zoom_slider.valueChanged.connect(self._on_zoom_slider)

        self.btn_open.clicked.connect(self._open_file_dialog)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_crop.clicked.connect(self._start_crop_picker)
        self.btn_apply.clicked.connect(self._apply_pending_crop)
        self.btn_reset.clicked.connect(self._reset_all)

        self.btn_apply.setEnabled(False)

        for w in (self.btn_open, self.btn_play, self.btn_crop,
                  self.btn_apply, self.btn_reset,
                  QLabel("Zoom:"), self.zoom_slider, self.lbl_zoom):
            bar.addWidget(w)
        bar.addStretch()

        vbox.addLayout(bar)

    # =========================================================================
    # RESIZE — keep overlay and crop picker in sync with video_frame
    # =========================================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self.video_frame.rect())
        if self._snap_widget:
            self._snap_widget.setGeometry(self.video_frame.rect())

    # =========================================================================
    # EVENT FILTER (fallback for Windows / macOS where app-level works)
    # =========================================================================

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ShiftModifier:
                delta = event.angleDelta().y()
                step  = self._ZOOM_STEP if delta > 0 else -self._ZOOM_STEP
                self._on_zoom_step(step)
                return True
        return False

    # =========================================================================
    # PLAYBACK
    # =========================================================================

    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "",
            "Video (*.mp4 *.mkv *.avi *.mov *.flv *.webm *.ts *.m4v);;All Files (*)"
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        media = self._vlc_instance.media_new(path)
        self._player.set_media(media)
        self._player.play()
        self.setWindowTitle(f"VLC Crop & Zoom — {os.path.basename(path)}")
        self._vid_w = self._vid_h = 0   # reset so _on_tick detects new dimensions
        self._overlay_raised = False
        self._reset_all(quiet=True)
        self._set_status(
            f"Playing: {os.path.basename(path)}   |   "
            "Shift+scroll = zoom   |   Draw Crop Box to select region"
        )

    def _toggle_play(self):
        if self._player.is_playing():
            self._player.pause()
        else:
            self._player.play()

    def _on_tick(self):
        """Called every 250 ms: seek-bar sync, dimension detection, overlay raise."""
        state = self._player.get_state()
        if state in (vlc.State.Playing, vlc.State.Paused):
            pos = self._player.get_position()
            if not self.seek_bar.isSliderDown():
                self.seek_bar.setValue(int(pos * 1000))

        # Detect video dimensions once after playback starts
        if self._vid_w == 0:
            w, h = self._player.video_get_size(0)
            if w and h:
                self._vid_w, self._vid_h = w, h
                self._set_status(
                    f"Video: {w}×{h}   |   "
                    "Shift+scroll = zoom   |   Draw Crop Box to select region"
                )

        # Raise the event-capture overlay above VLC's X11 sub-window.
        # VLC creates its sub-window shortly after playback starts, so we
        # wait until we have confirmed dimensions, then raise once.
        if self._vid_w > 0 and not self._overlay_raised:
            self._overlay.raise_()
            self._overlay_raised = True

    # =========================================================================
    # ZOOM  (crop-based: shrink the viewed region to simulate zoom)
    # =========================================================================

    def _on_zoom_step(self, step: float):
        """Called by Shift+scroll (via overlay or app-level filter)."""
        new_zoom = round(
            max(self._ZOOM_MIN, min(self._ZOOM_MAX, self._zoom + step)), 2
        )
        if new_zoom != self._zoom:
            self._zoom = new_zoom
            self._apply_zoom()

    def _on_zoom_slider(self, value: int):
        """Called when the toolbar zoom slider moves."""
        new_zoom = value / 4.0   # slider 4..32  →  zoom 1.0..8.0
        if abs(new_zoom - self._zoom) > 0.001:
            self._zoom = new_zoom
            self._apply_zoom(update_slider=False)  # don't recurse back into slider

    def _apply_zoom(self, update_slider: bool = True):
        """
        Zoom by center-cropping a 1/zoom portion of the video and letting
        VLC auto-fit that region to the window (scale=0).

        This is the correct approach for 'zoom into the video':
          - 1.0× → no crop, full frame displayed
          - 2.0× → crop centre 960×540 of a 1920×1080 video, fill window
          - 4.0× → crop centre 480×270, fill window
        Using video_set_scale() instead would just scale the decoded pixels,
        which clips at the window edge and doesn't 'zoom in'.
        """
        self.lbl_zoom.setText(f"Zoom: {self._zoom:.2f}×")
        if update_slider:
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(round(self._zoom / self._ZOOM_STEP))
            self.zoom_slider.blockSignals(False)

        if self._zoom <= 1.0 or self._vid_w == 0:
            # No zoom: remove crop, let VLC auto-fit
            self._player.video_set_crop_geometry(None)
            self._player.video_set_scale(0)
            self._set_status("Zoom: 1.00×  (no zoom)")
            return

        # Crop a centred region of size (vid_w/zoom) × (vid_h/zoom)
        cw = max(1, int(self._vid_w / self._zoom))
        ch = max(1, int(self._vid_h / self._zoom))
        cx = (self._vid_w - cw) // 2
        cy = (self._vid_h - ch) // 2

        crop_str = f"{cw}x{ch}+{cx}+{cy}"
        self._player.video_set_crop_geometry(crop_str)
        self._player.video_set_scale(0)   # auto-fit cropped region to window

        self._set_status(
            f"Zoom: {self._zoom:.2f}×   "
            f"(centre crop {cw}×{ch} of {self._vid_w}×{self._vid_h})"
        )

    # =========================================================================
    # CROP PICKER (snapshot overlay)
    # =========================================================================

    def _start_crop_picker(self):
        """
        Pause video, take a VLC snapshot, display it as an overlay so
        the user can drag a crop rectangle on the frozen frame.
        """
        if self._player.get_state() not in (vlc.State.Playing, vlc.State.Paused):
            self._set_status("Play a video first, then click Draw Crop Box.")
            return

        was_playing = self._player.is_playing()
        if was_playing:
            self._player.pause()
            time.sleep(0.15)

        snap_path = os.path.join(tempfile.gettempdir(), "vlc_crop_snap.png")
        # Remove stale snapshot so we don't show the wrong frame
        if os.path.exists(snap_path):
            os.remove(snap_path)

        ret = self._player.video_take_snapshot(0, snap_path, 0, 0)

        # Wait up to 1.5 s for VLC to write the file
        for _ in range(15):
            if os.path.exists(snap_path) and os.path.getsize(snap_path) > 0:
                break
            time.sleep(0.1)

        if ret != 0 or not os.path.exists(snap_path):
            self._set_status("Snapshot failed. Seek to a different position and try again.")
            if was_playing:
                self._player.play()
            return

        pixmap = QPixmap(snap_path)
        if pixmap.isNull():
            self._set_status("Snapshot was empty. Try again after the video has loaded.")
            if was_playing:
                self._player.play()
            return

        self._picker_was_playing = was_playing

        self._snap_widget = SnapshotCropPicker(pixmap, self.video_frame)
        self._snap_widget.setGeometry(self.video_frame.rect())
        self._snap_widget.show()
        self._snap_widget.raise_()
        self._snap_widget.setFocus()
        self._set_status(
            "Drag to draw crop box   |   Enter = Apply Crop   |   Esc = Cancel"
        )

    def _on_crop_picker_confirm(self):
        coords = self._snap_widget.get_video_crop()
        self._close_crop_picker()

        if coords:
            vx, vy, vw, vh = coords
            self._pending_crop = coords
            self.btn_apply.setEnabled(True)
            self._set_status(
                f"Crop selected: ({vx}, {vy})  {vw}×{vh} px   |   "
                "Click Apply Crop to activate it"
            )
        else:
            self._set_status("Selection too small — try again.")

        if self._picker_was_playing:
            self._player.play()

    def _on_crop_picker_cancel(self):
        self._close_crop_picker()
        self._set_status("Crop cancelled.")
        if self._picker_was_playing:
            self._player.play()

    def _close_crop_picker(self):
        if self._snap_widget:
            self._snap_widget.hide()
            self._snap_widget.deleteLater()
            self._snap_widget = None

    def _apply_pending_crop(self):
        if not self._pending_crop:
            self._set_status("Draw a crop box first (click Draw Crop Box).")
            return
        vx, vy, vw, vh = self._pending_crop
        crop_str = f"{vw}x{vh}+{vx}+{vy}"
        self._player.video_set_crop_geometry(crop_str)
        self._player.video_set_scale(0)   # auto-fit the crop to the window
        self._set_status(
            f"Crop applied: {crop_str}   Zoom: {self._zoom:.2f}×"
        )

    # =========================================================================
    # RESET
    # =========================================================================

    def _reset_all(self, quiet: bool = False):
        self._player.video_set_crop_geometry(None)
        self._player.video_set_scale(0)
        self._zoom         = 1.0
        self._pending_crop = None
        self._close_crop_picker()
        self.btn_apply.setEnabled(False)
        self.lbl_zoom.setText("Zoom: 1.00×")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(4)   # 4 × 0.25 = 1.0×
        self.zoom_slider.blockSignals(False)
        if not quiet:
            self._set_status(
                "Reset.   Shift+scroll = zoom   |   Draw Crop Box to select region"
            )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _set_status(self, msg: str):
        self.lbl_status.setText(msg)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    initial_file = sys.argv[1] if len(sys.argv) > 1 else None

    win = PlayerWindow(initial_file=initial_file)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
