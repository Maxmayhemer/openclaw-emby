# OpenClaw Emby Toolkit

A set of tools for [OpenClaw](https://github.com/openclaw) agents to interact with your [Emby](https://emby.media) media server — watch history profiling, metadata repair, and library health monitoring.

## Tools

### `emby-profile.py`
Generates a Markdown watch history profile from your Emby server. Useful for feeding into your agent's memory to understand your media preferences.

### `emby-4k-metadata-refresh.sh`
Batch metadata repair tool specifically for 4K Blu-ray folder libraries. Fixes missing posters and metadata using Emby's RemoteSearch/Apply API, which works correctly for Blu-ray folder structures where standard refresh does not.

## Requirements

```
pip install requests
```

The shell script requires `bash`, `curl`, and `jq`.

## Setup

1. Copy the credentials template:
   ```bash
   mkdir -p ~/.config/emby
   cp credentials.json.example ~/.config/emby/credentials.json
   chmod 600 ~/.config/emby/credentials.json
   ```

2. Fill in your Emby server URL, API key, and user ID.
   - **API key**: Emby Dashboard → Advanced → API Keys → New API Key
   - **User ID**: Emby Dashboard → Users → click your user → note the ID in the URL

## emby-profile.py

```bash
# Generate watch history profile
python emby-profile.py

# Force refresh (ignore cache)
python emby-profile.py --refresh

# Authenticate / update credentials
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

## emby-4k-metadata-refresh.sh

Repairs missing metadata and posters for 4K libraries stored in Blu-ray folder format (e.g., `Movie Title (Year) [imdbid-ttXXXXX]/BDMV/...`).

Standard Emby metadata refresh does not correctly resolve these items because ProviderIds are never populated from the folder structure alone. This script uses the `RemoteSearch/Apply` endpoint which directly injects matched metadata.

### Usage

```bash
# Run directly
bash emby-4k-metadata-refresh.sh

# Check progress log
tail -f /tmp/emby_4k_refresh.log
```

Configure your Emby URL and API key at the top of the script:
```bash
EMBY_URL="http://your-emby-server:8096"
API_KEY="your-api-key"
LIBRARY_ID="your-4k-library-id"   # Get from Emby Dashboard → Libraries
```

### How It Works

For each movie missing a TMDb ID or poster:
1. Extracts the IMDb ID from the folder name `[imdbid-ttXXXXX]` if present
2. Calls `POST /Items/RemoteSearch/Movie` with name + IMDb ID to find the TMDb match
3. Calls `POST /Items/RemoteSearch/Apply/{id}?ReplaceAllImages=true` to apply the result

Rate limited to 1 request/second to avoid overloading the server.

### Running Overnight via Cron (OpenClaw)

```json
{
  "id": "emby-4k-metadata-refresh",
  "schedule": "0 2 * * *",
  "description": "Repair missing 4K movie metadata overnight",
  "type": "shell",
  "command": "bash /path/to/emby-4k-metadata-refresh.sh",
  "enabled": true,
  "oneshot": true
}
```

## Credentials File

See `credentials.json.example`:

```json
{
  "server_url": "http://YOUR_EMBY_SERVER:8096",
  "api_key": "YOUR_EMBY_API_KEY",
  "user_id": "YOUR_EMBY_USER_ID",
  "username": "YourUsername"
}
```

## Library Health Tips

- **4K Blu-ray folders not getting metadata**: Use `emby-4k-metadata-refresh.sh`. Standard library scan will not fix these.
- **Enable automatic refresh**: Emby Dashboard → Libraries → Manage Library → enable "Automatically refresh content every N days" (30 days recommended).
- **Download images in advance**: Enable "Download images in advance" in each library's settings to pre-cache posters.
- **Schedule tasks to quiet hours**: Move all scheduled tasks (scan, subtitle download, thumbnail extraction) to 1–6 AM when playback is lowest.

---

Part of the [OpenClaw](https://github.com/openclaw) agent toolkit.
