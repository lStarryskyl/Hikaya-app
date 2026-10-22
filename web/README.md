# Hikaya — React UI

A working React + Vite + TypeScript + Tailwind implementation of the Hikaya
(حكاية) screens: Home, Explore Map, Create a Story (4-step flow), Story
Player, and Community Feed.

**Design source of truth:** Visily multi-screen export  
`visily-multiscreens (2) (1).pdf` (Home · Explore Map · Create · Story Player · Social Feed).

## Run it

```
npm install
npm run dev
```

Then open the local URL Vite prints (usually http://localhost:5173).

## What's real vs. what's mocked

- All navigation, the story creation stepper (recording timer, transcript
  editing, animation progress simulation, publish), the audio player
  (play/pause, scrubbing progress), map pin selection, and feed like/save
  toggles are functionally wired up with real React state — not static.
- All content (stories, comments, avatars) comes from `src/data/mock.ts`.
  Swap this for real API calls when the backend is ready; the shapes in
  `src/types.ts` are a reasonable starting contract.
- Photos are placeholder images from picsum.photos (seeded, so they're
  stable across reloads) with a light sepia filter to keep them visually
  consistent with the warm palette — swap in real photography before
  shipping.
- The map is a stylized illustration, not a real geographic map (no
  MapLibre/Mapbox wired in yet) — pins are positioned with percentage
  coordinates over a decorative background, matching the Visily mockup's
  illustrated-map style rather than a real GIS map.

## Structure

```
src/
  components/   Sidebar, TopBar, shared UI primitives (Badge, PillButton, Card)
  pages/        HomePage, ExploreMapPage, CreateStoryPage, StoryPlayerPage, CommunityFeedPage
  data/mock.ts  all mock content
  types.ts      shared TypeScript interfaces
```

## Design tokens

Colors, fonts, and radii are defined in `tailwind.config.js` — terracotta
(`#B85C38`) / gold / teal on cream (`#F7F4EE`), Fraunces for display
headings, Manrope for UI text, Noto Kufi Arabic for the Arabic wordmark.
