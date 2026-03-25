import { useCallback } from 'react'
import { motion, useMotionValue, useTransform, type PanInfo } from 'framer-motion'
import { usePlateStore } from '@/stores/plateStore'
import { PlateSummary } from './PlateSummary'
import { PlateItem } from './PlateItem'
import { PlateHandle } from './PlateHandle'

const PLATE_HEIGHT = 400

export function PlateOverlay() {
  const { summary, items, isOpen, setOpen } = usePlateStore()
  const y = useMotionValue(-PLATE_HEIGHT)
  const opacity = useTransform(y, [-PLATE_HEIGHT, 0], [0, 1])

  const handleDrag = useCallback(
    (_: unknown, info: PanInfo) => {
      // Show plate while dragging down
      if (info.offset.y > 20 && !isOpen) {
        setOpen(true)
      }
    },
    [isOpen, setOpen],
  )

  const handleDragEnd = useCallback(() => {
    // ALWAYS snap back — no lock threshold. Core anti-guilt mechanic.
    // User holds = sees plate. Releases = plate gone.
    setOpen(false)
  }, [setOpen])

  const isEmpty = items.length === 0 && !summary

  return (
    <motion.div
      className="fixed top-0 left-0 right-0 z-50 flex flex-col items-center touch-none"
      drag="y"
      dragConstraints={{ top: -PLATE_HEIGHT, bottom: 0 }}
      dragElastic={0.2}
      dragMomentum={false}
      onDrag={handleDrag}
      onDragEnd={handleDragEnd}
      style={{ y }}
      animate={{ y: isOpen ? 0 : -PLATE_HEIGHT }}
      transition={{ type: 'tween', duration: 0.3, ease: 'easeInOut' }}
    >
      <motion.div
        className="w-full bg-[#161513] rounded-b-[2.5rem] shadow-[0_20px_40px_rgba(0,0,0,0.6)] relative overflow-hidden flex flex-col pt-4 pb-10"
        style={{ opacity }}
      >
        <div className="px-8 mt-12 flex flex-col space-y-8">
          {isEmpty ? (
            <p className="text-on-surface-variant/50 text-sm text-center py-8 tracking-wide">
              nothing on your plate right now
            </p>
          ) : (
            <>
              {summary && <PlateSummary summary={summary} />}

              <section className="space-y-5" role="list" aria-label="Current items">
                {items.map((item) => (
                  <PlateItem key={item.id} item={item} />
                ))}
              </section>
            </>
          )}
        </div>

        <PlateHandle />

        <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-primary/5 rounded-full blur-[80px] pointer-events-none" />
      </motion.div>
    </motion.div>
  )
}
