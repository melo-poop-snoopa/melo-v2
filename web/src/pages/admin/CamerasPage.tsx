import { useEffect, useState } from "react"
import { Camera, Plus, Trash2, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { useAuthStore } from "@/store/auth-store"
import { supabase } from "@/services/supabase"
import { checkSetupHealth, deleteCamera } from "@/services/setup-api"
import { DiscoveryDialog } from "@/components/admin/camera-discovery/DiscoveryDialog"
import type { ShelterCamera, Stream } from "@/types"
import { cn } from "@/lib/utils"
import { toast, Toaster } from "sonner"

export default function CamerasPage() {
  const { shelterId } = useAuthStore()
  const [cameras, setCameras] = useState<(ShelterCamera & { stream?: Stream })[]>([])
  const [loading, setLoading] = useState(true)
  const [discoveryOpen, setDiscoveryOpen] = useState(false)
  const [setupOnline, setSetupOnline] = useState<boolean | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<(ShelterCamera & { stream?: Stream }) | null>(null)
  const [deleting, setDeleting] = useState(false)

  const fetchCameras = async () => {
    if (!shelterId) return
    setLoading(true)

    const { data: cameraData } = await supabase
      .from("shelter_cameras")
      .select("*")
      .eq("shelter_id", shelterId)
      .order("created_at")

    const { data: streamData } = await supabase
      .from("streams")
      .select("*")
      .eq("shelter_id", shelterId)

    const streamMap = new Map((streamData ?? []).map((s: Stream) => [s.id, s]))
    const enriched = (cameraData ?? []).map((cam: ShelterCamera) => ({
      ...cam,
      stream: cam.stream_id ? streamMap.get(cam.stream_id) : undefined,
    }))

    setCameras(enriched)
    setLoading(false)
  }

  useEffect(() => {
    fetchCameras()
  }, [shelterId])

  const handleAddCamera = async () => {
    if (!shelterId) return
    const online = await checkSetupHealth(shelterId)
    setSetupOnline(online)
    if (online) {
      setDiscoveryOpen(true)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget || !shelterId) return
    setDeleting(true)
    try {
      await deleteCamera(shelterId, deleteTarget.id, deleteTarget.stream_id)
      toast.success("Camera removed")
      await fetchCameras()
    } catch {
      // Fallback: delete directly via Supabase
      await supabase.from("shelter_cameras").delete().eq("id", deleteTarget.id)
      if (deleteTarget.stream_id) {
        await supabase.from("streams").delete().eq("id", deleteTarget.stream_id)
      }
      toast.success("Camera removed")
      await fetchCameras()
    }
    setDeleting(false)
    setDeleteTarget(null)
  }

  return (
    <div>
      <Toaster />
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-foreground">Cameras</h1>
        <Button
          onClick={handleAddCamera}
          className="bg-melo-500 text-white hover:bg-melo-600"
        >
          <Plus className="mr-1.5 h-4 w-4" /> Add Camera
        </Button>
      </div>

      {/* LMS offline warning */}
      {setupOnline === false && (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-sm font-medium text-amber-500">LMS not reachable</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Camera discovery requires the LMS to be running on this network.
            The LMS must be on the same LAN as the cameras you want to discover.
          </p>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading cameras...</span>
        </div>
      ) : cameras.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-white/10 bg-white/3 py-12">
          <Camera className="h-10 w-10 text-muted-foreground" />
          <div className="text-center">
            <p className="text-sm text-foreground">No cameras configured yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Click "Add Camera" to discover cameras on this network.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {cameras.map((cam) => (
            <div
              key={cam.id}
              className="flex items-center gap-4 rounded-xl border border-white/10 bg-white/3 p-4"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-black/30">
                <Camera className="h-5 w-5 text-muted-foreground" />
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {cam.stream?.name ?? `Camera ${cam.ip_address}`}
                </p>
                <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="font-mono">{cam.ip_address}:{cam.onvif_port}</span>
                  {cam.stream && (
                    <div className="flex items-center gap-1.5">
                      <span
                        className={cn(
                          "h-2 w-2 rounded-full",
                          cam.stream.status === "live" ? "bg-green-500" : "bg-muted-foreground/40"
                        )}
                      />
                      <span className="capitalize">{cam.stream.status}</span>
                    </div>
                  )}
                  {cam.username && (
                    <span>User: {cam.username}</span>
                  )}
                </div>
              </div>

              <button
                onClick={() => setDeleteTarget(cam)}
                className="shrink-0 rounded-md p-2 text-muted-foreground hover:bg-red-500/10 hover:text-red-500 transition-colors"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      <DiscoveryDialog
        open={discoveryOpen}
        onOpenChange={setDiscoveryOpen}
        onComplete={fetchCameras}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this camera?</AlertDialogTitle>
            <AlertDialogDescription>
              This will delete the camera configuration and stop its stream.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault()
                handleDelete()
              }}
              disabled={deleting}
              className="bg-red-600 text-white hover:bg-red-700"
            >
              {deleting ? "Removing..." : "Remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
