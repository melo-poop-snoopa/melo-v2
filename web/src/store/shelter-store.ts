import { create } from "zustand"
import { supabase } from "@/services/supabase"
import type { Shelter, Stream } from "@/types"

interface ShelterWithStreams extends Shelter {
  streams?: Stream[]
  liveCount?: number
}

interface ShelterStore {
  shelters: ShelterWithStreams[]
  currentShelter: ShelterWithStreams | null
  loading: boolean
  fetch: () => Promise<void>
  fetchById: (id: string) => Promise<void>
}

export const useShelterStore = create<ShelterStore>((set) => ({
  shelters: [],
  currentShelter: null,
  loading: false,

  fetch: async () => {
    set({ loading: true })
    const { data: shelters } = await supabase
      .from("shelters")
      .select("*, streams(*)")
      .order("name")

    const enriched = ((shelters ?? []) as ShelterWithStreams[]).map((s) => ({
      ...s,
      liveCount: (s.streams ?? []).filter((r: Stream) => r.status === "live").length,
    }))
    set({ shelters: enriched, loading: false })
  },

  fetchById: async (id) => {
    set({ loading: true })
    const { data } = await supabase
      .from("shelters")
      .select("*, streams(*)")
      .eq("id", id)
      .single()
    if (data) {
      const shelter = data as ShelterWithStreams
      shelter.liveCount = (shelter.streams ?? []).filter((s: Stream) => s.status === "live").length
      set({ currentShelter: shelter })
    }
    set({ loading: false })
  },
}))
