import csv, json, glob, os
rows = {r["output_file"]: r for r in csv.DictReader(open("questions/items.csv", newline="", encoding="utf-8"))}
out = []
for p in sorted(glob.glob("questions/*.json")):
    name = os.path.basename(p)
    entry = {"output_file": name, **{k: v for k, v in rows.get(name, {}).items() if k != "output_file"}}
    entry["data"] = json.load(open(p, encoding="utf-8"))
    out.append(entry)
missing = set(rows) - {os.path.basename(p) for p in glob.glob("questions/*.json")}
print(len(out), "items; csv rows without json:", sorted(missing))
json.dump(out, open("all_questions.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
