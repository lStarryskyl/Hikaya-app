import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import RequireAuth from './components/RequireAuth'
import { lazy, Suspense } from 'react'
import ErrorBoundary from './components/ErrorBoundary'
import { t, useLocale } from './i18n'
const HomePage = lazy(() => import('./pages/HomePage'))
const ExploreMapPage = lazy(() => import('./pages/ExploreMapPage'))
const CreateStoryPage = lazy(() => import('./pages/CreateStoryPage'))
const StoryPlayerPage = lazy(() => import('./pages/StoryPlayerPage'))
const CommunityFeedPage = lazy(() => import('./pages/CommunityFeedPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const PremiumPage = lazy(() => import('./pages/PremiumPage'))
const StaffPage = lazy(() => import('./pages/StaffPage'))
const SignInPage = lazy(() => import('./pages/AuthPages').then((m) => ({ default: m.SignInPage })))
const SignUpPage = lazy(() => import('./pages/AuthPages').then((m) => ({ default: m.SignUpPage })))

function Shell() {
  useLocale()
  return (
    <div className="min-h-screen flex bg-cream text-ink font-sans">
      <a href="#main-content" className="skip-link">
        {t('Skip to content')}
      </a>
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main id="main-content" tabIndex={-1} className="flex-1 min-w-0 pb-20 md:pb-0">
          <Suspense
            fallback={
              <p role="status" className="p-8">
                {t('Loading…')}
              </p>
            }
          >
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/explore" element={<ExploreMapPage />} />
              <Route
                path="/create"
                element={
                  <RequireAuth>
                    <CreateStoryPage />
                  </RequireAuth>
                }
              />
              <Route path="/story/:id" element={<StoryPlayerPage />} />
              <Route path="/feed" element={<CommunityFeedPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              <Route path="/premium" element={<PremiumPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route
                path="/staff"
                element={
                  <RequireAuth>
                    <StaffPage />
                  </RequireAuth>
                }
              />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  useLocale()
  return (
    <ErrorBoundary>
      <Suspense
        fallback={
          <p role="status" className="p-8">
            {t('Loading…')}
          </p>
        }
      >
        <Routes>
          <Route path="/signin" element={<SignInPage />} />
          <Route path="/signup" element={<SignUpPage />} />
          <Route path="*" element={<Shell />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  )
}
