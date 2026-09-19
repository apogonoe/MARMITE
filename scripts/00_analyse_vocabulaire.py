"""
Mesure le vocabulaire d'ingredients du corpus : combien de noms distincts,
et quelle part du corpus couvre le top-N. Determine la taille reelle du
travail d'ontologie canonique (etape 02).

Usage : python3 scripts/00_analyse_vocabulaire.py
"""
import json
from collections import Counter

import pandas as pd

CSV = "data/raw/foodcom_parsed.csv"

names = Counter()
units = Counter()
n_lines = 0
n_recipes = 0
n_no_unit = 0

for chunk in pd.read_csv(CSV, usecols=["ingredients"], chunksize=50_000, low_memory=False):
    for raw in chunk["ingredients"].dropna():
        try:
            items = json.loads(raw)
        except Exception:
            continue
        n_recipes += 1
        for it in items:
            nm = (it.get("name") or "").strip().lower()
            if not nm:
                continue
            names[nm] += 1
            n_lines += 1
            u = it.get("unit")
            if u:
                units[u.strip().lower()] += 1
            else:
                n_no_unit += 1

total = sum(names.values())
print(f"recettes lues          : {n_recipes:,}")
print(f"lignes d'ingredients   : {n_lines:,}  ({n_lines/max(n_recipes,1):.1f} par recette)")
print(f"noms distincts         : {len(names):,}")
print(f"lignes sans unite      : {n_no_unit:,}  ({n_no_unit/max(n_lines,1)*100:.1f} %)")
print()
print("--- couverture cumulee par le top-N des noms ---")
ordered = names.most_common()
cum = 0
targets = [100, 250, 500, 1000, 2000, 3000, 5000, 10000, 20000]
ti = 0
for i, (_, c) in enumerate(ordered, 1):
    cum += c
    while ti < len(targets) and i == targets[ti]:
        print(f"  top {targets[ti]:>6,} noms  ->  {cum/total*100:5.1f} % des lignes")
        ti += 1
print()
print("--- 30 ingredients les plus frequents ---")
for nm, c in ordered[:30]:
    print(f"  {c:>8,}  {nm}")
print()
print("--- 25 unites les plus frequentes ---")
for u, c in units.most_common(25):
    print(f"  {c:>8,}  {u}")

with open("data/work/vocab_ingredients.json", "w") as f:
    json.dump({"names": dict(ordered), "units": dict(units.most_common())}, f)
print("\n-> data/work/vocab_ingredients.json")
