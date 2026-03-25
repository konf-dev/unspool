export function AmbientGlow() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      <div className="absolute -bottom-32 -left-32 w-96 h-96 bg-primary/5 rounded-full blur-[120px]" />
      <div className="absolute top-1/4 -right-32 w-64 h-64 bg-tertiary/5 rounded-full blur-[100px]" />
    </div>
  )
}
