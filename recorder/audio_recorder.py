"""Audio recording worker.

Records from a specific input device (microphone) into a mono 16-bit WAV
file. Runs in a plain Python thread.
"""

import logging
import threading
import wave
from typing import Optional

import sounddevice as sd

log = logging.getLogger(__name__)


class AudioRecorder:
    """Records a chosen microphone to a mono 16-bit WAV file."""

    SAMPLE_RATE = 44100
    CHANNELS = 1
    DTYPE = "int16"
    BLOCK_SIZE = 1024  # frames per callback

    def __init__(self, output_path: str, device_index: Optional[int] = None):
        self.output_path = output_path
        self.device_index = device_index
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._error: Optional[str] = None
        self._blocks = 0

    # ---------------------------------------------------------------- public
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    @property
    def error(self) -> Optional[str]:
        return self._error

    # --------------------------------------------------------------- private
    def _resolve_device(self) -> int:
        """Return a valid device index or raise a clear error."""
        if self.device_index is not None and self.device_index >= 0:
            try:
                info = sd.query_devices(self.device_index)
                if info.get("max_input_channels", 0) <= 0:
                    raise RuntimeError(
                        f"Device {self.device_index} has no input channels"
                    )
                return self.device_index
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"Invalid audio device index {self.device_index}: {exc}"
                ) from exc

        # Fallback: use the system default, validated
        try:
            default_in = sd.default.device[0]
        except Exception:
            default_in = None

        if default_in is None or default_in < 0:
            # Try to pick the first device that actually has input channels
            for idx, info in enumerate(sd.query_devices()):
                if info.get("max_input_channels", 0) > 0:
                    log.warning(
                        "No default input device; using first available: %d (%s)",
                        idx, info.get("name"),
                    )
                    return idx
            raise RuntimeError("No microphone / input device found on this system")

        return default_in

    def _run(self) -> None:
        try:
            device = self._resolve_device()
            info = sd.query_devices(device)
            log.info(
                "Audio recording → device %d (%s), %d Hz, %d ch",
                device, info.get("name"), self.SAMPLE_RATE, self.CHANNELS,
            )

            with wave.open(self.output_path, "wb") as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.SAMPLE_RATE)

                def _callback(indata, frames, time_info, status):  # noqa: ARG001
                    if status:
                        log.warning("Audio stream status: %s", status)
                    if self._stop_event.is_set():
                        raise sd.CallbackStop()
                    wf.writeframes(indata.tobytes())
                    self._blocks += 1

                with sd.InputStream(
                    samplerate=self.SAMPLE_RATE,
                    channels=self.CHANNELS,
                    dtype=self.DTYPE,
                    blocksize=self.BLOCK_SIZE,
                    device=device,
                    callback=_callback,
                ):
                    self._stop_event.wait()

            log.info("Audio recording finished (%d blocks written)", self._blocks)

        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            log.exception("Audio recording failed")