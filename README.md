# OpenClaw Emby Toolkit

A set of tools for [OpenClaw](https://github.com/openclaw) agents to interact with your [Emby](https://emby.media) media server — watch history profiling and metadata repair.

## Tools

### `emby-profile.py`
Generates a Markdown watch history profile from your Emby server. Useful for feeding into your agent's memory to understand your media preferences.

### `emby-metadata-repair.sh`
Batch metadata repair for any Emby library. Fixes missing posters and metadata using Emby's `RemoteSearch/Apply` API — the approach that actually works when standard library refresh leaves items with blank posters or empty metadata.

Works on any library type: movies, TV shows, anime, etc. Especially effective for Blu-ray folder structures and items with `[imdbid-ttXXXXX]` embedded in the folder name.

## Requirements

```bash
pip install requests   # for emby-profile.py
# emby-metadata-repair.sh only needs python3 (stdlib only)
```

## Setup

1. Copy the credentials template:
   ```bash
   mkdir -p ~/.config/emby
   cp credentials.json.example ~/.config/emby/credentials.json
   chmod 600 ~/.config/emby/credentials.json
   ```

2. Fill in your Emby server URL, API key, and user ID:
   - **API key**: Emby Dashboard → Advanced → API Keys → New API Key
   - **User ID**: Emby Dashboard → Users → click your user → note the ID in the URL

---

## emby-profile.py

```bash
# Generate watch history profile
python emby-profile.py

# Force refresh (ignore cache)
python emby-profile.py --refresh

# Update credentials
python emby-profile.py --auth
```

**Output**: Markdown file (default: `~/emby-profile.md`) with:
- Recently watched movies and episodes
- Top genres and directors
- Watch frequency stats
- Continue Watching list

### Running Weekly via Cron (OpenClaw)

```json
{
  "id": "emby-profile-weekly",
  "schedule": "0 6 * * 0",
  "description": "Refresh Emby watch history profile",
  "type": "shell",
  "command": "python /path/to/emby-profile.py",
  "enabled": true
}
```

---

## emby-metadata-repair.sh

```bash
# Fix all libraries (movies only by default)
bash emby-metadata-repair.sh

# Target a specific library by name
bash emby-metadata-repair.sh --library-name "4K Movies"
bash emby-metadata-repair.sh --library-name "Anime"

# Target by library ID (from Emby Dashboard → Libraries URL)
bash emby-metadata-repair.sh --library-id abc123def456

# Fix TV shows instead of movies
bash emby-metadata-repair.sh --type Series

# Preview what would be fixed without making changes
bash emby-metadata-repair.sh --dry-run

# Check progress while running
tail -f /tmp/emby_metadata_repair.log
```

### Flags

| Flag | Description |
|------|-------------|
| `--library-name NAME` | Target libraries matching this name (partial match) |
| `--library-id ID` | Target a specific library by ID |
| `--type` | Item type: `Movie` (default), `Series`, `Episode`, `MusicVideo` |
| `--dry-run` | Report what would be fixed, make no changes |

### How It Works

For each item missing a poster or TMDb ID:
1. Extracts the IMDb ID from `[imdbid-ttXXXXX]` in the folder name if present
2. Calls `POST /Items/RemoteSearch/Movie` (or Series) with name + year + IMDb hint to find the match
3. Calls `POST /Items/RemoteSearch/Apply/{id}?ReplaceAllImages=true` to inject the metadata directly

Rate limited to ~1 request/2 seconds to stay gentle on the server.

**Why not just use "Refresh Metadata" in Emby?**
Standard refresh (`/Items/{id}/Refresh`) often leaves items unchanged if ProviderIds are empty — Emby doesn't know what to look up. `RemoteSearch/Apply` does a fresh search and injects the result, bypassing that state.

### Running Overnight via Cron (OpenClaw)

```json
{
  "id": "emby-metadata-repair",
  "schedule": "0 2 * * 0",
  "description": "Repair any items with missing posters or metadata",
  "type": "shell",
  "command": "bash /path/to/emby-metadata-repair.sh",
  "enabled": true,
  "oneshot": true
}
```

---

## Credentials File

`~/.config/emby/credentials.json`:
```json
{
  "server_url": "http://YOUR_EMBY_SERVER:8096",
  "api_key": "YOUR_EMBY_API_KEY",
  "user_id": "YOUR_EMBY_USER_ID",
  "username": "YourUsername"
}
```

See `credentials.json.example` for the template.

---

## Tips

- **Run `--dry-run` first** to see how many items need repair before committing to a long run.
- **Enable automatic refresh**: Emby Dashboard → Libraries → Manage Library → "Automatically refresh content every N days" (30 days recommended).
- **Download images in advance**: Enable "Download images in advance" in each library's settings.
- **Schedule tasks to quiet hours**: Move scans, subtitle downloads, and thumbnail extraction to 1–6 AM when playback is lowest.

---

Part of the [OpenClaw](https://github.com/openclaw) agent toolkit.
