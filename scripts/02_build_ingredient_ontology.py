"""
Construit l'ontologie d'ingredients canoniques : la colonne vertebrale du projet.
C'est elle qui relie les recettes, les prix et le garde-manger.

Entrees (data/ref/, versionnees — c'est du travail humain) :
  synonyms.csv        fusions curees a la main
  categories.csv      categories + conservation + fond de placard
  category_rules.csv  attribution auto par motif
  densities.csv       g/ml, pour convertir les volumes en masse
  piece_weights.csv   g/piece, pour convertir "2 oignons" en masse
  + data/work/vocab_ingredients.json  (produit par le script 00)

Sorties :
  data/ref/ingredients.csv   l'ontologie (versionnee)
  data/ref/aliases.csv       nom brut -> id canonique (versionne)

Usage : python3 scripts/02_build_ingredient_ontology.py [--top 3000]
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marmite.normalize.text import normalise, slug, COMPOSES  # noqa: E402

REF = Path("data/ref")
WORK = Path("data/work")

ALLERGENES = {
    "gluten": ["flour", "bread", "pasta", "spaghetti", "macaroni", "noodle",
               "cracker", "crumb", "barley", "couscous", "tortilla", "oat",
               "linguine", "penne", "lasagna", "semolina", "pastry", "crust"],
    "lactose": ["milk", "cream", "butter", "cheese", "yogurt", "buttermilk",
                "parmesan", "mozzarella", "cheddar", "feta", "ricotta", "jack"],
    "oeuf": ["egg", "mayonnaise"],
    "fruits_a_coque": ["almond", "walnut", "pecan", "cashew", "pistachio",
                       "hazelnut", "macadamia", "pine nut"],
    "arachide": ["peanut"],
    "soja": ["soy", "tofu", "edamame", "miso", "tempeh"],
    "poisson": ["fish", "salmon", "tuna", "cod", "anchovy", "sardine"],
    "crustaces": ["shrimp", "prawn", "crab", "lobster", "scallop", "clam", "oyster"],
}
# "margarine" contient "marg" mais pas de lactose ; "coconut milk" n'est pas laitier.
ALLERGENE_SAUF = {"lactose": ["coconut milk", "soy milk", "almond milk", "rice milk"]}


def lire(nom):
    """Lit un CSV de data/ref/ en ignorant les lignes de commentaire."""
    with open(REF / nom, encoding="utf-8") as f:
        lignes = [l for l in f if not l.lstrip().startswith("#")]
    return list(csv.DictReader(lignes))


def plus_long(nom, motifs):
    """Cherche le motif le plus long contenu dans `nom`. Permet d'ecrire une
    regle generale ('butter') puis son exception ('peanut butter')."""
    trouve, longueur = None, -1
    for motif, valeur in motifs:
        if motif in nom and len(motif) > longueur:
            trouve, longueur = valeur, len(motif)
    return trouve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3000,
                    help="nombre de formes repliees a canoniser")
    args = ap.parse_args()

    # 1. Repliement lexical du vocabulaire brut.
    brut = json.load(open(WORK / "vocab_ingredients.json"))["names"]
    folded, brut2replie = Counter(), {}
    for nm, c in brut.items():
        k = normalise(nm)
        if not k:
            continue
        brut2replie[nm] = k
        for part in COMPOSES.get(k, [k]):   # "salt and pepper" = 2 ingredients
            folded[part] += c
    total_lignes = sum(folded.values())
    json.dump(dict(folded.most_common()), open(WORK / "vocab_folded.json", "w"))

    # 2. Tables de reference.
    synonymes = {r["variante"]: r["canonique"] for r in lire("synonyms.csv")}
    categories = {r["id"]: r for r in lire("categories.csv")}
    regles_cat = [(r["motif"], r["categorie"]) for r in lire("category_rules.csv")]
    densites = [(r["match"], float(r["g_per_ml"])) for r in lire("densities.csv")]
    prix = {r["id"]: float(r["eur_kg"]) for r in lire("prices.csv")}
    poids = [(r["match"], (float(r["g_per_piece"]),
                           float(r["yield_ml"]) if r.get("yield_ml") else None))
             for r in lire("piece_weights.csv")]

    # 3. Forme repliee -> id canonique. Les fusions curees font autorite.
    replie2id = dict(synonymes)
    for forme, _ in folded.most_common(args.top):
        if forme not in replie2id:
            cid = slug(forme)
            if cid:
                replie2id[forme] = cid

    # 4. nom_en = la variante la PLUS FREQUENTE de chaque canonique.
    #    Indispensable : un id comme `sugar_brown` relu tel quel donnerait
    #    "sugar brown", qui ne correspond a aucune regle de densite.
    par_id = {}
    for forme, cid in replie2id.items():
        n = folded.get(forme, 0)
        if cid not in par_id or n > par_id[cid][1]:
            par_id[cid] = (forme, n)

    ing = {}
    for cid, (nom_en, _) in par_id.items():
        cat = plus_long(nom_en, regles_cat) or "autre"
        meta = categories.get(cat, categories["autre"])
        pw = plus_long(nom_en, poids)
        allerg = [a for a, mots in ALLERGENES.items()
                  if any(m in nom_en for m in mots)
                  and not any(x in nom_en for x in ALLERGENE_SAUF.get(a, []))]
        ing[cid] = {
            "id": cid, "nom_fr": "", "nom_en": nom_en, "categorie": cat,
            "g_par_ml": plus_long(nom_en, densites) or "",
            "g_par_piece": pw[0] if pw else "",
            # valeurs de repli, marquees comme estimations a la conversion
            "g_ml_defaut": meta["g_ml_defaut"],
            "g_piece_defaut": meta["g_piece_defaut"],
            "ml_jus": pw[1] if pw and pw[1] else "",
            "conservation_j": meta["conservation_j"],
            "fond_placard": meta["fond_placard"],
            "allergenes": ";".join(allerg),
            # prix cure si on en a un, sinon moyenne de la categorie
            "prix_eur_kg": prix.get(cid, float(meta["eur_kg_defaut"])),
            "prix_cure": 1 if cid in prix else 0,
            "occurrences": 0,
        }
    for forme, n in folded.items():
        cid = replie2id.get(forme)
        if cid in ing:
            ing[cid]["occurrences"] += n

    # 5. Alias : nom brut du corpus -> id(s) canonique(s).
    alias = {}
    for b, forme in brut2replie.items():
        ids = [replie2id[c] for c in COMPOSES.get(forme, [forme]) if c in replie2id]
        if ids:
            alias[b] = ";".join(ids)

    # 6. Ecriture.
    champs = ["id", "nom_fr", "nom_en", "categorie", "g_par_ml", "g_par_piece",
              "g_ml_defaut", "g_piece_defaut", "ml_jus", "conservation_j",
              "fond_placard", "allergenes", "prix_eur_kg", "prix_cure",
              "occurrences"]
    with open(REF / "ingredients.csv", "w", newline="", encoding="utf-8") as f:
        f.write("# Ontologie canonique des ingredients. nom_fr et prix_eur_kg\n"
                "# sont remplis par les etapes 04 (traduction) et 05 (prix).\n")
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows(sorted(ing.values(), key=lambda d: -d["occurrences"]))
    with open(REF / "aliases.csv", "w", newline="", encoding="utf-8") as f:
        f.write("# Nom brut du corpus -> id(s) canonique(s), separes par ';'\n")
        w = csv.writer(f)
        w.writerow(["brut", "canonique"])
        for k in sorted(alias):
            w.writerow([k, alias[k]])

    # 7. Rapport.
    couvert = sum(folded[f] for f in replie2id if f in folded)
    sans_cat = sum(1 for d in ing.values() if d["categorie"] == "autre")
    print(f"formes repliees        : {len(folded):,}")
    print(f"ingredients canoniques : {len(ing):,}")
    print(f"alias (noms bruts)     : {len(alias):,} / {len(brut):,} "
          f"({len(alias)/len(brut)*100:.1f} %)")
    print(f"couverture des lignes  : {couvert/total_lignes*100:.1f} %")
    print(f"sans categorie         : {sans_cat:,} ({sans_cat/len(ing)*100:.1f} %)")
    print(f"avec densite           : {sum(1 for d in ing.values() if d['g_par_ml']):,}")
    print(f"avec poids/piece       : {sum(1 for d in ing.values() if d['g_par_piece']):,}")
    print(f"prix cure a la main    : {sum(1 for d in ing.values() if d['prix_cure']):,}")


if __name__ == "__main__":
    main()
