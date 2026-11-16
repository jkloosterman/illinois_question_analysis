#!/usr/bin/env python3
"""Download item previews from the Illinois Digital Item Library.

Default target: https://il.digitalitemlibrary.com/home?subject=ELA&grades=Grade%206&view=ES

How the site works (an Angular app; no HTML scraping of the table needed):
  1. /apiBE/getJSONFromS3?account=il&subject=ela&grade=Grade 6&view=ES
     -> list of sections (e.g. "ES.ELA-LITERACY.L 6.4.1"), each with an
        "itemGuid" list of table rows (Item Identifier = "name", etc.).
  2. /apiBE/previewItem?itemUIN=<Item Identifier>&account=il
     -> {"success": "yes", "itemUrl": "<TestNav previewer page>"}  (the popup iframe)
  3. The previewer page has an empty #itemCanvasBody that its JavaScript fills
     from JSON at /api/tenants/<tenant>/item/<itemId>/getItemFlavor (sent with
     header x-authorization: <ticket from the page>). That JSON
     (msg.itemBodyHtml / msg.httpsItemBodyHtml) is the itemCanvasBody content,
     so it is saved as <Item Identifier>.json.

Output:
  <outdir>/<Item Identifier>.json   one per unique item
  <outdir>/items.csv                one row per (section, item)
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://il.digitalitemlibrary.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) item-library-downloader"
ROW_FIELDS = ["subject", "grade", "cluster", "item_type", "ccss_domain",
              "PCR_task_type", "passage_id", "release_admin"]


def fetch(url, headers=None, retries=3, timeout=60):
    hdrs = {"User-Agent": UA}
    hdrs.update(headers or {})
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode(r.headers.get_content_charset() or "utf-8")
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("_") or "item"


def get_item_json(identifier, account):
    """Return (status, data). status is 'ok' or an error message."""
    q = urllib.parse.urlencode({"itemUIN": identifier, "account": account})
    preview = json.loads(fetch(f"{BASE}/apiBE/previewItem?{q}"))
    if preview.get("success") != "yes" or not preview.get("itemUrl"):
        return f"not available: {preview.get('msg', '')}", None

    item_url = preview["itemUrl"]
    page = fetch(item_url)

    p = urllib.parse.urlparse(item_url)
    origin = f"{p.scheme}://{p.netloc}"
    tenant = re.search(r"/tenants/(\d+)/", item_url)
    item_id = re.search(r'id="itemId"\s+value="([^"]+)"', page)
    ticket = re.search(r"ticket:\s*'([^']*)'", page)
    if not (tenant and item_id and ticket):
        return "could not parse previewer page", None

    flavor_url = f"{origin}/api/tenants/{tenant.group(1)}/item/{item_id.group(1)}/getItemFlavor"
    data = json.loads(fetch(flavor_url, headers={
        "x-authorization": ticket.group(1),
        "Accept": "application/json",
        "Referer": item_url,
    }))
    if data.get("success") != "yes":
        return f"item JSON error: {data.get('msg', '')}"[:200], None
    return "ok", data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--account", default="il")
    ap.add_argument("--subject", default="ELA")
    ap.add_argument("--grade", default="Grade 6")
    ap.add_argument("--view", default="ES")
    ap.add_argument("--outdir", default="questions")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between items")
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    q = urllib.parse.urlencode({"account": args.account.lower(),
                                "subject": args.subject.lower(),
                                "grade": args.grade, "view": args.view})
    sections = sorted(json.loads(fetch(f"{BASE}/apiBE/getJSONFromS3?{q}")),
                      key=lambda s: s["name"])
    total = sum(len(s.get("itemGuid", [])) for s in sections)
    print(f"{len(sections)} sections, {total} table rows", flush=True)

    status_cache = {}  # identifier -> status (items can appear in several sections)
    rows = []
    n = 0
    for sec in sections:
        for item in sec.get("itemGuid", []):
            n += 1
            ident = item["name"]
            fname = safe_name(ident) + ".json"
            path = out / fname
            if ident not in status_cache:
                if path.exists() and not args.force:
                    status_cache[ident] = "ok (existing)"
                else:
                    try:
                        status, data = get_item_json(ident, args.account)
                        if data is not None:
                            path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
                    except Exception as e:  # keep going on individual failures
                        status = f"error: {e}"[:200]
                    status_cache[ident] = status
                    time.sleep(args.delay)
                print(f"[{n}/{total}] {sec['name']} {ident}: {status_cache[ident]}", flush=True)

            st = status_cache[ident]
            rows.append({
                "output_file": fname if st.startswith("ok") else "",
                "section": sec["name"],
                "section_description": sec.get("description", ""),
                "item_identifier": ident,
                **{f: item.get(f, "") for f in ROW_FIELDS},
                "status": st,
            })

    csv_path = out / "items.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["section"])
        w.writeheader()
        w.writerows(rows)
    ok = sum(1 for s in status_cache.values() if s.startswith("ok"))
    print(f"Done: {ok}/{len(status_cache)} unique items saved; CSV: {csv_path}")
    return 0 if ok == len(status_cache) else 1


if __name__ == "__main__":
    sys.exit(main())
