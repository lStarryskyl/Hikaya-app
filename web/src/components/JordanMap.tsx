import { forwardRef, lazy, Suspense } from 'react'
import ErrorBoundary from './ErrorBoundary'
import { t, useLocale } from '../i18n'
import type { JordanMapHandle, JordanMapProps } from './JordanMapCanvas'
export type { JordanMapHandle } from './JordanMapCanvas'
const Canvas = lazy(() => import('./JordanMapCanvas'))
const JordanMap = forwardRef<JordanMapHandle, JordanMapProps>(function JordanMap(props, ref) {
  useLocale()
  return (
    <ErrorBoundary
      fallback={
        <p role="status" className="p-6">
          {t('The map is unavailable. You can still browse and open stories from the list.')}
        </p>
      }
    >
      <Suspense
        fallback={
          <p role="status" className="p-6">
            {t('Loading the map…')}
          </p>
        }
      >
        <Canvas {...props} ref={ref} />
      </Suspense>
    </ErrorBoundary>
  )
})
export default JordanMap
