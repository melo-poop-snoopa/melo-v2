import { useCallback, useEffect, useRef, useState } from "react"
import { Settings, Loader2 } from "lucide-react"
import { useAuthStore } from "@/store/auth-store"
import { checkSetupHealth, shutdownLms } from "@/services/setup-api"
import { HoldToConfirmButton } from "@/components/admin/HoldToConfirmButton"
import { toast, Toaster } from "sonner"

export default function SettingsPage() {
  const { shelterId } = useAuthStore()
  const [lmsOnline, setLmsOnline] = useState<boolean | null>(null)
  const [shuttingDown, setShuttingDown] = useState(false)
  const [shutdownResult, setShutdownResult] = useState<number | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval>>(0 as unknown as ReturnType<typeof setInterval>)

  const pollHealth = useCallback(async () => {
    if (!shelterId) return
    const online = await checkSetupHealth(shelterId)
    setLmsOnline(online)
  }, [shelterId])

  useEffect(() => {
    pollHealth()
    intervalRef.current = setInterval(pollHealth, 10_000)
    return () => clearInterval(intervalRef.current)
  }, [pollHealth])

  const handleShutdown = async () => {
    if (!shelterId) return
    setShuttingDown(true)
    try {
      const res = await shutdownLms(shelterId)
      setShutdownResult(res.shutdown_duration_seconds)
      setLmsOnline(false)
      toast.success("Streams stopped successfully")
    } catch {
      toast.error("Failed to stop streams")
    } finally {
      setShuttingDown(false)
    }
  }

  return (
    <>
      <Toaster position="top-right" theme="dark" />

      <div className="mx-auto max-w-lg">
        <h1 className="mb-8 flex items-center gap-3 font-display text-2xl font-bold">
          <Settings className="h-6 w-6 text-melo-400" />
          Settings
        </h1>

        <div className="rounded-xl border border-white/10 bg-white/3 p-6">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Stream Control
          </h2>

          <div className="mb-6 flex items-center gap-2.5">
            <span
              className={`inline-block h-2.5 w-2.5 rounded-full ${
                lmsOnline === null
                  ? "animate-pulse bg-yellow-400"
                  : lmsOnline
                    ? "bg-emerald-400"
                    : "bg-zinc-500"
              }`}
            />
            <span className="text-sm text-muted-foreground">
              {lmsOnline === null
                ? "Checking..."
                : lmsOnline
                  ? "Online"
                  : "Offline"}
            </span>
          </div>

          <HoldToConfirmButton
            onConfirm={handleShutdown}
            disabled={!lmsOnline || shuttingDown || shutdownResult !== null}
          />

          {shuttingDown && (
            <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Stopping streams...
            </div>
          )}

          {shutdownResult !== null && (
            <p className="mt-4 text-sm text-muted-foreground">
              Streams stopped. System shutting down.
              <span className="ml-1 text-xs opacity-60">
                ({shutdownResult}s)
              </span>
            </p>
          )}
        </div>
      </div>
    </>
  )
}
