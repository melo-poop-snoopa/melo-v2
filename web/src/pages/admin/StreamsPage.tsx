import { useEffect, useState } from "react"
import { Check, Copy, Radio } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAuthStore } from "@/store/auth-store"
import { supabase } from "@/services/supabase"
import type { Stream } from "@/types"
import { useStreamStatus } from "@/hooks/use-stream-status"
import { cn } from "@/lib/utils"
import { toast, Toaster } from "sonner"

export default function StreamsPage() {
  const { shelterId } = useAuthStore()
  const [streams, setStreams] = useState<Stream[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState("")

  useEffect(() => {
    if (!shelterId) return
    supabase
      .from("streams")
      .select("*")
      .eq("shelter_id", shelterId)
      .order("created_at")
      .then(({ data }) => setStreams((data as Stream[]) ?? []))
  }, [shelterId])

  const saveRename = async (streamId: string) => {
    if (!editName.trim()) return
    const { data } = await supabase
      .from("streams")
      .update({ name: editName.trim() })
      .eq("id", streamId)
      .select()
      .single()
    if (data) {
      setStreams((ss) => ss.map((s) => (s.id === streamId ? (data as Stream) : s)))
      toast.success("Camera renamed")
    }
    setEditingId(null)
  }

  return (
    <div>
      <Toaster />
      <h1 className="mb-6 font-display text-2xl font-bold text-foreground">Streams</h1>

      {streams.length === 0 ? (
        <p className="text-muted-foreground">No streams configured yet. They appear once the LMS connects a camera.</p>
      ) : (
        <div className="flex flex-col gap-4">
          {streams.map((stream) => (
            <StreamRow
              key={stream.id}
              stream={stream}
              editing={editingId === stream.id}
              editName={editName}
              onStartEdit={() => { setEditingId(stream.id); setEditName(stream.name) }}
              onEditName={setEditName}
              onSave={() => saveRename(stream.id)}
              onCancel={() => setEditingId(null)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function StreamRow({
  stream, editing, editName,
  onStartEdit, onEditName, onSave, onCancel,
}: {
  stream: Stream
  editing: boolean
  editName: string
  onStartEdit: () => void
  onEditName: (v: string) => void
  onSave: () => void
  onCancel: () => void
}) {
  const status = useStreamStatus(stream)
  const [copied, setCopied] = useState(false)

  const copyHls = () => {
    if (!stream.hls_url) return
    navigator.clipboard.writeText(stream.hls_url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/3 p-4">
      <div className="flex items-start justify-between gap-4">
        {/* Name + status */}
        <div className="flex items-center gap-3 min-w-0">
          {stream.thumbnail_url ? (
            <img
              src={stream.thumbnail_url}
              alt={stream.name}
              className="h-12 w-20 shrink-0 rounded-lg object-cover"
            />
          ) : (
            <div className="flex h-12 w-20 shrink-0 items-center justify-center rounded-lg bg-black/30">
              <Radio className="h-5 w-5 text-muted-foreground" />
            </div>
          )}

          <div className="min-w-0">
            {editing ? (
              <div className="flex items-center gap-2">
                <Input
                  value={editName}
                  onChange={(e) => onEditName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && onSave()}
                  className="h-7 w-40 text-sm"
                  autoFocus
                />
                <Button size="sm" variant="ghost" onClick={onSave}>Save</Button>
                <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
              </div>
            ) : (
              <button
                onClick={onStartEdit}
                className="flex items-center gap-1.5 text-sm font-medium text-foreground hover:text-melo-500 transition-colors"
              >
                {stream.name}
                <span className="text-xs text-muted-foreground">(rename)</span>
              </button>
            )}

            <div className="mt-1 flex items-center gap-1.5">
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  status === "live" ? "bg-green-500" : "bg-muted-foreground/40"
                )}
              />
              <span className="text-xs text-muted-foreground capitalize">{status}</span>
              {stream.last_heartbeat && (
                <span className="text-xs text-muted-foreground">
                  · {relativeTime(stream.last_heartbeat)}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* HLS URL */}
      {stream.hls_url && (
        <div className="flex items-center gap-2 rounded-lg bg-black/20 px-3 py-2 font-mono text-xs text-muted-foreground">
          <span className="flex-1 truncate">{stream.hls_url}</span>
          <button onClick={copyHls} className="shrink-0 text-muted-foreground hover:text-foreground">
            {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
        </div>
      )}
    </div>
  )
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  return `${Math.floor(m / 60)}h ago`
}
