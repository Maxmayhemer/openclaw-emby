# Emby — Bot Skill Guide

This file teaches your OpenClaw bot what it can do with your Emby server using the tools in this repo. Load it into your bot's memory or reference it in your boot prompt.

All commands run via `emby-profile.py` or `emby-metadata-repair.sh`. Credentials live at `~/.config/emby/credentials.json` — the bot should never expose the API key in chat.

---

## What Your Bot Can Do

### 1. Check Server Health
**When to use:** User asks if the server is up, notices buffering, or asks for server info.

```bash
python tools/emby-profile.py --test
```

Returns: server name, version, OS, and connection status. If it fails, the server is down or credentials are wrong.

**Natural language triggers:**
- "Is the Emby server up?"
- "Check the server status"
- "Is anything wrong with Emby?"

---

### 2. See Who's Watching Right Now
**When to use:** User wants to know who's streaming, how many streams are active, or if it's safe to restart.

```bash
python tools/emby-profile.py --sessions
```

Returns: each active stream with username, title, and client app. Also shows idle sessions.

**Natural language triggers:**
- "Who's watching right now?"
- "Is anyone streaming?"
- "How many active streams?"
- "What is [person] watching?"

---

### 3. Search the Library
**When to use:** User wants to know if something is on the server, or needs an item ID for a follow-up action.

```bash
python tools/emby-profile.py --search "Breaking Bad"
python tools/emby-profile.py --search "The Batman 2022"
```

Returns: matching titles with type (Movie/Series/Episode), year, and item ID. Marks favorites with ★.

**Natural language triggers:**
- "Is [title] on Emby?"
- "Do we have [title]?"
- "Find [title] in the library"
- "Search for [title]"

---

### 4. Add or Remove Favorites / Watchlist
**When to use:** User wants to bookmark something to watch later, or clean up their watchlist.

```bash
python tools/emby-profile.py --add "Severance"
python tools/emby-profile.py --remove "Severance"
```

Searches for the title, picks the best match, and marks/unmarks it as a favorite. Favorites in Emby act as a personal watchlist.

**Natural language triggers:**
- "Add [title] to my watchlist"
- "Mark [title] as a favorite"
- "Remove [title] from my watchlist"
- "I want to remember to watch [title]"

---

### 5. See What's In Progress
**When to use:** User asks what they were watching, or wants a "continue watching" summary.

Run the full profile refresh (which outputs continue-watching to the profile file):
```bash
python tools/emby-profile.py
```

Or check the cached profile file directly:
```bash
cat memory/max-emby-profile.md   # adjust path to your output file
```

**Natural language triggers:**
- "What was I watching?"
- "What do I have in progress?"
- "What's in my continue watching?"
- "What episode was I on for [show]?"

---

### 6. Refresh the Watch Profile
**When to use:** User wants an up-to-date summary of their watch history, favorites, and in-progress items. Typically run on a weekly cron.

```bash
python tools/emby-profile.py
python tools/emby-profile.py --limit 200   # fetch more history
```

Writes a Markdown file with: currently watching, recently watched movies/shows, most-watched shows, and favorites. The bot can read this file to answer questions about the user's media preferences.

**Natural language triggers:**
- "Update my Emby profile"
- "Refresh my watch history"
- "What have I been watching lately?"

---

### 7. Check for Missing Metadata / Broken Posters
**When to use:** User notices missing posters, blank titles, or items with no description. Run a scan first to see the scope, then optionally trigger repair.

```bash
# Scan only — no changes made
python tools/emby-profile.py --missing-meta

# Scan and trigger Emby's built-in refresh on each broken item
python tools/emby-profile.py --missing-meta --refresh-meta
```

Reports each item missing: poster, backdrop, overview, year, genres, or rating. Good for a weekly health check.

**Natural language triggers:**
- "How many items are missing posters?"
- "Scan for broken metadata"
- "Are there any items with missing info?"
- "Do a metadata health check"

---

