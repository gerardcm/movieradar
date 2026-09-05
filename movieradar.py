#!/usr/bin/env python3
"""
movieradar.py

Finds movies that had their STREAMING debut (digital/streaming release, not
theatrical) within a rolling date window, filtered by IMDb rating and vote
count. Built for unattended runs on a schedule (e.g. Synology Task Scheduler,
cron, GitHub Actions).

Data sources:
  - TMDB "Discover" API -> which movies got a digital/streaming release in a
    region + date window (free API key: https://www.themoviedb.org/settings/api)
  - OMDb API -> IMDb rating + vote count per title (free API key, 1000 req/day:
    https://www.omdbapi.com/apikey.aspx)

Optional:
  - Auto-add qualifying movies to Radarr (so they show up in your library /
    "wanted" list).
  - Write results to CSV/JSON/Markdown/RSS.

Usage:
    python3 movieradar.py --config config.json

Or configure entirely via environment variables (see config.example.json for
the full list of keys / env var names) -- handy for CI or Docker.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape
from urllib import request, parse, error

TMDB_BASE = "https://api.themoviedb.org/3"
OMDB_BASE = "https://www.omdbapi.com/"

DEFAULT_CONFIG = {
    "tmdb_api_key": "",
    "omdb_api_key": "",
    "watch_region": "US",
    "days_back": 90,
    "min_imdb_rating": 6.5,
    "min_imdb_votes": 10000,
    "release_types": [4, 6],  # 4 = Digital, 6 = TV/straight-to-streaming
    "output_dir": ".",
    "output_formats": ["csv", "json", "md", "rss"],
    "feed_title": "New Streaming Movies (IMDb filtered)",
    "feed_link": "http://localhost/",
    "feed_description": "Movies newly available on streaming, filtered by IMDb rating/votes",
    "radarr": {
        "enabled": False,
        "url": "",
        "api_key": "",
        "root_folder_path": "",
        "quality_profile_id": 1,
        "monitored": True,
        "search_on_add": False
    }
}


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if path and os.path.exists(path):
        with open(path) as f:
            user_cfg = json.load(f)
        cfg.update({k: v for k, v in user_cfg.items() if k != "radarr"})
        if "radarr" in user_cfg:
            cfg["radarr"].update(user_cfg["radarr"])

    # Environment variables override file config (handy for Docker/CI/NAS use)
    env_map = {
        "TMDB_API_KEY": ("tmdb_api_key", str),
        "OMDB_API_KEY": ("omdb_api_key", str),
        "WATCH_REGION": ("watch_region", str),
        "DAYS_BACK": ("days_back", int),
        "MIN_IMDB_RATING": ("min_imdb_rating", float),
        "MIN_IMDB_VOTES": ("min_imdb_votes", int),
        "OUTPUT_DIR": ("output_dir", str),
        "RADARR_URL": (("radarr", "url"), str),
        "RADARR_API_KEY": (("radarr", "api_key"), str),
        "RADARR_ROOT_FOLDER": (("radarr", "root_folder_path"), str),
        "RADARR_QUALITY_PROFILE_ID": (("radarr", "quality_profile_id"), int),
        "RADARR_ENABLED": (("radarr", "enabled"), lambda v: v.lower() in ("1", "true", "yes")),
        "FEED_TITLE": ("feed_title", str),
        "FEED_LINK": ("feed_link", str),
        "FEED_DESCRIPTION": ("feed_description", str),
    }
    for env_key, (cfg_key, caster) in env_map.items():
        val = os.environ.get(env_key)
        if val is None:
            continue
        if isinstance(cfg_key, tuple):
            cfg[cfg_key[0]][cfg_key[1]] = caster(val)
        else:
            cfg[cfg_key] = caster(val)

    return cfg


def http_get_json(url, params, retries=3, backoff=2):
    qs = parse.urlencode(params)
    full_url = f"{url}?{qs}"
    for attempt in range(1, retries + 1):
        try:
            with request.urlopen(full_url, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(backoff * attempt)
                continue
            body = e.read().decode(errors="ignore")
            raise RuntimeError(f"HTTP {e.code} for {url}: {body[:300]}") from e
        except error.URLError as e:
            if attempt < retries:
                time.sleep(backoff * attempt)
                continue
            raise RuntimeError(f"Network error for {url}: {e}") from e
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


def discover_streaming_movies(cfg):
    """Query TMDB Discover for movies with a digital/streaming release in the
    configured region within the date window. Returns a de-duplicated list of
    TMDB movie summary dicts."""
    if not cfg["tmdb_api_key"]:
        sys.exit("Missing tmdb_api_key (set TMDB_API_KEY env var or config.json)")

    today = datetime.utcnow().date()
    start = today - timedelta(days=cfg["days_back"])

    seen = {}
    for release_type in cfg["release_types"]:
        page = 1
        while True:
            params = {
                "api_key": cfg["tmdb_api_key"],
                "region": cfg["watch_region"],
                "watch_region": cfg["watch_region"],
                "with_release_type": release_type,
                "release_date.gte": start.isoformat(),
                "release_date.lte": today.isoformat(),
                "sort_by": "primary_release_date.desc",
                "page": page,
            }
            data = http_get_json(f"{TMDB_BASE}/discover/movie", params)
            for m in data.get("results", []):
                seen[m["id"]] = m
            total_pages = data.get("total_pages", 1)
            if page >= total_pages or page >= 20:  # safety cap
                break
            page += 1
            time.sleep(0.25)  # be polite to the API

    return list(seen.values())


def get_imdb_id(cfg, tmdb_id):
    data = http_get_json(f"{TMDB_BASE}/movie/{tmdb_id}/external_ids", {"api_key": cfg["tmdb_api_key"]})
    return data.get("imdb_id")


def get_watch_providers(cfg, tmdb_id):
    data = http_get_json(f"{TMDB_BASE}/movie/{tmdb_id}/watch/providers", {"api_key": cfg["tmdb_api_key"]})
    region_data = data.get("results", {}).get(cfg["watch_region"], {})
    flatrate = region_data.get("flatrate", []) or []
    return [p["provider_name"] for p in flatrate]


def get_imdb_rating(cfg, imdb_id):
    if not cfg["omdb_api_key"] or not imdb_id:
        return None, None
    data = http_get_json(OMDB_BASE, {"i": imdb_id, "apikey": cfg["omdb_api_key"]})
    if data.get("Response") == "False":
        return None, None
    rating = data.get("imdbRating")
    votes = data.get("imdbVotes")
    try:
        rating = float(rating) if rating and rating != "N/A" else None
    except ValueError:
        rating = None
    try:
        votes = int(votes.replace(",", "")) if votes and votes != "N/A" else None
    except (ValueError, AttributeError):
        votes = None
    return rating, votes


def build_report(cfg):
    candidates = discover_streaming_movies(cfg)
    qualifying = []

    for m in candidates:
        tmdb_id = m["id"]
        title = m.get("title") or m.get("original_title")
        release_date = m.get("release_date", "")

        imdb_id = get_imdb_id(cfg, tmdb_id)
        rating, votes = get_imdb_rating(cfg, imdb_id)
        time.sleep(0.1)

        if rating is None or votes is None:
            continue
        if rating < cfg["min_imdb_rating"] or votes < cfg["min_imdb_votes"]:
            continue

        providers = get_watch_providers(cfg, tmdb_id)

        qualifying.append({
            "title": title,
            "release_date": release_date,
            "imdb_id": imdb_id,
            "imdb_rating": rating,
            "imdb_votes": votes,
            "tmdb_id": tmdb_id,
            "streaming_on": ", ".join(providers) if providers else "(unknown)",
            "imdb_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "",
        })

    qualifying.sort(key=lambda x: x["release_date"], reverse=True)
    return qualifying


def build_rss(cfg, rows):
    """Build an RSS 2.0 feed from qualifying movies. Each run's items replace
    the previous run's (the feed reflects "currently qualifying movies from
    the last N days", not a growing history)."""
    now = format_datetime(datetime.now(timezone.utc))
    items = []
    for r in rows:
        # Use an approximate pubDate from the release_date so readers sort
        # sensibly; fall back to now if release_date is missing/malformed.
        try:
            pub = format_datetime(
                datetime.strptime(r["release_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            )
        except (ValueError, TypeError):
            pub = now

        title = escape(r["title"])
        link = escape(r["imdb_url"] or cfg["feed_link"])
        # guid must be stable per movie so readers don't re-notify every run
        guid = escape(r["imdb_id"] or f"tmdb-{r['tmdb_id']}")
        description = escape(
            f"IMDb {r['imdb_rating']}/10 ({r['imdb_votes']:,} votes) — "
            f"streaming on {r['streaming_on']} — released {r['release_date']}"
        )
        items.append(
            "  <item>\n"
            f"    <title>{title}</title>\n"
            f"    <link>{link}</link>\n"
            f"    <guid isPermaLink=\"false\">{guid}</guid>\n"
            f"    <pubDate>{pub}</pubDate>\n"
            f"    <description>{description}</description>\n"
            "  </item>"
        )

    channel_title = escape(cfg["feed_title"])
    channel_link = escape(cfg["feed_link"])
    channel_desc = escape(cfg["feed_description"])

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "<channel>\n"
        f"  <title>{channel_title}</title>\n"
        f"  <link>{channel_link}</link>\n"
        f"  <description>{channel_desc}</description>\n"
        f"  <lastBuildDate>{now}</lastBuildDate>\n"
        + "\n".join(items) +
        "\n</channel>\n</rss>\n"
    )


def write_outputs(cfg, rows):
    out_dir = cfg["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    base = os.path.join(out_dir, f"streaming_movies_{stamp}")

    if "rss" in cfg["output_formats"]:
        # Stable filename (no date stamp) so the subscription URL never changes.
        rss_path = os.path.join(out_dir, "rss.xml")
        with open(rss_path, "w") as f:
            f.write(build_rss(cfg, rows))

    if "json" in cfg["output_formats"]:
        with open(base + ".json", "w") as f:
            json.dump(rows, f, indent=2)

    if "csv" in cfg["output_formats"]:
        with open(base + ".csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "title", "release_date", "imdb_rating", "imdb_votes",
                "streaming_on", "imdb_url"
            ])
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r[k] for k in writer.fieldnames})

    if "md" in cfg["output_formats"]:
        with open(base + ".md", "w") as f:
            f.write(f"# New streaming movies ({stamp})\n\n")
            f.write(f"IMDb rating >= {cfg['min_imdb_rating']}, votes >= {cfg['min_imdb_votes']}, "
                    f"last {cfg['days_back']} days, region {cfg['watch_region']}\n\n")
            if not rows:
                f.write("No qualifying movies found this run.\n")
            for r in rows:
                f.write(f"- **{r['title']}** ({r['release_date']}) — "
                        f"{r['imdb_rating']}/10, {r['imdb_votes']:,} votes — "
                        f"{r['streaming_on']} — [IMDb]({r['imdb_url']})\n")

    return base


