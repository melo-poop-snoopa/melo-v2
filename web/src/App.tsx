import { useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { useAuthStore } from "@/store/auth-store"
import { AuthGuard } from "@/components/admin/AuthGuard"
import { AdminLayout } from "@/components/admin/AdminLayout"
import { SiteGate } from "@/components/SiteGate"
import Landing from "@/pages/Landing"
import ShelterPage from "@/pages/ShelterPage"
import LoginPage from "@/pages/admin/LoginPage"
import ProfilePage from "@/pages/admin/ProfilePage"
import CatsPage from "@/pages/admin/CatsPage"
import CamerasPage from "@/pages/admin/CamerasPage"
import SettingsPage from "@/pages/admin/SettingsPage"

function AppRoutes() {
  const { init } = useAuthStore()

  useEffect(() => {
    init()
  }, [])

  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<Landing />} />
      <Route path="/shelter/:id" element={<ShelterPage />} />

      {/* Admin */}
      <Route path="/app/login" element={<LoginPage />} />
      <Route
        path="/app"
        element={
          <AuthGuard>
            <AdminLayout />
          </AuthGuard>
        }
      >
        <Route index element={<Navigate to="/app/profile" replace />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="cats" element={<CatsPage />} />
        <Route path="cameras" element={<CamerasPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <SiteGate>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </SiteGate>
  )
}
