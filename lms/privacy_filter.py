"""
Privacy filter: detects humans in RTSP stream frames and swaps HLS segments.

Opens a sub-stream RTSP connection via PyAV, decodes at 2 fps, and runs
YOLOv8-nano inference on class 0 (person). Sets a per-instance flag that
R2Uploader reads before each .ts upload. Pre-encodes a BRB .ts segment from
assets/brb.png at startup so the swap is latency-free.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DETECT_FPS = 2
_FRAME_INTERVAL = 1.0 / _DETECT_FPS
_ACTIVATION_FRAMES = _DETECT_FPS * 5   # 5 seconds of sustained detection before activating
_DEACTIVATION_FRAMES = _DETECT_FPS * 25  # counter ceiling; BRB clears after this many missed frames
_ASSETS_DIR = Path(__file__).parent.parent / "assets"


class PrivacyFilter:
    def __init__(
        self,
        stream_id: str,
        rtsp_url: str,
        confidence_threshold: float = 0.39,
        segment_duration: int = 4,
    ) -> None:
        self._stream_id = stream_id
        self._rtsp_url = rtsp_url
        self._confidence_threshold = confidence_threshold
        self._segment_duration = segment_duration
        self._human_detected = False
        self._consecutive_detections = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._brb_segment: bytes | None = None
        self._model = None

    def start(self) -> None:
        self._brb_segment = _encode_brb_segment(self._segment_duration)
        self._model = _load_model()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._detection_loop,
            daemon=True,
            name=f"privacy-{self._stream_id}",
        )
        self._thread.start()
        logger.info("PrivacyFilter started for stream %s", self._stream_id)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def is_human_detected(self) -> bool:
        with self._lock:
            return self._human_detected

    @property
    def brb_segment(self) -> bytes | None:
        return self._brb_segment

    def _detection_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._model is None:
                self._stop_event.wait(5)
                continue
            try:
                self._run_detection()
            except Exception:
                logger.exception("Detection error for stream %s — retrying in 5s", self._stream_id)
                self._stop_event.wait(5)

    def _run_detection(self) -> None:
        import av  # imported lazily so the module loads without av installed

        logger.info("Stream %s: opening RTSP for detection: %s", self._stream_id, self._rtsp_url)
        container = av.open(
            self._rtsp_url,
            options={"rtsp_transport": "tcp", "stimeout": "5000000"},
        )
        try:
            video = container.streams.video[0]
            logger.info(
                "Stream %s: RTSP opened, codec=%s, %dx%d",
                self._stream_id, video.codec_context.name,
                video.codec_context.width, video.codec_context.height,
            )

            frame_count = 0
            next_at = time.monotonic()
            for frame in container.decode(video=0):
                if self._stop_event.is_set():
                    break

                now = time.monotonic()
                if now < next_at:
                    continue
                next_at = now + _FRAME_INTERVAL

                frame_count += 1
                img = frame.to_ndarray(format="rgb24")
                results = self._model(img, classes=[0], conf=0.15, verbose=False)

                detected = any(
                    float(box.conf) >= self._confidence_threshold
                    for r in results
                    for box in r.boxes
                )

                if detected:
                    self._consecutive_detections = min(
                        self._consecutive_detections + 1, _DEACTIVATION_FRAMES
                    )
                else:
                    self._consecutive_detections = max(
                        self._consecutive_detections - 1, 0
                    )

                if frame_count <= 3 or frame_count % 20 == 0:
                    confs = [
                        f"{float(box.conf):.2f}"
                        for r in results for box in r.boxes
                    ]
                    logger.info(
                        "Stream %s: frame #%d detected=%s confs=%s counter=%d (activate=%d ceil=%d)",
                        self._stream_id, frame_count, detected,
                        confs, self._consecutive_detections, _ACTIVATION_FRAMES, _DEACTIVATION_FRAMES,
                    )

                with self._lock:
                    if self._consecutive_detections >= _ACTIVATION_FRAMES:
                        if not self._human_detected:
                            logger.info("Stream %s: human_detected → True", self._stream_id)
                        self._human_detected = True
                    elif self._consecutive_detections == 0 and self._human_detected:
                        logger.info("Stream %s: human_detected → False", self._stream_id)
                        self._human_detected = False
        finally:
            container.close()


# ── Module-level helpers ───────────────────────────────────────────────────────

def _load_model():
    try:
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")
        logger.info("YOLOv8-nano model loaded")
        return model
    except Exception:
        logger.exception("Failed to load YOLOv8-nano — privacy filter will not run")
        return None


def _encode_brb_segment(segment_duration: int) -> bytes | None:
    brb_png = _ASSETS_DIR / "brb.png"
    if not brb_png.exists():
        _generate_brb_png(brb_png)

    with tempfile.NamedTemporaryFile(suffix=".ts", delete=False) as f:
        out_path = Path(f.name)

    try:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(brb_png),
            "-t", str(segment_duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "stillimage",
            "-an",
            "-f", "mpegts",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        if result.returncode != 0:
            logger.error("BRB segment encoding failed: %s", result.stderr.decode())
            return None
        data = out_path.read_bytes()
        logger.info("BRB segment pre-encoded (%d bytes)", len(data))
        return data
    except Exception:
        logger.exception("Failed to encode BRB segment")
        return None
    finally:
        out_path.unlink(missing_ok=True)


def _generate_brb_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1280, 720), color=(0x1A, 0x1A, 0x2E))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=72)
        except TypeError:
            font = ImageFont.load_default()
        text = "Be Right Back"
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (1280 - (bbox[2] - bbox[0])) // 2
        y = (720 - (bbox[3] - bbox[1])) // 2
        draw.text((x, y), text, fill="white", font=font)
        img.save(path)
        logger.info("Generated brb.png at %s", path)
    except Exception:
        logger.warning("Could not generate brb.png", exc_info=True)
