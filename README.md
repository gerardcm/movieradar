# movieradar

Finds movies that just debuted on streaming (not theatrical releases),
filtered by IMDb rating and vote count, and writes CSV/JSON/Markdown/RSS
reports. No paid APIs, no dependencies beyond the Python standard library.

- **TMDB** tells us which movies got a digital/streaming release in a region + date window.
- **OMDb** gives the IMDb rating and vote count for each title.
- Optionally auto-adds qualifying movies to **Radarr**.

## Quick start

```bash
git clone https://github.com/gerardcm/movieradar.git
cd movieradar
cp config.example.json config.json
```

Edit `config.json`:
- `tmdb_api_key` — free key from https://www.themoviedb.org/settings/api
- `omdb_api_key` — free key from https://www.omdbapi.com/apikey.aspx (1,000 req/day)
- `watch_region` — e.g. `"US"`
- `min_imdb_rating` / `min_imdb_votes` / `days_back` — your thresholds
- `output_dir` — where reports land (keep this **outside** the repo folder; see `.gitignore`)

Run it:

```bash
python3 movieradar.py --config config.json
```

## Config reference

| Key | Meaning |
|---|---|
| `tmdb_api_key` / `omdb_api_key` | API credentials (also settable via `TMDB_API_KEY` / `OMDB_API_KEY` env vars) |
| `watch_region` | ISO country code for streaming availability (`WATCH_REGION`) |
| `days_back` | Rolling window size in days (`DAYS_BACK`) |
| `min_imdb_rating` / `min_imdb_votes` | Filter thresholds (`MIN_IMDB_RATING` / `MIN_IMDB_VOTES`) |
| `release_types` | TMDB release types to include — `4` = Digital, `6` = TV/straight-to-streaming |
| `output_dir` | Where reports are written (`OUTPUT_DIR`) |
| `output_formats` | Any of `csv`, `json`, `md`, `rss` |
| `feed_title` / `feed_link` / `feed_description` | RSS channel metadata (`FEED_TITLE` / `FEED_LINK` / `FEED_DESCRIPTION`) |
| `radarr.*` | Optional auto-add to Radarr — see below |

Every config key can be overridden by an environment variable, which is handy
for Docker/CI without touching `config.json`.

## RSS feed

Every run writes a stable `rss.xml` (filename never changes) into
`output_dir`, reflecting whatever currently qualifies. Point any feed reader
at it once you're serving `output_dir` over HTTP (see `docs/synology.md` for
a Synology Web Station setup).

## Radarr auto-add

Set `radarr.enabled: true` and fill in `radarr.url` / `radarr.api_key` /
`radarr.root_folder_path` / `radarr.quality_profile_id`. Qualifying movies
get added as monitored; set `radarr.search_on_add: true` if you also want
Radarr to immediately search for a release.

## Running it on a schedule

Two ways to keep the code on your NAS in sync with this repo — pick one:

1. **`run.sh` (git-based)** — clones once, then `git pull --ff-only` before
   every run. Requires `git` on the host. Good if you want the full repo
   (docs included) checked out.
2. **`run_from_github.py` (no git needed)** — fetches `movieradar.py` fresh
   from `raw.githubusercontent.com` on every run and executes it, no local
   checkout to keep in sync. Just needs `config.json` sitting next to it.
   Same "pull from GitHub at runtime" pattern, just for the code itself
   instead of a config file.

Either way, `config.json` (your real API keys) stays local and is never
fetched from or pushed to GitHub. See [`docs/synology.md`](docs/synology.md)
for the exact Task Scheduler setup for both options. Works the same with
cron, a systemd timer, or a GitHub Actions scheduled workflow elsewhere.

## Notes / limitations

- TMDB's digital release date is crowd-sourced and can lag a few days behind
  the actual streaming debut — a 90-day window with weekly runs gives enough
  overlap that nothing should slip through.
- OMDb's free tier caps at 1,000 lookups/day; a quarter's worth of streaming
  releases is nowhere close to that.
- Ratings/votes are a snapshot at run time — a title added right after
  release may not yet have enough votes and will simply appear in a later
  run once it clears the threshold.

## License

MIT — see [LICENSE](LICENSE).
