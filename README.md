# movieradar

Finds movies currently streaming (flatrate/free/ads — not rent/buy) across
your chosen countries, filtered by IMDb rating, vote count, and a release-year
cutoff. Sends a Telegram message for each newly-qualifying movie; silent
otherwise. No dependencies beyond the Python standard library.

- **TMDB** tells us what's currently streaming, per country.
- **OMDb** gives the IMDb rating and vote count for each title.
- **Telegram** delivers the notification.
- `state.json` tracks what's already been notified so you don't get repeats.

## Quick start

```bash
git clone https://github.com/gerardcm/movieradar.git
cd movieradar
cp config.example.json config.json
```

Edit `config.json`:

| Key | Meaning |
|---|---|
| `tmdb_api_key` | free key from https://www.themoviedb.org/settings/api |
| `omdb_api_key` | free key from https://www.omdbapi.com/apikey.aspx (1,000 req/day) |
| `countries` | ISO country codes to check streaming availability in, e.g. `["US","GB","ES"]` |
| `providers` | TMDB watch-provider IDs to restrict to; `[]` = no restriction |
| `monetization_types` | any of `flatrate`, `free`, `ads` (case-insensitive) |
| `min_rating` / `min_votes` | IMDb filter thresholds |
| `language` | TMDB result language, e.g. `"en"` |
| `min_release_year` | ignore movies released before this year |
| `discovery_buffer_days` | wait this many days after a movie first shows up streaming before checking its IMDb rating/votes and possibly notifying (default `1`) |
| `max_pages_per_provider` | safety cap on TMDB pagination per country |
| `state_file` | path to the notified-movies tracking file |
| `telegram_bot_token` / `telegram_chat_id` | from [@BotFather](https://t.me/BotFather) and your chat id |

Every key can also be set via an environment variable (`TMDB_API_KEY`,
`OMDB_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `MIN_RATING`,
`MIN_VOTES`, `MIN_RELEASE_YEAR`, `DISCOVERY_BUFFER_DAYS`, `LANGUAGE`,
`STATE_FILE`) — handy for Docker/CI without touching `config.json`.

Run it:

```bash
python3 movieradar.py --config config.json
```

## Running it on a schedule

Two launchers, pick one — see [`docs/synology.md`](docs/synology.md) for the
full Synology Task Scheduler walkthrough:

- **`run.sh`** — git-based, `git pull --ff-only` then runs.
- **`run_from_github.py`** — no git needed, re-fetches `movieradar.py` from
  `raw.githubusercontent.com` on every run.

Either way `config.json` and `state.json` stay local and are never fetched
from or pushed to GitHub.

## Notes / limitations

- "Currently streaming" is based on TMDB's watch-provider data for each
  country, which is crowd-sourced and can occasionally lag reality by a few
  days.
- A newly-discovered movie sits for `discovery_buffer_days` (default 1 day)
  before its IMDb rating/votes are even checked, so its rating has a little
  time to reflect actual reviews and we don't burn an OMDb lookup on a title
  that might disappear from a provider the next day. `state.json` tracks
  each movie's first-seen date (`first_seen`) to enforce this.
- OMDb's free tier caps at 1,000 lookups/day — nowhere close to what this
  needs for a normal watchlist size.
- If you ever want to re-notify about everything currently qualifying,
  delete `state.json` (or the entries you want to reset) and run again.

## License

MIT — see [LICENSE](LICENSE).
