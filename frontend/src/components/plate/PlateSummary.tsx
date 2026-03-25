interface PlateSummaryProps {
  summary: string
}

export function PlateSummary({ summary }: PlateSummaryProps) {
  return (
    <section>
      <div className="max-w-[85%]">
        <span className="text-[10px] tracking-[0.2em] uppercase text-primary/60 font-medium mb-3 block">
          perspective
        </span>
        <h1 className="text-2xl font-light leading-[1.4] text-on-surface tracking-tight">
          {summary}
        </h1>
      </div>
    </section>
  )
}
