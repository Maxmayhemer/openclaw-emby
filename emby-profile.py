#!/usr/bin/env python3
"""
emby-profile.py — Fetch your Emby watch history, favorites, and manage watchlist.

Credentials: ~/.config/emby/credentials.json

Usage:
  python tools/emby-profile.py                      # Fetch and write memory/emby-profile.md
  python tools/emby-profile.py --limit 200          # Override recently played items (default 150)
  python tools/emby-profile.py --test               # Test connection only
  python tools/emby-profile.py --search "Severance" # Search library for a title
  python tools/emby-profile.py --add "Severance"    # Add to favorites/watchlist
  python tools/emby-profile.py --remove "Severance" # Remove from favorites/watchlist
  python tools/emby-profile.py --missing-meta       # Scan library for items with missing metadata
  python tools/emby-profile.py --missing-meta --refresh-meta  # Scan + push refresh on each missing item
"""

import sys
import json
import argparse
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

CREDS_FILE  = Path.home() / ".config" / "emby" / "credentials.json"
OUTPUT_FILE = Path(__file__).parent.parent / "memory" / "emby-profile.md"


def load_creds():
    if not CREDS_FILE.exists():
        print(f"ERROR: credentials not found at {CREDS_FILE}")
        sys.exit(1)
    return json.loads(CREDS_FILE.read_text())


def api_get(creds, path, params=None):
    p = dict(params or {})
    p["api_key"] = creds["api_key"]
    url = creds["server_url"].rstrip("/") + path + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={
        "X-Emby-Token": creds["api_key"],
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} on {path}: {e.read().decode()[:200]}")


def fetch_recently_played(creds, limit):
    """Fetch recently played items sorted by last played date."""
    data = api_get(creds, f"/Users/{creds['user_id']}/Items", {
        "SortBy": "DatePlayed",
        "SortOrder": "Descending",
        "Filters": "IsPlayed",
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Episode",
        "Fields": "DateCreated,Genres,SeriesName,ParentIndexNumber,IndexNumber,UserData",
        "Limit": limit,
    })
    return data.get("Items", [])


def fetch_favorites(creds):
    """Fetch favorited movies and shows."""
    results = []
    for kind in ("Movie", "Series"):
        data = api_get(creds, f"/Users/{creds['user_id']}/Items", {
            "Filters": "IsFavorite",
            "Recursive": "true",
            "IncludeItemTypes": kind,
            "Fields": "Genres,CommunityRating,ProductionYear",
            "Limit": 200,
            "SortBy": "SortName",
        })
        results.extend(data.get("Items", []))
    return results


def fetch_continue_watching(creds):
    """Fetch in-progress items."""
    data = api_get(creds, f"/Users/{creds['user_id']}/Items/Resume", {
        "Recursive": "true",
        "Fields": "SeriesName,ParentIndexNumber,IndexNumber,UserData",
        "Limit": 20,
    })
    return data.get("Items", [])


def search_library(creds, query, limit=10):
    """Search the Emby library for a title."""
    data = api_get(creds, "/Items", {
        "SearchTerm": query,
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Series,Episode",
        "Fields": "ProductionYear,SeriesName,ParentIndexNumber,IndexNumber",
        "Limit": limit,
        "UserId": creds["user_id"],
    })
    return data.get("Items", [])


