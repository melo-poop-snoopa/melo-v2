"""
Privacy filter: detects humans in RTSP stream frames.

Opens a sub-stream RTSP connection via PyAV, decodes at 2 fps, and runs
YOLOv8-nano inference on class 0 (person). Sets a per-instance flag that
the heartbeat manager writes to Supabase as ``privacy_active``.
"""
from __future__ import annotations

import gc
import logging
import threading
import time

logger = logging.getLogger(__name__)

_DETECT_FPS = 2
_FRAME_INTERVAL = 1.0 / _DETECT_FPS
_ACTIVATION_FRAMES = 3                  # ~1.5s of sustained detection before activating
_DEACTIVATION_FRAMES = _DETECT_FPS * 25  # counter ceiling; clears after this many missed frames
_CONTAINER_RESTART_INTERVAL = 300  # reopen RTSP every 5min to flush buffers and break decode hangs
_GC_EVERY_N_FRAMES = 500


class PrivacyFilter:
    def __init__(
        self,
        stream_id: str,
        rtsp_url: str,
        confidence_threshold: float = 0.39,
    ) -> None:
        self._stream_id = stream_id
        self._rtsp_url = rtsp_url
        self._confidence_threshold = confidence_threshold
        self._human_detected = False
        self._consecutive_detections = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = None
        self._debug_frames_saved = False

    def start(self) -> None:
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
            options={
                "rtsp_transport": "tcp",
                "stimeout": "5000000",
                "timeout": "10000000",
            },
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
            container_opened_at = time.monotonic()

            for frame in container.decode(video=0):
                if self._stop_event.is_set():
                    break

                if time.monotonic() - container_opened_at > _CONTAINER_RESTART_INTERVAL:
                    logger.info("Stream %s: restarting RTSP container to reclaim memory", self._stream_id)
                    break

                now = time.monotonic()
                if now < next_at:
                    continue
                next_at = now + _FRAME_INTERVAL

                frame_count += 1
                img = frame.to_ndarray(format="rgb24")

                if frame_count <= 3 and not self._debug_frames_saved:
                    logger.info(
                        "Stream %s: frame #%d shape=%s mean_pixel=%.1f",
                        self._stream_id, frame_count, img.shape, img.mean(),
                    )
                    try:
                        from PIL import Image
                        debug_path = f"/tmp/melo-debug-{self._stream_id[:8]}-f{frame_count}.jpg"
                        Image.fromarray(img).save(debug_path, quality=85)
                        logger.info("Saved debug frame to %s", debug_path)
                    except Exception:
                        logger.exception("Failed to save debug frame")
                    if frame_count == 3:
                        self._debug_frames_saved = True

                results = self._model(img, classes=[0], conf=0.10, verbose=False)

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

                del results
                del img
                if frame_count % _GC_EVERY_N_FRAMES == 0:
                    gc.collect()
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
