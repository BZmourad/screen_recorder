"""Screen recording worker.

Captures a chosen source (monitor or window) using `mss` and writes frames to
an MP4 file using OpenCV's VideoWriter. Runs inside a QThread so the GUI stays
responsive.

Frame pacing:
    We drive capture by FRAME INDEX. Frame n is captured at approximately
    `start_time + n/fps`. Because VideoWriter assumes the n-th frame it
    receives plays at n/fps, the output file duration is exactly
    `frames_written / fps`, matching real elapsed time even if the machine
    occasionally falls behind. We never drop frames — we just capture late.

Mouse cursor:
    mss uses BitBlt which excludes the cursor. We draw it manually. All
    Windows API calls are bound with explicit 64-bit-safe signatures to
    avoid "int too long to convert" OverflowError on 64-bit handles.
"""

import ctypes
import threading
import time
from ctypes import wintypes

import cv2
import mss
import numpy as np
from PySide6.QtCore import QThread, Signal

from .sources import CaptureSource


# --------------------------------------------------------------------------- #
# Windows API bindings (64-bit safe)
# --------------------------------------------------------------------------- #
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", _POINT),
    ]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class _BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# --- Explicit function signatures (the key fix for OverflowError) ---------- #
_user32.GetCursorInfo.argtypes = [ctypes.POINTER(_CURSORINFO)]
_user32.GetCursorInfo.restype = wintypes.BOOL

_user32.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ICONINFO)]
_user32.GetIconInfo.restype = wintypes.BOOL

_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC

_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int

_gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
_gdi32.GetObjectW.restype = ctypes.c_int

_gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.POINTER(_BITMAPINFO),
    wintypes.UINT,
]
_gdi32.GetDIBits.restype = ctypes.c_int

_gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
_gdi32.DeleteObject.restype = wintypes.BOOL


# --------------------------------------------------------------------------- #
# Cursor renderer
# --------------------------------------------------------------------------- #
class CursorRenderer:
    """Draws the Windows mouse cursor onto a BGR frame, in place."""

    CURSOR_SHOWING = 0x00000001
    DI_NORMAL = 0x0003
    DIB_RGB_COLORS = 0

    def __init__(self) -> None:
        self._cache: dict[int, np.ndarray] = {}
        self._hotspots: dict[int, tuple[int, int]] = {}

    def draw(self, frame: np.ndarray, origin_x: int, origin_y: int) -> None:
        ci = _CURSORINFO()
        ci.cbSize = ctypes.sizeof(_CURSORINFO)

        if not _user32.GetCursorInfo(ctypes.byref(ci)):
            return
        if not (ci.flags & self.CURSOR_SHOWING):
            return
        if not ci.hCursor:
            return

        # HANDLE is not directly hashable as int in some ctypes setups —
        # normalize safely.
        hcursor = int(ci.hCursor) if not isinstance(ci.hCursor, int) else ci.hCursor
        if hcursor == 0:
            return

        cached = self._get_cursor(hcursor)
        if cached is None:
            return
        cursor_img, (hot_x, hot_y) = cached

        # Screen-space → frame-local coordinates
        cx = ci.ptScreenPos.x - origin_x - hot_x
        cy = ci.ptScreenPos.y - origin_y - hot_y

        ch, cw = cursor_img.shape[:2]
        fh, fw = frame.shape[:2]

        x0, y0 = max(cx, 0), max(cy, 0)
        x1, y1 = min(cx + cw, fw), min(cy + ch, fh)
        if x1 <= x0 or y1 <= y0:
            return

        sx0, sy0 = x0 - cx, y0 - cy
        sx1, sy1 = sx0 + (x1 - x0), sy0 + (y1 - y0)
        cursor_crop = cursor_img[sy0:sy1, sx0:sx1]
        roi = frame[y0:y1, x0:x1]

        alpha = cursor_crop[:, :, 3:4].astype(np.float32) / 255.0
        bgr = cursor_crop[:, :, :3].astype(np.float32)
        roi[:] = (bgr * alpha + roi.astype(np.float32) * (1.0 - alpha)).astype(
            np.uint8
        )

    # --------------------------------------------------------------- private
    def _get_cursor(self, hcursor: int):
        if hcursor in self._cache:
            return self._cache[hcursor], self._hotspots[hcursor]

        result = self._read_cursor(hcursor)
        if result is None:
            return None

        img, hotspot = result
        if len(self._cache) > 32:
            self._cache.clear()
            self._hotspots.clear()
        self._cache[hcursor] = img
        self._hotspots[hcursor] = hotspot
        return img, hotspot

    def _read_cursor(self, hcursor: int):
        ii = _ICONINFO()
        if not _user32.GetIconInfo(hcursor, ctypes.byref(ii)):
            return None

        try:
            bmp = _BITMAP()
            if _gdi32.GetObjectW(
                ii.hbmColor, ctypes.sizeof(_BITMAP), ctypes.byref(bmp)
            ) == 0:
                return None

            width, height = bmp.bmWidth, bmp.bmHeight
            if width <= 0 or height <= 0:
                return None

            bmi = _BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # top-down
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB

            hdc = _user32.GetDC(None)
            try:
                # --- color bitmap ---
                buf = (ctypes.c_ubyte * (width * height * 4))()
                _gdi32.GetDIBits(
                    hdc,
                    ii.hbmColor,
                    0,
                    height,
                    ctypes.byref(buf),
                    ctypes.byref(bmi),
                    self.DIB_RGB_COLORS,
                )
                bgra = np.frombuffer(buf, dtype=np.uint8).reshape(
                    (height, width, 4)
                ).copy()

                # If alpha channel is entirely zero, the cursor uses an
                # AND-mask instead. Rebuild alpha from the mask.
                if bgra[:, :, 3].max() == 0 and ii.hbmMask:
                    mask_buf = (ctypes.c_ubyte * (width * height * 4))()
                    _gdi32.GetDIBits(
                        hdc,
                        ii.hbmMask,
                        0,
                        height,
                        ctypes.byref(mask_buf),
                        ctypes.byref(bmi),
                        self.DIB_RGB_COLORS,
                    )
                    mask = np.frombuffer(mask_buf, dtype=np.uint8).reshape(
                        (height, width, 4)
                    )
                    bgra[:, :, 3] = np.where(
                        mask[:, :, 0] > 0, 0, 255
                    ).astype(np.uint8)
            finally:
                _user32.ReleaseDC(None, hdc)

            return bgra, (int(ii.xHotspot), int(ii.yHotspot))
        finally:
            if ii.hbmColor:
                _gdi32.DeleteObject(ii.hbmColor)
            if ii.hbmMask:
                _gdi32.DeleteObject(ii.hbmMask)


