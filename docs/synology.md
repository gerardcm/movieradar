# Running movieradar on Synology, referencing this repo

Two options, both keep `config.json` (your real API keys) local and out of
git entirely:

- **Option A — git-based (`run.sh`)**: a real clone of this repo on the NAS,
  updated with `git pull`. Requires `git` on the host.
- **Option B — no-git (`run_from_github.py`)**: just a launcher script and
  `config.json` on the NAS; it fetches `movieradar.py` fresh from
  `raw.githubusercontent.com` on every run. Nothing to keep in sync manually,
  and no `git` dependency — closer to how a lot of self-hosted "pull config
  from GitHub at runtime" scripts already work.

Pick whichever fits your setup. Option B is simpler if you don't already
have `git` on the NAS.

## Option A: git-based (`run.sh`)

### 1. Clone the repo onto the NAS

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

### 2. Test it once

```bash
bash /volume1/scripts/movieradar/run.sh
```

`run.sh` cd's into its own directory, runs `git pull --ff-only`, checks that
`config.json` exists, then runs `movieradar.py`. It's the single command
Task Scheduler will call.

### 3. Schedule it

DSM → Control Panel → Task Scheduler → Create → Scheduled Task →
User-defined script.

- **Schedule tab**: weekly is plenty — new streaming titles don't show up
  hourly.
- **Task Settings tab → Run command**:

  ```bash
  bash /volume1/scripts/movieradar/run.sh
  ```

- Check **"Send run details by email"** — the script prints a plain-text
  summary to stdout, so this becomes your notification with zero extra
  setup.

`git pull --ff-only` inside `run.sh` will fail loudly (and show up in the
emailed run details) if you ever have local, uncommitted changes to tracked
files on the NAS — which you shouldn't, since the only file you edit locally
(`config.json`) is gitignored and untouched by pulls.

## Option B: no-git (`run_from_github.py`)

### 1. Put two files on the NAS — no clone needed

Over SSH, or by just copying via File Station:

```bash
mkdir -p /volume1/scripts/movieradar
cd /volume1/scripts/movieradar
curl -O https://raw.githubusercontent.com/gerardcm/movieradar/main/run_from_github.py
curl -O https://raw.githubusercontent.com/gerardcm/movieradar/main/config.example.json
cp config.example.json config.json
```

Edit `config.json` with your real TMDB/OMDb keys, same as Option A.

### 2. Test it once

```bash
python3 /volume1/scripts/movieradar/run_from_github.py
```

This fetches the latest `movieradar.py` from GitHub into
`_movieradar_fetched.py` next to it, then runs it against your local
`config.json`. Every run re-fetches, so the code is always current with
whatever's on the `main` branch — nothing to `git pull` or keep in sync.

### 3. Schedule it

Same as Option A's Task Scheduler steps, just with this run command:

```bash
python3 /volume1/scripts/movieradar/run_from_github.py
```

Check **"Send run details by email"** here too for the same zero-setup
notification.

## Optional: serve the RSS feed

If `output_dir` in `config.json` points at a folder under Web Station's
document root (e.g. `/volume1/web/movieradar`), install Web Station from
Package Center, point a Virtual Host at that folder, and subscribe your feed
reader to `http://<nas-ip>:<port>/movieradar/rss.xml`. Use your Tailscale/VPN
setup to read it remotely instead of exposing Web Station to the public
internet.
