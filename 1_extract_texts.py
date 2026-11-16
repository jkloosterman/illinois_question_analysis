#!/usr/bin/env python3
"""Extract the user-visible text from questions/*.json (msg.itemBodyHtml)
into texts/<name>.txt.

Hidden content is dropped: elements with class "visuallyhidden" (screen-reader
only text), "hidden" (e.g. the glossary definitions list), the `hidden`
attribute, inline display:none / visibility:hidden, and script/style/template
tags. Dropdowns (<select>) are rendered as "[option1 / option2 / ...]" so the
choices a user would see when opening them are kept.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag, Comment

HIDDEN_CLASSES = {"visuallyhidden", "hidden", "sr-only"}
DROP_TAGS = {"script", "style", "template", "noscript", "head", "textarea"}
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3",
    "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
    "section", "table", "tr", "ul", "label",
}


def is_hidden(tag: Tag) -> bool:
    if tag.name in DROP_TAGS:
        return True
    if HIDDEN_CLASSES & set(tag.get("class") or []):
        return True
    if tag.has_attr("hidden"):
        return True
    if tag.name == "input" and tag.get("type", "").lower() == "hidden":
        return True
    style = (tag.get("style") or "").replace(" ", "").lower()
    return "display:none" in style or "visibility:hidden" in style


def render(node, out: list) -> None:
    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            out.append(re.sub(r"\s+", " ", str(child)))
            continue
        if not isinstance(child, Tag) or is_hidden(child):
            continue
        name = child.name
        if name == "br":
            out.append("\n")
        elif name == "select":
            opts = [o.get_text(" ", strip=True) for o in child.find_all("option")]
            opts = [o for o in opts if o and o.lower() != "choose..."]
            out.append(" [" + " / ".join(opts) + "] ")
        elif name in ("td", "th"):
            render(child, out)
            out.append("\t")
        elif any(c.startswith("int-choice-") for c in child.get("class") or []):
            # keep "A." and its answer text on one line
            render(child, out)
            out.append(" ")
        elif name in BLOCK_TAGS:
            out.append("\n")
            if name == "hr":
                out.append("----------")
            render(child, out)
            out.append("\n")
        else:
            render(child, out)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    out: list = []
    render(soup, out)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(out).split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse runs of blank lines
    return text.strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("indir", nargs="?", default="questions")
    ap.add_argument("outdir", nargs="?", default="texts")
    args = ap.parse_args()

    indir, outdir = Path(args.indir), Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(indir.glob("*.json")):
        try:
            html = json.loads(path.read_text(encoding="utf-8"))["msg"]["itemBodyHtml"]
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            print(f"skipping {path}: {e!r}", file=sys.stderr)
            continue
        (outdir / f"{path.stem}.txt").write_text(html_to_text(html), encoding="utf-8")
        count += 1
    print(f"wrote {count} files to {outdir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
