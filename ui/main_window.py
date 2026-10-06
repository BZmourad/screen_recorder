"""Main application window for the screen recorder."""

import logging
import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logger import get_log_file
from recorder import (
    AudioDevice,
    AudioRecorder,
    CaptureSource,
    ScreenRecorder,
    get_default_input_device,
    list_all_sources,
    list_input_devices,
    make_temp_path,
    mux_audio_video,
)
from ui.overlay import POSITIONS, RecordingOverlay  # --- v4 ---

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Screen Recorder")
        self.setMinimumWidth(660)

        self.recorder: ScreenRecorder | None = None
        self.audio_recorder: AudioRecorder | None = None

        self._temp_video: str | None = None
        self._temp_audio: str | None = None
        self._final_output: str | None = None
        self._audio_enabled: bool = False

        # --- v4 ---
        self.overlay = RecordingOverlay()

        self._build_ui()
        self._refresh_sources()
        self._refresh_audio_devices()

        log.info("Main window ready (log file: %s)", get_log_file())

    # ------------------------------------------------------------------ UI --
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Source row ---
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Source:"))

        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(320)
        source_row.addWidget(self.source_combo, stretch=1)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Re-scan monitors and windows")
        self.refresh_btn.clicked.connect(self._refresh_sources)
        source_row.addWidget(self.refresh_btn)

        layout.addLayout(source_row)

        # --- Options row ---
        options_row = QHBoxLayout()
        self.cursor_checkbox = QCheckBox("Show mouse cursor")
        self.cursor_checkbox.setChecked(True)
        options_row.addWidget(self.cursor_checkbox)

        self.audio_checkbox = QCheckBox("Record audio")
        self.audio_checkbox.setChecked(False)
        self.audio_checkbox.toggled.connect(self._on_audio_toggled)
        options_row.addWidget(self.audio_checkbox)

        # --- v4 : overlay toggle ---
        self.overlay_checkbox = QCheckBox("Show recording indicator")
        self.overlay_checkbox.setChecked(True)
        self.overlay_checkbox.toggled.connect(self._on_overlay_toggled)
        options_row.addWidget(self.overlay_checkbox)

        options_row.addStretch(1)
        layout.addLayout(options_row)

        # --- Microphone row ---
        mic_row = QHBoxLayout()
        mic_row.addSpacing(20)
        mic_row.addWidget(QLabel("Microphone:"))

        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(360)
        self.mic_combo.setEnabled(False)
        mic_row.addWidget(self.mic_combo, stretch=1)

        self.mic_refresh_btn = QPushButton("↻")
        self.mic_refresh_btn.setToolTip("Re-scan microphones")
        self.mic_refresh_btn.setEnabled(False)
        self.mic_refresh_btn.clicked.connect(self._refresh_audio_devices)
        mic_row.addWidget(self.mic_refresh_btn)

        layout.addLayout(mic_row)

        # --- v4 : overlay position row ---
        overlay_row = QHBoxLayout()
        overlay_row.addSpacing(20)
        overlay_row.addWidget(QLabel("Indicator position:"))

        self.overlay_position_combo = QComboBox()
        for pos in POSITIONS:
            self.overlay_position_combo.addItem(pos, pos)
        # Default: bottom-right
        idx = self.overlay_position_combo.findData("bottom-right")
        if idx >= 0:
            self.overlay_position_combo.setCurrentIndex(idx)
        self.overlay_position_combo.currentIndexChanged.connect(
            self._on_overlay_position_changed
        )
        overlay_row.addWidget(self.overlay_position_combo)
        overlay_row.addStretch(1)

        layout.addLayout(overlay_row)

        # --- Output path row ---
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Save to:"))

        self.path_edit = QLineEdit(self._default_output_path())
        self.path_edit.setReadOnly(True)
        path_row.addWidget(self.path_edit, stretch=1)

        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._choose_output_path)
        path_row.addWidget(self.browse_btn)

        layout.addLayout(path_row)

        # --- Buttons row ---
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Recording")
        self.start_btn.clicked.connect(self._start_recording)
        self.stop_btn = QPushButton("Stop Recording")
        self.stop_btn.clicked.connect(self._stop_recording)
        self.stop_btn.setEnabled(False)

        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        # --- Status + timer ---
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 14px; padding: 6px;")

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; padding: 10px;"
        )

        layout.addWidget(self.status_label)
        layout.addWidget(self.timer_label)

    # ------------------------------------------------------------- Sources --
    def _refresh_sources(self) -> None:
        current = self.source_combo.currentData()
        self.source_combo.clear()
        sources = list_all_sources()

        if not sources:
            self.source_combo.addItem("No sources found", None)
            self.source_combo.setEnabled(False)
            self.start_btn.setEnabled(False)
            log.warning("No capture sources found")
            return

        for src in sources:
            self.source_combo.addItem(src.label, src)

        if isinstance(current, CaptureSource):
            for i in range(self.source_combo.count()):
                data = self.source_combo.itemData(i)
                if (
                    isinstance(data, CaptureSource)
                    and data.kind == current.kind
                    and data.source_id == current.source_id
                ):
                    self.source_combo.setCurrentIndex(i)
                    break

        self.source_combo.setEnabled(True)
        self.start_btn.setEnabled(True)

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

    # --- v4 ----------------------------------------------------------------
    def _on_overlay_toggled(self, checked: bool) -> None:
        self.overlay_position_combo.setEnabled(checked)
        log.debug("Overlay checkbox toggled: %s", checked)

    def _on_overlay_position_changed(self, _index: int) -> None:
        pos = self.overlay_position_combo.currentData()
        if pos:
            self.overlay.set_position(pos)
            log.debug("Overlay position changed to: %s", pos)

    # ------------------------------------------------------------- Helpers --
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
        source: CaptureSource | None = self.source_combo.currentData()
        if source is None:
            QMessageBox.warning(self, "No source", "Please choose a capture source.")
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

        selected_mic: AudioDevice | None = None
        if self._audio_enabled:
            selected_mic = self.mic_combo.currentData()
            if selected_mic is None:
                QMessageBox.warning(
                    self, "No microphone",
                    "Audio is enabled but no microphone is selected.",
                )
                return

        if self._audio_enabled:
            self._temp_video = make_temp_path(".mp4")
            self._temp_audio = make_temp_path(".wav")
            video_target = self._temp_video
        else:
            self._temp_video = None
            self._temp_audio = None
            video_target = final_output

        log.info(
            "Start recording | source=%s | fps=30 | audio=%s | mic=%s | overlay=%s | overlay_pos=%s | output=%s",
            source.label, self._audio_enabled,
            selected_mic.label if selected_mic else "—",
            self.overlay_checkbox.isChecked(),
            self.overlay_position_combo.currentData(),
            final_output,
        )

        # --- v4 : start overlay BEFORE the recorder so it's already
        #     excluded from capture when the first frame is grabbed.
        if self.overlay_checkbox.isChecked():
            self.overlay.start(self.overlay_position_combo.currentData())

        # --- Start audio ---
        if self._audio_enabled and selected_mic is not None:
            self.audio_recorder = AudioRecorder(
                self._temp_audio, device_index=selected_mic.index
            )
            self.audio_recorder.start()

        # --- Start video ---
        self.recorder = ScreenRecorder(
            output_path=video_target,
            source=source,
            fps=30,
            draw_cursor=self.cursor_checkbox.isChecked(),
        )
        self.recorder.started_recording.connect(self._on_recording_started)
        self.recorder.stopped_recording.connect(self._on_recording_stopped)
        self.recorder.error_occurred.connect(self._on_error)
        self.recorder.elapsed_time.connect(self._on_elapsed_time)
        self.recorder.start()

        self._set_recording_ui(True)
        self.status_label.setText("Recording…")
        self.timer_label.setText("00:00:00")

    def _stop_recording(self) -> None:
        if self.recorder and self.recorder.isRunning():
            log.info("Stop requested by user")
            self.status_label.setText("Stopping…")
            self.stop_btn.setEnabled(False)

            if self.audio_recorder is not None:
                self.audio_recorder.stop()

            self.recorder.stop()

    # ------------------------------------------------------------- Signals --
    def _on_recording_started(self, path: str) -> None:
        source_label = self.source_combo.currentText()
        log.info("Video recording started → %s", path)
        self.status_label.setText(
            f"Recording [{source_label}] → {os.path.basename(self._final_output or path)}"
        )

    def _on_recording_stopped(self, path: str) -> None:
        log.info("Video recording stopped → %s", path)

        # --- v4 : hide overlay as soon as recording stops ---
        self.overlay.stop()

        self._set_recording_ui(False)
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
        self._refresh_sources()

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

        # --- v4 ---
        self.overlay.stop()

        self.status_label.setText("Error")
        self._set_recording_ui(False)
        if self.audio_recorder is not None:
            self.audio_recorder.stop()
            self.audio_recorder = None
        self._cleanup_temp_files()
        QMessageBox.critical(self, "Recording error", message)

    # ----------------------------------------------------------------- UI --
    def _set_recording_ui(self, recording: bool) -> None:
        self.start_btn.setEnabled(not recording)
        self.stop_btn.setEnabled(recording)
        self.browse_btn.setEnabled(not recording)
        self.path_edit.setEnabled(not recording)
        self.source_combo.setEnabled(not recording)
        self.refresh_btn.setEnabled(not recording)
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
        self.overlay.stop()
        if self.recorder and self.recorder.isRunning():
            self.recorder.stop()
            self.recorder.wait(3000)
        if self.audio_recorder is not None:
            self.audio_recorder.stop()
        self._cleanup_temp_files()
        event.accept()