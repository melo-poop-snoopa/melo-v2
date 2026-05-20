# Melo v2 — 50-Hour Demo Reliability & Security Audit

**Date:** 2026-05-19
**Target:** Raspberry Pi 5 (8GB RAM, 128GB SD), 1 Bawofu camera, LOCAL_DEV=true
**Goal:** Investor/stakeholder proof — zero visible downtime for 50 continuous hours, fully unattended

---

## Critical Gaps Found & Fixes Applied

### P0: Would crash or exhaust resources within 50 hours

| # | Issue | File | Fix Applied |
|---|-------|------|-------------|
| 1 | **No log rotation** — `FileHandler` with no size limit; ~250-500 MB of logs over 50 hours, plus debug frames written to `/tmp` on every privacy filter restart (every 30 min) | `lms/main.py:101` | Switched to `RotatingFileHandler` (50 MB max, 3 backups). Debug frames now only saved on first container open, not every restart. |
| 2 | **`_uploaded` / `_lost_segments` sets grow unbounded** — every segment filename ever seen is kept in memory forever | `lms/r2_uploader.py:67-69` | `_lost_segments` now pruned of entries no longer on disk during cleanup. `_uploaded` was already partially pruned (line 329). |
| 3 | **Stderr thread leak on FFmpeg restart** — each `_spawn()` created a new thread without joining the old one; 100+ orphaned threads over 50 hours | `lms/hls_pipeline.py:143-153` | Old stderr thread is now joined (3s timeout) before spawning a new one. `stop()` also joins the stderr thread. |
| 4 | **Watchdog ignores stop during reconnect sleep** — `time.sleep(30)` in backoff loop can't be interrupted, causing the watchdog to keep running after `stop()` | `lms/reconnect.py:56` | Replaced `time.sleep()` with `stop_event.wait()` so the sleep is interruptible. Stop event is now passed through from the pipeline. |
| 5 | **Privacy filter hangs indefinitely** — `container.decode()` blocks forever if RTSP stream hangs; container restart interval (30 min) doesn't help since the check only runs after a frame is decoded | `lms/privacy_filter.py:97,101` | Reduced `_CONTAINER_RESTART_INTERVAL` from 1800s to 300s. PyAV's `timeout` option (10s) limits connection-level hangs. Worst case: 5-min recovery instead of indefinite. |

### P1: Could cause visible degradation

| # | Issue | File | Fix Applied |
|---|-------|------|-------------|
| 6 | **No systemd watchdog** — `Restart=on-failure` only catches exits, not hangs; a deadlocked process runs forever | `deploy/melo-lms.service` | Added `WatchdogSec=120`. Process heartbeat now sends `sd_notify("WATCHDOG=1")` every 60s. Also increased `TimeoutStopSec` from 30 to 60 for graceful R2 drain. |
| 7 | **Reconnect gives up after 20 attempts** (~7 min) — camera goes permanently offline, needs LMS restart | `lms/reconnect.py:18` | Removed the 20-attempt cap. Reconnect now retries indefinitely with backoff up to 60s, checking stop_event between attempts. |
| 8 | **R2Uploader drops pending uploads on shutdown** — `shutdown(wait=False)` abandons in-flight uploads | `lms/r2_uploader.py:103` | Changed to `shutdown(wait=True, cancel_futures=True)` — in-flight uploads finish, queued ones are cancelled. |

### P2: Security (could cause embarrassment during investor demo)

| # | Issue | File | Fix Applied |
|---|-------|------|-------------|
| 9 | **Unauthenticated setup API** — anyone on the LAN can POST to `/api/shutdown`, add/delete cameras, scan the network | `setup/app.py:28-33` | Added bearer token auth via `SETUP_API_TOKEN` env var. All POST/DELETE endpoints require `Authorization: Bearer <token>`. GET `/api/health` remains open. |
| 10 | **CORS allow-all** — any website visited by someone on the LAN could make cross-origin requests to port 8000 | `setup/app.py:30` | Restricted to `SETUP_CORS_ORIGINS` env var (defaults to localhost dev servers). |

### Accepted Risks (not fixed — low impact for this demo)

