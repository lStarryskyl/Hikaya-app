# Place photos (demo seed)

Source photos for the six places. `python -m app.seed_demo` converts each to WebP at 480, 960
and 1600 pixels wide into the media store and serves them from `/media/places/<slug>/<width>.webp`.
The file stem is the photo's slug, listed with its caption in `app/demo_data.py`. Ten of these `.png`
files are really JPEGs; the seed reads each file by its content, not its name.

**Licensing: not cleared.** This repository is public. Before the demo, confirm the team owns or
has a licence for every photo here. `madaba-loom.png` carries an Alamy watermark and must be
replaced; it is kept in the gallery only until then and is not used as any cover.

To replace a photo, drop a new file with the same name (PNG, JPEG or WebP), delete its folder
under the media store's `places/`, and run the seed again.
