import { useNavigate } from "react-router-dom"
import { MapPin } from "lucide-react"
import { cn } from "@/lib/utils"
import type { Shelter, Stream } from "@/types"

interface ShelterCardProps {
  shelter: Shelter & { streams?: Stream[]; liveCount?: number }
  className?: string
}

export function ShelterCard({ shelter, className }: ShelterCardProps) {
  const navigate = useNavigate()
  const liveCount = shelter.liveCount ?? 0
  const streams = shelter.streams ?? []
  const firstStream = streams[0]
  const thumbnail = firstStream?.thumbnail_url

  return (
    <button
      onClick={() => navigate(`/shelter/${shelter.id}`)}
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/5 text-left transition-all duration-200 hover:bg-white/10 hover:shadow-xl hover:-translate-y-0.5",
        className
      )}
    >
      {/* Thumbnail */}
      <div className="aspect-video w-full overflow-hidden bg-black/40">
        {thumbnail ? (
          <img
            src={thumbnail}
            alt={shelter.name}
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-4xl">🐱</div>
        )}

        {liveCount > 0 && (
          <div className="absolute top-3 right-3 flex items-center gap-1.5 rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-semibold text-white shadow">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
            </span>
            {liveCount} LIVE
          </div>
        )}
      </div>

      {/* Info */}
      <div className="flex flex-col gap-1 p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-display font-semibold text-foreground leading-tight">{shelter.name}</h3>
          {shelter.verification === "verified" && (
            <span className="mt-0.5 shrink-0 text-mint-500" title="Verified shelter">✓</span>
          )}
        </div>
        {shelter.location && (
          <p className="flex items-center gap-1 text-xs text-muted-foreground">
            <MapPin className="h-3 w-3" />
            {shelter.location}
          </p>
        )}
        {streams.length > 0 && (
          <p className="text-xs text-muted-foreground mt-1">
            {streams.length} camera{streams.length !== 1 ? "s" : ""}
            {liveCount > 0 ? ` · ${liveCount} live` : " · offline"}
          </p>
        )}
      </div>
    </button>
  )
}
