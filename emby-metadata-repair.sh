#!/bin/bash
# emby-metadata-repair.sh — Fix missing posters and metadata for any Emby library
# Uses RemoteSearch/Apply which works where standard library refresh does not
# (especially effective for Blu-ray folder structures and items with [imdbid-...] in path)
#
# Usage:
#   bash emby-metadata-repair.sh                         # all Movie libraries
#   bash emby-metadata-repair.sh --library-name "4K Movies"
#   bash emby-metadata-repair.sh --library-id abc123
#   bash emby-metadata-repair.sh --type Series           # TV shows
#   bash emby-metadata-repair.sh --dry-run               # preview only, no changes
#
# Credentials: ~/.config/emby/credentials.json
#   { "server_url": "...", "api_key": "...", "user_id": "..." }

CREDS="$HOME/.config/emby/credentials.json"
LOG="/tmp/emby_metadata_repair.log"

if [ ! -f "$CREDS" ]; then
    echo "ERROR: $CREDS not found. Copy credentials.json.example and fill it in."
    exit 1
fi

python3 - "$@" <<'PYEOF'
import sys, os, json, urllib.request, urllib.error, time, re, argparse

# --- Args ---
ap = argparse.ArgumentParser()
ap.add_argument("--library-name", help="Library name to target (partial match)")
ap.add_argument("--library-id",   help="Library parent ID to target")
ap.add_argument("--type",         default="Movie", choices=["Movie", "Series", "Episode", "MusicVideo"],
                help="Item type to search for (default: Movie)")
ap.add_argument("--dry-run",      action="store_true", help="Report what would be fixed, make no changes")
args = ap.parse_args()

LOG = os.environ.get("EMBY_REPAIR_LOG", "/tmp/emby_metadata_repair.log")
DELAY = 2.0  # seconds between API calls

# --- Credentials ---
creds_path = os.path.expanduser("~/.config/emby/credentials.json")
with open(creds_path) as f:
    creds = json.load(f)

BASE = creds["server_url"].rstrip("/")
KEY  = creds["api_key"]
EUID = creds["user_id"]

# --- Helpers ---
def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def api(path, method="GET", data=None, params=None):
    sep = "&" if "?" in path else "?"
    extra = ""
    if params:
        extra = "&" + "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}{path}{sep}api_key={KEY}{extra}"
    for attempt in range(4):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = r.read()
                return json.loads(resp) if resp else {}
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < 3:
                time.sleep(10); continue
            return {"_error": e.code}
        except Exception as e:
            if attempt < 3:
                time.sleep(5); continue
            return {"_error": str(e)}

IMDB_RE = re.compile(r'\[imdbid-(tt\d+)\]', re.IGNORECASE)

# --- Find target libraries ---
libraries = api(f"/Library/VirtualFolders")
if not isinstance(libraries, list):
    log(f"ERROR: Could not fetch libraries: {libraries}")
    sys.exit(1)

targets = []
for lib in libraries:
    lid = lib.get("ItemId") or lib.get("Id")
    name = lib.get("Name", "")
    if args.library_id and lid != args.library_id:
        continue
    if args.library_name and args.library_name.lower() not in name.lower():
        continue
    targets.append({"id": lid, "name": name})

if not targets:
    if args.library_id or args.library_name:
        log("ERROR: No matching libraries found.")
        sys.exit(1)
    # Default: all libraries
    targets = [{"id": lib.get("ItemId") or lib.get("Id"), "name": lib.get("Name", "")}
               for lib in libraries]

log(f"{'DRY RUN — ' if args.dry_run else ''}Target libraries: {', '.join(t['name'] for t in targets)}")
log(f"Item type: {args.type}")

# --- Collect items with missing metadata ---
all_items = []
for lib in targets:
    log(f"Scanning library: {lib['name']} ({lib['id']})")
    start = 0
    lib_count = 0
    while True:
        r = api(f"/Users/{EUID}/Items",
                params={
                    "ParentId": lib["id"],
                    "IncludeItemTypes": args.type,
                    "Recursive": "true",
                    "Fields": "ProviderIds,ImageTags,Name,ProductionYear",
                    "Limit": 200,
                    "StartIndex": start,
                })
        items = r.get("Items", [])
        total = r.get("TotalRecordCount", 0)
        for item in items:
            missing_tmdb   = not item.get("ProviderIds", {}).get("Tmdb")
            missing_poster = not item.get("ImageTags", {}).get("Primary")
            if missing_tmdb or missing_poster:
                item["_library"] = lib["name"]
                all_items.append(item)
                lib_count += 1
        start += 200
        if start >= total:
            break
        time.sleep(0.3)
    log(f"  → {lib_count} items need repair (out of {total} total)")

log(f"Total items to repair: {len(all_items)}")

if args.dry_run:
    log("Dry run — no changes made. Remove --dry-run to apply fixes.")
    sys.exit(0)

if not all_items:
    log("Nothing to do. All items have posters and TMDb IDs.")
    sys.exit(0)

# --- Search type for RemoteSearch ---
SEARCH_TYPE_MAP = {
    "Movie":      "/Items/RemoteSearch/Movie",
    "Series":     "/Items/RemoteSearch/Series",
    "Episode":    "/Items/RemoteSearch/Episode",
    "MusicVideo": "/Items/RemoteSearch/MusicVideo",
}
search_endpoint = SEARCH_TYPE_MAP.get(args.type, "/Items/RemoteSearch/Movie")

# --- Apply fixes ---
ok = skipped = err = 0
for i, item in enumerate(all_items):
    name = item["Name"]
    year = item.get("ProductionYear")
    iid  = item["Id"]

    # Extract IMDb ID from [imdbid-ttXXXXX] in name/path if present
    m = IMDB_RE.search(name)
    imdb_id = m.group(1) if m else None
    clean_name = IMDB_RE.sub("", name).strip()

    search_info = {"Name": clean_name}
    if year:
        search_info["Year"] = year
    if imdb_id:
        search_info["ProviderIds"] = {"Imdb": imdb_id}

    results = api(search_endpoint, method="POST", data={
        "SearchInfo": search_info,
        "ItemId": iid,
        "IncludeDisabledProviders": False
    })

    if not isinstance(results, list) or not results:
        log(f"  [{i+1}/{len(all_items)}] No results: {clean_name} ({year})")
        skipped += 1
        time.sleep(DELAY)
        continue

    top = results[0]
    apply = api(f"/Items/RemoteSearch/Apply/{iid}?ReplaceAllImages=true",
                method="POST", data=top)
    if isinstance(apply, dict) and apply.get("_error"):
        log(f"  [{i+1}/{len(all_items)}] ERR {apply['_error']}: {clean_name}")
        err += 1
    else:
        ok += 1

    if (i + 1) % 50 == 0:
        log(f"  Progress: {i+1}/{len(all_items)} — OK={ok} SKIPPED={skipped} ERR={err}")

    time.sleep(DELAY)

log(f"Done. OK={ok}  SKIPPED={skipped}  ERRORS={err}")
log(f"Full log: {LOG}")
PYEOF
