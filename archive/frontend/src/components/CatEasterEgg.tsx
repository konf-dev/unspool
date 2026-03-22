import { useEffect, useCallback } from 'react'
import './CatEasterEgg.css'

type CatVariant = 'hopper' | 'observer' | 'peek'

interface CatEasterEggProps {
  variant: CatVariant
  onDone: () => void
}

const ANIMATION_DURATIONS: Record<CatVariant, number> = {
  hopper: 4000,
  observer: 4000,
  peek: 3500,
}

function CatSvg({ variant }: { variant: CatVariant }) {
  if (variant === 'peek') {
    return (
      <svg
        width="24"
        height="28"
        viewBox="0 0 24 28"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M4 28V18C4 12 8 8 12 8C16 8 20 12 20 18V28"
          fill="currentColor"
        />
        <path d="M4 14L1 6L7 11Z" fill="currentColor" />
        <path d="M20 14L23 6L17 11Z" fill="currentColor" />
        <circle cx="9" cy="16" r="1.5" fill="var(--color-sky-bottom)" />
        <circle cx="15" cy="16" r="1.5" fill="var(--color-sky-bottom)" />
      </svg>
    )
  }

  if (variant === 'observer') {
    return (
      <svg
        width="28"
        height="24"
        viewBox="0 0 28 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M8 24V14C8 9 11 6 14 6C17 6 20 9 20 14V24"
          fill="currentColor"
        />
        <path d="M8 10L5 2L11 8Z" fill="currentColor" />
        <path d="M20 10L23 2L17 8Z" fill="currentColor" />
        <circle cx="11.5" cy="13" r="1.2" fill="var(--color-sky-bottom)" />
        <circle cx="16.5" cy="13" r="1.2" fill="var(--color-sky-bottom)" />
        <path
          d="M24 22C24 22 25 20 26 22C27 24 25 24 24 22Z"
          fill="currentColor"
          className="cat-tail"
        />
      </svg>
    )
  }

  return (
    <svg
      width="30"
      height="20"
      viewBox="0 0 30 20"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M8 20V12C8 7 11 4 15 4C19 4 22 7 22 12V20"
        fill="currentColor"
      />
      <path d="M8 8L5 1L11 6Z" fill="currentColor" />
      <path d="M22 8L25 1L19 6Z" fill="currentColor" />
      <circle cx="12.5" cy="11" r="1" fill="var(--color-sky-bottom)" />
      <circle cx="17.5" cy="11" r="1" fill="var(--color-sky-bottom)" />
      <line
        x1="6"
        y1="18"
        x2="8"
        y2="16"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <line
        x1="24"
        y1="18"
        x2="22"
        y2="16"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function CatEasterEgg({ variant, onDone }: CatEasterEggProps) {
  const handleAnimationEnd = useCallback(() => {
    onDone()
  }, [onDone])

  useEffect(() => {
    const timer = setTimeout(handleAnimationEnd, ANIMATION_DURATIONS[variant])
    return () => clearTimeout(timer)
  }, [variant, handleAnimationEnd])

  return (
    <div
      className={`cat-easter-egg cat-${variant}`}
      aria-hidden="true"
    >
      <CatSvg variant={variant} />
    </div>
  )
}
