import { type ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'tertiary'

const variants: Record<Variant, string> = {
  primary:
    'bg-primary text-on-primary rounded-full font-medium tracking-wide hover:bg-primary-dim active:scale-[0.98] transition-all duration-300',
  secondary:
    'bg-surface-container-high text-on-surface-variant rounded-full font-light tracking-wide hover:text-on-surface hover:bg-surface-bright active:scale-[0.98] transition-all duration-300',
  tertiary:
    'text-secondary tracking-wide hover:bg-surface-container-high rounded-full transition-all duration-300',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

export function Button({ variant = 'primary', className = '', children, ...props }: ButtonProps) {
  return (
    <button
      className={`px-6 py-3 text-sm ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
