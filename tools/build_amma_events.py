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

# An anchor in NEXT SHOWS looks like:
#   <a href="https://armoredmmaxp.com/portland/">
#     <img src="https://static.wixstatic.com/media/<id>~mv2.jpg/v1/fill/.../file.jpg" alt="...">
# We capture the ticket href, the wix media id, and the original extension.
LINKED_IMG = re.compile(
    r'<a[^>]+href="([^"]+)"[^>]*>\s*<img[^>]+src="'
    r'https://static\.wixstatic\.com/media/([0-9a-zA-Z_]+~mv2\.(?:jpg|jpeg|png|webp))',
    re.IGNORECASE,
)
NEXT_STOP = re.compile(r'NEXT STOP:\s*([^<]+?)\s*</', re.IGNORECASE)
NEXT_DATE = re.compile(r'(SATURDAY|SUNDAY|FRIDAY|MONDAY|TUESDAY|WEDNESDAY|THURSDAY)\s+[A-Z]+\s+\d{1,2}\s*(?:TH|ST|ND|RD)?', re.IGNORECASE)

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
    for href, media in LINKED_IMG.findall(html):
        href = href.strip()
        if not href or media in seen:
            continue
        # Only keep real event ticket links (skip social/menu links).
        if not (href.startswith("http") and ("armoredmmaxp.com" in href or "feverup.com" in href or "/events" in href)):
            continue
        seen.add(media)
        events.append({
            "title": title_from_ticket(href),
            "subtitle": "",
            "city": title_from_ticket(href),
            "date": "",
            "image_url": raw_media_url(media),
            "ticket_url": href,
        })
        if len(events) >= max_events:
            break

    up_next = {}
    m = NEXT_STOP.search(html)
    if m:
        up_next["headline"] = "NEXT STOP"
        up_next["city"] = m.group(1).strip()
    d = NEXT_DATE.search(html)
    if d:
        up_next["date"] = d.group(0).strip()

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
        print("WARNING: no events parsed - site layout may have changed.", file=sys.stderr)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Wrote %s (%d events)" % (args.out, len(data["events"])))

if __name__ == "__main__":
    main()
