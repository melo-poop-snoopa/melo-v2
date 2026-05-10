import { useEffect, useRef, useState } from "react"
import { Pencil, Plus, Trash2, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { useAuthStore } from "@/store/auth-store"
import { useCatStore } from "@/store/cat-store"
import { CatProfileCard } from "@/components/CatProfileCard"
import { supabase } from "@/services/supabase"
import type { Cat } from "@/types"
import { AGE_BRACKET_LABELS } from "@/types"
import { toast, Toaster } from "sonner"

type FormState = {
  name: string
  age_bracket: Cat["age_bracket"]
  personality: string[]
  stream_id: string
  photo_url: string | null
}

const emptyForm = (): FormState => ({
  name: "",
  age_bracket: "adult",
  personality: [],
  stream_id: "",
  photo_url: null,
})

export default function CatsPage() {
  const { shelterId } = useAuthStore()
  const { cats, fetchForShelter, create, update, remove } = useCatStore()
  const [streams, setStreams] = useState<{ id: string; name: string }[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [editCat, setEditCat] = useState<Cat | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm())
  const [tagInput, setTagInput] = useState("")
  const [saving, setSaving] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!shelterId) return
    fetchForShelter(shelterId)
    supabase.from("streams").select("id, name").eq("shelter_id", shelterId).then(({ data }) => {
      setStreams((data ?? []) as { id: string; name: string }[])
    })
  }, [shelterId])

  const openAdd = () => {
    setEditCat(null)
    setForm(emptyForm())
    setTagInput("")
    setDialogOpen(true)
  }

  const openEdit = (cat: Cat) => {
    setEditCat(cat)
    setForm({
      name: cat.name,
      age_bracket: cat.age_bracket,
      personality: cat.personality,
      stream_id: cat.stream_id ?? "",
      photo_url: cat.photo_url,
    })
    setTagInput("")
    setDialogOpen(true)
  }

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !shelterId) return
    const path = `${shelterId}/${Date.now()}-${file.name}`
    const { error } = await supabase.storage.from("cat-photos").upload(path, file)
    if (error) { toast.error("Photo upload failed"); return }
    const { data: { publicUrl } } = supabase.storage.from("cat-photos").getPublicUrl(path)
    setForm((f) => ({ ...f, photo_url: publicUrl }))
  }

  const addTag = () => {
    const tag = tagInput.trim()
    if (!tag || form.personality.includes(tag)) return
    setForm((f) => ({ ...f, personality: [...f.personality, tag] }))
    setTagInput("")
  }

  const removeTag = (tag: string) =>
    setForm((f) => ({ ...f, personality: f.personality.filter((t) => t !== tag) }))

  const handleSave = async () => {
    if (!shelterId || !form.name.trim()) return
    setSaving(true)
    const payload = {
      shelter_id: shelterId,
      name: form.name.trim(),
      age_bracket: form.age_bracket,
      personality: form.personality,
      stream_id: form.stream_id || null,
      photo_url: form.photo_url,
    }
    if (editCat) {
      await update(editCat.id, payload)
      toast.success("Cat updated")
    } else {
      const created = await create(payload)
      if (!created) toast.error("Failed to create cat")
      else toast.success(`${form.name} added!`)
    }
    setSaving(false)
    setDialogOpen(false)
  }

  const handleDelete = async () => {
    if (!deleteId) return
    await remove(deleteId)
    toast.success("Cat removed")
    setDeleteId(null)
  }

  return (
    <div>
      <Toaster />
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold text-foreground">Cats</h1>
        <Button onClick={openAdd} className="bg-melo-500 text-white hover:bg-melo-600">
          <Plus className="mr-1.5 h-4 w-4" /> Add cat
        </Button>
      </div>

      {cats.length === 0 ? (
        <p className="text-muted-foreground">No cats yet — add one!</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {cats.map((cat) => (
            <div key={cat.id} className="relative group">
              <CatProfileCard cat={cat} />
              <div className="absolute right-2 top-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() => openEdit(cat)}
                  className="rounded-md bg-white/90 p-1.5 shadow hover:bg-white"
                >
                  <Pencil className="h-3.5 w-3.5 text-foreground" />
                </button>
                <button
                  onClick={() => setDeleteId(cat.id)}
                  className="rounded-md bg-white/90 p-1.5 shadow hover:bg-red-50"
                >
                  <Trash2 className="h-3.5 w-3.5 text-red-500" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add/edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editCat ? "Edit cat" : "Add cat"}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            {/* Photo */}
            <div className="flex items-center gap-3">
              <div className="h-14 w-14 overflow-hidden rounded-full bg-melo-100">
                {form.photo_url ? (
                  <img src={form.photo_url} alt="Cat" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-2xl">🐱</div>
                )}
              </div>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="text-sm text-melo-600 hover:underline"
              >
                Upload photo
              </button>
              <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handlePhotoUpload} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cat-name">Name *</Label>
              <Input
                id="cat-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Biscuit"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Age bracket</Label>
              <Select
                value={form.age_bracket}
                onValueChange={(v) => setForm((f) => ({ ...f, age_bracket: v as Cat["age_bracket"] }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(AGE_BRACKET_LABELS).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Personality tags</Label>
              <div className="flex gap-2">
                <Input
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
                  placeholder="Type tag, press Enter"
                />
                <Button type="button" variant="outline" onClick={addTag}>Add</Button>
              </div>
              {form.personality.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {form.personality.map((tag) => (
                    <span
                      key={tag}
                      className="flex items-center gap-1 rounded-full bg-melo-100 px-2.5 py-0.5 text-xs text-melo-700"
                    >
                      {tag}
                      <button onClick={() => removeTag(tag)}>
                        <X className="h-3 w-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>Assign to stream (optional)</Label>
              <Select
                value={form.stream_id}
                onValueChange={(v) => setForm((f) => ({ ...f, stream_id: v }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">None</SelectItem>
                  {streams.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
            <Button
              className="bg-melo-500 text-white hover:bg-melo-600"
              onClick={handleSave}
              disabled={saving || !form.name.trim()}
            >
              {saving ? "Saving…" : editCat ? "Save changes" : "Add cat"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteId} onOpenChange={(o) => !o && setDeleteId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this cat?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the cat profile. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-red-600 text-white hover:bg-red-700"
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
