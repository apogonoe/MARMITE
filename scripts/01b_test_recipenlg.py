"""
Mesure combien d'instructions de cuisine RecipeNLG pourrait fournir a notre
catalogue, par appariement de titre. Plan B si le dataset Kaggle d'origine
n'est pas accessible.

Usage : python3 scripts/01b_test_recipenlg.py
"""
import glob
import json
import re
from collections import Counter

import pandas as pd


def cle(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def main():
    fichiers = sorted(glob.glob("data/raw/recipenlg_*.parquet"))
    print(f"lecture de {len(fichiers)} fichiers…", flush=True)
    df = pd.concat([pd.read_parquet(f, columns=["title", "directions", "source"])
                    for f in fichiers], ignore_index=True)
    print(f"RecipeNLG : {len(df):,} recettes")
    print("sources   :", dict(Counter(df['source']).most_common()))

    etapes = {}
    for t, d in zip(df["title"], df["directions"]):
        k = cle(t)
        if k and k not in etapes:
            etapes[k] = d
    print(f"titres distincts : {len(etapes):,}\n")

    cat = json.load(open("web/recipes.json"))
    deja = sum(1 for r in cat["recipes"] if r["st"])
    gagnes = apparies = 0
    exemples = []
    for r in cat["recipes"]:
        k = cle(r["t"])
        if k in etapes:
            apparies += 1
            if not r["st"]:
                gagnes += 1
                if len(exemples) < 3:
                    exemples.append((r["t"], etapes[k]))
    n = cat["n"]
    print(f"catalogue                     : {n:,}")
    print(f"  ont deja des instructions   : {deja:,} ({deja/n*100:.1f} %)")
    print(f"  apparies dans RecipeNLG     : {apparies:,} ({apparies/n*100:.1f} %)")
    print(f"  GAGNEES par RecipeNLG       : {gagnes:,} ({gagnes/n*100:.1f} %)")
    print(f"  -> couverture totale        : {(deja+gagnes)/n*100:.1f} %")
    if exemples:
        print("\n--- exemple de recette recuperee ---")
        t, d = exemples[0]
        print(f"{t}")
        for e in list(d)[:4]:
            print(f"   - {e[:100]}")


if __name__ == "__main__":
    main()
