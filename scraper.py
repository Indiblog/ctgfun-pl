import os
import re
import time
import requests
from pathlib import Path
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup

# ── CONFIG ────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("FTP_PUBLIC_URL", "http://ftp.ctgfun.com").rstrip("/") + "/"

TMDB_API_KEY = os.environ["TMDB_API_KEY"]
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"

OUTPUT_FILE = Path("output/playlist.m3u")
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".divx", ".flv"}
SKIP_FOLDERS = {"..", ".", ""}

# ── CATEGORY DEPTH MAP ────────────────────────────────────────────────────────
# Controls how many folder levels are used to build the group-title.
#
#   English/  → depth 1  → group = "English Movies"
#               (movies sit directly in /English/MovieFolder/)
#
#   Indian/   → depth 2  → group = "Indian > Hindi" / "Indian > South Indian"
#               (/Indian/Hindi Movies/MovieFolder/)
#
#   Others/   → depth 2  → group = "Others > 4K" / "Others > Asian" etc.
#               (/Others/4K MOVIES/MovieFolder/)
#
#   TV_Series → depth 2  → group = "TV Series > ShowName"
#               (/TV_Series/ShowName/SeasonFolder/episode.mkv)
#
CATEGORY_DEPTH_MAP = {
    "English":   1,
    "Indian":    2,
    "Others":    2,
    "TV_Series": 2,
}

MAX_CATEGORY_DEPTH = 2  # fallback for any unknown top-level folders

# ── FOLDER RENAME MAP ─────────────────────────────────────────────────────────
# Maps raw FTP folder names to clean display labels used in group-title.
# Applied at every level (top-level and sub-level).
#
# Key  = exact folder name as it appears in the URL (decoded)
# Value = what to display in the M3U group-title
#
FOLDER_RENAME_MAP = {
    # Top-level folders
    "English":              "English Movies",
    "Indian":               "Indian",
    "Others":               "Others",
    "TV_Series":            "TV Series",

    # Indian sub-folders
    "Hindi Movies":         "Hindi",
    "South Indian Movies":  "South Indian",

    # Others sub-folders  — map cryptic archive aliases to readable names
    "4K MOVIES":            "4K",
    "Asian Movie":          "Asian",
    "European Movies":      "European",
    "AA":                   "New Arrivals",   # AA = Archive/Additions dump
    "PB":                   "Archive",        # PB = Prison Break + misc
    "PR":                   "Archive",        # PR = misc releases
    "M":                    "Archive",        # M = misc
    "BB OPT":               "Archive",
    # "Others > Others" → flatten to just "Others > Misc"
    # (handled via FLATTEN_PATHS below)
}

# ── FOLDERS TO SKIP ENTIRELY ─────────────────────────────────────────────────
# Folder names (decoded) to skip — non-video or irrelevant.
# Applied at every depth level.
#
SKIP_FOLDER_NAMES = {
    "GAMES",    # games, not video
    "App",      # Android APKs, not video
}

# ── PATH FLATTENING ───────────────────────────────────────────────────────────
# For paths where the sub-folder name is redundant (e.g. "Others/Others"),
# map the raw folder-path prefix → replacement category label.
# Key = tuple of decoded folder names leading to this point (after rename).
# Value = override group-title string.
#
FLATTEN_CATEGORY_MAP = {
    # "Others > Others" is a nested misc dump — flatten to just "Others > Misc"
    ("Others", "Others"):     "Others > Misc",
}

# ── SESSION ───────────────────────────────────────────────────────────────────
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; M3U-Scraper/1.0)"
})


# ── HELPERS ───────────────────────────────────────────────────────────────────

def rename_folder(name: str) -> str:
    """Return the display label for a raw folder name."""
    return FOLDER_RENAME_MAP.get(name, name)


def build_category(raw_parts: list[str]) -> str:
    """
    Given a list of raw folder names, produce a clean group-title string.
    Applies rename map and checks for flatten overrides.
    """
    renamed = [rename_folder(p) for p in raw_parts]

    # Check flatten map (using raw parts as key)
    key = tuple(raw_parts)
    if key in FLATTEN_CATEGORY_MAP:
        return FLATTEN_CATEGORY_MAP[key]

    return " > ".join(renamed) if renamed else "Movies"


# ── HTTP DIRECTORY CRAWLER ────────────────────────────────────────────────────

def crawl(url, depth=0, raw_parts=None):
    """
    Recursively crawl an HTTP open directory and collect video file entries.

    raw_parts: list of raw (un-renamed) folder names collected so far.
               Used to drive depth logic and flatten map lookups.
    """
    if raw_parts is None:
        raw_parts = []

    results = []

    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [WARN] Could not fetch {url} — {e}")
        return results

    soup = BeautifulSoup(resp.text, "html.parser")
    links = soup.find_all("a", href=True)

    for link in links:
        href = link["href"].strip()

        # Skip parent / navigation / off-site links
        if (href in ("../", "..", "/", "")
                or href.startswith("?")
                or href.startswith("#")
                or (href.startswith("http") and not href.startswith(BASE_URL))):
            continue

        full_url = urljoin(url, href)
        decoded_name = unquote(href.rstrip("/"))

        if not full_url.startswith(BASE_URL):
            continue

        if href.endswith("/"):
            # ── Folder → maybe recurse ────────────────────────────────────
            folder_name = decoded_name

            if folder_name in SKIP_FOLDERS:
                continue

            # Skip explicitly excluded folder names (GAMES, App, etc.)
            if folder_name in SKIP_FOLDER_NAMES:
                print(f"{'  ' * depth}⛔ Skipping: {folder_name}/")
                continue

            # Determine max depth for this top-level section
            top_folder = raw_parts[0] if raw_parts else folder_name
            max_depth = CATEGORY_DEPTH_MAP.get(top_folder, MAX_CATEGORY_DEPTH)

            # Extend category path only while we're within the allowed depth
            if depth < max_depth:
                new_raw_parts = raw_parts + [folder_name]
            else:
                new_raw_parts = raw_parts  # freeze category once at max depth

            print(f"{'  ' * depth}📁 {folder_name}")
            results.extend(crawl(full_url, depth + 1, new_raw_parts))

        else:
            # ── File → check extension ────────────────────────────────────
            ext = Path(decoded_name).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                continue

            category = build_category(raw_parts)

            results.append({
                "url":      full_url,
                "filename": decoded_name,
                "category": category,
            })

    return results


