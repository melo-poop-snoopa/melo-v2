import { create } from "zustand"
import { supabase } from "@/services/supabase"
import type { Stream } from "@/types"

interface StreamStore {
  streams: Stream[]
  loading: boolean
  fetch: () => Promise<void>
  subscribe: () => () => void
  setStreams: (streams: Stream[]) => void
  upsertStream: (stream: Stream) => void
}

export const useStreamStore = create<StreamStore>((set, get) => ({
  streams: [],
  loading: false,

  fetch: async () => {
    set({ loading: true })
    const { data } = await supabase.from("streams").select("*").order("created_at")
    set({ streams: (data as Stream[]) ?? [], loading: false })
  },

  subscribe: () => {
    const channel = supabase
      .channel("streams-realtime")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "streams" },
        (payload) => {
          if (payload.eventType === "UPDATE" || payload.eventType === "INSERT") {
            get().upsertStream(payload.new as Stream)
          }
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  },

  setStreams: (streams) => set({ streams }),

  upsertStream: (updated) =>
    set((state) => ({
      streams: state.streams.some((s) => s.id === updated.id)
        ? state.streams.map((s) => (s.id === updated.id ? updated : s))
        : [...state.streams, updated],
    })),
}))
