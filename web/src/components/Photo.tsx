import { photoSrcSet, photoUrl, type Photo as PhotoData } from '../discover'

/**
 * A responsive place photo. With no photo it shows a warm gradient, so layouts keep their
 * shape while data loads or when a story has no picture.
 */
export default function Photo({
  photo,
  width,
  sizes,
  className = '',
  alt,
}: {
  photo: PhotoData | null | undefined
  /** The width it is usually shown at, in CSS pixels; picks the default file. */
  width: number
  sizes?: string
  className?: string
  alt?: string
}) {
  if (!photo) {
    return (
      <div
        aria-hidden
        className={`bg-gradient-to-br from-terracotta-light via-gold-light to-teal-light ${className}`}
      />
    )
  }
  return (
    <img
      src={photoUrl(photo, width)}
      srcSet={photoSrcSet(photo)}
      sizes={sizes ?? `${width}px`}
      alt={alt ?? ''}
      loading="lazy"
      className={className}
    />
  )
}
