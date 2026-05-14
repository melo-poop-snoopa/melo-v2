import * as React from "react"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

interface CheckboxProps {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  className?: string
  onClick?: (e: React.MouseEvent) => void
}

export function Checkbox({ checked, onCheckedChange, className, onClick }: CheckboxProps) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={checked}
      onClick={(e) => {
        onClick?.(e)
        onCheckedChange?.(!checked)
      }}
      className={cn(
        "flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors",
        checked
          ? "border-melo-500 bg-melo-500 text-white"
          : "border-white/20 bg-transparent hover:border-white/40",
        className,
      )}
    >
      {checked && <Check className="h-3 w-3" />}
    </button>
  )
}