# ── FILENAME PARSER ───────────────────────────────────────────────────────────

def parse_movie_name(filename):
    """Extract a clean title and year from a messy scene/release filename."""
    name = Path(filename).stem
    name = re.sub(r"[._]", " ", name)

    match = re.search(r"\b(19|20)\d{2}\b", name)
    if match:
        year = match.group(0)
        title = name[:match.start()].strip()
    else:
        year = None
        title = name

    # Strip common quality/encoding tags
    title = re.sub(
        r"\s+(1080p|720p|480p|4k|2160p|uhd|bluray|blu ray|bdrip|brrip|webrip|"
        r"web dl|web|hdtv|hdcam|cam|hdrip|x264|x265|hevc|avc|aac|dts|ac3|"
        r"h264|h265|dvdrip|dvdscr|extended|remastered|theatrical|proper|"
        r"yify|yts|rarbg|10bit|hdr|dolby|atmos|directors cut|unrated|retail).*$",
        "", title, flags=re.IGNORECASE
    ).strip(" -[]()").strip()

    title = re.sub(r"[\[\]()]", "", title).strip()
    return title, year


# ── TMDB LOOKUP ───────────────────────────────────────────────────────────────

_tmdb_cache = {}


def tmdb_search(title, year=None):
    """Search TMDB for movie metadata. Returns a dict or None."""
    cache_key = f"{title}|||{year}"
    if cache_key in _tmdb_cache:
        return _tmdb_cache[cache_key]

    params = {"api_key": TMDB_API_KEY, "query": title, "language": "en-US"}
    if year:
        params["primary_release_year"] = year

    for attempt in range(3):
        try:
            resp = SESSION.get(
                "https://api.themoviedb.org/3/search/movie",
                params=params, timeout=10
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            break
        except requests.RequestException as e:
            print(f"  [TMDB WARN] Attempt {attempt + 1}: {e}")
            time.sleep(2)
    else:
        _tmdb_cache[cache_key] = None
        return None

    # Retry without year filter if no results
    if not results and year:
        return tmdb_search(title, year=None)

    if not results:
        _tmdb_cache[cache_key] = None
        return None

    m = results[0]
    info = {
        "title":        m.get("title", title),
        "year":         (m.get("release_date") or "")[:4] or year or "",
        "overview":     m.get("overview", "").replace('"', "'"),
        "tmdb_id":      m.get("id"),
        "poster_url":   (TMDB_IMAGE_BASE + m["poster_path"]) if m.get("poster_path") else "",
        "backdrop_url": (TMDB_IMAGE_BASE + m["backdrop_path"]) if m.get("backdrop_path") else "",
    }
    _tmdb_cache[cache_key] = info
    time.sleep(0.25)   # be polite to TMDB rate limits
    return info


# ── M3U BUILDER ───────────────────────────────────────────────────────────────

def build_m3u(files):
    lines = ["#EXTM3U\n"]
    total = len(files)

    # Sort by category → filename for a tidy, folder-grouped playlist
    files_sorted = sorted(
        files,
        key=lambda f: (f["category"].lower(), f["filename"].lower())
    )

    matched = unmatched = 0

    for i, entry in enumerate(files_sorted, 1):
        filename = entry["filename"]
        url      = entry["url"]
        category = entry["category"]

        title, year = parse_movie_name(filename)
        print(f"[{i}/{total}] {category} | {title} ({year or '?'})")

        info = tmdb_search(title, year)

        if info:
            display_title = f"{info['title']} ({info['year']})" if info["year"] else info["title"]
            logo          = info["poster_url"] or info["backdrop_url"]
            overview      = info["overview"]
            group         = category
            matched += 1
        else:
            display_title = f"{title} ({year})" if year else title
            logo          = ""
            overview      = ""
            group         = f"{category} [Unmatched]"
            unmatched += 1
            print(f"  ⚠️  No TMDB match found")

        extinf = (
            f'#EXTINF:-1 '
            f'tvg-name="{display_title}" '
            f'tvg-logo="{logo}" '
            f'group-title="{group}" '
            f'tvg-plot="{overview}",'
            f'{display_title}'
        )
        lines.append(extinf)
        lines.append(url)
        lines.append("")

    print(f"\n✅ Matched: {matched} | ⚠️  Unmatched: {unmatched} | Total: {total}")
    return "\n".join(lines)


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"🌐 Crawling: {BASE_URL}\n")
    files = crawl(BASE_URL)
    print(f"\n🎬 Found {len(files)} video file(s)\n")

    if not files:
        print("❌ No files found. Check the URL or network access.")
        exit(1)

    m3u = build_m3u(files)
    OUTPUT_FILE.write_text(m3u, encoding="utf-8")
    print(f"\n📄 Playlist saved to: {OUTPUT_FILE}")
