import { create } from "zustand"
import { supabase } from "@/services/supabase"
import type { Cat } from "@/types"

interface CatStore {
  cats: Cat[]
  loading: boolean
  fetchForShelter: (shelterId: string) => Promise<void>
  create: (cat: Omit<Cat, "id" | "created_at" | "updated_at">) => Promise<Cat | null>
  update: (id: string, patch: Partial<Cat>) => Promise<void>
  remove: (id: string) => Promise<void>
}

export const useCatStore = create<CatStore>((set) => ({
  cats: [],
  loading: false,

  fetchForShelter: async (shelterId) => {
    set({ loading: true })
    const { data } = await supabase
      .from("cats")
      .select("*")
      .eq("shelter_id", shelterId)
      .order("name")
    set({ cats: (data as Cat[]) ?? [], loading: false })
  },

  create: async (cat) => {
    const { data, error } = await supabase.from("cats").insert(cat).select().single()
    if (error || !data) return null
    const created = data as Cat
    set((s) => ({ cats: [...s.cats, created] }))
    return created
  },

  update: async (id, patch) => {
    const { data } = await supabase.from("cats").update(patch).eq("id", id).select().single()
    if (data) {
      set((s) => ({
        cats: s.cats.map((c) => (c.id === id ? (data as Cat) : c)),
      }))
    }
  },

  remove: async (id) => {
    await supabase.from("cats").delete().eq("id", id)
    set((s) => ({ cats: s.cats.filter((c) => c.id !== id) }))
  },
}))
