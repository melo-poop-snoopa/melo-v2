import { useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ArrowLeft, Camera, Link, Loader2, Plus, Radar, WifiOff } from "lucide-react"
import { cn } from "@/lib/utils"
import { discoverCameras } from "@/services/setup-api"
import type { DiscoveredCamera } from "@/types"

interface ScanStepProps {
  shelterId: string
  onComplete: (cameras: DiscoveredCamera[]) => void
  onClose: () => void
}

type Mode = "chooser" | "scanning" | "manual" | "rtsp"

export function ScanStep({ shelterId, onComplete, onClose }: ScanStepProps) {
  const [mode, setMode] = useState<Mode>("chooser")
  const [discovered, setDiscovered] = useState<DiscoveredCamera[] | null>(null)
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set())
  const [manualHost, setManualHost] = useState("")
  const [manualPort, setManualPort] = useState("80")
  const [rtspUrl, setRtspUrl] = useState("")
  const [rtspStreamName, setRtspStreamName] = useState("")

  useEffect(() => {
    if (mode !== "scanning") return
    let cancelled = false
    setDiscovered(null)

    discoverCameras(shelterId)
      .then(({ cameras }) => {
        if (cancelled) return
        setDiscovered(cameras)
        setSelectedIndices(new Set(cameras.map((_, i) => i)))
      })
      .catch(() => {
        if (cancelled) return
        setDiscovered([])
        setSelectedIndices(new Set())
      })

    return () => { cancelled = true }
  }, [mode])

  const toggleCamera = (index: number) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  const submitManual = () => {
    if (!manualHost.trim()) return
    const port = Number.parseInt(manualPort, 10) || 80
    onComplete([{
      host: manualHost.trim(),
      port,
      xaddrs: `http://${manualHost.trim()}:${port}/onvif/device_service`,
      device_uuid: null,
    }])
  }

  const submitRtsp = () => {
    if (!rtspUrl.trim() || !rtspStreamName.trim()) return
    let host = ""
    try {
      const parsed = new URL(rtspUrl.trim())
      host = parsed.hostname
    } catch { /* leave host empty — backend will parse */ }
    onComplete([{
      host,
      port: 0,
      xaddrs: "",
      device_uuid: null,
      rtsp_url: rtspUrl.trim(),
      stream_name: rtspStreamName.trim(),
    }])
  }

  const selectedCameras = discovered?.filter((_, i) => selectedIndices.has(i)) ?? []

  if (mode === "chooser") {
    return (
      <div className="flex flex-col gap-3">
        <button
          type="button"
          onClick={() => setMode("scanning")}
          className="w-full rounded-lg bg-white/5 p-4 text-left transition hover:bg-white/10"
        >
          <div className="flex items-center gap-3">
            <Radar className="h-5 w-5 text-melo-500" />
            <div className="flex-1">
              <p className="text-sm font-medium text-foreground">Scan network</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Auto-detect ONVIF cameras on this LAN.
              </p>
            </div>
          </div>
        </button>

        <button
          type="button"
          onClick={() => setMode("manual")}
          className="w-full rounded-lg bg-white/5 p-4 text-left transition hover:bg-white/10"
        >
          <div className="flex items-center gap-3">
            <Plus className="h-5 w-5 text-melo-500" />
            <div className="flex-1">
              <p className="text-sm font-medium text-foreground">Add manually</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Enter the camera's IP address and ONVIF port.
              </p>
            </div>
          </div>
        </button>

        <button
          type="button"
          onClick={() => setMode("rtsp")}
          className="w-full rounded-lg bg-white/5 p-4 text-left transition hover:bg-white/10"
        >
          <div className="flex items-center gap-3">
            <Link className="h-5 w-5 text-melo-500" />
            <div className="flex-1">
              <p className="text-sm font-medium text-foreground">RTSP stream</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Paste a stream URL for non-ONVIF cameras (Tuya, Tapo, etc.).
              </p>
            </div>
          </div>
        </button>

        <Button variant="outline" className="w-full" onClick={onClose}>
          Cancel
        </Button>
      </div>
    )
  }

  if (mode === "rtsp") {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 rounded-lg bg-white/5 p-4">
          <div className="flex flex-col gap-2">
            <Label className="text-xs text-muted-foreground">Stream Name</Label>
            <Input
              value={rtspStreamName}
              onChange={(e) => setRtspStreamName(e.target.value)}
              placeholder="e.g. Kitten Room"
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label className="text-xs text-muted-foreground">RTSP URL</Label>
            <Input
              value={rtspUrl}
              onChange={(e) => setRtspUrl(e.target.value)}
              placeholder="rtsp://user:pass@192.168.1.50:8554/stream0"
              className="font-mono text-xs"
            />
          </div>
          <Button
            className="w-full bg-melo-500 text-white hover:bg-melo-600"
            onClick={submitRtsp}
            disabled={!rtspUrl.trim() || !rtspStreamName.trim()}
          >
            Continue
          </Button>
        </div>
        <Button variant="ghost" className="w-full" onClick={() => setMode("chooser")}>
          <ArrowLeft className="h-3 w-3 mr-1" /> Back
        </Button>
      </div>
    )
  }

  if (mode === "manual") {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3 rounded-lg bg-white/5 p-4">
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2 flex flex-col gap-2">
              <Label className="text-xs text-muted-foreground">Host / IP</Label>
              <Input
                value={manualHost}
                onChange={(e) => setManualHost(e.target.value)}
                placeholder="192.168.1.50"
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label className="text-xs text-muted-foreground">ONVIF Port</Label>
              <Input
                value={manualPort}
                onChange={(e) => setManualPort(e.target.value)}
                placeholder="80"
              />
            </div>
          </div>
          <Button
            className="w-full bg-melo-500 text-white hover:bg-melo-600"
            onClick={submitManual}
            disabled={!manualHost.trim()}
          >
            Continue
          </Button>
        </div>
        <Button variant="ghost" className="w-full" onClick={() => setMode("chooser")}>
          <ArrowLeft className="h-3 w-3 mr-1" /> Back
        </Button>
      </div>
    )
  }

  // Scanning + results
  return (
    <div className="flex flex-col gap-4">
      {discovered === null ? (
        <div className="flex flex-col items-center gap-3 py-8">
          <Loader2 className="h-8 w-8 animate-spin text-melo-500" />
          <p className="text-sm text-muted-foreground">Scanning network for cameras...</p>
        </div>
      ) : discovered.length === 0 ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col items-center gap-3 rounded-lg bg-white/5 p-6 text-center">
            <WifiOff className="h-8 w-8 text-muted-foreground" />
            <div>
              <p className="text-sm text-foreground">No cameras detected</p>
              <p className="text-xs text-muted-foreground mt-1">
                Make sure the cameras are powered on and connected to this network.
              </p>
            </div>
          </div>
          <Button
            className="w-full bg-melo-500 text-white hover:bg-melo-600"
            onClick={() => setMode("manual")}
          >
            <Plus className="h-3 w-3 mr-1" /> Add camera manually
          </Button>
          <Button variant="ghost" className="w-full" onClick={() => setMode("chooser")}>
            <ArrowLeft className="h-3 w-3 mr-1" /> Back
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <Badge variant="outline" className="self-start bg-melo-100/10 text-melo-500 border-melo-500/30">
            {discovered.length} camera{discovered.length !== 1 ? "s" : ""} found
          </Badge>
          <div className="flex flex-col gap-2">
            {discovered.map((cam, i) => (
              <div
                key={`${cam.host}:${cam.port}`}
                className={cn(
                  "flex items-center gap-3 rounded-lg bg-white/5 p-3 cursor-pointer transition",
                  !selectedIndices.has(i) && "opacity-50",
                )}
                onClick={() => toggleCamera(i)}
              >
                <Checkbox
                  checked={selectedIndices.has(i)}
                  onCheckedChange={() => toggleCamera(i)}
                  onClick={(e) => e.stopPropagation()}
                />
                <Camera className="h-4 w-4 text-melo-500" />
                <div className="flex-1">
                  <p className="text-sm text-foreground">
                    ONVIF Camera
                  </p>
                  <p className="text-xs font-mono text-muted-foreground">
                    {cam.host}:{cam.port}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <Button
            className="w-full mt-1 bg-melo-500 text-white hover:bg-melo-600"
            disabled={selectedCameras.length === 0}
            onClick={() => onComplete(selectedCameras)}
          >
            Enter Credentials{selectedCameras.length > 0 ? ` (${selectedCameras.length})` : ""}
          </Button>
          <Button variant="ghost" className="w-full" onClick={() => setMode("manual")}>
            <Plus className="h-3 w-3 mr-1" /> Add another manually
          </Button>
          <Button variant="ghost" className="w-full" onClick={() => setMode("chooser")}>
            <ArrowLeft className="h-3 w-3 mr-1" /> Back
          </Button>
        </div>
      )}
    </div>
  )
}
