export interface Shelter {
  id: string
  name: string
  slug: string
  description: string | null
  location: string | null
  logo_url: string | null
  donation_url: string | null
  verification: "unverified" | "verified"
  impact_metrics: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface Stream {
  id: string
  shelter_id: string
  name: string
  hls_url: string | null
  thumbnail_url: string | null
  status: "live" | "offline" | "starting"
  last_heartbeat: string | null
  created_at: string
  updated_at: string
}

export interface Cat {
  id: string
  shelter_id: string
  stream_id: string | null
  name: string
  age_bracket: "kitten" | "adult" | "senior"
  personality: string[]
  photo_url: string | null
  created_at: string
  updated_at: string
}

export const AGE_BRACKET_LABELS: Record<Cat["age_bracket"], string> = {
  kitten: "Kitten",
  adult: "Adult",
  senior: "Senior",
}

export const AGE_BRACKET_COLORS: Record<Cat["age_bracket"], string> = {
  kitten: "bg-mint-100 text-mint-700",
  adult: "bg-lavender-100 text-lavender-600",
  senior: "bg-peach-100 text-peach-600",
}

export const HEARTBEAT_STALE_MS = 45_000

export interface ShelterCamera {
  id: string
  shelter_id: string
  stream_id: string | null
  ip_address: string
  onvif_port: number
  username: string | null
  created_at: string
  updated_at: string
}

export interface DiscoveredCamera {
  host: string
  port: number
  xaddrs: string
  device_uuid: string | null
}

export type DiscoveryStep = "scan" | "credentials" | "testing" | "results"
