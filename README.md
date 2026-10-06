# Screen Recorder (v3)

A minimal desktop app to record a **monitor or window** to MP4, optionally
with **microphone audio**.

## Features

- 🖥️ Pick any **monitor** or visible **window**
- 🎙️ Optional **microphone** recording (checkbox)
- 🎥 30 FPS MP4 output
- ⏱️ Live elapsed-time counter
- 🔄 **Refresh** button to re-scan sources
- 🧵 Non-blocking UI
- ✅ Clear status: Ready / Recording… / Merging… / Recording stopped / Error

## Requirements

- Python 3.11+
- Windows 10/11 (window enumeration uses `pywin32`)

## Installation

```bash
cd screen_recorder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

1. Pick a **Source**.
2. Check **Show mouse cursor** if desired (on by default).
3. Check **Record audio (microphone)** if you want sound.
4. Click **Start Recording**.
5. Click **Stop Recording** — the file is saved.

## How audio works

1. When you click **Start Recording**, two streams start in parallel:
   - The video thread (`ScreenRecorder`) writes to a temporary MP4.
   - The audio thread (`AudioRecorder`) writes the microphone to a WAV.
2. When you click **Stop**, both stop, then FFmpeg merges them into the final
   MP4 (`-c:v copy -c:a aac -shortest`), so the video stream is **not
   re-encoded** — the merge takes well under a second.
3. Temporary files are deleted.

FFmpeg is provided by **`imageio-ffmpeg`**, which bundles a static binary —
no system install needed.

If you record without the audio checkbox, the video is written directly to
the target path (no temp file, no merge step).

## Building a standalone Windows `.exe`

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name ScreenRecorder ^
    --hidden-import=win32gui ^
    --hidden-import=win32con ^
    --collect-binaries=imageio_ffmpeg ^
    --collect-data=imageio_ffmpeg ^
    main.py
```

The result is `dist/ScreenRecorder.exe`.

> **Note :** `--collect-binaries` and `--collect-data` for `imageio_ffmpeg`
> are **required** — otherwise the bundled FFmpeg binary won't be included
> and audio merging will fail at runtime.

## MVP Scope (intentionally excluded)

No webcam, region selection, multi-monitor stitching, system-audio capture,
hotkeys, streaming, editing, or cloud upload. Only **microphone** audio is
supported.

## Logs

The app writes a rolling log file to:

```
screen_recorder/logs/screen_recorder.log
```

(up to 3 rotated files × 1 MB each). Attach this file when reporting a bug.

## Microphone selection

1. Check **Record audio**.
2. The **Microphone** dropdown becomes active and lists every input device
   reported by the OS, prefixed by its host API (MME / WASAPI / DirectSound).
3. The system default is preselected. Use **↻** to re-scan after plugging in a
   new device.

If no microphone is detected, the checkbox is disabled and the log records
the reason.

## Troubleshooting audio

| Message | Fix |
|---|---|
| `Error querying device -1` | Fixed in this version — the app now initializes PortAudio at startup and passes an explicit device index. |
| `No microphone detected` | Plug in a microphone, then click **↻**. Check Windows **Settings → Privacy → Microphone** if it still doesn't appear. |
| `Invalid audio device index` | Device was unplugged between selection and start. Click **↻** and pick again. |
| Audio out of sync with video | Use a shorter recording; `-shortest` trims to the shorter stream. |

## Recording indicator (v4)

While recording, a small dark circle can be shown on screen with:
- a blinking red REC dot,
- the elapsed time (`HH:MM:SS`).

**Options** (in the main window):
- ☑️ **Show recording indicator** — enable/disable the overlay.
- **Indicator position** — `top-left`, `top-right`, `bottom-left`, `bottom-right`.

### It does not appear in the video

The overlay window is marked with the Windows API
`SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`, so `mss`/BitBlt ignores it
during capture. The indicator stays visible for you while recording but is
**absent from the final MP4**.

> **Requirement:** Windows 10 version 2004 (May 2020) or later.
> On older builds the API fails and a warning is written to the log — in that
> case the overlay *may* be visible in the video.

The overlay is click-through: it never steals focus or blocks mouse input.