def add_to_radarr(cfg, rows):
    radarr = cfg["radarr"]
    if not radarr.get("enabled"):
        return
    if not radarr.get("url") or not radarr.get("api_key"):
        print("Radarr integration enabled but url/api_key missing; skipping.", file=sys.stderr)
        return

    headers = {"X-Api-Key": radarr["api_key"], "Content-Type": "application/json"}
    for r in rows:
        payload = {
            "title": r["title"],
            "tmdbId": r["tmdb_id"],
            "qualityProfileId": radarr.get("quality_profile_id", 1),
            "rootFolderPath": radarr.get("root_folder_path", ""),
            "monitored": radarr.get("monitored", True),
            "addOptions": {"searchForMovie": radarr.get("search_on_add", False)},
        }
        req = request.Request(
            radarr["url"].rstrip("/") + "/api/v3/movie",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                resp.read()
                print(f"Added to Radarr: {r['title']}")
        except error.HTTPError as e:
            body = e.read().decode(errors="ignore")
            # Radarr returns 400 if the movie already exists; don't treat as fatal
            print(f"Radarr add skipped/failed for {r['title']}: HTTP {e.code} {body[:200]}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    cfg = load_config(args.config)
    rows = build_report(cfg)
    base_path = write_outputs(cfg, rows)
    add_to_radarr(cfg, rows)

    fmt_note = "/".join(cfg["output_formats"])
    print(f"\n{len(rows)} qualifying movie(s) found. Reports written to {base_path}.[{fmt_note}]")
    if "rss" in cfg["output_formats"]:
        print(f"RSS feed: {os.path.join(cfg['output_dir'], 'rss.xml')}")
    print()
    for r in rows:
        print(f"- {r['title']} ({r['release_date']}): {r['imdb_rating']}/10, "
              f"{r['imdb_votes']:,} votes, on {r['streaming_on']}")


if __name__ == "__main__":
    main()
