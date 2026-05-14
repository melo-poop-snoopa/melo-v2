import { useEffect, useRef } from "react"
import Hls from "hls.js"
import { cn } from "@/lib/utils"
import type { Stream } from "@/types"
import { useStreamStatus } from "@/hooks/use-stream-status"

interface StreamPlayerProps {
  stream: Stream
  className?: string
}

export function StreamPlayer({ stream, className }: StreamPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsRef = useRef<Hls | null>(null)
  const status = useStreamStatus(stream)
  const isLive = status === "live" && !!stream.hls_url

  useEffect(() => {
    const video = videoRef.current
    if (!video || !isLive || !stream.hls_url) return

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: false,
        liveSyncDurationCount: 2,
        liveMaxLatencyDurationCount: 4,
        liveDurationInfinity: true,
        backBufferLength: 0,
        manifestLoadingMaxRetry: 6,
        manifestLoadingRetryDelay: 1000,
        levelLoadingMaxRetry: 6,
        levelLoadingRetryDelay: 1000,
        fragLoadingMaxRetry: 6,
        fragLoadingRetryDelay: 500,
      })
      hlsRef.current = hls
      hls.loadSource(stream.hls_url)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}))

      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.details === Hls.ErrorDetails.FRAG_LOAD_ERROR) {
          console.warn(`[melo] segment fetch failed: ${data.frag?.relurl} (${data.response?.code})`)
        } else if (data.details === Hls.ErrorDetails.FRAG_LOAD_TIMEOUT) {
          console.warn(`[melo] segment fetch timed out: ${data.frag?.relurl}`)
        } else if (data.fatal) {
          console.error(`[melo] fatal HLS error: ${data.type} / ${data.details}`)
        }
      })

      let lastSn = -1
      hls.on(Hls.Events.FRAG_CHANGED, (_event, data) => {
        const sn = data.frag.sn as number
        if (lastSn >= 0 && sn > lastSn + 1) {
          console.warn(`[melo] skipped ${sn - lastSn - 1} segment(s): jumped from sn=${lastSn} to sn=${sn}`)
        }
        lastSn = sn
      })
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = stream.hls_url
      video.play().catch(() => {})
    }

    return () => {
      hlsRef.current?.destroy()
      hlsRef.current = null
    }
  }, [isLive, stream.hls_url])

  return (
    <div className={cn("relative overflow-hidden rounded-xl bg-black aspect-video", className)}>
      {isLive ? (
        <>
          <video
            ref={videoRef}
            className="h-full w-full object-cover"
            muted
            playsInline
            autoPlay
          />
          <LivePill />
        </>
      ) : (
        <OfflineOverlay thumbnail={stream.thumbnail_url} name={stream.name} />
      )}
    </div>
  )
}

function LivePill() {
  return (
    <div className="absolute top-3 left-3 flex items-center gap-1.5 rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-semibold text-white shadow">
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
      </span>
      LIVE
    </div>
  )
}

function OfflineOverlay({ thumbnail, name }: { thumbnail: string | null; name: string }) {
  return (
    <div className="relative flex h-full w-full items-center justify-center">
      {thumbnail && (
        <img
          src={thumbnail}
          alt={name}
          className="absolute inset-0 h-full w-full object-cover opacity-40"
        />
      )}
      <div className="relative z-10 flex flex-col items-center gap-2 text-white">
        <div className="rounded-full bg-white/20 px-3 py-1 text-sm font-medium">Offline</div>
        <p className="text-xs text-white/70">{name}</p>
      </div>
    </div>
  )
}
