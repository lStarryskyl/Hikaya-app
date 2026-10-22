import { ReactNode } from 'react'

export function Badge({ children, tone = 'terracotta' }: { children: ReactNode; tone?: 'terracotta' | 'gold' | 'teal' }) {
  const tones: Record<string, string> = {
    terracotta: 'bg-terracotta-light text-terracotta-dark',
    gold: 'bg-gold-light text-gold',
    teal: 'bg-teal-light text-teal',
  }
  return (
    <span className={`text-[10px] font-semibold px-2.5 py-1 rounded-full ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function PillButton({
  children,
  variant = 'primary',
  className = '',
  ...rest
}: { children: ReactNode; variant?: 'primary' | 'outline' | 'teal' | 'ghost'; className?: string } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const variants: Record<string, string> = {
    primary: 'bg-terracotta text-cream hover:brightness-105',
    outline: 'border border-border text-ink2 hover:bg-cream',
    teal: 'bg-teal text-cream hover:brightness-105',
    ghost: 'text-muted2 hover:bg-cream',
  }
  return (
    <button
      className={`inline-flex items-center gap-2 text-sm font-medium px-4 py-2.5 rounded-full transition ${variants[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-panel border border-border rounded-xl2 ${className}`}>
      {children}
    </div>
  )
}
