import { useState } from 'react'
import { initials } from '../auth'

export default function Avatar({
  name,
  src,
  className = 'h-9 w-9',
}: {
  name: string
  src?: string
  className?: string
}) {
  const [failedSource, setFailedSource] = useState<string | null>(null)
  if (src && failedSource !== src)
    return (
      <img
        src={src}
        alt={name}
        loading="lazy"
        decoding="async"
        onError={() => setFailedSource(src)}
        className={`shrink-0 rounded-full object-cover ${className}`}
      />
    )
  return (
    <span
      role="img"
      aria-label={name || 'Avatar'}
      dir="auto"
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-terracotta-light text-xs font-semibold text-terracotta-dark ${className}`}
    >
      {initials(name)}
    </span>
  )
}
