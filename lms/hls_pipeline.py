"""
FFmpeg-based HLS pipeline: RTSP → .m3u8 + .ts segments.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_RESTART_DELAY = 3.0


class HLSPipeline:
    def __init__(
        self,
        stream_id: str,
        rtsp_url: str,
        output_dir: Path,
        segment_duration: int = 1,
        playlist_size: int = 8,
        video_codec: str = "copy",
        preset: str = "ultrafast",
        fps: int = 30,
        video_bitrate: str = "1500k",
    ) -> None:
        self._stream_id = stream_id
        self._rtsp_url = rtsp_url
        self._output_dir = output_dir
        self._segment_duration = segment_duration
        self._playlist_size = playlist_size
        self._video_codec = video_codec
        self._preset = preset
        self._fps = fps
        self._video_bitrate = video_bitrate
        self._process: subprocess.Popen[bytes] | None = None
        self._stop_event = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._watchdog_last_report: float = 0.0
        self._stall_count: int = 0
        self._restart_count: int = 0

    def start(self) -> None:
        if self._process and self._process.poll() is None:
            return

        self._output_dir.mkdir(parents=True, exist_ok=True)
        for stale in self._output_dir.iterdir():
            if stale.suffix in (".ts", ".m3u8"):
                stale.unlink(missing_ok=True)
        self._stop_event.clear()
        self._spawn()

        self._watchdog_thread = threading.Thread(
            target=self._watchdog, daemon=True, name=f"hls-watchdog-{self._stream_id}"
        )
        self._watchdog_thread.start()
        logger.info("HLS pipeline started for stream %s", self._stream_id)

    def request_stop(self) -> None:
        self._stop_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=10)
        logger.info("HLS pipeline stopped for stream %s", self._stream_id)

    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def last_segment_time(self) -> float | None:
        """Return mtime of the newest .ts segment, or None if no segments exist."""
        segments = list(self._output_dir.glob("*.ts"))
        if not segments:
            return None
        return max(s.stat().st_mtime for s in segments)

    def _build_ffmpeg_cmd(self) -> list[str]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg not found on PATH")

        segment_pattern = str(self._output_dir / "seg_%05d.ts")
        playlist_path = str(self._output_dir / "stream.m3u8")

        cmd = [
            ffmpeg,
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-rtsp_transport", "tcp",
            "-i", self._rtsp_url,
        ]

        if self._video_codec == "copy":
            cmd += ["-c:v", "copy"]
        else:
            gop_size = self._segment_duration * self._fps
            cmd += [
                "-vf", "scale=1280:720",
                "-r", str(self._fps),
                "-c:v", self._video_codec,
                "-preset", self._preset,
                "-tune", "zerolatency",
                "-b:v", self._video_bitrate,
                "-maxrate", self._video_bitrate,
                "-bufsize", self._video_bitrate,
                "-g", str(gop_size),
                "-keyint_min", str(gop_size),
                "-sc_threshold", "0",
                "-force_key_frames", f"expr:gte(t,n_forced*{self._segment_duration})",
            ]

        cmd += [
            "-an",
            "-f", "hls",
            "-hls_time", str(self._segment_duration),
            "-hls_list_size", str(self._playlist_size),
            "-hls_flags", "append_list+delete_segments",
            "-hls_segment_filename", segment_pattern,
            playlist_path,
        ]
        return cmd

    def _spawn(self) -> None:
        cmd = self._build_ffmpeg_cmd()
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, daemon=True, name=f"ffmpeg-stderr-{self._stream_id}"
        )
        self._stderr_thread.start()

    def _read_stderr(self) -> None:
        proc = self._process
        if not proc or not proc.stderr:
            return
        for raw_line in proc.stderr:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            if any(k in line.lower() for k in ("error", "dropping", "timeout", "overread")):
                logger.warning("[ffmpeg:%s] %s", self._stream_id, line)
            else:
                logger.debug("[ffmpeg:%s] %s", self._stream_id, line)

    def _watchdog(self) -> None:
        from lms.reconnect import reconnect_with_backoff

        while not self._stop_event.is_set():
            if self._process:
                self._wait_or_detect_stall()
            if self._stop_event.is_set():
                break

            rc = self._process.returncode if self._process else "?"
            logger.warning(
                "FFmpeg exited for stream %s (rc=%s) — reconnecting",
                self._stream_id, rc,
            )

            reconnect_with_backoff(
                stream_id=self._stream_id,
                attempt_fn=self._try_restart,
                stop_fn=self._stop_event.is_set,
                on_failure=lambda: logger.critical(
                    "PERMANENT FAILURE: stream %s exhausted all reconnect attempts. "
                    "Manual intervention required.", self._stream_id
                ),
            )

    def _wait_or_detect_stall(self) -> None:
        _STALL_TIMEOUT = 30
        last_seg = self.last_segment_time
        stall_since: float | None = None

        while not self._stop_event.is_set():
            try:
                self._process.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                pass

            current_seg = self.last_segment_time
            if current_seg != last_seg:
                last_seg = current_seg
                stall_since = None
            else:
                if stall_since is None:
                    stall_since = time.time()
                elif time.time() - stall_since > _STALL_TIMEOUT:
                    self._stall_count += 1
                    logger.warning(
                        "FFmpeg stalled for stream %s (no new segment in %ds) — killing",
                        self._stream_id, _STALL_TIMEOUT,
                    )
                    self._process.kill()
                    self._process.wait(timeout=5)
                    return

            now = time.time()
            if now - self._watchdog_last_report > 300:
                self._watchdog_last_report = now
                logger.info(
                    "[watchdog] stream=%s ffmpeg_pid=%d stalls=%d restarts=%d",
                    self._stream_id,
                    self._process.pid if self._process else 0,
                    self._stall_count,
                    self._restart_count,
                )

    def _try_restart(self) -> bool:
        try:
            self._spawn()
            try:
                self._process.wait(timeout=2)
                return False
            except subprocess.TimeoutExpired:
                self._restart_count += 1
                return True
        except Exception:
            logger.exception("Restart failed for stream %s", self._stream_id)
            return False