def add_favorite(creds, item_id):
    """Mark an item as a favorite (add to watchlist)."""
    url = creds["server_url"].rstrip("/") + f"/Users/{creds['user_id']}/FavoriteItems/{item_id}"
    req = urllib.request.Request(url, data=b"", headers={
        "X-Emby-Token": creds["api_key"],
        "Accept": "application/json",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def remove_favorite(creds, item_id):
    """Unmark an item as a favorite (remove from watchlist)."""
    url = creds["server_url"].rstrip("/") + f"/Users/{creds['user_id']}/FavoriteItems/{item_id}?api_key={creds['api_key']}"
    req = urllib.request.Request(url, headers={
        "X-Emby-Token": creds["api_key"],
        "Accept": "application/json",
    }, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def get_server_info(creds):
    """Get Emby server status and system info."""
    return api_get(creds, "/System/Info")


def get_sessions(creds):
    """Get all active Emby sessions."""
    return api_get(creds, "/Sessions") or []


def restart_server(creds):
    """Restart the Emby server process."""
    url = creds["server_url"].rstrip("/") + f"/System/Restart?api_key={creds['api_key']}"
    req = urllib.request.Request(url, data=b"", headers={"X-Emby-Token": creds["api_key"]}, method="POST")
    urllib.request.urlopen(req, timeout=10)
    print("[OK] Restart signal sent to Emby.")


def fetch_all_library(creds, kind, batch=500, max_items=None, start_index=0):
    """Fetch all items of a given type from the full library."""
    items = []
    start = 0
    fields = "Overview,Genres,CommunityRating,ProductionYear,OfficialRating,ImageTags,BackdropImageTags,Path"
    while True:
        data = api_get(creds, "/Items", {
            "Recursive": "true",
            "IncludeItemTypes": kind,
            "Fields": fields,
            "StartIndex": start,
            "Limit": batch,
            "SortBy": "SortName",
            "UserId": creds["user_id"],
        })
        chunk = data.get("Items", [])
        if max_items:
            remaining = max_items - len(items)
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
        items.extend(chunk)
        if not chunk or len(chunk) < batch or (max_items and len(items) >= max_items):
            break
        start += batch
    return items


def check_missing_meta(item):
    """Return list of missing metadata field names for an item."""
    missing = []
    if not item.get("Overview", "").strip():
        missing.append("overview")
    if not item.get("ProductionYear"):
        missing.append("year")
    if not item.get("Genres"):
        missing.append("genres")
    if not item.get("OfficialRating"):
        missing.append("rating")
    if not item.get("CommunityRating"):
        missing.append("community_rating")
    tags = item.get("ImageTags") or {}
    if "Primary" not in tags:
        missing.append("poster")
    if not item.get("BackdropImageTags"):
        missing.append("backdrop")
    return missing


def refresh_item_meta(creds, item_id):
    """Trigger a metadata + image refresh for a single item."""
    url = (creds["server_url"].rstrip("/")
           + f"/Items/{item_id}/Refresh"
           + f"?MetadataRefreshMode=FullRefresh"
           + f"&ImageRefreshMode=FullRefresh"
           + f"&ReplaceAllMetadata=false"
           + f"&ReplaceAllImages=false"
           + f"&api_key={creds['api_key']}")
    req = urllib.request.Request(url, data=b"", headers={"X-Emby-Token": creds["api_key"]}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except Exception as e:
        return str(e)


def scan_missing_meta(creds, do_refresh=False, batch=500):
    """Scan full library for items with incomplete metadata."""
    results = {}
    total = 0
    for kind in ("Movie", "Series"):
        print(f"  Scanning {kind}s...", flush=True)
        items = fetch_all_library(creds, kind, batch=batch)
        print(f"    {len(items)} {kind}s found")
        missing_items = []
        for item in items:
            missing = check_missing_meta(item)
            if missing:
                missing_items.append((item, missing))
        results[kind] = missing_items
        total += len(missing_items)

    print(f"\n{'='*60}")
    print(f"MISSING METADATA REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    for kind, missing_items in results.items():
        if not missing_items:
            print(f"[OK] All {kind}s have complete metadata.\n")
            continue
        print(f"## {kind}s with missing metadata ({len(missing_items)})\n")
        for item, missing in missing_items:
            name = item.get("Name", "?")
            year = item.get("ProductionYear", "")
            label = f"{name} ({year})" if year else name
            print(f"  [{', '.join(missing)}]  {label}")
            if do_refresh:
                status = refresh_item_meta(creds, item["Id"])
                print(f"    → refresh queued (HTTP {status})")
        print()

    print(f"Total: {total} item(s) with incomplete metadata.")
    if do_refresh and total:
        print("Refresh scans have been queued on the server.")


def fetch_user_stats(creds):
    """Get basic user stats."""
    try:
        data = api_get(creds, f"/Users/{creds['user_id']}")
        return data.get("Policy", {}), data.get("Name", "User")
    except Exception:
        return {}, "User"


def item_label(item):
    kind = item.get("Type", "")
    name = item.get("Name", "?")
    series = item.get("SeriesName")
    season = item.get("ParentIndexNumber")
    ep = item.get("IndexNumber")
    year = item.get("ProductionYear", "")

    if kind == "Episode" and series:
        if season and ep:
            return f"{series} S{season:02d}E{ep:02d} — {name}"
        return f"{series} — {name}"
    if year:
        return f"{name} ({year})"
    return name


def write_output(recently_played, favorites, continuing, creds):
    lines = [
        "# Emby Watch Profile",
        "",
        f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} ET_",
        "",
    ]

    # Continue watching
    if continuing:
        lines += ["## Currently Watching / In Progress", ""]
        for item in continuing:
            label = item_label(item)
            pct = ""
            ud = item.get("UserData", {})
            if ud.get("PlayedPercentage"):
                pct = f" ({int(ud['PlayedPercentage'])}%)"
            lines.append(f"- {label}{pct}")
        lines.append("")

    # Recently played — break into movies vs shows
    movies_played = [i for i in recently_played if i.get("Type") == "Movie"]
    eps_played    = [i for i in recently_played if i.get("Type") == "Episode"]

    # Show watch frequency
    if eps_played:
        show_counts = Counter(i.get("SeriesName", "?") for i in eps_played)
        lines += ["## Most Watched Shows (recent)", ""]
        for show, count in show_counts.most_common(20):
            lines.append(f"- {show} ({count} episodes)")
        lines.append("")

        lines += [f"## Recently Watched Episodes (last {min(40, len(eps_played))})", ""]
        for item in eps_played[:40]:
            lines.append(f"- {item_label(item)}")
        lines.append("")

    if movies_played:
        lines += [f"## Recently Watched Movies (last {min(30, len(movies_played))})", ""]
        for item in movies_played[:30]:
            lines.append(f"- {item_label(item)}")
        lines.append("")

    # Favorites
    fav_movies = [f for f in favorites if f.get("Type") == "Movie"]
    fav_shows  = [f for f in favorites if f.get("Type") in ("Series", "Show")]

    if fav_movies:
        lines += [f"## Favorite Movies ({len(fav_movies)})", ""]
        for f in fav_movies:
            rating = f.get("CommunityRating")
            rating_str = f" ★{rating:.1f}" if rating else ""
            genres = ", ".join(f.get("Genres", [])[:3])
            genre_str = f" [{genres}]" if genres else ""
            lines.append(f"- {item_label(f)}{rating_str}{genre_str}")
        lines.append("")

    if fav_shows:
        lines += [f"## Favorite Shows ({len(fav_shows)})", ""]
        for f in fav_shows:
            rating = f.get("CommunityRating")
            rating_str = f" ★{rating:.1f}" if rating else ""
            lines.append(f"- {item_label(f)}{rating_str}")
        lines.append("")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(lines) + "\n")
    print(f"[OK] Written to {OUTPUT_FILE}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",     action="store_true", help="Test connection + show server info")
    parser.add_argument("--limit",    type=int, default=150, help="Recently played items (default 150)")
    parser.add_argument("--search",   metavar="TITLE", help="Search library for a title")
    parser.add_argument("--add",      metavar="TITLE", help="Add title to favorites/watchlist")
    parser.add_argument("--remove",   metavar="TITLE", help="Remove title from favorites/watchlist")
    parser.add_argument("--sessions",     action="store_true", help="Show who is currently streaming")
    parser.add_argument("--restart",      action="store_true", help="Restart the Emby server (warns if streams active)")
    parser.add_argument("--missing-meta", action="store_true", help="Scan library for items with missing metadata")
    parser.add_argument("--refresh-meta", action="store_true", help="With --missing-meta: push a refresh scan on each missing item")
    parser.add_argument("--batch", type=int, default=500, help="Batch size for missing metadata scans (default 500)")
    args = parser.parse_args()

    creds = load_creds()

    if args.sessions:
        sessions = get_sessions(creds)
        active = [s for s in sessions if s.get("NowPlayingItem")]
        idle   = [s for s in sessions if not s.get("NowPlayingItem")]
        print(f"Active streams ({len(active)}):")
        for s in active:
            user = s.get("UserName", "unknown")
            item = s.get("NowPlayingItem", {})
            title = item.get("Name", "?")
            series = item.get("SeriesName")
            label = f"{series} — {title}" if series else title
            client = s.get("Client", "")
            print(f"  {user}: {label}  [{client}]")
        if idle:
            print(f"Idle sessions: {', '.join(s.get('UserName','?') for s in idle if s.get('UserName'))}")
        return

    if args.restart:
        sessions = get_sessions(creds)
        active = [s for s in sessions if s.get("NowPlayingItem")]
        if active:
            print(f"WARNING: {len(active)} active stream(s) will be interrupted:")
            for s in active:
                print(f"  {s.get('UserName','?')}: {s.get('NowPlayingItem',{}).get('Name','?')}")
            confirm = input("Restart anyway? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("Cancelled.")
                return
        restart_server(creds)
        return

    if args.missing_meta:
        scan_missing_meta(creds, do_refresh=args.refresh_meta, batch=args.batch)
        return

    if args.test:
        try:
            user = api_get(creds, f"/Users/{creds['user_id']}")
            print(f"[OK] Connected as: {user.get('Name')}")
            info = get_server_info(creds)
            print(f"  Server:  {info.get('ServerName', '?')} v{info.get('Version', '?')}")
            print(f"  OS:      {info.get('OperatingSystem', '?')}")
            print(f"  Up since: {(info.get('SystemUpdateLevel') or '?')}")
        except Exception as e:
            print(f"[FAIL] {e}")
            sys.exit(1)
        return

    if args.search:
        results = search_library(creds, args.search)
        if not results:
            print(f"No results for '{args.search}'")
        for item in results:
            label = item_label(item)
            fav = "[★] " if item.get("UserData", {}).get("IsFavorite") else "    "
            print(f"{fav}{label}  (id: {item['Id']}, type: {item['Type']})")
        return

    if args.add:
        results = search_library(creds, args.add, limit=5)
        if not results:
            print(f"No results for '{args.add}'")
            sys.exit(1)
        item = results[0]
        label = item_label(item)
        add_favorite(creds, item["Id"])
        print(f"[★] Added to favorites: {label}")
        return

    if args.remove:
        results = search_library(creds, args.remove, limit=5)
        if not results:
            print(f"No results for '{args.remove}'")
            sys.exit(1)
        # Prefer already-favorited match
        faved = [i for i in results if i.get("UserData", {}).get("IsFavorite")]
        item = faved[0] if faved else results[0]
        label = item_label(item)
        remove_favorite(creds, item["Id"])
        print(f"[✓] Removed from favorites: {label}")
        return

    print("Fetching recently played...")
    recently_played = fetch_recently_played(creds, args.limit)
    print(f"  {len(recently_played)} items")

    print("Fetching favorites...")
    favorites = fetch_favorites(creds)
    print(f"  {len(favorites)} favorites")

    print("Fetching continue watching...")
    continuing = fetch_continue_watching(creds)
    print(f"  {len(continuing)} in progress")

    write_output(recently_played, favorites, continuing, creds)


if __name__ == "__main__":
    main()
