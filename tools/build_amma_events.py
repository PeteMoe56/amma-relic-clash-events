#!/usr/bin/env python3
"""
build_amma_events.py  -  AMMA Relic Clash "AMMA Live" feed generator.

Scrapes the "NEXT SHOWS" section of https://www.armoredmma.com/ and writes the
stable JSON manifest the game reads (config/amma_events_defaults.json schema).

This is the AUTO-UPDATE ENGINE: run it on a schedule (cron / GitHub Action / any
server) and publish the resulting amma_events.json at the URL set in
LiveEventPromo.MANIFEST_URL. The game fetches that one URL, so the game never has
to understand the marketing site's HTML.

Usage:
    python3 build_amma_events.py                 # fetch live site -> amma_events.json
    python3 build_amma_events.py -o out.json     # custom output path
    python3 build_amma_events.py --html page.html  # parse a saved page (offline test)
    python3 build_amma_events.py --max 3         # number of events (default 3)

No third-party deps (urllib + regex only).
"""
import argparse, json, re, sys, datetime
from urllib.request import Request, urlopen

SITE = "https://www.armoredmma.com/"
WIX_MEDIA = "https://static.wixstatic.com/media/"

# An anchor in NEXT SHOWS wraps the poster image and links to the ticket page. We pull the
# whole anchor (href + inner HTML) so we can read both the Wix media id AND the <img alt="...">,
# which usually carries "City, ST" (e.g. alt="Event-Photos-Pittsburgh,-PA-REV.png").
ANCHOR = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>((?:(?!</a>)[\s\S])*?)</a>', re.IGNORECASE)
MEDIA = re.compile(r'src="https://static\.wixstatic\.com/media/([0-9a-zA-Z_]+~mv2\.(?:jpg|jpeg|png|webp))', re.IGNORECASE)
ALT = re.compile(r'alt="([^"]*)"', re.IGNORECASE)
ALT_CITY = re.compile(r'Event[-_ ]?Photos[-_ ]([A-Za-z .\'-]+?)[,\-\s]+([A-Z]{2})\b', re.IGNORECASE)
# "NEXT STOP:" then the first "City, ST" within a short window, even across tags.
NEXT_STOP_CITY = re.compile(r'NEXT STOP:[\s\S]{0,300}?([A-Z][A-Za-z .]+,\s*[A-Z]{2})', re.IGNORECASE)
NEXT_DATE = re.compile(r'(SATURDAY|SUNDAY|FRIDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY)\s+[A-Z]+\s+\d{1,2}\s*(?:TH|ST|ND|RD)?', re.IGNORECASE)

def city_from_alt(alt):
    m = ALT_CITY.search(alt or "")
    if not m:
        return ""
    city = re.sub(r'[-_]+', ' ', m.group(1)).strip().title()
    return "%s, %s" % (city, m.group(2).upper())


def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (AMMA-feed-bot)"})
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def raw_media_url(media_id_with_ext):
    # Use the original uploaded file (no avif transform) so non-browser clients
    # (Godot's Image loader) can decode it.
    return WIX_MEDIA + media_id_with_ext

def title_from_ticket(href):
    # https://armoredmmaxp.com/portland/  ->  "Portland"
    slug = re.sub(r'https?://[^/]+/', '', href).strip('/').split('/')[0]
    slug = slug.replace('-', ' ').strip()
    return slug.title() if slug else "Upcoming Event"

def build(html, max_events):
    events = []
    seen = set()
    for href, inner in ANCHOR.findall(html):
        href = href.strip()
        msrc = MEDIA.search(inner)
        if not href or not msrc:
            continue
        media = msrc.group(1)
        if media in seen:
            continue
        # Only keep real event ticket links (skip social/menu links).
        if not (href.startswith("http") and ("armoredmmaxp.com" in href or "feverup.com" in href or "/events" in href)):
            continue
        seen.add(media)
        malt = ALT.search(inner)
        city = city_from_alt(malt.group(1) if malt else "") or title_from_ticket(href)
        events.append({
            "title": city,
            "subtitle": "",
            "city": city,
            "date": "",
            "image_url": raw_media_url(media),
            "ticket_url": href,
        })
        if len(events) >= max_events:
            break

    up_next = {}
    mc = NEXT_STOP_CITY.search(html)
    if mc:
        up_next["headline"] = "NEXT STOP"
        up_next["city"] = mc.group(1).strip()
    md = NEXT_DATE.search(html)
    if md:
        up_next["date"] = md.group(0).strip()

    # The lead poster's alt sometimes lacks a state; backfill its "City, ST" from NEXT STOP.
    if events and "," not in events[0]["city"] and up_next.get("city"):
        parts = up_next["city"].split(",")
        nice = (parts[0].strip().title() + ", " + parts[1].strip().upper()) if len(parts) == 2 else up_next["city"].strip().title()
        events[0]["city"] = nice
        events[0]["title"] = nice

    return {
        "enabled": True,
        "updated": datetime.date.today().isoformat(),
        "source": "armoredmma.com/NEXT-SHOWS",
        "up_next": up_next,
        "events": events,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="amma_events.json")
    ap.add_argument("--html", help="parse a saved HTML file instead of fetching")
    ap.add_argument("--max", type=int, default=3)
    args = ap.parse_args()

    html = open(args.html, encoding="utf-8").read() if args.html else fetch(SITE)
    data = build(html, args.max)
    if not data["events"]:
        print("ERROR: no events parsed - site layout may have changed; refusing to overwrite.", file=sys.stderr)
        sys.exit(1)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Wrote %s (%d events)" % (args.out, len(data["events"])))

if __name__ == "__main__":
    main()
