"""Main application window for the screen recorder.

Responsive layout:
  * Wide window (≥ 960 px): thumbnails on the left, controls in a right sidebar.
  * Narrow window: everything stacked vertically in a single column.
"""

import logging
import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from logger import get_countdown_seconds, get_log_file, get_test_env
from recorder import (
    AudioDevice,
    AudioRecorder,
    CaptureSource,
    ScreenRecorder,
    get_default_input_device,
    list_input_devices,
    list_monitors,
    make_temp_path,
    mux_audio_video,
)
from ui.icons import make_icon
from ui.overlay import POSITIONS, RecordingOverlay
from ui.responsive_grid import ResponsiveGrid
from ui.screen_thumbnail import ScreenThumbnail
from ui.theme import Colors

log = logging.getLogger(__name__)

# Layout breakpoints (pixels)
WIDE_BREAKPOINT = 960
THUMB_MIN_WIDTH_WIDE = 280
THUMB_MIN_WIDTH_NARROW = 220


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Screen Recorder")
        self.setMinimumSize(620, 700)
        self.resize(1100, 820)

        self.recorder: ScreenRecorder | None = None
        self.audio_recorder: AudioRecorder | None = None

        self._temp_video: str | None = None
        self._temp_audio: str | None = None
        self._final_output: str | None = None
        self._audio_enabled: bool = False
        self._selected_mic: AudioDevice | None = None

        self._selected_source: CaptureSource | None = None
        self._thumbnails: list[ScreenThumbnail] = []

        self.overlay = RecordingOverlay()

        self._countdown_timer: QTimer | None = None
        self._countdown_remaining: int = 0

        self._is_wide: bool = True

        self._build_ui()
        self._refresh_screens()
        self._refresh_audio_devices()

        log.info("Main window ready (log file: %s)", get_log_file())

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # ========== Header ==========
        root.addLayout(self._build_header())

        # ========== Splitter: content (left) + controls (right) ==========
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(12)
        self.splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: transparent; }}"
        )

        self.screens_panel = self._build_screens_panel()
        self.controls_panel = self._build_controls_panel()

        self.splitter.addWidget(self.screens_panel)
        self.splitter.addWidget(self.controls_panel)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([700, 340])

        root.addWidget(self.splitter, stretch=1)

        # ========== Status bar ==========
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusBar")
        self.status_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status_label)

    # -------------------------------------------------------------- Header --
    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title = QLabel("Screen Recorder")
        title.setObjectName("titleLabel")
        title_box.addWidget(title)

        subtitle = QLabel("Record your screen to MP4, optionally with microphone audio.")
        subtitle.setObjectName("subtitleLabel")
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch(1)

        return header

    # ------------------------------------------------------- Screens panel --
    def _build_screens_panel(self) -> QWidget:
        panel = QGroupBox("  Screens")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(10)

        # Header row inside the group
        head = QHBoxLayout()
        head.setSpacing(10)

        self.screen_count_label = QLabel("Detecting screens…")
        self.screen_count_label.setObjectName("hint")
        head.addWidget(self.screen_count_label)
        head.addStretch(1)

        self.refresh_screens_btn = QPushButton("  Refresh")
        self.refresh_screens_btn.setIcon(make_icon("refresh", Colors.TEXT_MUTED, 16))
        self.refresh_screens_btn.setToolTip("Re-scan monitors and update previews")
        self.refresh_screens_btn.setObjectName("ghostButton")
        self.refresh_screens_btn.clicked.connect(self._refresh_screens)
        head.addWidget(self.refresh_screens_btn)

        panel_layout.addLayout(head)

        # Scrollable area
        self.screens_scroll = QScrollArea()
        self.screens_scroll.setWidgetResizable(True)
        self.screens_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.screens_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.screens_scroll.setMinimumHeight(220)

        self.screens_grid = ResponsiveGrid(
            item_min_width=THUMB_MIN_WIDTH_WIDE, spacing=14
        )
        self.screens_scroll.setWidget(self.screens_grid)

        panel_layout.addWidget(self.screens_scroll, stretch=1)
        return panel

    # ------------------------------------------------------ Controls panel --
    def _build_controls_panel(self) -> QWidget:
        # This panel contains everything: options, timer, buttons.
        # It's a plain widget so we can stick it in the splitter or below.
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # --- Timer ---
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("timerLabel")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setProperty("state", "idle")
        layout.addWidget(self.timer_label)

        # --- Action buttons ---
        action_box = QGroupBox("  Actions")
        action_layout = QVBoxLayout(action_box)
        action_layout.setSpacing(10)

        self.start_btn = QPushButton("  Start Recording")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setIcon(make_icon("play", "#0b0f14", 16))
        self.start_btn.setMinimumHeight(46)
        self.start_btn.clicked.connect(self._start_recording)
        self.start_btn.setEnabled(False)
        action_layout.addWidget(self.start_btn)

        row = QHBoxLayout()
        row.setSpacing(10)

        self.pause_btn = QPushButton("  Pause")
        self.pause_btn.setObjectName("warningButton")
        self.pause_btn.setIcon(make_icon("pause", "#0b0f14", 16))
        self.pause_btn.setMinimumHeight(46)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.pause_btn.setEnabled(False)
        row.addWidget(self.pause_btn, stretch=1)

        self.stop_btn = QPushButton("  Stop")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.setIcon(make_icon("stop", "#ffffff", 16))
        self.stop_btn.setMinimumHeight(46)
        self.stop_btn.clicked.connect(self._stop_recording)
        self.stop_btn.setEnabled(False)
        row.addWidget(self.stop_btn, stretch=1)

        action_layout.addLayout(row)
        layout.addWidget(action_box)

        # --- Options ---
        opts_box = QGroupBox("  Options")
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setSpacing(12)

        self.cursor_checkbox = QCheckBox("Show mouse cursor")
        self.cursor_checkbox.setChecked(True)
        opts_layout.addWidget(self.cursor_checkbox)

        self.audio_checkbox = QCheckBox("Record audio")
        self.audio_checkbox.setChecked(False)
        self.audio_checkbox.toggled.connect(self._on_audio_toggled)
        opts_layout.addWidget(self.audio_checkbox)

        self.overlay_checkbox = QCheckBox("Show recording indicator")
        self.overlay_checkbox.setChecked(True)
        self.overlay_checkbox.toggled.connect(self._on_overlay_toggled)
        opts_layout.addWidget(self.overlay_checkbox)

        # Separator
        opts_layout.addWidget(self._hline())

        # Microphone row
        mic_row = QHBoxLayout()
        mic_row.setSpacing(8)

        mic_icon = QLabel()
        mic_icon.setPixmap(make_icon("mic", Colors.TEXT_MUTED, 16).pixmap(16, 16))
        mic_row.addWidget(mic_icon)

        self.mic_combo = QComboBox()
        self.mic_combo.setEnabled(False)
        self.mic_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        mic_row.addWidget(self.mic_combo, stretch=1)

        self.mic_refresh_btn = QPushButton()
        self.mic_refresh_btn.setIcon(make_icon("refresh", Colors.TEXT_MUTED, 16))
        self.mic_refresh_btn.setToolTip("Re-scan microphones")
        self.mic_refresh_btn.setEnabled(False)
        self.mic_refresh_btn.setObjectName("iconButton")
        self.mic_refresh_btn.clicked.connect(self._refresh_audio_devices)
        mic_row.addWidget(self.mic_refresh_btn)

        opts_layout.addLayout(mic_row)

        # Overlay position
        pos_row = QHBoxLayout()
        pos_row.setSpacing(8)

        dot_icon = QLabel()
        dot_icon.setPixmap(make_icon("dot", Colors.REC_DOT, 16).pixmap(16, 16))
        pos_row.addWidget(dot_icon)

        self.overlay_position_combo = QComboBox()
        for pos in POSITIONS:
            self.overlay_position_combo.addItem(pos, pos)
        idx = self.overlay_position_combo.findData("bottom-right")
        if idx >= 0:
            self.overlay_position_combo.setCurrentIndex(idx)
        self.overlay_position_combo.currentIndexChanged.connect(
            self._on_overlay_position_changed
        )
        self.overlay_position_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        pos_row.addWidget(self.overlay_position_combo, stretch=1)

        opts_layout.addLayout(pos_row)

        # Output path
        opts_layout.addWidget(self._hline())

        path_label = QLabel("Save to")
        path_label.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 9pt; font-weight: 600; "
            f"letter-spacing: 0.6px;"
        )
        opts_layout.addWidget(path_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self.path_edit = QLineEdit(self._default_output_path())
        self.path_edit.setReadOnly(True)
        self.path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        path_row.addWidget(self.path_edit, stretch=1)

        self.browse_btn = QPushButton()
        self.browse_btn.setIcon(make_icon("folder", Colors.TEXT_MUTED, 16))
        self.browse_btn.setToolTip("Choose save location")
        self.browse_btn.setObjectName("iconButton")
        self.browse_btn.clicked.connect(self._choose_output_path)
        path_row.addWidget(self.browse_btn)

        opts_layout.addLayout(path_row)
        layout.addWidget(opts_box)

        layout.addStretch(1)

        wrapper.setMinimumWidth(300)
        wrapper.setMaximumWidth(420)
        return wrapper

    # ------------------------------------------------------------- Helpers --
    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet(f"color: {Colors.BORDER}; background-color: {Colors.BORDER};")
        line.setFixedHeight(1)
        return line

    @staticmethod
    def _default_output_path() -> str:
        videos_dir = os.path.join(os.path.expanduser("~"), "Videos")
        if not os.path.isdir(videos_dir):
            videos_dir = os.path.expanduser("~")
        filename = datetime.now().strftime("screen_recording_%Y-%m-%d_%H-%M-%S.mp4")
        return os.path.join(videos_dir, filename)

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        total = int(seconds)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _set_timer_state(self, state: str) -> None:
        """state ∈ {'idle', 'recording', 'paused'}"""
        self.timer_label.setProperty("state", state)
        self.timer_label.style().unpolish(self.timer_label)
        self.timer_label.style().polish(self.timer_label)

    # ------------------------------------------------------------ Responsive
    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        wide = self.width() >= WIDE_BREAKPOINT

        if wide != self._is_wide:
            self._is_wide = wide
            self._apply_layout_mode(wide)

        # Update the thumbnail minimum width for the responsive grid
        new_min = THUMB_MIN_WIDTH_WIDE if wide else THUMB_MIN_WIDTH_NARROW
        if self.screens_grid._item_min_width != new_min:  # noqa: SLF001
            self.screens_grid.set_item_min_width(new_min)

    def _apply_layout_mode(self, wide: bool) -> None:
        """Rearrange panels depending on available width."""
        # Detach both panels from the splitter
        self.screens_panel.setParent(None)
        self.controls_panel.setParent(None)

        # Reset splitter
        while self.splitter.count():
            self.splitter.widget(0).setParent(None)

        if wide:
            self.splitter.setOrientation(Qt.Horizontal)
            self.splitter.addWidget(self.screens_panel)
            self.splitter.addWidget(self.controls_panel)
            self.splitter.setStretchFactor(0, 1)
            self.splitter.setStretchFactor(1, 0)
            self.splitter.setSizes([700, 340])
        else:
            self.splitter.setOrientation(Qt.Vertical)
            self.splitter.addWidget(self.screens_panel)
            self.splitter.addWidget(self.controls_panel)
            self.splitter.setStretchFactor(0, 1)
            self.splitter.setStretchFactor(1, 0)
            self.splitter.setSizes([400, 400])

        self.screens_panel.show()
        self.controls_panel.show()

        log.debug("Layout mode: %s", "wide" if wide else "narrow")

    # ------------------------------------------------------------- Screens --
    def _refresh_screens(self) -> None:
        log.info("Refreshing screens list")

        previous_id = self._selected_source.source_id if self._selected_source else None

        self.screens_grid.clear()
        for thumb in self._thumbnails:
            thumb.setParent(None)
            thumb.deleteLater()
        self._thumbnails.clear()
        self._selected_source = None

        monitors = list_monitors()
        if not monitors:
            self.screen_count_label.setText("No screen detected")
            self.start_btn.setEnabled(False)
            log.warning("No monitors detected")
            return

        self.screen_count_label.setText(
            f"{len(monitors)} screen(s) detected — click one to select"
        )

        for src in monitors:
            thumb = ScreenThumbnail(src)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            self.screens_grid.add_item(thumb)
            self._thumbnails.append(thumb)

            if previous_id is not None and src.source_id == previous_id:
                self._select_source(src)

        if self._selected_source is None:
            self._select_source(monitors[0])

        self.start_btn.setEnabled(True)

    def _on_thumbnail_clicked(self, source: CaptureSource) -> None:
        self._select_source(source)

    def _select_source(self, source: CaptureSource) -> None:
        self._selected_source = source
        for thumb in self._thumbnails:
            thumb.set_selected(thumb.source.source_id == source.source_id)
        log.info("Selected source: %s", source.label)

    # ------------------------------------------------------- Audio devices --
    def _refresh_audio_devices(self) -> None:
        current = self.mic_combo.currentData()

        self.mic_combo.clear()
        devices = list_input_devices()

        if not devices:
            self.mic_combo.addItem("No microphone detected", None)
            self.mic_combo.setEnabled(False)
            self.audio_checkbox.setEnabled(False)
            log.warning("No audio input devices found")
            return

        self.audio_checkbox.setEnabled(True)

        for dev in devices:
            self.mic_combo.addItem(dev.label, dev)

        if isinstance(current, AudioDevice):
            for i in range(self.mic_combo.count()):
                data = self.mic_combo.itemData(i)
                if isinstance(data, AudioDevice) and data.index == current.index:
                    self.mic_combo.setCurrentIndex(i)
                    break
        else:
            default_dev = get_default_input_device()
            if default_dev is not None:
                for i in range(self.mic_combo.count()):
                    data = self.mic_combo.itemData(i)
                    if isinstance(data, AudioDevice) and data.index == default_dev.index:
                        self.mic_combo.setCurrentIndex(i)
                        log.info("Default microphone: %s", data.label)
                        break

        self.mic_combo.setEnabled(self.audio_checkbox.isChecked())

    def _on_audio_toggled(self, checked: bool) -> None:
        self.mic_combo.setEnabled(checked and self.mic_combo.count() > 0)
        self.mic_refresh_btn.setEnabled(checked and self.mic_combo.count() > 0)
        log.debug("Audio checkbox toggled: %s", checked)

    def _on_overlay_toggled(self, checked: bool) -> None:
        self.overlay_position_combo.setEnabled(checked)
        log.debug("Overlay checkbox toggled: %s", checked)

    def _on_overlay_position_changed(self, _index: int) -> None:
        pos = self.overlay_position_combo.currentData()
        if pos:
            self.overlay.set_position(pos)
            log.debug("Overlay position changed to: %s", pos)

    # ------------------------------------------------------------- Actions --
    def _choose_output_path(self) -> None:
        if self.recorder and self.recorder.isRunning():
            return

        default = self.path_edit.text() or self._default_output_path()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recording as", default, "MP4 video (*.mp4)"
        )
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self.path_edit.setText(path)

    def _start_recording(self) -> None:
        if self._selected_source is None:
            QMessageBox.warning(self, "No screen", "Please select a screen to record.")
            return

        final_output = self.path_edit.text().strip()
        if not final_output:
            QMessageBox.warning(self, "No output path", "Please choose a save location.")
            return

        directory = os.path.dirname(final_output)
        if directory and not os.path.isdir(directory):
            QMessageBox.warning(
                self, "Invalid folder", f"The folder does not exist:\n{directory}"
            )
            return

        self._final_output = final_output
        self._audio_enabled = self.audio_checkbox.isChecked()

        if self._audio_enabled:
            self._selected_mic = self.mic_combo.currentData()
            if self._selected_mic is None:
                QMessageBox.warning(
                    self, "No microphone",
                    "Audio is enabled but no microphone is selected.",
                )
                return
        else:
            self._selected_mic = None

        countdown = get_countdown_seconds()
        if countdown > 0:
            self._run_countdown(countdown)
        else:
            self._start_recording_now()

    def _run_countdown(self, seconds: int) -> None:
        log.info("Starting countdown: %d s", seconds)
        self._lock_ui(True)
        self.status_label.setText(f"Starting in {seconds}…")

        pos = self.overlay_position_combo.currentData() or "bottom-right"
        self.overlay.set_target_screen(self._selected_source)
        self.overlay.start_countdown(seconds, pos)

        self._countdown_remaining = seconds
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._on_countdown_tick)
        self._countdown_timer.start()

    def _on_countdown_tick(self) -> None:
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            if self._countdown_timer is not None:
                self._countdown_timer.stop()
                self._countdown_timer = None
            self.status_label.setText("Ready")
            self._start_recording_now()
        else:
            self.status_label.setText(f"Starting in {self._countdown_remaining}…")

    def _start_recording_now(self) -> None:
        source = self._selected_source
        if source is None:
            log.error("_start_recording_now called without a valid source")
            return

        if self._audio_enabled:
            self._temp_video = make_temp_path(".mp4")
            self._temp_audio = make_temp_path(".wav")
            video_target = self._temp_video
        else:
            self._temp_video = None
            self._temp_audio = None
            video_target = self._final_output

        log.info(
            "Start recording | source=%s | fps=30 | audio=%s | mic=%s | "
            "overlay=%s | overlay_pos=%s | test_watermark=%s | output=%s",
            source.label, self._audio_enabled,
            self._selected_mic.label if self._selected_mic else "—",
            self.overlay_checkbox.isChecked(),
            self.overlay_position_combo.currentData(),
            get_test_env(),
            self._final_output,
        )

        if self.overlay_checkbox.isChecked():
            self.overlay.set_target_screen(source)
            self.overlay.start(self.overlay_position_combo.currentData())

        if self._audio_enabled and self._selected_mic is not None:
            self.audio_recorder = AudioRecorder(
                self._temp_audio, device_index=self._selected_mic.index
            )
            self.audio_recorder.start()

        self.recorder = ScreenRecorder(
            output_path=video_target,
            source=source,
            fps=30,
            draw_cursor=self.cursor_checkbox.isChecked(),
            test_watermark=get_test_env(),   
        )
        self.recorder.started_recording.connect(self._on_recording_started)
        self.recorder.stopped_recording.connect(self._on_recording_stopped)
        self.recorder.error_occurred.connect(self._on_error)
        self.recorder.elapsed_time.connect(self._on_elapsed_time)
        self.recorder.start()

        self._set_recording_ui(True)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("  Pause")
        self.pause_btn.setIcon(make_icon("pause", "#0b0f14", 16))
        self._set_timer_state("recording")
        self.status_label.setText("Recording…")
        self.timer_label.setText("00:00:00")

    def _toggle_pause(self) -> None:
        if self.recorder is None:
            return
        if self.recorder.is_paused():
            self.recorder.resume()
            self.pause_btn.setText("  Pause")
            self.pause_btn.setIcon(make_icon("pause", "#0b0f14", 16))
            self._set_timer_state("recording")
            self.status_label.setText("Recording…")
            log.info("Resume requested")
        else:
            self.recorder.pause()
            self.pause_btn.setText("  Resume")
            self.pause_btn.setIcon(make_icon("play", "#0b0f14", 16))
            self._set_timer_state("paused")
            self.status_label.setText("Paused")
            log.info("Pause requested")

    def _stop_recording(self) -> None:
        if self.recorder and self.recorder.isRunning():
            log.info("Stop requested by user")
            self.status_label.setText("Stopping…")
            self.stop_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)

            if self.audio_recorder is not None:
                self.audio_recorder.stop()

            self.recorder.stop()

    # ------------------------------------------------------------- Signals --
    def _on_recording_started(self, path: str) -> None:
        label = self._selected_source.label if self._selected_source else "?"
        log.info("Video recording started → %s", path)
        self.status_label.setText(
            f"Recording [{label}]  →  {os.path.basename(self._final_output or path)}"
        )

    def _on_recording_stopped(self, path: str) -> None:
        log.info("Video recording stopped → %s", path)
        self.overlay.stop()
        self._set_recording_ui(False)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("  Pause")
        self._set_timer_state("idle")
        self.recorder = None

        if self._audio_enabled and self._temp_video and self._temp_audio:
            if self.audio_recorder is not None and self.audio_recorder.error:
                log.error("Audio recorder reported error: %s", self.audio_recorder.error)
                QMessageBox.warning(
                    self,
                    "Audio error",
                    f"Audio recording failed:\n{self.audio_recorder.error}\n\n"
                    "The video will be saved without audio.",
                )
                self._finalize_without_audio()
            else:
                log.info("Muxing audio+video → %s", self._final_output)
                self.status_label.setText("Merging audio and video…")
                QApplication.processEvents()

                error = mux_audio_video(
                    self._temp_video, self._temp_audio, self._final_output
                )
                if error:
                    log.error("Mux failed: %s", error)
                    QMessageBox.critical(
                        self,
                        "Mux error",
                        f"Could not merge audio and video:\n{error}\n\n"
                        "Saving the silent video instead.",
                    )
                    self._finalize_without_audio()
                else:
                    log.info("Mux succeeded → %s", self._final_output)
                    self._cleanup_temp_files()
                    self.status_label.setText("Recording stopped (with audio)")
        else:
            if self.status_label.text().startswith("Recording"):
                self.status_label.setText("Recording stopped")

        self.audio_recorder = None
        self._temp_video = None
        self._temp_audio = None

    def _finalize_without_audio(self) -> None:
        try:
            import shutil
            if self._temp_video and self._final_output:
                shutil.move(self._temp_video, self._final_output)
                log.info("Saved silent video → %s", self._final_output)
            self.status_label.setText("Recording stopped (no audio)")
        except Exception as exc:  # noqa: BLE001
            log.exception("Could not move silent video")
            QMessageBox.critical(self, "Save error", str(exc))
        finally:
            self._cleanup_temp_files()

    def _cleanup_temp_files(self) -> None:
        for p in (self._temp_video, self._temp_audio):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    log.debug("Removed temp file %s", p)
                except OSError as exc:
                    log.warning("Could not remove temp file %s: %s", p, exc)

    def _on_elapsed_time(self, seconds: float) -> None:
        self.timer_label.setText(self._format_elapsed(seconds))

    def _on_error(self, message: str) -> None:
        log.error("Recording error: %s", message)

        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer = None

        self.overlay.stop()
        self.status_label.setText("Error")
        self._set_recording_ui(False)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("  Pause")
        self._set_timer_state("idle")

        if self.audio_recorder is not None:
            self.audio_recorder.stop()
            self.audio_recorder = None
        self._cleanup_temp_files()
        QMessageBox.critical(self, "Recording error", message)

    # ----------------------------------------------------------------- UI --
    def _lock_ui(self, locked: bool) -> None:
        self.start_btn.setEnabled(not locked)
        self.browse_btn.setEnabled(not locked)
        self.path_edit.setEnabled(not locked)
        self.refresh_screens_btn.setEnabled(not locked)
        for thumb in self._thumbnails:
            thumb.setEnabled(not locked)
        self.cursor_checkbox.setEnabled(not locked)
        self.audio_checkbox.setEnabled(not locked)
        self.overlay_checkbox.setEnabled(not locked)
        self.overlay_position_combo.setEnabled(not locked)
        self.mic_combo.setEnabled(not locked and self.audio_checkbox.isChecked())
        self.mic_refresh_btn.setEnabled(not locked and self.audio_checkbox.isChecked())
        self.pause_btn.setEnabled(not locked)
        self.stop_btn.setEnabled(not locked)

    def _set_recording_ui(self, recording: bool) -> None:
        self.start_btn.setEnabled(not recording)
        self.stop_btn.setEnabled(recording)
        self.pause_btn.setEnabled(recording)
        self.browse_btn.setEnabled(not recording)
        self.path_edit.setEnabled(not recording)
        self.refresh_screens_btn.setEnabled(not recording)

        for thumb in self._thumbnails:
            thumb.setEnabled(not recording)

        self.cursor_checkbox.setEnabled(not recording)
        self.audio_checkbox.setEnabled(not recording)
        self.overlay_checkbox.setEnabled(not recording)

        audio_on = self.audio_checkbox.isChecked()
        self.mic_combo.setEnabled(not recording and audio_on)
        self.mic_refresh_btn.setEnabled(not recording and audio_on)

        overlay_on = self.overlay_checkbox.isChecked()
        self.overlay_position_combo.setEnabled(not recording and overlay_on)

    def closeEvent(self, event) -> None:  # noqa: N802
        log.info("Application closing")

        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer = None

        self.overlay.stop()

        if self.recorder and self.recorder.isRunning():
            if self.recorder.is_paused():
                self.recorder.resume()
            self.recorder.stop()
            self.recorder.wait(3000)

        if self.audio_recorder is not None:
            self.audio_recorder.stop()

        self._cleanup_temp_files()
        event.accept()