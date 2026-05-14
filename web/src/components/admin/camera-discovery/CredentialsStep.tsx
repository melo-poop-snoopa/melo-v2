import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { ArrowLeft, ArrowRight } from "lucide-react"
import type { DiscoveredCamera } from "@/types"

interface CredentialsStepProps {
  cameras: DiscoveredCamera[]
  onSubmit: (username: string, password: string, streamNames: Map<string, string>) => void
  onBack: () => void
}

export function CredentialsStep({ cameras, onSubmit, onBack }: CredentialsStepProps) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [streamNames, setStreamNames] = useState<Map<string, string>>(
    () => new Map(cameras.map((c) => [`${c.host}:${c.port}`, `Camera ${c.host}`]))
  )

  const isValid = username.trim() !== ""

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (isValid) {
      onSubmit(username.trim(), password, streamNames)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Provide ONVIF credentials for{" "}
        <span className="text-foreground font-medium">{cameras.length}</span>{" "}
        selected camera{cameras.length !== 1 ? "s" : ""}.
        {cameras.length > 1 && (
          <span className="block mt-1 text-muted-foreground">
            The same credentials will be used for all selected cameras.
          </span>
        )}
      </p>

      <div className="flex flex-col gap-1 rounded-lg bg-white/5 p-2">
        {cameras.map((cam) => (
          <div key={`${cam.host}:${cam.port}`} className="flex items-center gap-2 px-1 py-0.5 text-xs">
            <span className="text-muted-foreground">ONVIF</span>
            <span className="font-mono text-muted-foreground">{cam.host}:{cam.port}</span>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-4 py-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor="onvif-username">Username</Label>
          <Input
            id="onvif-username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="admin"
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="onvif-password">Password</Label>
          <Input
            id="onvif-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password (optional for some cameras)"
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label>Stream names</Label>
          <p className="text-xs text-muted-foreground">
            Name each camera stream so viewers know what they're watching.
          </p>
          {cameras.map((cam) => {
            const key = `${cam.host}:${cam.port}`
            return (
              <div key={key} className="flex items-center gap-2">
                <span className="text-xs font-mono text-muted-foreground w-32 shrink-0 truncate">
                  {cam.host}:{cam.port}
                </span>
                <Input
                  value={streamNames.get(key) ?? ""}
                  onChange={(e) =>
                    setStreamNames((prev) => new Map(prev).set(key, e.target.value))
                  }
                  placeholder="e.g. Kitten Room"
                  className="text-sm"
                />
              </div>
            )
          })}
        </div>
      </div>

      <div className="flex justify-between pt-2">
        <Button
          type="button"
          variant="ghost"
          onClick={onBack}
          className="gap-1 text-muted-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <Button
          type="submit"
          disabled={!isValid}
          className="gap-1 bg-melo-500 text-white hover:bg-melo-600"
        >
          Test & Save
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    </form>
  )
}
