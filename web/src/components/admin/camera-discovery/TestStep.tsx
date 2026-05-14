import { useEffect, useState, useCallback, useRef } from "react"
import { Check, Loader2, X } from "lucide-react"
import { testCamera, saveCamera } from "@/services/setup-api"
import type { DiscoveredCamera } from "@/types"

export interface TestResult {
  camera: DiscoveredCamera
  streamName: string
  success: boolean
  cameraId?: string
  streamId?: string
  error?: string
}

interface TestStepProps {
  cameras: DiscoveredCamera[]
  username: string
  password: string
  streamNames: Map<string, string>
  shelterId: string
  onComplete: (results: TestResult[]) => void
}

export function TestStep({
  cameras,
  username,
  password,
  streamNames,
  shelterId,
  onComplete,
}: TestStepProps) {
  const [results, setResults] = useState<Map<string, TestResult>>(new Map())
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete
  const hasRun = useRef(false)

  const run = useCallback(async () => {
    const allResults: TestResult[] = []

    for (const cam of cameras) {
      const key = `${cam.host}:${cam.port}`
      const streamName = streamNames.get(key) || `Camera ${cam.host}`

      try {
        const testRes = await testCamera(shelterId, cam.host, cam.port, username, password)
        if (!testRes.success) {
          const result: TestResult = {
            camera: cam,
            streamName,
            success: false,
            error: testRes.error || "ONVIF connection failed",
          }
          setResults((prev) => new Map(prev).set(key, result))
          allResults.push(result)
          continue
        }

        const saveRes = await saveCamera(shelterId, {
          shelter_id: shelterId,
          host: cam.host,
          port: cam.port,
          username,
          password,
          stream_name: streamName,
        })

        const result: TestResult = {
          camera: cam,
          streamName,
          success: true,
          cameraId: saveRes.camera_id,
          streamId: saveRes.stream_id,
        }
        setResults((prev) => new Map(prev).set(key, result))
        allResults.push(result)
      } catch (err) {
        const result: TestResult = {
          camera: cam,
          streamName,
          success: false,
          error: err instanceof Error ? err.message : "Unknown error",
        }
        setResults((prev) => new Map(prev).set(key, result))
        allResults.push(result)
      }
    }

    setTimeout(() => onCompleteRef.current(allResults), 500)
  }, [cameras, username, password, streamNames, shelterId])

  useEffect(() => {
    if (hasRun.current) return
    hasRun.current = true
    void run()
  }, [run])

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Testing ONVIF connections and saving cameras...
      </p>

      <div className="flex flex-col gap-2">
        {cameras.map((cam) => {
          const key = `${cam.host}:${cam.port}`
          const result = results.get(key)

          return (
            <div
              key={key}
              className="flex items-center gap-3 rounded-lg bg-white/5 p-3"
            >
              <div className="flex h-5 w-5 items-center justify-center">
                {!result ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : result.success ? (
                  <Check className="h-4 w-4 text-green-500" />
                ) : (
                  <X className="h-4 w-4 text-red-500" />
                )}
              </div>
              <div className="flex-1">
                <p className="text-sm text-foreground">
                  {streamNames.get(key) || `Camera ${cam.host}`}
                </p>
                <p className="text-xs font-mono text-muted-foreground">
                  {cam.host}:{cam.port}
                </p>
              </div>
              {result && (
                <span
                  className={`text-xs ${
                    result.success ? "text-green-500" : "text-red-500"
                  }`}
                >
                  {result.success ? "Saved" : result.error ?? "Failed"}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
