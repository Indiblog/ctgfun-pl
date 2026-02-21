# 🎬 M3U Playlist Generator for OTT Navigator

Automatically scrapes [ftp.ctgfun.com](http://ftp.ctgfun.com), fetches movie artwork & descriptions from TMDB, and generates a categorised M3U playlist for use in **OTT Navigator** on Android/Google TV.

---

## 📋 Features

- Crawls all folders & subfolders on the FTP open directory
- Categorises movies by folder structure (e.g. `Hollywood > Action`)
- Fetches **poster artwork** and **descriptions** from TMDB
- Auto-updates every 6 hours via GitHub Actions
- Served via GitHub Pages as a public M3U URL

---

## 🚀 Setup (One-Time)

### Step 1 — Add Your TMDB API Key as a Secret
1. Go to [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) and get a free API key
2. In your GitHub repo go to **Settings → Secrets and variables → Actions → New repository secret**
3. Add:
   - Name: `TMDB_API_KEY`
   - Value: your key

### Step 2 — Enable GitHub Pages
1. Go to **Settings → Pages**
2. Under **Source**, select `Deploy from a branch`
3. Choose branch: `main`, folder: `/output`
4. Click **Save**

### Step 3 — Run the Workflow
1. Go to **Actions → Generate M3U Playlist**
2. Click **Run workflow**
3. Wait ~5–10 minutes for it to complete

### Step 4 — Add to OTT Navigator
Your playlist URL will be:
```
https://YOUR_USERNAME.github.io/YOUR_REPO_NAME/playlist.m3u
```
Open OTT Navigator → Settings → Playlists → Add Playlist → paste the URL above.

---

## ⚙️ Configuration

Edit `scraper.py` to adjust:

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://ftp.ctgfun.com` | The FTP open directory to scrape |
| `MAX_CATEGORY_DEPTH` | `2` | How many folder levels to use as category |
| `VIDEO_EXTENSIONS` | `.mkv .mp4 .avi ...` | Which file types to include |

---

## 📁 File Structure

```
├── .github/
│   └── workflows/
│       └── generate-m3u.yml   ← GitHub Actions automation
├── output/
│   └── playlist.m3u           ← Auto-generated (served via GitHub Pages)
├── scraper.py                 ← Main scraper script
├── requirements.txt           ← Python dependencies
└── README.md
```

---

## 🔄 Auto-Update Schedule

The workflow runs **every 6 hours** automatically. You can also trigger it manually anytime from the **Actions** tab.
