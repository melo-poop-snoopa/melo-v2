import { useState, type FormEvent, type ReactNode } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

const SITE_PASSWORD = import.meta.env.VITE_SITE_PASSWORD as string | undefined
const STORAGE_KEY = "melo-gate-ok"

export function SiteGate({ children }: { children: ReactNode }) {
  if (!SITE_PASSWORD) return <>{children}</>

  const [authed, setAuthed] = useState(
    () => sessionStorage.getItem(STORAGE_KEY) === "1",
  )
  const [value, setValue] = useState("")
  const [error, setError] = useState(false)

  if (authed) return <>{children}</>

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (value === SITE_PASSWORD) {
      sessionStorage.setItem(STORAGE_KEY, "1")
      setAuthed(true)
    } else {
      setError(true)
      setValue("")
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <form onSubmit={handleSubmit} className="flex w-full max-w-xs flex-col gap-4">
        <span className="text-center font-display text-2xl font-bold text-melo-500">
          melo
        </span>
        <p className="text-center text-sm text-muted-foreground">
          Enter the password to continue
        </p>
        <Input
          type="password"
          placeholder="Password"
          value={value}
          onChange={(e) => {
            setValue(e.target.value)
            setError(false)
          }}
          aria-invalid={error}
          autoFocus
        />
        {error && (
          <p className="text-center text-sm text-destructive">Wrong password</p>
        )}
        <Button type="submit">Enter</Button>
      </form>
    </div>
  )
}
