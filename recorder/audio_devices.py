"""Enumerate available microphone / input devices."""

import logging
from dataclasses import dataclass
from typing import List, Optional

import sounddevice as sd

log = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    index: int
    name: str
    channels: int
    sample_rate: float

    @property
    def label(self) -> str:
        return f"{self.name}  ({int(self.sample_rate)} Hz, {self.channels} ch)"


def _ensure_portaudio_initialized() -> None:
    """Force PortAudio to enumerate devices.

    Without this, the first `InputStream` call on some Windows setups fails
    with "Error querying device -1" because the default device index hasn't
    been resolved yet.
    """
    try:
        sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        log.warning("PortAudio init query failed: %s", exc)


def list_input_devices() -> List[AudioDevice]:
    """Return all devices that support at least one input channel."""
    _ensure_portaudio_initialized()

    devices: List[AudioDevice] = []
    try:
        host_apis = sd.query_hostapis()
        raw = sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to query audio devices: %s", exc)
        return []

    for idx, info in enumerate(raw):
        max_in = info.get("max_input_channels", 0)
        if max_in <= 0:
            continue

        name = info.get("name", f"Device {idx}")
        # Prefix with host API name to disambiguate MME vs WASAPI vs DirectSound
        try:
            host_name = host_apis[info["hostapi"]]["name"]
        except Exception:
            host_name = "?"
        display_name = f"[{host_name}] {name}"

        devices.append(
            AudioDevice(
                index=idx,
                name=display_name,
                channels=max_in,
                sample_rate=info.get("default_samplerate", 44100.0),
            )
        )

    log.info("Found %d input device(s)", len(devices))
    for d in devices:
        log.debug("  input device %d: %s", d.index, d.label)

    return devices


def get_default_input_device() -> Optional[AudioDevice]:
    """Return the system default input device, or the first available one."""
    _ensure_portaudio_initialized()

    # 1. Try the system default
    try:
        default_in = sd.default.device[0]
        if default_in is not None and default_in >= 0:
            info = sd.query_devices(default_in)
            if info.get("max_input_channels", 0) > 0:
                host = sd.query_hostapis()[info["hostapi"]]["name"]
                return AudioDevice(
                    index=default_in,
                    name=f"[{host}] {info['name']}",
                    channels=info["max_input_channels"],
                    sample_rate=info.get("default_samplerate", 44100.0),
                )
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not query default input device: %s", exc)

    # 2. Fall back to the first input device in the list
    devices = list_input_devices()
    return devices[0] if devices else None