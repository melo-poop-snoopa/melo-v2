import { useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { useAuthStore } from "@/store/auth-store"
import { AuthGuard } from "@/components/admin/AuthGuard"
import { AdminLayout } from "@/components/admin/AdminLayout"
import Landing from "@/pages/Landing"
import ShelterPage from "@/pages/ShelterPage"
import LoginPage from "@/pages/admin/LoginPage"
import ProfilePage from "@/pages/admin/ProfilePage"
import CatsPage from "@/pages/admin/CatsPage"
import StreamsPage from "@/pages/admin/StreamsPage"
import CamerasPage from "@/pages/admin/CamerasPage"

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
        <Route path="streams" element={<StreamsPage />} />
        <Route path="cameras" element={<CamerasPage />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