| Issue | Why it's acceptable |
|-------|-------------------|
| RTSP credentials visible in `ps aux` (FFmpeg CLI args) | Private LAN, single-user Pi, no shared access |
| Supabase RLS policies are permissive stubs | Service role key is only on the Pi; public key (web frontend) has read-only access via PostgREST |
| KMS `encrypt()` method missing | LOCAL_DEV=true bypasses KMS entirely; passwords stored as hex (reversible but functional) |
| `os._exit(0)` at end of main() | Systemd restarts cleanly within 10s; not a user-visible issue |
| No push alerting when stream goes down | Heartbeat updates Supabase; dashboard shows live/offline status |

---

## Pre-Flight Checklist

Run these commands on the Pi **before starting the 50-hour clock**:

```bash
# ── 1. Generate a setup API token and add to .env ──
TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "SETUP_API_TOKEN=$TOKEN" >> /home/melo-lms/melo-v2/.env
echo "Save this token — you'll need it for the admin dashboard: $TOKEN"

# ── 2. Verify .env is correct ──
grep -E "LOCAL_DEV|SETUP_API_TOKEN|SUPABASE_URL|R2_BUCKET" /home/melo-lms/melo-v2/.env

# ── 3. Disk space (need >10 GB free) ──
df -h /
# If tight:
sudo rm -f /var/log/melo/session_*.log
rm -f /tmp/melo-debug-*.jpg

# ── 4. Clean stale segments from previous runs ──
find /home/melo-lms/melo-v2/segments -name "*.ts" -o -name "*.m3u8" 2>/dev/null | wc -l
# If non-zero:
rm -rf /home/melo-lms/melo-v2/segments/*/

# ── 5. Deploy updated code + systemd config ──
cd /home/melo-lms/melo-v2
git pull
sudo cp deploy/melo-lms.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable melo-lms

# ── 6. Verify FFmpeg ──
ffmpeg -version | head -1

# ── 7. Verify camera is reachable ──
ping -c 3 <CAMERA_IP>

# ── 8. Start and verify ──
sudo systemctl restart melo-lms
sleep 20
journalctl -u melo-lms --since "1 min ago" | grep -E "pipeline started|R2 uploader started|PrivacyFilter started"

# ── 9. Verify uploads are flowing ──
sleep 10
journalctl -u melo-lms --since "1 min ago" | grep "Uploaded"

# ── 10. Baseline memory ──
journalctl -u melo-lms --since "5 min ago" | grep "\[process\]"

# ── 11. Verify API auth works ──
curl -s http://localhost:8000/api/health
# Should return: {"status":"ok"}
curl -s -X POST http://localhost:8000/api/discover
# Should return: 401 (no token)
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/discover
# Should return: {"cameras":[...]}

# ── 12. Verify stream is live in browser ──
echo "Open the Melo dashboard and confirm the stream is playing."
```

## Monitoring During the Demo

Check on the system periodically via SSH:

```bash
# Process health (memory, threads, uptime)
journalctl -u melo-lms | grep "\[process\]" | tail -5

# Stream health (upload count, errors)
journalctl -u melo-lms | grep "\[summary\]" | tail -5

# Watchdog health (stalls, restarts)
journalctl -u melo-lms | grep "\[watchdog\]" | tail -5

# Disk usage
df -h /

# Thread count (should be stable, not growing)
ps -o nlwp= -p $(pgrep -f "uv run lms")

# Check for any CRITICAL or ERROR logs
journalctl -u melo-lms -p err --since "1 hour ago"
```

## Files Modified

- `lms/main.py` — log rotation (RotatingFileHandler), systemd watchdog (sd_notify)
- `lms/hls_pipeline.py` — stderr thread lifecycle (join before re-spawn, join on stop)
- `lms/reconnect.py` — infinite retry with stop_event-aware sleep, increased max delay
- `lms/r2_uploader.py` — prune `_lost_segments`, graceful pool shutdown
- `lms/privacy_filter.py` — 5-min container restart, debug frames only on first open
- `setup/app.py` — bearer token auth on all mutating endpoints, restricted CORS origins
- `deploy/melo-lms.service` — WatchdogSec=120, TimeoutStopSec=60
- `.env.example` — documented SETUP_API_TOKEN and SETUP_CORS_ORIGINS
