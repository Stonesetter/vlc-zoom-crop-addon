#!/usr/bin/env python3
"""
vlc_player_gui.py — Interactive VLC player with drag-to-crop and Shift+scroll zoom

Controls:
  Shift + scroll wheel    Zoom in / out (0.25x steps)
  Click "Draw Crop Box"   Pauses video, shows a live snapshot of the current frame.
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
from PyQt5.QtGui import QPixmap, QKeySequence


# =============================================================================
# SNAPSHOT CROP PICKER
# Shown as a full overlay over the video area when the user clicks Draw Crop Box.
# Displays a frozen frame from the video; user drags to select the crop region.
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

        self._pixmap = pixmap          # the snapshot image (scaled to fit the widget)
        self._drag_start = None
        self._drag_end   = None
        self._dragging   = False
        self._final_rect = None        # QRect in widget coords (set after mouse release)

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
        from PyQt5.QtGui import QPainter
        painter = QPainter(self)
        if not self._pixmap.isNull():
            # Centre the pixmap (letterbox/pillarbox to fill the widget)
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

    # ---- helpers -------------------------------------------------------------

    def get_video_crop(self) -> tuple | None:
        """
        Convert the rubber-band selection from widget pixel coords to actual
        video pixel coords, accounting for letterbox/pillarbox scaling.
        Returns (x, y, w, h) in video pixels, or None if no selection.
        """
        if not self._final_rect or self._final_rect.width() < 5 or self._final_rect.height() < 5:
            return None

        r  = self._final_rect
        iw = self._pixmap.width()
        ih = self._pixmap.height()
        ww = self.width()
        wh = self.height()

        # Scale used by paintEvent (KeepAspectRatio into the widget)
        scale = min(ww / iw, wh / ih)
        off_x = (ww - iw * scale) / 2
        off_y = (wh - ih * scale) / 2

        vx = max(0, int((r.x()      - off_x) / scale))
        vy = max(0, int((r.y()      - off_y) / scale))
        vw = max(1, int(r.width()            / scale))
        vh = max(1, int(r.height()           / scale))

        # Clamp to image bounds
        vw = min(vw, iw - vx)
        vh = min(vh, ih - vy)

        return (vx, vy, vw, vh)

    def _confirm(self):
        # Signal back to the parent window (PlayerWindow)
        self.parent()._on_crop_picker_confirm()

    def _cancel(self):
        self.parent()._on_crop_picker_cancel()


# =============================================================================
# MAIN PLAYER WINDOW
# =============================================================================

class PlayerWindow(QMainWindow):

    def __init__(self, initial_file: str = None):
        super().__init__()
        self.setWindowTitle("VLC Crop & Zoom")
        self.resize(1280, 780)

        # --- VLC setup --------------------------------------------------------
        # --no-xlib avoids an Xlib threading crash on some Linux setups
        args = ["--no-xlib"] if sys.platform.startswith("linux") else []
        self._vlc_instance = vlc.Instance(*args)
        self._player       = self._vlc_instance.media_player_new()

        # --- State ------------------------------------------------------------
        self._vid_w        = 0       # actual video width  (0 until detected)
        self._vid_h        = 0       # actual video height (0 until detected)
        self._zoom         = 1.0     # current zoom level
        self._pending_crop = None    # (vx, vy, vw, vh) selected but not yet applied
        self._snap_widget  = None    # SnapshotCropPicker when active

        # --- Build UI ---------------------------------------------------------
        self._build_ui()

        # Install app-level event filter so we can intercept Shift+scroll
        # before VLC's embedded window swallows the event.
        QApplication.instance().installEventFilter(self)

        # Poll timer: keep seek bar in sync + detect video dimensions
        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()

        # Open a file passed on the command line
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

        # ---- Video rendering frame ----
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background: black;")
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_frame.setMinimumSize(640, 360)
        vbox.addWidget(self.video_frame, stretch=1)

        # Tell VLC to render into this widget's window handle
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

        self.btn_open.clicked.connect(self._open_file_dialog)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_crop.clicked.connect(self._start_crop_picker)
        self.btn_apply.clicked.connect(self._apply_pending_crop)
        self.btn_reset.clicked.connect(self._reset_all)

        self.btn_apply.setEnabled(False)   # grey until a crop is drawn

        for w in (self.btn_open, self.btn_play, self.btn_crop,
                  self.btn_apply, self.btn_reset, self.lbl_zoom):
            bar.addWidget(w)
        bar.addStretch()

        hint = QLabel("Shift+scroll = zoom  |  Draw Crop Box → drag on snapshot → Enter to apply")
        hint.setStyleSheet("color: #777; font-size: 10px;")
        bar.addWidget(hint)

        vbox.addLayout(bar)

    # =========================================================================
    # EVENT HANDLING
    # =========================================================================

    def eventFilter(self, obj, event):
        """
        Application-level filter.
        Intercept Shift+scroll anywhere in the app for zoom control.
        This runs before VLC's embedded window can swallow the event.
        """
        if event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ShiftModifier:
                delta = event.angleDelta().y()
                step  = 0.25 if delta > 0 else -0.25
                self._zoom = round(max(0.25, min(16.0, self._zoom + step)), 2)
                self._player.video_set_scale(self._zoom)
                self.lbl_zoom.setText(f"Zoom: {self._zoom:.2f}×")
                self._set_status(
                    f"Zoom: {self._zoom:.2f}×   (Shift+scroll to adjust)"
                )
                return True   # consumed — don't pass on
        return False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the crop picker overlay the same size as the video frame
        if self._snap_widget:
            self._snap_widget.setGeometry(self.video_frame.rect())

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
        """Called every 250 ms: sync seek bar and detect video dimensions."""
        state = self._player.get_state()
        if state in (vlc.State.Playing, vlc.State.Paused):
            pos = self._player.get_position()
            if not self.seek_bar.isSliderDown():
                self.seek_bar.setValue(int(pos * 1000))

        # Grab video dimensions once after playback starts
        if self._vid_w == 0:
            w, h = self._player.video_get_size(0)
            if w and h:
                self._vid_w, self._vid_h = w, h
                self._set_status(
                    f"Video: {w}×{h}   |   "
                    "Shift+scroll = zoom   |   Draw Crop Box to select region"
                )

    # =========================================================================
    # CROP PICKER (snapshot overlay)
    # =========================================================================

    def _start_crop_picker(self):
        """
        Pause the video, take a snapshot of the current frame, display it as
        a full overlay so the user can drag a crop rectangle on it.
        """
        if self._player.get_state() not in (vlc.State.Playing, vlc.State.Paused):
            self._set_status("Play a video first, then click Draw Crop Box.")
            return

        # Pause and wait a frame so we capture a clean image
        was_playing = self._player.is_playing()
        if was_playing:
            self._player.pause()
            time.sleep(0.15)

        # Ask VLC to write the current frame to a temp PNG
        snap_path = os.path.join(tempfile.gettempdir(), "vlc_crop_snap.png")
        ret = self._player.video_take_snapshot(0, snap_path, 0, 0)

        # Wait up to 1.5 s for the file to appear
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

        # Store whether video was playing so we can resume after the picker closes
        self._picker_was_playing = was_playing

        # Show the crop picker as an overlay covering the video frame
        self._snap_widget = SnapshotCropPicker(pixmap, self.video_frame)
        self._snap_widget.setGeometry(self.video_frame.rect())
        self._snap_widget.show()
        self._snap_widget.setFocus()
        self._set_status(
            "Drag to draw crop box   |   Enter = Apply Crop   |   Esc = Cancel"
        )

    def _on_crop_picker_confirm(self):
        """Called by SnapshotCropPicker when user presses Enter."""
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
        """Called by SnapshotCropPicker when user presses Esc."""
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
        """Apply the stored pending crop to the live video."""
        if not self._pending_crop:
            self._set_status("Draw a crop box first (click Draw Crop Box).")
            return
        vx, vy, vw, vh = self._pending_crop
        crop_str = f"{vw}x{vh}+{vx}+{vy}"
        self._player.video_set_crop_geometry(crop_str)
        self._set_status(
            f"Crop applied: {crop_str}   Zoom: {self._zoom:.2f}×"
        )

    # =========================================================================
    # RESET
    # =========================================================================

    def _reset_all(self, quiet: bool = False):
        """Remove all crop and zoom, restore the original view."""
        self._player.video_set_crop_geometry(None)
        self._player.video_set_scale(0)   # 0 = auto-fit to window
        self._zoom         = 1.0
        self._pending_crop = None
        self._close_crop_picker()
        self.btn_apply.setEnabled(False)
        self.lbl_zoom.setText("Zoom: 1.00×")
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

    # Accept an optional video file path as the first argument
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None

    win = PlayerWindow(initial_file=initial_file)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
