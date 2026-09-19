"""
Calcule le cout de chaque recette a partir des masses resolues a l'etape 03
et des prix de l'ontologie.

Deux chiffres sont produits par recette :
  cout_total   : somme sur tous les ingredients
  cout_portion : ramene au nombre de parts (c'est celui qui parle a l'usage)

Et un indicateur de fiabilite : `conf`, la part de la masse de la recette dont
le prix vient d'un ingredient tarife a la main plutot que d'une moyenne de
categorie. L'app s'en sert pour afficher « ~3,20 EUR » plutot qu'un faux exact.

Usage : python3 scripts/06_price_recipes.py
"""
import csv
import json
from statistics import median

ING = "data/ref/ingredients.csv"
IN = "data/work/recipes.jsonl"
OUT = "data/work/recipes_prices.jsonl"


def main():
    with open(ING, encoding="utf-8") as f:
        ing = {r["id"]: r for r in csv.DictReader(
            l for l in f if not l.lstrip().startswith("#"))}

    n = 0
    couts, par_portion = [], []
    sans_portions = 0
    with open(IN, encoding="utf-8") as fin, open(OUT, "w", encoding="utf-8") as fout:
        for ligne in fin:
            r = json.loads(ligne)
            total = 0.0
            masse_cure = masse_tot = 0.0
            manquants = 0
            for it in r["ing"]:
                fiche = ing.get(it.get("cid") or "")
                g = it.get("g")
                if not fiche or g is None:
                    manquants += 1
                    continue
                total += g / 1000.0 * float(fiche["prix_eur_kg"])
                masse_tot += g
                if fiche["prix_cure"] == "1":
                    masse_cure += g

            portions = r.get("portions") or 0
            r["cout"] = round(total, 2)
            r["cout_part"] = round(total / portions, 2) if portions else None
            r["conf"] = round(masse_cure / masse_tot, 2) if masse_tot else 0.0
            r["ing_sans_prix"] = manquants
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")

            couts.append(total)
            if r["cout_part"] is not None:
                par_portion.append(r["cout_part"])
            else:
                sans_portions += 1
            n += 1

    print(f"recettes tarifees      : {n:,}")
    print(f"sans nombre de parts   : {sans_portions:,} ({sans_portions/n*100:.1f} %)")
    print(f"cout total median      : {median(couts):.2f} EUR")
    print(f"cout/portion median    : {median(par_portion):.2f} EUR")
    par_portion.sort()
    for q in (0.1, 0.25, 0.5, 0.75, 0.9):
        print(f"  q{int(q*100):<3} cout/portion    : {par_portion[int(q*len(par_portion))]:.2f} EUR")


if __name__ == "__main__":
    main()
