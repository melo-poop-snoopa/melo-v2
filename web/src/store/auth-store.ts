import { create } from "zustand"
import type { Session, User } from "@supabase/supabase-js"
import { supabase } from "@/services/supabase"

interface AuthStore {
  session: Session | null
  user: User | null
  shelterId: string | null
  loading: boolean
  init: () => Promise<() => void>
  login: (email: string, password: string) => Promise<string | null>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthStore>((set) => ({
  session: null,
  user: null,
  shelterId: null,
  loading: true,

  init: async () => {
    const { data } = await supabase.auth.getSession()
    const session = data.session
    set({
      session,
      user: session?.user ?? null,
      shelterId: (session?.user?.user_metadata?.shelter_id as string) ?? null,
      loading: false,
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      set({
        session,
        user: session?.user ?? null,
        shelterId: (session?.user?.user_metadata?.shelter_id as string) ?? null,
      })
    })

    return () => subscription.unsubscribe()
  },

  login: async (email, password) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return error?.message ?? null
  },

  logout: async () => {
    await supabase.auth.signOut()
    set({ session: null, user: null, shelterId: null })
  },
}))
