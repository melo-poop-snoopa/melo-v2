import { useEffect, useState } from "react"
import type { Stream } from "@/types"
import { HEARTBEAT_STALE_MS } from "@/types"

export function isStreamLive(stream: Stream): boolean {
  if (stream.status !== "live") return false
  if (!stream.last_heartbeat) return false
  const age = Date.now() - new Date(stream.last_heartbeat).getTime()
  return age < HEARTBEAT_STALE_MS
}

export function useStreamStatus(stream: Stream): "live" | "offline" {
  const [status, setStatus] = useState<"live" | "offline">(
    isStreamLive(stream) ? "live" : "offline"
  )

  useEffect(() => {
    const check = () => setStatus(isStreamLive(stream) ? "live" : "offline")
    check()
    const id = setInterval(check, 15_000)
    return () => clearInterval(id)
  }, [stream.status, stream.last_heartbeat])

  return status
}
