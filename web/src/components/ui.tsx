import { Link, type LinkProps } from 'react-router-dom'
import { t, useLocale } from '../i18n'
import { ReactNode } from 'react'

export function Badge({
  children,
  tone = 'terracotta',
}: {
  children: ReactNode
  tone?: 'terracotta' | 'gold' | 'teal'
}) {
  useLocale()

  const tones: Record<string, string> = {
    terracotta: 'bg-terracotta-light text-terracotta-dark',
    gold: 'bg-gold-light text-gold',
    teal: 'bg-teal-light text-teal',
  }
  return (
    <span className={`text-[10px] font-semibold px-2.5 py-1 rounded-full ${tones[tone]}`}>
      {t(children)}
    </span>
  )
}

export function PillButton({
  children,
  variant = 'primary',
  className = '',
  ...rest
}: {
  children: ReactNode
  variant?: 'primary' | 'outline' | 'teal' | 'ghost'
  className?: string
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  useLocale()

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
      {t(children)}
    </button>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  useLocale()

  return (
    <div className={`bg-panel border border-border rounded-xl2 ${className}`}>{t(children)}</div>
  )
}

export function PillLink({
  children,
  variant = 'primary',
  className = '',
  ...props
}: LinkProps & { variant?: 'primary' | 'outline' | 'teal' | 'ghost' }) {
  const variants = {
    primary: 'bg-terracotta text-cream',
    outline: 'border border-border text-ink2',
    teal: 'bg-teal text-cream',
    ghost: 'text-muted2',
  }
  return (
    <Link
      {...props}
      className={`inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium transition ${variants[variant]} ${className}`}
    >
      {children}
    </Link>
  )
}
