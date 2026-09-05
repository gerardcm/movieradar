#!/usr/bin/env python3
"""
movieradar.py

Finds movies currently available on streaming (flatrate/free/ads -- not
rent/buy) across your chosen countries, released on/after a cutoff year,
filtered by IMDb rating and vote count. Sends a Telegram notification for
each newly-qualifying movie (state is tracked in state_file so you're not
renotified every run) and prints a silent-run summary otherwise.

Data sources:
  - TMDB "Discover" API -> which movies are currently streaming, per country
    (free API key: https://www.themoviedb.org/settings/api)
  - OMDb API -> IMDb rating + vote count per title (free API key, 1000 req/day:
    https://www.omdbapi.com/apikey.aspx)
  - Telegram Bot API -> notifications

Usage:
    python3 movieradar.py --config config.json
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from urllib import request, parse, error

TMDB_BASE = "https://api.themoviedb.org/3"
OMDB_BASE = "https://www.omdbapi.com/"
TELEGRAM_BASE = "https://api.telegram.org"

DEFAULT_CONFIG = {
    "tmdb_api_key": "",
    "omdb_api_key": "",
    "countries": ["US"],
    "providers": [],                              # TMDB provider IDs; empty = no restriction
    "monetization_types": ["flatrate", "free", "ads"],
    "min_rating": 6.5,
    "min_votes": 10000,
    "language": "en",
    "min_release_year": date.today().year - 1,
    "max_pages_per_provider": 20,
    "state_file": "state.json",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
}


def load_config(path):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if path and os.path.exists(path):
        with open(path) as f:
            user_cfg = json.load(f)
        cfg.update(user_cfg)

    # Environment variables override file config (handy for Docker/CI/NAS use)
    env_map = {
        "TMDB_API_KEY": ("tmdb_api_key", str),
        "OMDB_API_KEY": ("omdb_api_key", str),
        "TELEGRAM_BOT_TOKEN": ("telegram_bot_token", str),
        "TELEGRAM_CHAT_ID": ("telegram_chat_id", str),
        "MIN_RATING": ("min_rating", float),
        "MIN_VOTES": ("min_votes", int),
        "MIN_RELEASE_YEAR": ("min_release_year", int),
        "LANGUAGE": ("language", str),
        "STATE_FILE": ("state_file", str),
    }
    for env_key, (cfg_key, caster) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
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
    """Query TMDB Discover, once per configured country, for movies currently
    available via the configured monetization types (flatrate/free/ads),
    released on/after min_release_year. Returns a de-duplicated list of TMDB
    movie summary dicts (deduped across countries by tmdb id)."""
    if not cfg["tmdb_api_key"]:
        sys.exit("Missing tmdb_api_key (set TMDB_API_KEY env var or config.json)")

    seen = {}
    for country in cfg["countries"]:
        page = 1
        while True:
            params = {
                "api_key": cfg["tmdb_api_key"],
                "language": cfg["language"],
                "region": country,
                "watch_region": country,
                "with_watch_monetization_types": "|".join(m.lower() for m in cfg["monetization_types"]),
                "primary_release_date.gte": f"{cfg['min_release_year']}-01-01",
                "sort_by": "popularity.desc",
                "page": page,
            }
            if cfg["providers"]:
                params["with_watch_providers"] = ",".join(str(p) for p in cfg["providers"])

            data = http_get_json(f"{TMDB_BASE}/discover/movie", params)
            for m in data.get("results", []):
                seen.setdefault(m["id"], m)
            total_pages = data.get("total_pages", 1)
            if page >= total_pages or page >= cfg["max_pages_per_provider"]:
                break
            page += 1
            time.sleep(0.25)  # be polite to the API

    return list(seen.values())


def get_imdb_id(cfg, tmdb_id):
    data = http_get_json(f"{TMDB_BASE}/movie/{tmdb_id}/external_ids", {"api_key": cfg["tmdb_api_key"]})
    return data.get("imdb_id")


def get_watch_providers(cfg, tmdb_id):
    """Returns {country: [provider names]} across all configured countries."""
    data = http_get_json(f"{TMDB_BASE}/movie/{tmdb_id}/watch/providers", {"api_key": cfg["tmdb_api_key"]})
    results = data.get("results", {})
    by_country = {}
    for country in cfg["countries"]:
        region_data = results.get(country, {})
        names = set()
        for mtype in ("flatrate", "free", "ads"):
            for p in region_data.get(mtype, []) or []:
                names.add(p["provider_name"])
        if names:
            by_country[country] = sorted(names)
    return by_country


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
        if rating < cfg["min_rating"] or votes < cfg["min_votes"]:
            continue

        providers_by_country = get_watch_providers(cfg, tmdb_id)
        streaming_on = "; ".join(
            f"{country}: {', '.join(names)}" for country, names in providers_by_country.items()
        ) or "(unknown)"

        qualifying.append({
            "title": title,
            "release_date": release_date,
            "imdb_id": imdb_id,
            "imdb_rating": rating,
            "imdb_votes": votes,
            "tmdb_id": tmdb_id,
            "streaming_on": streaming_on,
            "imdb_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "",
        })

    qualifying.sort(key=lambda x: x["release_date"], reverse=True)
    return qualifying


def load_state(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"notified_imdb_ids": []}


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def send_telegram_message(cfg, text):
    if not cfg["telegram_bot_token"] or not cfg["telegram_chat_id"]:
        return
    payload = json.dumps({
        "chat_id": cfg["telegram_chat_id"],
        "text": text,
        "disable_web_page_preview": False,
    }).encode()
    req = request.Request(
        f"{TELEGRAM_BASE}/bot{cfg['telegram_bot_token']}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            resp.read()
    except error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        print(f"Telegram notify failed: HTTP {e.code} {body[:200]}", file=sys.stderr)
    except error.URLError as e:
        print(f"Telegram notify failed: {e}", file=sys.stderr)


def notify_new_movies(cfg, rows):
    """Sends one Telegram message per movie not already in state_file, then
    updates state_file. Returns the list of newly-notified rows."""
    state = load_state(cfg["state_file"])
    known = set(state.get("notified_imdb_ids", []))

    new_rows = [r for r in rows if (r["imdb_id"] or f"tmdb-{r['tmdb_id']}") not in known]

    for r in new_rows:
        key = r["imdb_id"] or f"tmdb-{r['tmdb_id']}"
        message = (
            f"🎬 {r['title']} ({r['release_date'][:4]})\n"
            f"IMDb {r['imdb_rating']}/10 ({r['imdb_votes']:,} votes)\n"
            f"Streaming on: {r['streaming_on']}\n"
            f"{r['imdb_url']}"
        )
        send_telegram_message(cfg, message)
        known.add(key)

    state["notified_imdb_ids"] = sorted(known)
    save_state(cfg["state_file"], state)
    return new_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    cfg = load_config(args.config)
    rows = build_report(cfg)
    new_rows = notify_new_movies(cfg, rows)

    # Silent run: only print when something new was found.
    if new_rows:
        print(f"{len(new_rows)} new qualifying movie(s):")
        for r in new_rows:
            print(f"- {r['title']} ({r['release_date']}): {r['imdb_rating']}/10, "
                  f"{r['imdb_votes']:,} votes, on {r['streaming_on']}")
    else:
        print("No new qualifying movies this run.")


if __name__ == "__main__":
    main()
