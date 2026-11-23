import csv, json, glob, os
rows = {r["output_file"]: r for r in csv.DictReader(open("questions/items.csv", newline="", encoding="utf-8"))}
out = []
for p in sorted(glob.glob("texts/*.txt")):
    stem = os.path.basename(p)[:-4]
    name = stem + ".json"
    meta = {k: v for k, v in rows.get(name, {}).items() if k != "output_file"}
    out.append({"output_file": name, **meta, "text": open(p, encoding="utf-8").read()})

# Drop near-duplicates: word-3-gram Jaccard similarity >= THRESHOLD with an already kept item.
THRESHOLD = 0.2
def shingles(t):
    w = " ".join(t.lower().split()).split()
    return set(zip(w, w[1:], w[2:]))
kept, kept_sh, dropped = [], [], []
for e in out:
    sh = shingles(e["text"])
    dup = next((k["output_file"] for k, ks in zip(kept, kept_sh) if sh == ks or (sh and ks and len(sh & ks) / len(sh | ks) >= THRESHOLD)), None)
    if dup: dropped.append((e["output_file"], dup))
    else: kept.append(e); kept_sh.append(sh)
print("dropped", len(dropped), "near-duplicates:", dropped)
out = kept
print(len(out), "items; without csv row:", [e["output_file"] for e in out if "section" not in e])
json.dump(out, open("all_questions_text.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