# --------------------------------------------------------------------------- #
# Recorder
# --------------------------------------------------------------------------- #
class ScreenRecorder(QThread):
    """Background thread that captures a source and encodes it to MP4."""

    started_recording = Signal(str)
    stopped_recording = Signal(str)
    error_occurred = Signal(str)
    elapsed_time = Signal(float)

    def __init__(
        self,
        output_path: str,
        source: CaptureSource,
        fps: int = 30,
        draw_cursor: bool = True,
    ):
        super().__init__()
        self.output_path = output_path
        self.source = source
        self.fps = fps
        self.draw_cursor = draw_cursor
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------------ run --
        # ------------------------------------------------------------------ run --
    def run(self) -> None:
        writer = None
        try:
            bbox = self.source.resolve_bbox()
            if bbox is None:
                raise RuntimeError(f"Source is not available: {self.source.label}")

            width, height = bbox["width"], bbox["height"]

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(
                self.output_path, fourcc, self.fps, (width, height)
            )
            if not writer.isOpened():
                raise RuntimeError(
                    f"Could not open video writer for {self.output_path}"
                )

            cursor = CursorRenderer() if self.draw_cursor else None

            self.started_recording.emit(self.output_path)

            frame_interval = 1.0 / self.fps
            start_time = time.perf_counter()
            last_emit = start_time

            # Number of frames that SHOULD have been written by now,
            # based on wall-clock elapsed time. This is our master clock.
            frames_written = 0

            with mss.mss() as sct:
                while not self._stop_event.is_set():
                    elapsed = time.perf_counter() - start_time
                    target_frames = int(elapsed / self.fps_inv())  # = elapsed * fps

                    # If we are AHEAD of schedule (machine faster than 30 FPS),
                    # wait until it's time for the next frame.
                    if frames_written >= target_frames:
                        # Sleep a tiny amount to avoid busy-waiting
                        time.sleep(0.001)
                        continue

                    # --- Capture one frame -----------------------------------
                    bbox = self.source.resolve_bbox()
                    if bbox is None:
                        raise RuntimeError(
                            f"Source disappeared: {self.source.label}"
                        )

                    frame = np.array(sct.grab(bbox))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    fh, fw = frame.shape[:2]
                    if (fw, fh) != (width, height):
                        frame = cv2.resize(frame, (width, height))

                    if cursor is not None:
                        cursor.draw(frame, bbox["left"], bbox["top"])

                    # --- Write the frame enough times to catch up ------------
                    # We write the SAME frame `catch_up` times, where
                    # catch_up = target_frames - frames_written. This keeps the
                    # output file's duration == real elapsed time, no matter
                    # how slow the capture pipeline is.
                    catch_up = target_frames - frames_written
                    # Safety cap: never write more than 5 duplicate frames at
                    # once, in case of a huge stall (e.g. user dragged a window
                    # for 2 seconds and we had no chance to capture).
                    catch_up = min(catch_up, 5)

                    for _ in range(catch_up):
                        writer.write(frame)
                        frames_written += 1

                    # --- Elapsed signal (≈1 Hz) -----------------------------
                    now = time.perf_counter()
                    if now - last_emit >= 1.0:
                        self.elapsed_time.emit(now - start_time)
                        last_emit = now

        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))
        finally:
            if writer is not None:
                writer.release()
            self.stopped_recording.emit(self.output_path)

    def fps_inv(self) -> float:
        """1 / fps, i.e. seconds per frame."""
        return 1.0 / self.fps