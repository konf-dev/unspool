import { PulseDot } from '@/components/shared/PulseDot'

export function LoadingScreen() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="flex flex-col items-center gap-6">
        <h1 className="text-on-surface font-extralight text-3xl tracking-[-0.04em]">
          unspool
        </h1>
        <PulseDot />
      </div>
    </div>
  )
}
