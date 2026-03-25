import { PulseDot } from '@/components/shared/PulseDot'

export function ThinkingIndicator() {
  return (
    <div className="pl-6 py-2 animate-fade-in">
      <PulseDot label="thinking..." />
    </div>
  )
}
