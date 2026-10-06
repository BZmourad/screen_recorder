# Screen Recorder — Documentation

A minimal desktop application for recording monitors to MP4, with optional
microphone audio, pause/resume, countdown, and a screen indicator.

Built with **Python 3.11+**, **PySide6**, **mss**, **OpenCV**, **sounddevice**.

---

## Table of contents

1. [Overview](#overview)
2. [Features](#features)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Running the app](#running-the-app)
6. [User guide](#user-guide)
7. [Configuration (`.env`)](#configuration-env)
8. [Output files and folders](#output-files-and-folders)
9. [Architecture](#architecture)
10. [How it works (deep dive)](#how-it-works-deep-dive)
11. [Logging](#logging)
12. [Building a standalone `.exe`](#building-a-standalone-exe)
13. [Troubleshooting](#troubleshooting)
14. [Development](#development)
15. [Roadmap](#roadmap)
16. [License](#license)

---

## Overview

Screen Recorder is a single-window desktop app that captures a monitor
(full screen) and encodes the frames into an MP4 file. It supports:

- Choosing **which monitor** to record among the detected screens.
- Optional **microphone audio**, merged into the same MP4 at the end.
- **Pause / Resume** during recording without creating gaps in the video.
- **Countdown** before recording starts (configurable).
- **On-screen recording indicator** (REC dot + timer) that does not appear
  in the recorded video.
- Optional **TEST watermark** baked into the video for development builds.

The app targets **Windows 10/11**. macOS/Linux support is not currently
provided.

---

## Features

### Capture
- Full-monitor capture (one screen at a time) at 30 FPS.
- Multi-monitor: thumbnails let you choose which screen.
- Mouse cursor is drawn into the video (toggle).
- Frame pacing uses an absolute schedule to guarantee the output duration
  equals the real elapsed time.

### Audio
- Optional microphone recording.
- Device selection from all available input devices.
- Audio and video are recorded in parallel then muxed with FFmpeg.

### UI
- Dark, responsive layout.
- Thumbnails for each monitor with a live preview.
- Big timer with color states: idle / recording / paused.
- Status bar showing the current step.

### Recording indicator
- Dark circle with a blinking red dot and the elapsed time.
- Position configurable (4 corners).
- Positioned on the **target screen**, not the primary one.
- Excluded from screen capture via `SetWindowDisplayAffinity` (Windows 10
  2004+), so it does not appear in the video.

### Configuration
- All runtime options in a `.env` file at the project root:
  logging, countdown, test watermark, app version, app name.

### Diagnostics
- Rotating log file in `logs/screen_recorder.log`.
- Global `sys.excepthook` that logs uncaught exceptions.

---

## Requirements

- **Python 3.11+** (3.13 tested).
- **Windows 10/11** (10.0.19045 tested).
- A working audio driver if you plan to record microphone audio.
- ~200 MB free disk space for the virtual environment and dependencies.

### Python dependencies

```
PySide6>=6.6.0
mss>=9.0.1
opencv-python>=4.9.0
numpy>=1.26.0
sounddevice>=0.4.6
imageio-ffmpeg>=0.4.9
python-dotenv>=1.0.0
```

Optional (dev only):

```
pyinstaller>=6.0
```

---

## Installation

### 1. Clone or download

```bash
git clone <repo-url> screen_recorder
cd screen_recorder
```

### 2. Create a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # Linux/macOS (not supported)
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Create your `.env`

```bash
copy .env.example .env
```

Then edit `.env` to match your preferences. See
[Configuration](#configuration-env).

### 5. Verify the install

```bash
python -c "import PySide6, mss, cv2, sounddevice, imageio_ffmpeg; print('ok')"
```

Expected output: `ok`.

---

## Running the app

```bash
python main.py
```

The main window opens. If no monitors are detected, the app displays
"No screen detected" and the Start button stays disabled.

> **Note:** always launch via `python main.py` from the activated
> virtual environment. Do **not** call the `pyinstaller` binary directly
> from the system PATH — it belongs to a different Python install.

---

## User guide

### Main window

```
┌──────────────────────────────────────────────────────────────────────┐
│  Screen Recorder                                                     │
│  Record your screen to MP4, optionally with microphone audio.       │
│                                                                      │
│  ┌── Screens ───────────────────────┐  ┌── Actions ──────────────┐  │
│  │ 2 screens detected — click one    │  │ ┌─────────────────────┐ │  │
│  │ ┌────────┐ ┌────────┐  [Refresh]  │  │ │  ▶ Start Recording  │ │  │
│  │ │[prev]  │ │[prev]  │             │  │ └─────────────────────┘ │  │
│  │ │Screen 1│ │Screen 2│             │  │ ┌────────┐ ┌──────────┐│  │
│  │ └────────┘ └────────┘             │  │ │ ⏸ Pause │ │ ⏹ Stop  ││  │
│  │                                   │  │ └────────┘ └──────────┘│  │
│  └───────────────────────────────────┘  └─────────────────────────┘  │
│                                                                      │
│  ┌── Options ────────────────────────────────────────────────────┐  │
│  │ ☑ Show mouse cursor       ☐ Record audio                      │  │
│  │ ☑ Show recording indicator                                    │  │
│  │ 🎙 Microphone: [ Realtek Audio Array ▾ ] [↻]                  │  │
│  │ 🔴 Indicator position: [ bottom-right ▾ ]                     │  │
│  │ 📁 Save to: [ C:\Users\...\Videos\screen_recording_...mp4 ] [📂] │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│                       00:00:00                                       │
│                                                                      │
│                         Ready                                        │
└──────────────────────────────────────────────────────────────────────┘
```

### Recording a screen

1. **Pick a screen.** Click the thumbnail of the monitor you want to record.
   The selected card is outlined in blue and shows a ✓ badge.
2. **Choose your options:**
   - *Show mouse cursor* — bake the mouse pointer into the video.
   - *Record audio* — enables the microphone dropdown.
   - *Show recording indicator* — display the on-screen circle during capture.
   - *Indicator position* — top-left / top-right / bottom-left / bottom-right.
3. **Choose a save location** by clicking the 📂 button next to "Save to".
   By default the file goes to `~/Videos/screen_recording_<timestamp>.mp4`.
4. Click **Start Recording**.
   - If a countdown is configured (`COUNTDOWN_SECONDS > 0`), a big number
     appears in the chosen corner for N seconds before recording starts.
   - The circle with the blinking red dot and the timer appears.
5. Click **Pause** if you need to interrupt. The video file will not contain
   a gap — the pause duration is simply excluded.
6. Click **Stop Recording** to finish. If audio was enabled, the app merges
   audio and video automatically (a progress message appears in the status
   bar for a fraction of a second).

### Keyboard interactions

Currently none — the app is entirely mouse-driven. Global hotkeys are on
the roadmap.

### What happens after Stop

- If audio was enabled and the mux succeeds, the file is at the chosen path
  with both video and audio.
- If audio failed (no microphone, device busy), a warning is shown and the
  video is saved silently.
- If mux fails (rare), the silent video is preserved and a critical dialog
  explains what went wrong.

---

## Configuration (`.env`)

All runtime options live in a `.env` file at the project root. Copy the
provided `.env.example` to start.

| Key | Type | Default | Description |
|---|---|---|---|
| `APP_NAME` | string | `ScreenRecorder` | Window/process name (used by `.exe`). |
| `APP_VERSION` | string | `dev` | Version string, used in the test watermark. |
| `LOGGING_ENABLED` | `0`/`1` | `1` | Enable or disable logging entirely. |
| `LOG_LEVEL` | string | `DEBUG` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `LOG_TO_CONSOLE` | `0`/`1` | `1` | Also print logs to the console. |
| `COUNTDOWN_SECONDS` | int | `3` | Countdown before recording starts. `0` disables. Clamped to `[0, 10]`. |
| `TEST_ENV` | `0`/`1` | `0` | Bake a "TEST BUILD" banner into the video. |
| `MIC_DEVICE_INDEX` | int | *(unset)* | Force a specific mic index on startup. |
| `OVERLAY_POSITION` | string | `bottom-right` | `top-left`, `top-right`, `bottom-left`, `bottom-right`. |

### Example `.env`

```env
APP_NAME=ScreenRecorder
APP_VERSION=1.0.0

LOGGING_ENABLED=1
LOG_LEVEL=INFO
LOG_TO_CONSOLE=1

COUNTDOWN_SECONDS=3
TEST_ENV=0

OVERLAY_POSITION=bottom-right
```

### Behaviour notes

- Booleans accept `1/0`, `true/false`, `yes/no`, `on/off` (case-insensitive).
- Unknown keys are ignored.
- Missing file → all defaults are used, no error.
- `TEST_ENV=1` bakes a banner into every recorded video:
  ```
  TEST BUILD v<APP_VERSION> — Not for production
  This banner is removed in release builds.
  ```

---

## Output files and folders

### Where recordings go

By default, recordings are saved to:

```
C:\Users\<You>\Videos\screen_recording_YYYY-MM-DD_HH-MM-SS.mp4
```

You can override the path via the 📂 button before starting.

### Video specs (default)

| Property | Value |
|---|---|
| Container | MP4 |
| Codec | H.264 (`mp4v` fourcc) |
| Resolution | Native monitor resolution |
| Frame rate | 30 FPS (constant) |
| Audio | AAC 192 kbps, mono 44.1 kHz |
| Duration | Real elapsed time, pauses excluded |

### Temporary files

When audio is enabled, the app writes two temporary files (video and
audio) during recording, then merges them and deletes both. Locations:

```
%LOCALAPPDATA%\Temp\tmpXXXX.mp4
%LOCALAPPDATA%\Temp\tmpXXXX.wav
```

These are cleaned up automatically unless the app crashes mid-recording.

### Logs

```
<project>/logs/screen_recorder.log
```

Rotated: max 1 MB per file, 3 backups kept. Older files are named
`screen_recorder.log.1`, `.2`, `.3`.

---

## Architecture

### Project structure

```
screen_recorder/
├── main.py                    # entry point, installs excepthook
├── logger.py                  # central logging + .env helpers
├── requirements.txt
├── .env                       # local config (git-ignored)
├── .env.example               # template
├── .gitignore
├── README.md
├── DOCUMENTATION.md           # this file
├── assets/
│   └── icon.ico               # .exe icon
├── logs/                      # (git-ignored)
├── ui/
│   ├── __init__.py
│   ├── main_window.py         # main window, layout, actions
│   ├── overlay.py             # floating REC indicator / countdown
│   ├── screen_thumbnail.py    # clickable monitor preview card
│   ├── responsive_grid.py     # grid that reflows on resize
│   ├── theme.py               # colors + global QSS
│   └── icons.py               # inline SVG icons
└── recorder/
    ├── __init__.py
    ├── sources.py             # monitor enumeration (mss)
    ├── screen_recorder.py     # QThread: capture + encode + cursor + watermark
    ├── audio_devices.py       # microphone enumeration (sounddevice)
    ├── audio_recorder.py      # thread: capture mic to WAV
    └── muxer.py               # ffmpeg wrapper (imageio-ffmpeg)
```

### Layered design

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│              setup_logging() · apply_theme()                │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    ui/main_window.py                        │
│         Orchestration · Signals · User interactions         │
└──┬────────────────────┬───────────────────────┬─────────────┘
   │                    │                       │
   │                    │                       │
┌──▼─────────┐  ┌───────▼──────────┐  ┌─────────▼──────────┐
│ ui/overlay │  │ recorder/screen  │  │ recorder/audio     │
│ REC circle │  │ ScreenRecorder   │  │ AudioRecorder      │
│ countdown  │  │ (QThread)        │  │ (Thread)           │
└────────────┘  └───────┬──────────┘  └─────────┬──────────┘
                        │                       │
                        │                       │
                ┌───────▼──────┐         ┌──────▼───────┐
                │ mss + cv2    │         │ sounddevice  │
                │ + win32 API  │         │ + wave       │
                └──────────────┘         └──────────────┘
                        │                       │
                        └───────────┬───────────┘
                                    │
                          ┌─────────▼──────────┐
                          │  recorder/muxer    │
                          │  imageio-ffmpeg    │
                          └────────────────────┘
```

### Threading model

- **Main thread**: Qt event loop, GUI updates, signals.
- **`ScreenRecorder` (QThread)**: capture + encode loop. Emits signals:
  `started_recording`, `stopped_recording`, `error_occurred`,
  `elapsed_time`.
- **`AudioRecorder` (Thread)**: sounddevice callback writes to a WAV file
  in a plain Python thread. No Qt signals — errors are polled after join.
- **`RecordingOverlay` (QWidget)**: lives on the main thread; uses two
  `QTimer` instances (blink + clock).

Cross-thread communication is signal-based for Qt, join-based for the
plain thread.

---

## How it works (deep dive)

### 1. Monitor enumeration (`recorder/sources.py`)

`mss.mss().monitors` returns a list:

```
[0] virtual screen (all monitors combined)
[1] primary monitor
[2] second monitor
...
```

We skip index 0 and produce one `CaptureSource` per physical monitor, with
`source_id = 1, 2, 3, ...`.

Each `CaptureSource.resolve_bbox()` returns the monitor's bounding box
in **physical pixels** at the time of the call. This is re-evaluated on
every frame, so if the user changes resolution mid-recording, we follow.

### 2. Screen capture (`recorder/screen_recorder.py`)

The main loop:

```python
while not stop:
    # Pause handling: skip frames while paused
    if paused: sleep(0.05); continue

    # Frame pacing: absolute schedule
    elapsed = now - start_time - total_paused
    target_frames = int(elapsed * fps)
    if frames_written >= target_frames:
        sleep(0.001); continue

    # Capture
    bbox = source.resolve_bbox()
    frame = cv2.cvtColor(np.array(sct.grab(bbox)), BGRA2BGR)

    # Optional: resize if window changed
    # Optional: draw cursor
    # Optional: draw test watermark

    # Catch-up: write frame N times if we fell behind
    catch_up = min(target_frames - frames_written, 5)
    for _ in range(catch_up):
        writer.write(frame)
        frames_written += 1
```

**Why the catch-up loop matters:** `cv2.VideoWriter` assumes the N-th frame
it receives plays at N/FPS. If the machine can't keep up at 30 FPS, we
duplicate the last frame so the total duration still matches wall-clock
time. This is what guarantees that a 19-second recording produces a
19-second video, even on slow machines.

### 3. Mouse cursor rendering

`mss` uses BitBlt on Windows, which excludes the cursor. We draw it
manually:

1. `GetCursorInfo()` → screen position + cursor handle.
2. `GetIconInfo()` → color bitmap + mask bitmap + hotspot.
3. `GetDIBits()` → raw BGRA pixels.
4. Alpha-blend the cursor onto the frame at the right screen-local
   coordinates.

Cursors are cached per handle (with a 32-entry cap) for performance.

### 4. Screen indicator (`ui/overlay.py`)

A frameless, always-on-top, click-through QWidget shows the REC circle.
Its HWND is marked with:

```python
SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
```

so Windows excludes it from screen capture. This requires Windows 10
version 2004 or later.

The overlay's position is computed from the **target screen's** logical
rectangle, matched to a `QScreen` by device name (`\\.\DISPLAY1`,
`\\.\DISPLAY2`). This is done to avoid ambiguity on multi-monitor setups
with identical resolutions.

### 5. Audio recording (`recorder/audio_recorder.py`)

`sounddevice.InputStream` opens the chosen device and calls our callback
every `blocksize=1024` frames. The callback writes raw int16 samples to a
`wave.Wave_write` object. On stop, the stream closes and the WAV is
finalized.

### 6. Muxing (`recorder/muxer.py`)

Uses the FFmpeg binary bundled with `imageio-ffmpeg`:

```
ffmpeg -y
    -i video.mp4
    -i audio.wav
    -c:v copy         # no re-encode
    -c:a aac -b:a 192k
    -shortest         # trim to the shortest stream
    -movflags +faststart
    output.mp4
```

The video stream is copied bit-for-bit (no quality loss, instant). Only
the audio is encoded.

### 7. Test watermark

If `TEST_ENV=1`, each frame gets a two-line banner baked into its bottom
edge. This is drawn **before** the frame is written, so it is part of the
video file. Unlike the REC overlay, the test watermark is not excluded
from capture.

---

## Logging

### Where

- Console (if `LOG_TO_CONSOLE=1`)
- File: `<project>/logs/screen_recorder.log`

### Format

```
HH:MM:SS | LEVEL   | module                    | message
```

Example:

```
19:40:49 | INFO    | ui.main_window            | Selected source: Screen 2  (1920×1080)
19:40:52 | INFO    | ui.overlay                | Overlay target matched by NAME: '\\.\DISPLAY2'
19:40:52 | INFO    | recorder.screen_recorder  | Recording paused
19:41:01 | INFO    | ui.main_window            | Video recording stopped → ...
```

### Controlling verbosity

- `LOGGING_ENABLED=0` → installs a `NullHandler`, no log output.
- `LOG_LEVEL=INFO` → only INFO and above.
- `LOG_LEVEL=DEBUG` → everything including per-device enumeration.

### Uncaught exceptions

`main.py` installs a global `sys.excepthook` that logs any uncaught
exception with full traceback before the default handler runs. This means
crash reasons always end up in the log file.

---

## Building a standalone `.exe`

### 1. Install PyInstaller in the venv

```bash
pip install pyinstaller
```

### 2. Create the icon

PyInstaller needs `.ico`, not `.png`:

```python
from PIL import Image
img = Image.open("assets/icon.png")
img.save("assets/icon.ico", sizes=[(16,16), (32,32), (48,48), (256,256)])
```

### 3. Use the provided `.spec`

The project ships with a `ScreenRecorder.spec` that includes all required
hidden imports and data files (`sounddevice` DLLs, `imageio-ffmpeg`
binary, `.env`, icon).

### 4. Build — always via `python -m PyInstaller`

**Do not call `pyinstaller` directly** if you have a global Python install
in your PATH (common with Laragon, Anaconda, etc.). Use:

```bash
python -m PyInstaller --clean ScreenRecorder.spec
```

Output: `dist/ScreenRecorder.exe`.

### 5. What to ship

```
dist/
├── ScreenRecorder.exe     # ~80-150 MB
└── .env                   # optional, editable by the user
```

The `.env` is looked up **next to the `.exe`** first, then falls back to
the one embedded at build time. Users can override settings without
recompiling.

### 6. Common build issues

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'sounddevice'` at build | Running `pyinstaller` from a different Python | Use `python -m PyInstaller` from the venv |
| Same error at runtime | `sounddevice.py` + `_sounddevice_data/` not embedded | `datas` must include both |
| `ffmpeg not found` | `imageio-ffmpeg` binary not embedded | Add `imageio_ffmpeg` folder to `datas` |
| `.exe` fails silently | `console=False` hides the traceback | Build with `console=True` for debugging |
| Icon not updated in Explorer | Windows caches icons | Rename the `.exe` or run `ie4uinit.exe -show` |

---

## Troubleshooting

### The app crashes on start with `TypeError: unsupported operand type(s) for |`

Cause: `X | None` used on a PySide6 type (`QPixmap`, `QWidget`, `QTimer`,
etc.). Shiboken types don't support PEP 604.

Fix: use `Optional[X]` from `typing` for all PySide6 types. This is a
permanent rule of the project.

### `OverflowError: int too long to convert` in the cursor code

Cause: passing a 64-bit Windows handle to a ctypes function declared
without explicit argtypes.

Fix: all Win32 functions must set `.argtypes` with `wintypes.HANDLE` (a
`c_void_p`) — never rely on the default `c_int`.

### The recorded video is too fast or too short

Cause: the capture pipeline runs slower than the target FPS.

Fix: this was addressed by the catch-up loop. If it still happens, verify
that `frames_written` is being incremented inside the loop and that the
written frame count matches `elapsed * fps` in the logs.

### The recording indicator appears in the video

Cause: `SetWindowDisplayAffinity` failed with error 8 (usually too early).

Fix: the call happens after `show()` + `QTimer.singleShot(0, ...)`. On
Windows builds older than 10.0.2004, the call fails with a different
error — the overlay will then be visible in the video.

### Audio error "Error querying device -1"

Cause: PortAudio was not initialized before opening the stream.

Fix: `_ensure_portaudio_initialized()` calls `sd.query_devices()` at
import time. The mic index is always passed explicitly to
`InputStream(device=...)`.

### "No QScreen matched physical size ..." in the logs

Cause: the overlay couldn't map the mss monitor to a Qt `QScreen` by
size.

Fix: the current implementation matches by **device name**
(`\\.\DISPLAY1`) using `EnumDisplayMonitors`, which is immune to DPI and
resolution quirks.

### `.env` not picked up at runtime

Cause: the working directory changed, or `.env` is not next to the `.exe`.

Fix: `_candidate_env_paths()` in `logger.py` looks next to the `.exe`
first, then inside `sys._MEIPASS`. Place your `.env` next to the `.exe`.

---

## Development

### Style rules

- Use `Optional[X]` (never `X | None`) for any PySide6 type.
- Log with `log = logging.getLogger(__name__)` at module top.
- Don't use `print()` — everything goes through `logging`.
- No inline magic numbers in the UI: colors come from `ui/theme.py`.
- All Win32 ctypes calls must set `.argtypes` explicitly.

### Running from source

```bash
.venv\Scripts\activate
python main.py
```

### Adding a new monitor option

1. Add the widget in `ui/main_window.py` inside `_build_controls_panel`.
2. Wire its signal to a handler on `MainWindow`.
3. Pass the value to `ScreenRecorder(...)` in `_start_recording_now`.
4. Document the new option in this file.

### Adding a new `.env` key

1. Add the key in `.env` and `.env.example`.
2. Add a getter in `logger.py` (e.g. `get_my_key()`).
3. Use it where needed.
4. Update the configuration table in this file.

### Adding a new screen-capture backend

The `ScreenRecorder` currently uses `mss`. To add a GPU-based backend:

1. Define an abstraction (`capture_bbox(bbox) -> ndarray`).
2. Implement a `WgcCapturer` (Windows Graphics Capture) variant.
3. Select the backend at construction time based on a new `.env` key or a
   UI toggle.

### Debugging tips

- Set `LOG_LEVEL=DEBUG` to see per-device enumeration and overlay matching.
- Build with `console=True` temporarily to see runtime tracebacks.
- Use `pyi-archive_viewer dist/ScreenRecorder.exe` to verify what's inside
  the executable.

---

## Roadmap

See `ROADMAP.md` for the detailed plan. Short version:

- **v9** — robustness: overlay targeting, sync, tests, build script.
- **v10** — UX: global hotkeys, system tray, notifications, preview.
- **v11** — capture quality: FPS, resolution, codec, region selection.
- **v12** — audio: system loopback, noise reduction, VU meter.
- **v13** — editing: trim, watermark, subtitles, history.
- **v14** — sharing: upload, CLI, API.
- **v15** — platforms: macOS, Linux, auto-update, code signing.
- **v16** — advanced: streaming, scheduling, plugins.

---

## License

*To be defined by the project owner. Recommend MIT for internal tools,
Apache 2.0 for public projects.*