import { cn } from "@/lib/utils"
import type { Cat } from "@/types"
import { AGE_BRACKET_LABELS, AGE_BRACKET_COLORS } from "@/types"

interface CatProfileCardProps {
  cat: Cat
  className?: string
}

export function CatProfileCard({ cat, className }: CatProfileCardProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 text-center",
        className
      )}
    >
      {/* Photo */}
      <div className="relative h-20 w-20 overflow-hidden rounded-full bg-melo-100">
        {cat.photo_url ? (
          <img src={cat.photo_url} alt={cat.name} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-3xl">🐱</div>
        )}
      </div>

      {/* Name + age */}
      <div className="flex flex-col items-center gap-1">
        <h4 className="font-display font-semibold text-foreground">{cat.name}</h4>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-xs font-medium",
            AGE_BRACKET_COLORS[cat.age_bracket]
          )}
        >
          {AGE_BRACKET_LABELS[cat.age_bracket]}
        </span>
      </div>

      {/* Personality tags */}
      {cat.personality.length > 0 && (
        <div className="flex flex-wrap justify-center gap-1">
          {cat.personality.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-melo-50 px-2 py-0.5 text-xs text-melo-700 dark:bg-melo-900/30 dark:text-melo-300"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
