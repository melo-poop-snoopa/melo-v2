import { BrowserRouter, Routes, Route } from "react-router-dom"

function Landing() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <h1 className="text-4xl font-display font-bold text-melo-500">
        melo — live cat streams
      </h1>
    </div>
  )
}

function ShelterPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <h1 className="text-2xl font-display">Shelter Page (placeholder)</h1>
    </div>
  )
}

function Dashboard() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <h1 className="text-2xl font-display">Shelter Admin Dashboard (placeholder)</h1>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/shelter/:id" element={<ShelterPage />} />
        <Route path="/dashboard/*" element={<Dashboard />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
