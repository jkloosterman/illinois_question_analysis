#!/usr/bin/env python3
"""Count words across texts/*.txt and rank them by English frequency.

Words are normalized with the Snowball (Porter2) English stemmer, so e.g.
"feather", "feathers" and "feathered" are counted together. Snowball sometimes
over-stems unrelated words to the same stem (experiment/experience -> "experi",
organ/organism/organic -> "organ"), so each stem group is split further: a form
only joins a shorter form from its group when the leftover is an ordinary
suffix (-s, -es, -ed, -ing, -er, -ly, -ness, ...).

Stems are often not real words, so each group is reported under an actual
surface form from the texts: its base (shortest) form if that is an English
word, else its most common form in English (per wordfreq), else (e.g. names)
the form that occurs most often in the texts.

The English rank comes from wordfreq's frequency list for English
(1 = most common word, "the"). Words not in that list get an empty rank.

Output CSV columns:
  word        the representative English word for the stem group
  count       total occurrences of all forms in the group, across all texts
  rank        rank of `word` among the most common English words
  num_texts   number of texts the group appears in
  forms       all surface forms seen, with counts (e.g. "feathers:12 feather:3")

Requires: pip install nltk wordfreq
"""
import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from nltk.stem.snowball import SnowballStemmer
from wordfreq import top_n_list, zipf_frequency

# Letters (incl. accented) with optional internal apostrophes or hyphens:
# don't, well-known, Neftalí. Digits are not words.
L = r"[^\W\d_]+"
WORD_RE = re.compile(rf"{L}(?:['-]{L})*")

# Leftovers allowed when attaching a longer form to a shorter base form.
SUFFIXES = {"", "s", "es", "ed", "d", "ing", "er", "ers", "est", "ly", "ness",
            "ment", "ments", "ful", "fully", "ies", "ied", "ier", "iest", "ily",
            "iness", "ically", "ally", "al"}
APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})
DASHES = str.maketrans({"‐": "-", "‑": "-"})


def tokenize(text):
    text = text.lower().translate(APOSTROPHES).translate(DASHES)
    for tok in WORD_RE.findall(text):
        if tok.endswith("'s"):          # possessive: chickadee's -> chickadee
            tok = tok[:-2]
        if tok:
            yield tok


def split_group(counter):
    """Split one stem group into clusters {base form: Counter of forms}."""
    clusters = {}
    for f in sorted(counter, key=lambda f: (len(f), f)):
        home = None
        for base in sorted(clusters, key=len, reverse=True):
            roots = {base}
            if len(base) > 3 and base[-1] in "ey":
                roots.add(base[:-1])                    # make -> making, happy -> happiness
            if len(base) >= 3 and base[-1] not in "aeiouwxy":
                roots.add(base + base[-1])              # run -> running
            if any(f.startswith(r) and f[len(r):] in SUFFIXES for r in roots):
                home = base
                break
        if home is None:
            clusters[f] = Counter()
            home = f
        clusters[home][f] = counter[f]
    return clusters


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--indir", default="texts", help="directory of .txt files")
    ap.add_argument("--out", default="wordcount.csv", help="output CSV path")
    ap.add_argument("--rank-list-size", type=int, default=500_000,
                    help="how many top English words to rank (default 500000)")
    args = ap.parse_args()

    files = sorted(Path(args.indir).glob("*.txt"))
    if not files:
        sys.exit(f"No .txt files found in {args.indir}/")

    stemmer = SnowballStemmer("english")
    stem_cache = {}
    forms = defaultdict(Counter)      # stem -> Counter(surface form -> count)
    texts_with = defaultdict(set)     # surface form -> set of file names

    for path in files:
        for tok in tokenize(path.read_text(encoding="utf-8")):
            stem = stem_cache.get(tok)
            if stem is None:
                stem = stem_cache[tok] = stemmer.stem(tok)
            forms[stem][tok] += 1
            texts_with[tok].add(path.name)

    english = top_n_list("en", args.rank_list_size)
    rank_of = {}
    for i, w in enumerate(english, 1):
        rank_of.setdefault(w, i)

    rows = []
    for counter in forms.values():
        for base, cluster in split_group(counter).items():
            known = [f for f in cluster if f in rank_of]
            if base in rank_of:
                word = base
            elif known:
                # Most common in English; ties broken by count in the texts.
                word = max(known, key=lambda f: (zipf_frequency(f, "en"), cluster[f]))
            else:
                word = max(cluster, key=lambda f: (cluster[f], -len(f)))
            files_seen = set().union(*(texts_with[f] for f in cluster))
            rows.append({
                "word": word,
                "count": sum(cluster.values()),
                "rank": rank_of.get(word, ""),
                "num_texts": len(files_seen),
                "forms": " ".join(f"{f}:{c}" for f, c in cluster.most_common()),
            })

    rows.sort(key=lambda r: (-r["count"], r["word"]))
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["word", "count", "rank", "num_texts", "forms"])
        w.writeheader()
        w.writerows(rows)

    print(f"Read {len(files)} texts; wrote {len(rows)} words to {args.out}")


if __name__ == "__main__":
    main()
