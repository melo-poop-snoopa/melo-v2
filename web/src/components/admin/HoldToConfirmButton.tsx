import { useCallback, useRef, useState } from "react"
import { cn } from "@/lib/utils"

interface HoldToConfirmButtonProps {
  onConfirm: () => void
  holdDuration?: number
  disabled?: boolean
  label?: string
  activeLabel?: string
  className?: string
}

export function HoldToConfirmButton({
  onConfirm,
  holdDuration = 3000,
  disabled = false,
  label = "Stop Stream",
  activeLabel = "Hold to stop...",
  className,
}: HoldToConfirmButtonProps) {
  const [progress, setProgress] = useState(0)
  const [holding, setHolding] = useState(false)
  const rafRef = useRef<number>(0)
  const startRef = useRef<number>(0)

  const reset = useCallback(() => {
    setHolding(false)
    setProgress(0)
    cancelAnimationFrame(rafRef.current)
  }, [])

  const tick = useCallback(() => {
    const elapsed = performance.now() - startRef.current
    const p = Math.min(elapsed / holdDuration, 1)
    setProgress(p)

    if (p >= 1) {
      setHolding(false)
      setProgress(0)
      onConfirm()
      return
    }

    rafRef.current = requestAnimationFrame(tick)
  }, [holdDuration, onConfirm])

  const handlePointerDown = useCallback(() => {
    if (disabled) return
    startRef.current = performance.now()
    setHolding(true)
    rafRef.current = requestAnimationFrame(tick)
  }, [disabled, tick])

  return (
    <button
      type="button"
      onPointerDown={handlePointerDown}
      onPointerUp={reset}
      onPointerLeave={reset}
      onPointerCancel={reset}
      disabled={disabled}
      aria-label={`${label} — press and hold for ${holdDuration / 1000} seconds to confirm`}
      className={cn(
        "relative select-none overflow-hidden rounded-lg px-6 py-3 text-sm font-semibold transition-colors",
        "border border-red-500/30 text-red-400",
        disabled
          ? "cursor-not-allowed opacity-40"
          : "cursor-pointer hover:border-red-500/50 hover:text-red-300 active:scale-[0.98]",
        className,
      )}
    >
      <div
        className="pointer-events-none absolute inset-0 origin-left transition-none"
        style={{
          transform: `scaleX(${progress})`,
          background: `linear-gradient(90deg, rgba(245, 158, 11, 0.25), rgba(239, 68, 68, 0.35))`,
        }}
      />
      <span className="relative z-10">{holding ? activeLabel : label}</span>
    </button>
  )
}
