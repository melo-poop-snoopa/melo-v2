import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { Cat, LayoutDashboard, Radio, LogOut } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuthStore } from "@/store/auth-store"
import { Button } from "@/components/ui/button"

const NAV = [
  { to: "/app/profile", label: "Shelter Profile", icon: LayoutDashboard },
  { to: "/app/cats", label: "Cats", icon: Cat },
  { to: "/app/streams", label: "Streams", icon: Radio },
]

export function AdminLayout() {
  const { logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate("/app/login", { replace: true })
  }

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-white/10 bg-white/3 px-4 py-6">
        <span className="mb-8 px-2 font-display text-xl font-bold text-melo-500">melo admin</span>

        <nav className="flex flex-col gap-1">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-melo-100 text-melo-700 font-medium dark:bg-melo-900/40 dark:text-melo-300"
                    : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-muted-foreground"
            onClick={handleLogout}
          >
            <LogOut className="mr-2 h-4 w-4" /> Logout
          </Button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto p-8">
        <Outlet />
      </main>
    </div>
  )
}
