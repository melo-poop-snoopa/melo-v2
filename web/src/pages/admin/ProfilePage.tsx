import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useAuthStore } from "@/store/auth-store"
import { supabase } from "@/services/supabase"
import type { Shelter } from "@/types"
import { Toaster } from "sonner"
import { toast } from "sonner"

export default function ProfilePage() {
  const { shelterId } = useAuthStore()
  const [shelter, setShelter] = useState<Shelter | null>(null)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: "",
    description: "",
    location: "",
    donation_url: "",
    adoptions_2025: "",
    cats_in_care: "",
  })

  useEffect(() => {
    if (!shelterId) return
    supabase
      .from("shelters")
      .select("*")
      .eq("id", shelterId)
      .single()
      .then(({ data }) => {
        if (!data) return
        const s = data as Shelter
        setShelter(s)
        setForm({
          name: s.name,
          description: s.description ?? "",
          location: s.location ?? "",
          donation_url: s.donation_url ?? "",
          adoptions_2025: String((s.impact_metrics as Record<string, unknown>)?.adoptions_2025 ?? ""),
          cats_in_care: String((s.impact_metrics as Record<string, unknown>)?.cats_in_care ?? ""),
        })
      })
  }, [shelterId])

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !shelterId) return
    const ext = file.name.split(".").pop()
    const path = `${shelterId}/logo.${ext}`
    const { error } = await supabase.storage.from("shelter-assets").upload(path, file, { upsert: true })
    if (error) { toast.error("Logo upload failed"); return }
    const { data: { publicUrl } } = supabase.storage.from("shelter-assets").getPublicUrl(path)
    await supabase.from("shelters").update({ logo_url: publicUrl }).eq("id", shelterId)
    setShelter((s) => s ? { ...s, logo_url: publicUrl } : s)
    toast.success("Logo updated")
  }

  const handleSave = async () => {
    if (!shelterId) return
    setSaving(true)
    const impact_metrics: Record<string, number> = {}
    if (form.adoptions_2025) impact_metrics.adoptions_2025 = Number(form.adoptions_2025)
    if (form.cats_in_care) impact_metrics.cats_in_care = Number(form.cats_in_care)

    const { error } = await supabase.from("shelters").update({
      name: form.name,
      description: form.description || null,
      location: form.location || null,
      donation_url: form.donation_url || null,
      impact_metrics: Object.keys(impact_metrics).length ? impact_metrics : null,
    }).eq("id", shelterId)

    setSaving(false)
    if (error) toast.error(error.message)
    else toast.success("Profile saved")
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  if (!shelterId) {
    return (
      <div className="text-muted-foreground">
        No shelter assigned to your account. Ask a platform admin to set your shelter_id in user metadata.
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      <Toaster />
      <h1 className="mb-6 font-display text-2xl font-bold text-foreground">Shelter Profile</h1>

      <div className="flex flex-col gap-5">
        {/* Logo */}
        <div className="flex items-center gap-4">
          {shelter?.logo_url ? (
            <img src={shelter.logo_url} alt="Logo" className="h-16 w-16 rounded-xl object-cover" />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-xl bg-melo-100 text-2xl">🏠</div>
          )}
          <div>
            <Label htmlFor="logo" className="cursor-pointer text-sm font-medium text-melo-600 hover:underline">
              Upload logo
            </Label>
            <input id="logo" type="file" accept="image/*" className="hidden" onChange={handleLogoUpload} />
            <p className="text-xs text-muted-foreground">PNG, JPG up to 5 MB</p>
          </div>
        </div>

        <Field label="Shelter name" id="name" value={form.name} onChange={set("name")} />
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="description">Description</Label>
          <Textarea
            id="description"
            rows={3}
            value={form.description}
            onChange={set("description")}
            placeholder="A few words about your shelter…"
          />
        </div>
        <Field label="Location" id="location" value={form.location} onChange={set("location")} placeholder="City, State" />
        <Field label="Donation URL" id="donation_url" value={form.donation_url} onChange={set("donation_url")} placeholder="https://…" />

        <div className="flex gap-4">
          <Field label="Adoptions in 2025" id="adoptions_2025" value={form.adoptions_2025} onChange={set("adoptions_2025")} type="number" />
          <Field label="Cats in care" id="cats_in_care" value={form.cats_in_care} onChange={set("cats_in_care")} type="number" />
        </div>

        <Button
          className="mt-2 bg-melo-500 text-white hover:bg-melo-600 self-start"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </div>
  )
}

function Field({
  label, id, value, onChange, placeholder, type = "text",
}: {
  label: string; id: string; value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string; type?: string
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} value={value} onChange={onChange} placeholder={placeholder} />
    </div>
  )
}
