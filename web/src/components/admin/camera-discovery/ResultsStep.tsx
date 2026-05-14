import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Check, X } from "lucide-react"
import type { TestResult } from "./TestStep"

interface ResultsStepProps {
  results: TestResult[]
  onDone: () => void
}

export function ResultsStep({ results, onDone }: ResultsStepProps) {
  const succeeded = results.filter((r) => r.success)
  const failed = results.filter((r) => !r.success)

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        {succeeded.length > 0 ? (
          <>
            <span className="text-foreground font-medium">{succeeded.length}</span>{" "}
            camera{succeeded.length !== 1 ? "s" : ""} saved and streaming.
          </>
        ) : (
          <>
            No cameras were saved. Check credentials and try again.
          </>
        )}
      </p>

      <div className="flex flex-col gap-3 max-h-[300px] overflow-y-auto">
        {/* Succeeded */}
        <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-3">
          <div className="mb-2 flex items-center gap-2">
            <Check className="h-4 w-4 text-green-500" />
            <span className="text-sm font-medium text-green-500">Saved</span>
            <Badge
              variant="outline"
              className="ml-auto text-[10px] bg-green-500/10 text-green-500 border-green-500/30"
            >
              {succeeded.length}
            </Badge>
          </div>
          {succeeded.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">None</p>
          ) : (
            <div className="flex flex-col gap-1">
              {succeeded.map((r) => (
                <div
                  key={`${r.camera.host}:${r.camera.port}`}
                  className="flex items-center justify-between rounded px-2 py-1 text-xs"
                >
                  <span className="text-foreground">{r.streamName}</span>
                  <span className="font-mono text-muted-foreground">
                    {r.camera.host}:{r.camera.port}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {failed.length > 0 && (
          <>
            <Separator />
            <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
              <div className="mb-2 flex items-center gap-2">
                <X className="h-4 w-4 text-red-500" />
                <span className="text-sm font-medium text-red-500">Failed</span>
                <Badge
                  variant="outline"
                  className="ml-auto text-[10px] bg-red-500/10 text-red-500 border-red-500/30"
                >
                  {failed.length}
                </Badge>
              </div>
              <div className="flex flex-col gap-1">
                {failed.map((r) => (
                  <div
                    key={`${r.camera.host}:${r.camera.port}`}
                    className="flex items-center justify-between rounded px-2 py-1 text-xs"
                  >
                    <span className="text-foreground">{r.streamName}</span>
                    <span className="text-red-400 truncate ml-2 max-w-[200px]">
                      {r.error}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="flex justify-end pt-2">
        <Button
          onClick={onDone}
          className="bg-melo-500 text-white hover:bg-melo-600"
        >
          Done
        </Button>
      </div>
    </div>
  )
}
