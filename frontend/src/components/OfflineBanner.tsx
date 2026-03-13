import './OfflineBanner.css'

interface OfflineBannerProps {
  visible: boolean
}

export function OfflineBanner({ visible }: OfflineBannerProps) {
  if (!visible) return null

  return (
    <div className="offline-banner" role="alert">
      <span className="offline-banner-dot" />
      offline — messages will send when you're back
    </div>
  )
}
