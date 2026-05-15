import { useEffect, useMemo } from "react"
import { Heart } from "lucide-react"
import { useShelterStore } from "@/store/shelter-store"
import { useStreamStore } from "@/store/stream-store"
import { ShelterCard } from "@/components/ShelterCard"
import { StreamPlayer } from "@/components/StreamPlayer"
import { isStreamLive } from "@/hooks/use-stream-status"
import type { Stream } from "@/types"

export default function Landing() {
  const { shelters, fetch: fetchShelters, loading } = useShelterStore()
  const { streams, fetch: fetchStreams, subscribe } = useStreamStore()

  useEffect(() => {
    fetchShelters()
    fetchStreams()
    const unsub = subscribe()
    return unsub
  }, [])

  const heroStream = useMemo<Stream | undefined>(() => {
    const live = streams.filter(isStreamLive)
    if (live.length === 0) return undefined
    return live[Math.floor(Math.random() * live.length)]
  }, [streams])

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <header className="sticky top-0 z-40 flex items-center justify-between border-b border-white/10 bg-background/80 px-6 py-4 backdrop-blur">
        <span className="font-display text-xl font-bold text-melo-500">melo</span>
        <a
          href="/app/login"
          className="rounded-lg border border-white/20 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          Shelter login
        </a>
      </header>

      {/* Hero */}
      <section className="relative flex flex-col items-center gap-8 px-6 py-16 text-center">
        <div className="max-w-2xl">
          <h1 className="font-display text-5xl font-bold leading-tight text-foreground">
            Watch cats. <span className="text-melo-500">Adopt one.</span>
          </h1>
          <p className="mt-4 text-lg text-muted-foreground">
            Live streams from shelters. Meet cats in real time, then give them a home.
          </p>
        </div>

        {heroStream ? (
          <div className="w-full max-w-3xl">
            <StreamPlayer stream={heroStream} className="shadow-2xl" />
            <p className="mt-3 text-sm text-muted-foreground">
              Live from a shelter near you
            </p>
          </div>
        ) : (
          <div className="flex h-48 w-full max-w-3xl items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-muted-foreground">
            No streams live right now — check back soon 🐾
          </div>
        )}
      </section>

      {/* Shelter grid — hidden for demo */}
      {/* TODO: restore shelter grid after demo — remove the `{false && (...)}` wrapper */}
      {false && (
      <section className="mx-auto max-w-6xl px-6 pb-20">
        <div className="mb-8 flex items-center justify-between">
          <h2 className="font-display text-2xl font-bold text-foreground">Shelters</h2>
          {loading && <span className="text-sm text-muted-foreground">Loading…</span>}
        </div>

        {shelters.length === 0 && !loading ? (
          <p className="text-muted-foreground">No shelters yet.</p>
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {shelters.map((shelter) => (
              <ShelterCard key={shelter.id} shelter={shelter} />
            ))}
          </div>
        )}
      </section>
      )}

      {/* Footer */}
      <footer className="border-t border-white/10 px-6 py-8 text-center text-sm text-muted-foreground">
        <span className="flex items-center justify-center gap-1.5">
          Made with <Heart className="h-3.5 w-3.5 fill-melo-500 text-melo-500" /> for shelter cats
        </span>
      </footer>
    </div>
  )
}
