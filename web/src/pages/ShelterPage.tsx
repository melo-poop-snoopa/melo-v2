import { useEffect } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { ArrowLeft, BadgeCheck, ExternalLink, MapPin } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useShelterStore } from "@/store/shelter-store"
import { useCatStore } from "@/store/cat-store"
import { StreamPlayer } from "@/components/StreamPlayer"
import { CatProfileCard } from "@/components/CatProfileCard"
import type { Stream } from "@/types"

export default function ShelterPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { currentShelter, fetchById, loading } = useShelterStore()
  const { cats, fetchForShelter } = useCatStore()

  useEffect(() => {
    if (!id) return
    fetchById(id)
    fetchForShelter(id)
  }, [id])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Loading…
      </div>
    )
  }

  if (!currentShelter) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">Shelter not found.</p>
        <Button variant="outline" onClick={() => navigate("/")}>Back to home</Button>
      </div>
    )
  }

  const streams = (currentShelter.streams ?? []) as Stream[]
  const impactStr = formatImpact(currentShelter.impact_metrics)

  return (
    <div className="min-h-screen bg-background">
      {/* Sticky donate button */}
      {currentShelter.donation_url && (
        <div className="sticky top-0 z-40 flex justify-end border-b border-white/10 bg-background/80 px-6 py-3 backdrop-blur">
          <Button
            asChild
            className="bg-melo-500 text-white hover:bg-melo-600"
          >
            <a href={currentShelter.donation_url} target="_blank" rel="noopener noreferrer">
              Donate <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
            </a>
          </Button>
        </div>
      )}

      <div className="mx-auto max-w-5xl px-6 py-10">
        {/* Back */}
        <button
          onClick={() => navigate("/")}
          className="mb-6 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> All shelters
        </button>

        {/* Shelter header */}
        <div className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-4">
            {currentShelter.logo_url ? (
              <img
                src={currentShelter.logo_url}
                alt={currentShelter.name}
                className="h-16 w-16 rounded-xl object-cover"
              />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-melo-100 text-3xl">🏠</div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-display text-3xl font-bold text-foreground">
                  {currentShelter.name}
                </h1>
                {currentShelter.verification === "verified" && (
                  <BadgeCheck className="h-6 w-6 text-mint-500" aria-label="Verified shelter" />
                )}
              </div>
              {currentShelter.location && (
                <p className="mt-1 flex items-center gap-1 text-sm text-muted-foreground">
                  <MapPin className="h-3.5 w-3.5" /> {currentShelter.location}
                </p>
              )}
              {impactStr && (
                <p className="mt-2 text-sm font-medium text-mint-600">{impactStr}</p>
              )}
            </div>
          </div>
        </div>

        {currentShelter.description && (
          <p className="mb-10 max-w-2xl text-muted-foreground leading-relaxed">
            {currentShelter.description}
          </p>
        )}

        {/* Streams */}
        {streams.length > 0 && (
          <section className="mb-12">
            <h2 className="mb-4 font-display text-xl font-bold text-foreground">Live cameras</h2>
            <div className="grid gap-6 sm:grid-cols-2">
              {streams.map((stream) => {
                const streamCats = cats.filter((c) => c.stream_id === stream.id)
                return (
                  <div key={stream.id} className="flex flex-col gap-3">
                    <StreamPlayer stream={stream} />
                    <p className="text-sm font-medium text-foreground">{stream.name}</p>
                    {streamCats.length > 0 && (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                        {streamCats.map((cat) => (
                          <CatProfileCard key={cat.id} cat={cat} />
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {/* Cats without a stream */}
        {(() => {
          const unassigned = cats.filter((c) => !c.stream_id)
          if (unassigned.length === 0) return null
          return (
            <section className="mb-12">
              <h2 className="mb-4 font-display text-xl font-bold text-foreground">Meet the cats</h2>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
                {unassigned.map((cat) => (
                  <CatProfileCard key={cat.id} cat={cat} />
                ))}
              </div>
            </section>
          )
        })()}

        {/* Donation section */}
        {currentShelter.donation_url && (
          <section className="rounded-2xl border border-melo-200 bg-melo-50 p-8 text-center dark:border-melo-800 dark:bg-melo-950/30">
            <h2 className="font-display text-2xl font-bold text-foreground">
              Help us care for these cats 🐾
            </h2>
            <p className="mt-2 text-muted-foreground">
              Every donation goes directly to food, vet care, and finding forever homes.
            </p>
            <Button
              asChild
              size="lg"
              className="mt-6 bg-melo-500 text-white hover:bg-melo-600"
            >
              <a href={currentShelter.donation_url} target="_blank" rel="noopener noreferrer">
                Donate to {currentShelter.name} <ExternalLink className="ml-2 h-4 w-4" />
              </a>
            </Button>
          </section>
        )}
      </div>
    </div>
  )
}

function formatImpact(metrics: Record<string, unknown> | null): string {
  if (!metrics) return ""
  const parts: string[] = []
  if (metrics.adoptions_2025) parts.push(`${metrics.adoptions_2025} adoptions in 2025`)
  if (metrics.cats_in_care) parts.push(`${metrics.cats_in_care} cats in care`)
  return parts.length ? parts.join(" · ") : ""
}
