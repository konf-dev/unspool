import { useState, useCallback, useEffect } from 'react'
import { getApiUrl } from '../lib/api'

function isPushSupported(): boolean {
  return 'PushManager' in window && 'serviceWorker' in navigator && 'Notification' in window
}

function isStandalone(): boolean {
  const nav = navigator as Navigator & { standalone?: boolean }
  return (
    nav.standalone === true ||
    window.matchMedia('(display-mode: standalone)').matches
  )
}

type PermissionState = NotificationPermission | 'unsupported'

interface UsePushReturn {
  isSupported: boolean
  permissionState: PermissionState
  requestPermission: () => Promise<void>
}

export function usePush(token: string, messageCount: number): UsePushReturn {
  const [isSupported] = useState(() => isPushSupported())
  const [permissionState, setPermissionState] = useState<PermissionState>(() =>
    isPushSupported() ? Notification.permission : 'unsupported',
  )
  const [hasRequested, setHasRequested] = useState(false)

  const requestPermission = useCallback(async () => {
    if (!isSupported || hasRequested) return

    const permission = await Notification.requestPermission()
    setPermissionState(permission)
    setHasRequested(true)

    if (permission !== 'granted') return

    const registration = await navigator.serviceWorker.ready
    const vapidKey = import.meta.env.VITE_VAPID_PUBLIC_KEY as string | undefined

    if (!vapidKey) return

    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: vapidKey,
    })

    try {
      await fetch(`${getApiUrl()}/api/push/subscribe`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(subscription.toJSON()),
      })
    } catch {
      // Push subscription registration is non-critical
    }
  }, [isSupported, hasRequested, token])

  useEffect(() => {
    if (!isSupported || hasRequested) return
    if (permissionState !== 'default') return

    const shouldPrompt = messageCount >= 6 && (isStandalone() || !('standalone' in navigator))

    if (shouldPrompt) {
      void requestPermission()
    }
  }, [isSupported, hasRequested, permissionState, messageCount, requestPermission])

  return { isSupported, permissionState, requestPermission }
}
