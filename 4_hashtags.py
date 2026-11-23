#!/usr/bin/env python3
"""Generate 5 hashtags for each distinct informational (RI) text.

Reads texts/*.txt belonging to items in questions/items.csv whose section
contains "ES.ELA-LITERACY.RI", drops duplicate texts (identical or
near-duplicates: texts whose word 5-gram Jaccard similarity to an
already-kept text is at least --similarity; the first file in sorted order
is kept), and runs
the prompt in hashtag_prompt.txt on each text via the `claude` CLI
(`claude -p`). Output CSV columns: filename, hashtags.

Existing rows in the output CSV are kept, so an interrupted run resumes.
"""
import argparse
import csv
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TAG_RE = re.compile(r"#\w+")
WORD_RE = re.compile(r"\w+")
SHINGLE = 5


def shingles(text):
    words = WORD_RE.findall(text.lower())
    return {tuple(words[i:i + SHINGLE]) for i in range(max(len(words) - SHINGLE + 1, 1))}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 1.0


def hashtags(prompt, text, model):
    full = f"{prompt}\n\nText:\n{text}\n\nRespond with only the 5 hashtags, separated by spaces."
    cmd = ["claude", "-p", "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    res = subprocess.run(cmd, input=full, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or f"claude exited {res.returncode}")
    tags = TAG_RE.findall(res.stdout)
    if len(tags) != 5:
        raise RuntimeError(f"expected 5 hashtags, got {res.stdout.strip()!r}")
    return " ".join(tags)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--indir", default="texts")
    ap.add_argument("--items", default="questions/items.csv")
    ap.add_argument("--section", default="ES.ELA-LITERACY.RI")
    ap.add_argument("--prompt", default="hashtag_prompt.txt")
    ap.add_argument("--out", default="hashtags.csv")
    ap.add_argument("--model", default=None, help="model for claude -p (default: CLI default)")
    ap.add_argument("--similarity", type=float, default=0.5,
                    help="Jaccard similarity of word 5-grams at or above which a "
                         "text counts as a duplicate (default 0.5)")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    with open(args.items, newline="", encoding="utf-8") as fh:
        wanted = {Path(r["output_file"]).stem for r in csv.DictReader(fh)
                  if args.section in r["section"]}
    files = sorted(p for p in Path(args.indir).glob("*.txt") if p.stem in wanted)
    if not files:
        sys.exit(f"No .txt files in {args.indir}/ match section {args.section}")

    unique, kept = [], []   # kept: shingle sets of the unique texts
    for p in files:
        text = p.read_text(encoding="utf-8").strip()
        sh = shingles(text)
        for (other, _), osh in zip(unique, kept):
            if jaccard(sh, osh) >= args.similarity:
                print(f"{p.name}: duplicate of {other}", file=sys.stderr)
                break
        else:
            unique.append((p.name, text))
            kept.append(sh)
    print(f"{len(files)} texts, {len(unique)} unique", file=sys.stderr)

    done = {}
    if Path(args.out).exists():
        with open(args.out, newline="", encoding="utf-8") as fh:
            done = {r["filename"]: r["hashtags"] for r in csv.DictReader(fh)}
    todo = [(n, t) for n, t in unique if n not in done]

    prompt = Path(args.prompt).read_text(encoding="utf-8").strip()

    def work(item):
        name, text = item
        try:
            return name, hashtags(prompt, text, args.model)
        except Exception as e:
            print(f"{name}: {e}", file=sys.stderr)
            return name, None

    with ThreadPoolExecutor(args.workers) as ex:
        for name, tags in ex.map(work, todo):
            if tags:
                done[name] = tags
                print(f"{name}: {tags}", file=sys.stderr)

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["filename", "hashtags"])
        for name, _ in unique:
            if name in done:
                w.writerow([name, done[name]])
    missing = [n for n, _ in unique if n not in done]
    if missing:
        print(f"{len(missing)} failed (re-run to retry): {missing}", file=sys.stderr)


if __name__ == "__main__":
    main()
