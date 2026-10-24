import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import RequireAuth from './components/RequireAuth'
import HomePage from './pages/HomePage'
import ExploreMapPage from './pages/ExploreMapPage'
import CreateStoryPage from './pages/CreateStoryPage'
import StoryPlayerPage from './pages/StoryPlayerPage'
import CommunityFeedPage from './pages/CommunityFeedPage'
import ProfilePage from './pages/ProfilePage'
import NotificationsPage from './pages/NotificationsPage'
import SettingsPage from './pages/SettingsPage'
import StaffPage from './pages/StaffPage'
import { SignInPage, SignUpPage } from './pages/AuthPages'

function Shell() {
  return (
    <div className="min-h-screen flex bg-cream text-ink font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 min-w-0">
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
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/signin" element={<SignInPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route path="*" element={<Shell />} />
    </Routes>
  )
}
