# Running movieradar on Synology, referencing this repo

The Synology only holds a shallow clone of this repo plus your local
`config.json` (never committed). Updates to the code happen by `git pull`,
not by copying files onto the NAS by hand.

## 1. Clone the repo onto the NAS

Over SSH (Control Panel → Terminal & SNMP → enable SSH first):

```bash
mkdir -p /volume1/scripts
cd /volume1/scripts
git clone https://github.com/gerardcm/movieradar.git
cd movieradar
cp config.example.json config.json
```

Edit `config.json` with your real TMDB/OMDb keys and set `output_dir` to
somewhere Web Station can serve if you want the RSS feed, e.g.
`/volume1/web/movieradar`.

If DSM doesn't have `git` available natively, install "Git Server" from
Package Center (it bundles the `git` CLI), or run everything inside a
`python:3.12-slim` container that has git preinstalled via `apt-get`.

## 2. Test it once

Native Python (Package Center → install "Python 3"):

```bash
python3 /volume1/scripts/movieradar/movieradar.py --config /volume1/scripts/movieradar/config.json
```

Or via Docker (no DSM Python setup needed):

```bash
docker run --rm \
  -v /volume1/scripts/movieradar:/app \
  -w /app \
  python:3.12-slim \
  python3 movieradar.py --config config.json
```

## 3. Schedule it: pull + run

DSM → Control Panel → Task Scheduler → Create → Scheduled Task →
User-defined script.

- **Schedule tab**: weekly is plenty — new streaming titles don't show up
  hourly.
- **Task Settings tab → Run command**:

  ```bash
  cd /volume1/scripts/movieradar && git pull --ff-only && python3 movieradar.py --config config.json
  ```

  (swap the `python3 ...` line for the `docker run ...` command above if
  you're using the container route)

- Check **"Send run details by email"** — the script prints a plain-text
  summary to stdout, so this becomes your notification with zero extra
  setup.

`git pull --ff-only` will fail loudly (and show up in the emailed run
details) if you ever have local, uncommitted changes to tracked files on the
NAS — which you shouldn't, since the only file you edit locally
(`config.json`) is gitignored and untouched by pulls.

## 4. Optional: serve the RSS feed

If `output_dir` in `config.json` points at a folder under Web Station's
document root (e.g. `/volume1/web/movieradar`), install Web Station from
Package Center, point a Virtual Host at that folder, and subscribe your feed
reader to `http://<nas-ip>:<port>/movieradar/rss.xml`. Use your Tailscale/VPN
setup to read it remotely instead of exposing Web Station to the public
internet.
