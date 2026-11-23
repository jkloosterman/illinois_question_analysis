#!/usr/bin/env python3
"""Add a Beck/McKeown/Kucan word-tier column to wordcount.csv.

Tiers (https://www.vocabulary-matters.org/word-tiers):
  1  basic, common words that need no direct instruction (clock, baby, happy)
  2  high-utility academic words, more typical of writing than speech
     (contradict, precede, circumstances)
  3  rare, domain-specific words (exoskeleton, chrysalis, filibuster);
     proper names, foreign words and fragments are also put here

The tiers are judged by the MEANING of each word (by Claude, for Grade 6
readers), not by frequency. The judgments live in tiers.json
({"word": 1|2|3}); this script just applies them to wordcount.csv.
Words missing from tiers.json get an empty tier and are reported. Re-running
replaces any existing "tier" column.
"""
import argparse
import csv
import json
from collections import Counter


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="wordcount.csv", help="CSV to annotate in place")
    ap.add_argument("--tiers", default="tiers.json", help="word -> tier judgments")
    args = ap.parse_args()

    with open(args.tiers, encoding="utf-8") as fh:
        tiers = json.load(fh)

    with open(args.csv, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = [f for f in reader.fieldnames if f != "tier"]
        rows = list(reader)

    counts = Counter()
    missing = []
    for row in rows:
        t = tiers.get(row["word"], "")
        row["tier"] = t
        counts[t] += 1
        if t == "":
            missing.append(row["word"])

    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields + ["tier"])
        w.writeheader()
        w.writerows(rows)

    print(f"Annotated {len(rows)} words in {args.csv}: "
          + ", ".join(f"tier {t}: {counts[t]}" for t in (1, 2, 3)))
    if missing:
        print(f"{len(missing)} words not in {args.tiers}: {' '.join(missing[:20])} ...")


if __name__ == "__main__":
    main()
