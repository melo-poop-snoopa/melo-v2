/**
 * Client for the LMS Setup API.
 *
 * The LMS registers its local IP in Supabase on startup. The dashboard reads
 * it from the shelter's `lms_url` field, so the browser can reach the LMS
 * on the same network for camera discovery and ONVIF testing.
 */

import { supabase } from "@/services/supabase"

let _cachedBaseUrl: string | null = null

async function getBaseUrl(shelterId: string): Promise<string> {
  if (_cachedBaseUrl) return _cachedBaseUrl

  const { data } = await supabase
    .from("shelters")
    .select("lms_url")
    .eq("id", shelterId)
    .single()

  const url = data?.lms_url as string | null
  if (!url) throw new Error("LMS URL not registered — is the LMS running?")
  _cachedBaseUrl = url
  return url
}

export function clearLmsCache() {
  _cachedBaseUrl = null
}

export interface DiscoverResponse {
  cameras: Array<{
    host: string
    port: number
    xaddrs: string
    device_uuid: string | null
  }>
}

export interface TestCameraResponse {
  success: boolean
  rtsp_url: string | null
  error: string | null
}

export interface SaveCameraResponse {
  camera_id: string
  stream_id: string
}

export async function checkSetupHealth(shelterId: string): Promise<boolean> {
  try {
    const base = await getBaseUrl(shelterId)
    const res = await fetch(`${base}/api/health`, {
      signal: AbortSignal.timeout(3000),
    })
    return res.ok
  } catch {
    _cachedBaseUrl = null
    return false
  }
}

export async function discoverCameras(shelterId: string): Promise<DiscoverResponse> {
  const base = await getBaseUrl(shelterId)
  const res = await fetch(`${base}/api/discover`, { method: "POST" })
  if (!res.ok) throw new Error(`Discovery failed: ${res.status}`)
  return res.json()
}

export async function testCamera(
  shelterId: string,
  host: string,
  port: number,
  username: string,
  password: string,
): Promise<TestCameraResponse> {
  const base = await getBaseUrl(shelterId)
  const res = await fetch(`${base}/api/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ host, port, username, password }),
  })
  if (!res.ok) throw new Error(`Test failed: ${res.status}`)
  return res.json()
}

export async function testRtspUrl(
  shelterId: string,
  rtspUrl: string,
): Promise<TestCameraResponse> {
  const base = await getBaseUrl(shelterId)
  const res = await fetch(`${base}/api/test-rtsp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rtsp_url: rtspUrl }),
  })
  if (!res.ok) throw new Error(`RTSP test failed: ${res.status}`)
  return res.json()
}

export async function saveCamera(
  shelterId: string,
  params: {
    shelter_id: string
    host: string
    port: number
    username: string
    password: string
    stream_name: string
    rtsp_url?: string
  },
): Promise<SaveCameraResponse> {
  const base = await getBaseUrl(shelterId)
  const res = await fetch(`${base}/api/cameras`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(`Save failed: ${res.status}`)
  return res.json()
}

export interface ShutdownResponse {
  status: string
  shutdown_duration_seconds: number
}

export async function shutdownLms(shelterId: string): Promise<ShutdownResponse> {
  const base = await getBaseUrl(shelterId)
  const res = await fetch(`${base}/api/shutdown`, {
    method: "POST",
    signal: AbortSignal.timeout(30000),
  })
  if (!res.ok) throw new Error(`Shutdown failed: ${res.status}`)
  const data = await res.json()
  clearLmsCache()
  return data
}

export async function deleteCamera(
  shelterId: string,
  cameraId: string,
  streamId: string | null,
): Promise<void> {
  const base = await getBaseUrl(shelterId)
  const res = await fetch(`${base}/api/cameras`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ camera_id: cameraId, stream_id: streamId }),
  })
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`)
}
