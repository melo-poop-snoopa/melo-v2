/**
 * Client for the LMS Setup API.
 *
 * The LMS registers its local IP in Supabase on startup. The dashboard reads
 * it from the shelter's `lms_url` field, so the browser can reach the LMS
 * on the same network for camera discovery and ONVIF testing.
 */

import { supabase } from "@/services/supabase"

let _cachedBaseUrl: string | null = null
const SETUP_API_TOKEN_KEY = "melo.setupApiToken"

function getTokenStorageKey(shelterId: string): string {
  return `${SETUP_API_TOKEN_KEY}:${shelterId}`
}

function getEnvSetupApiToken(): string {
  return (import.meta.env.VITE_SETUP_API_TOKEN as string | undefined)?.trim() ?? ""
}

export function getSetupApiToken(shelterId: string): string {
  if (typeof window === "undefined") return getEnvSetupApiToken()
  return window.localStorage.getItem(getTokenStorageKey(shelterId))?.trim() || getEnvSetupApiToken()
}

export function setSetupApiToken(shelterId: string, token: string) {
  if (typeof window === "undefined") return
  const trimmed = token.trim()
  const key = getTokenStorageKey(shelterId)
  if (trimmed) {
    window.localStorage.setItem(key, trimmed)
  } else {
    window.localStorage.removeItem(key)
  }
}

async function getErrorMessage(res: Response, fallback: string): Promise<string> {
  let detail = ""
  try {
    const json = await res.json()
    if (typeof json?.detail === "string") detail = json.detail
    else if (typeof json?.error === "string") detail = json.error
  } catch {
    try {
      const text = (await res.text()).trim()
      if (text) detail = text
    } catch {
      // Ignore parse failures and keep the fallback message.
    }
  }

  const prefix = `${fallback}: ${res.status}`
  if (!detail) return prefix
  return `${prefix} (${detail})`
}

async function setupFetch(
  shelterId: string,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const base = await getBaseUrl(shelterId)
  const headers = new Headers(init.headers)
  const token = getSetupApiToken(shelterId)
  if (token) headers.set("Authorization", `Bearer ${token}`)
  return fetch(`${base}${path}`, { ...init, headers })
}

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
    const res = await setupFetch(shelterId, "/api/health", {
      signal: AbortSignal.timeout(3000),
    })
    return res.ok
  } catch {
    _cachedBaseUrl = null
    return false
  }
}

export async function discoverCameras(shelterId: string): Promise<DiscoverResponse> {
  const res = await setupFetch(shelterId, "/api/discover", { method: "POST" })
  if (!res.ok) throw new Error(await getErrorMessage(res, "Discovery failed"))
  return res.json()
}

export async function testCamera(
  shelterId: string,
  host: string,
  port: number,
  username: string,
  password: string,
): Promise<TestCameraResponse> {
  const res = await setupFetch(shelterId, "/api/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ host, port, username, password }),
  })
  if (!res.ok) throw new Error(await getErrorMessage(res, "Test failed"))
  return res.json()
}

export async function testRtspUrl(
  shelterId: string,
  rtspUrl: string,
): Promise<TestCameraResponse> {
  const res = await setupFetch(shelterId, "/api/test-rtsp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rtsp_url: rtspUrl }),
  })
  if (!res.ok) throw new Error(await getErrorMessage(res, "RTSP test failed"))
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
    device_uuid?: string
  },
): Promise<SaveCameraResponse> {
  const res = await setupFetch(shelterId, "/api/cameras", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  })
  if (!res.ok) throw new Error(await getErrorMessage(res, "Save failed"))
  return res.json()
}

export interface ShutdownResponse {
  status: string
  shutdown_duration_seconds: number
}

export async function shutdownLms(shelterId: string): Promise<ShutdownResponse> {
  const res = await setupFetch(shelterId, "/api/shutdown", {
    method: "POST",
    signal: AbortSignal.timeout(30000),
  })
  if (!res.ok) throw new Error(await getErrorMessage(res, "Shutdown failed"))
  const data = await res.json()
  clearLmsCache()
  return data
}

export async function deleteCamera(
  shelterId: string,
  cameraId: string,
  streamId: string | null,
): Promise<void> {
  const res = await setupFetch(shelterId, "/api/cameras", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ camera_id: cameraId, stream_id: streamId }),
  })
  if (!res.ok) throw new Error(await getErrorMessage(res, "Delete failed"))
}
