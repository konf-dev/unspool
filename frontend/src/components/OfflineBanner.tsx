import './OfflineBanner.css'

interface OfflineBannerProps {
  visible: boolean
}

export function OfflineBanner({ visible }: OfflineBannerProps) {
  return (
    <div
      className={`offline-banner ${visible ? 'visible' : ''}`}
      role="alert"
      aria-hidden={!visible}
    >
      <span className="offline-banner-dot" />
      offline — messages will send when you're back
    </div>
  )
}
