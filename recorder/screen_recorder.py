"""Screen recording worker.

Captures a chosen monitor using `mss` and writes frames to
an MP4 file using OpenCV's VideoWriter. Runs inside a QThread so the GUI stays
responsive.

Frame pacing:
    Frame n is captured at approximately `start_time + n/fps`. Because
    VideoWriter assumes the n-th frame it receives plays at n/fps, the output
    file duration is exactly `frames_written / fps`, matching real elapsed
    time even if the machine occasionally falls behind. We never drop frames
    — we just capture late (or duplicate frames when very late).

Pause / Resume:
    A `_pause_event` (threading.Event) stops the capture loop without
    stopping the thread. While paused, `_total_paused` accumulates the paused
    wall-clock time, which is subtracted from `elapsed`, so the file duration
    stays correct and the timer displayed to the user pauses too.

Mouse cursor:
    mss uses BitBlt which excludes the cursor. We draw it manually. All
    Windows API calls are bound with explicit 64-bit-safe signatures to
    avoid "int too long to convert" OverflowError on 64-bit handles.
"""

import ctypes
import logging
import threading
import time
from ctypes import wintypes

import cv2
import mss
import numpy as np
from PySide6.QtCore import QThread, Signal

from .sources import CaptureSource

log = logging.getLogger(__name__)


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
# Test watermark
# --------------------------------------------------------------------------- #
def _draw_test_watermark(frame: np.ndarray) -> None:
    """Bake a semi-transparent "TEST" banner at the bottom of the frame.

    The banner is drawn in-place. Font size, padding and margins scale with
    the frame width so the result looks consistent on any resolution.
    """
    h, w = frame.shape[:2]

    # Sizes relative to the frame width — clamp for very small/large frames
    font_scale = max(0.5, min(1.4, w / 1400.0))
    thickness = max(1, int(round(font_scale * 2)))
    margin = max(12, int(w * 0.02))
    pad_x = max(12, int(w * 0.015))
    pad_y = max(8,  int(h * 0.012))

    text = "TEST BUILD — Production version will not show this banner"

    # Measure text size to size the banner
    (text_w, text_h), baseline = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )

    banner_w = text_w + pad_x * 2
    banner_h = text_h + baseline + pad_y * 2

    x1 = margin
    y1 = h - margin - banner_h
    x2 = x1 + banner_w
    y2 = y1 + banner_h

    # Clamp inside the frame
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(w, x2)
    y2 = min(h, y2)

    # Semi-transparent black banner via alpha blend on the ROI
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 0), thickness=-1)
    alpha = 0.55
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # Yellow-ish text for high visibility
    text_color = (0, 220, 255)  # BGR → yellow
    text_x = x1 + pad_x
    text_y = y2 - pad_y - baseline // 2
    cv2.putText(
        frame,
        text,
        (text_x, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        text_color,
        thickness,
        cv2.LINE_AA,
    )

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
        test_watermark: bool = False,
    ):
        super().__init__()
        self.output_path = output_path
        self.source = source
        self.fps = fps
        self.draw_cursor = draw_cursor
        self.test_watermark = test_watermark

        # --- v5 : pause support ---
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()   # set = paused
        self._total_paused = 0.0                # accumulated pause seconds
        self._pause_started_at = 0.0            # perf_counter when pause began

    # ------------------------------------------------------------------ API --
    def stop(self) -> None:
        """Request the recording loop to stop."""
        self._stop_event.set()

    def pause(self) -> None:
        """Pause the recording (idempotent)."""
        if self._pause_event.is_set():
            return
        self._pause_started_at = time.perf_counter()
        self._pause_event.set()
        log.info("Recording paused")

    def resume(self) -> None:
        """Resume from pause (idempotent)."""
        if not self._pause_event.is_set():
            return
        self._total_paused += time.perf_counter() - self._pause_started_at
        self._pause_event.clear()
        log.info("Recording resumed (total paused: %.2fs)", self._total_paused)

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

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

            start_time = time.perf_counter()
            last_emit = start_time
            frames_written = 0

            with mss.mss() as sct:
                while not self._stop_event.is_set():
                    # --- Pause handling --------------------------------------
                    if self._pause_event.is_set():
                        # Small sleeps so stop() stays responsive
                        time.sleep(0.05)
                        continue

                    # Effective elapsed time = wall clock − paused time
                    now = time.perf_counter()
                    elapsed = now - start_time - self._total_paused
                    target_frames = int(elapsed * self.fps)

                    # If we are ahead of schedule, wait
                    if frames_written >= target_frames:
                        time.sleep(0.001)
                        continue

                    # --- Capture one frame -----------------------------------
                    bbox = self.source.resolve_bbox()
                    if bbox is None:
                        raise RuntimeError(
                            f"Monitor is no longer available: {self.source.label}"
                        )

                    frame = np.array(sct.grab(bbox))
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    fh, fw = frame.shape[:2]
                    if (fw, fh) != (width, height):
                        frame = cv2.resize(frame, (width, height))

                    if cursor is not None:
                        cursor.draw(frame, bbox["left"], bbox["top"])

                    if self.test_watermark:
                        _draw_test_watermark(frame)

                    # --- Catch-up: write the frame enough times --------------
                    catch_up = target_frames - frames_written
                    catch_up = min(catch_up, 5)   # safety cap

                    for _ in range(catch_up):
                        writer.write(frame)
                        frames_written += 1

                    # --- Elapsed signal (≈1 Hz) ------------------------------
                    now = time.perf_counter()
                    if now - last_emit >= 1.0:
                        self.elapsed_time.emit(elapsed)
                        last_emit = now

        except Exception as exc:  # noqa: BLE001
            log.exception("Screen recorder thread failed")
            self.error_occurred.emit(str(exc))
        finally:
            if writer is not None:
                writer.release()
            self.stopped_recording.emit(self.output_path)