### 8. Fix Missing Posters / Metadata (Deep Repair)
**When to use:** Standard refresh didn't fix missing posters (common with Blu-ray folder structures or items that have never had a provider ID set). This does a fresh remote search and injects the result directly.

```bash
# Dry run first — see what would be fixed
bash tools/emby-metadata-repair.sh --dry-run

# Fix movies in a specific library
bash tools/emby-metadata-repair.sh --library-name "Movies"

# Fix a 4K library
bash tools/emby-metadata-repair.sh --library-name "4K Movies"

# Fix TV shows
bash tools/emby-metadata-repair.sh --type Series --library-name "TV Shows"

# Fix anime
bash tools/emby-metadata-repair.sh --type Series --library-name "Anime"

# Watch progress
tail -f /tmp/emby_metadata_repair.log
```

**Natural language triggers:**
- "Fix the missing posters in [library]"
- "My [library] library is missing artwork"
- "Run a full metadata repair on [library]"
- "A lot of movies are missing posters, fix them"

**Note:** This runs at ~1 item every 2 seconds to stay gentle. A large library (500+ items) takes 15–20 minutes. Best scheduled overnight.

---

### 9. Restart the Server
**When to use:** Server is behaving oddly, after a system update, or user explicitly requests it. The bot will always check for active streams first and warn before proceeding.

```bash
python tools/emby-profile.py --restart
```

The script checks active streams and requires confirmation if anyone is watching. Never restart silently mid-stream.

**Natural language triggers:**
- "Restart the Emby server"
- "Emby is acting weird, restart it"
- "Reboot Emby"

**Bot behavior:** Always run `--sessions` first. Tell the user how many active streams there are. Only restart if they confirm or if there are zero streams.

---

## Scheduled Maintenance (Recommended Crons)

| Task | Schedule | Command |
|------|----------|---------|
| Refresh watch profile | Weekly, Sunday 6 AM | `python tools/emby-profile.py` |
| Missing metadata scan | Weekly, Sunday 6:05 AM | `python tools/emby-profile.py --missing-meta` |
| Deep metadata repair | Weekly, Sunday 2 AM | `bash tools/emby-metadata-repair.sh` |

Run repair before the scan so the scan reflects the post-repair state.

---

## Common Scenarios

**"My library looks fine but posters are missing for new stuff I added"**
→ Run `--missing-meta` to confirm scope, then `emby-metadata-repair.sh --library-name "..."` targeting the affected library.

**"Emby is slow / buffering"**
→ Check `--sessions` for how many active streams. Check `--test` to confirm server is responsive. If server is responsive but slow, check if a scan or thumbnail extraction task is running (visible in Emby Dashboard → Scheduled Tasks).

**"I want to know if [title] is on the server before I tell someone"**
→ Run `--search "[title]"` and report back.

**"Add these to my watchlist: [list of titles]"**
→ Run `--add` for each one. Report any that couldn't be found.

**"Something looks wrong with Emby, give me a full status"**
→ Run `--test`, then `--sessions`. Report: server up/down, version, active streams, any errors.

---

## What the Bot Should NOT Do

- Never expose the API key in chat
- Never restart while streams are active without explicit user confirmation
- Never run `--refresh-meta` on the full library without warning — it queues thousands of server jobs and can hammer the server
- Never run `emby-metadata-repair.sh` without `--dry-run` first on an unfamiliar library
- Don't assume library names — always check with `--search` or ask the user what their libraries are called

---

## Setup Reference

Credentials at `~/.config/emby/credentials.json`:
```json
{
  "server_url": "http://YOUR_EMBY_SERVER:8096",
  "api_key":    "YOUR_EMBY_API_KEY",
  "user_id":    "YOUR_EMBY_USER_ID",
  "username":   "YourUsername"
}
```

- **API key**: Emby Dashboard → Advanced → API Keys → New API Key
- **User ID**: Emby Dashboard → Users → click your user → ID is in the URL bar
- **Server URL**: the address you use to reach Emby in a browser (include port, no trailing slash)
