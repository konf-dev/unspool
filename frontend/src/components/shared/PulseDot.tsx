export function PulseDot({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative flex items-center justify-center">
        <div className="w-2 h-2 rounded-full bg-primary animate-pulse-sage" />
        <div className="absolute w-4 h-4 rounded-full bg-primary/10 animate-ping" />
      </div>
      {label && (
        <span className="text-[11px] tracking-wider text-on-surface-variant/60 font-medium">
          {label}
        </span>
      )}
    </div>
  )
}
