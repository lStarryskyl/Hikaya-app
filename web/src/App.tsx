import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import HomePage from './pages/HomePage'
import ExploreMapPage from './pages/ExploreMapPage'
import CreateStoryPage from './pages/CreateStoryPage'
import StoryPlayerPage from './pages/StoryPlayerPage'
import CommunityFeedPage from './pages/CommunityFeedPage'
import ProfilePage from './pages/ProfilePage'
import NotificationsPage from './pages/NotificationsPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <div className="min-h-screen flex bg-cream text-ink font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <TopBar />
        <main className="flex-1 min-w-0">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/explore" element={<ExploreMapPage />} />
            <Route path="/create" element={<CreateStoryPage />} />
            <Route path="/story/:id" element={<StoryPlayerPage />} />
            <Route path="/feed" element={<CommunityFeedPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
