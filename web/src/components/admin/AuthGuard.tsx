import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { useAuthStore } from "@/store/auth-store"

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (!loading && !session) {
      navigate("/app/login", { replace: true })
    }
  }, [session, loading])

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Loading…
      </div>
    )
  }

  if (!session) return null
  return <>{children}</>
}
