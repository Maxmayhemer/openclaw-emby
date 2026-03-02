#!/bin/bash
# Overnight batch: fix all 4K movies using RemoteSearch/Apply (the approach that actually works)
python3 << 'PYEOF'
import urllib.request, urllib.error, json, time, re, sys
from datetime import datetime

BASE  = "https://29595.brr.savethecdn.com"
KEY   = "e073802ec6e843799e02d5cb2b878d55"
EUID  = "e8a030c06293418aa8d33bc342dd666c"
PARENT= "879905"
LOG   = "/tmp/emby_4k_refresh.log"
DELAY = 2.0  # seconds between movies — stay gentle

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    open(LOG, "a").write(line + "\n")

def api(path, method="GET", data=None):
    sep = "&" if "?" in path else "?"
    url = f"{BASE}{path}{sep}api_key={KEY}"
    for attempt in range(4):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method,
                                      headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
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

log("Starting 4K metadata fix via RemoteSearch/Apply...")

# Collect all 4K movies still missing TMDb ID
all_items = []
start = 0
while True:
    r = api(f"/Users/{EUID}/Items?ParentId={PARENT}"
            f"&Fields=ProviderIds,ImageTags,Name,ProductionYear"
            f"&Limit=200&StartIndex={start}")
    items = r.get("Items", [])
    total = r.get("TotalRecordCount", 0)
    for item in items:
        # Include if missing poster OR missing TMDb ID
        if not item.get("ProviderIds", {}).get("Tmdb") or \
           not item.get("ImageTags", {}).get("Primary"):
            all_items.append(item)
    start += 200
    if start >= total:
        break
    time.sleep(0.3)

log(f"Found {len(all_items)} movies needing metadata fix (out of {total} total)")

ok = skipped = err = 0
for i, item in enumerate(all_items):
    name  = item["Name"]
    year  = item.get("ProductionYear")
    iid   = item["Id"]

    # Extract IMDb ID from name/filename tag
    m = IMDB_RE.search(name)
    imdb_id = m.group(1) if m else None

    # Clean up display name (remove the [imdbid-...] tag)
    clean_name = IMDB_RE.sub("", name).strip()

    search_info = {"Name": clean_name}
    if year:
        search_info["Year"] = year
    if imdb_id:
        search_info["ProviderIds"] = {"Imdb": imdb_id}

    results = api("/Items/RemoteSearch/Movie", method="POST", data={
        "SearchInfo": search_info,
        "ItemId": iid,
        "IncludeDisabledProviders": False
    })

    if not isinstance(results, list) or not results:
        log(f"  [{i+1}] No results: {clean_name} ({year})")
        skipped += 1
        time.sleep(DELAY)
        continue

    top = results[0]
    apply = api(f"/Items/RemoteSearch/Apply/{iid}?ReplaceAllImages=true", method="POST", data=top)
    if isinstance(apply, dict) and apply.get("_error"):
        log(f"  [{i+1}] ERR apply {apply['_error']}: {clean_name}")
        err += 1
    else:
        ok += 1

    if (i + 1) % 100 == 0:
        log(f"  Progress: {i+1}/{len(all_items)} — OK={ok} SKIP={skipped} ERR={err}")

    time.sleep(DELAY)

log(f"Complete. OK={ok} SKIPPED={skipped} ERRORS={err}")
PYEOF
