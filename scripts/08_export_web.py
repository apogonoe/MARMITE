"""
Exporte le catalogue filtre vers web/, au format consomme par la PWA.

Filtres de qualite (mesures sur le corpus : 87 925 recettes retenues sur 490 457)
  - une photo disponible
  - un nombre de parts connu (sinon pas de prix par personne)
  - >= 80 % des ingredients resolus vers l'ontologie
  - 3 a 20 ingredients, temps total entre 1 et 240 min

Sorties :
  web/recipes.json      catalogue compact (ingredients et tags internes en index)
  web/ingredients.json  ontologie : nom, categorie, prix/kg, conservation, allergenes

Usage : python3 scripts/09_export_web.py
"""
import argparse
import csv
import glob
import json
import re
from collections import Counter
from pathlib import Path

SRC = "data/work/recipes_prices.jsonl"
WEB = Path("web")
PREFIXE_IMG = "https://img.sndimg.com/food/image/upload/"
ING_NOMS = {}   # id canonique -> nom anglais, pour la detection de cuisine


def lire_ref(nom):
    """Lit un CSV de data/ref/ en ignorant les lignes de commentaire."""
    with open(f"data/ref/{nom}", encoding="utf-8") as f:
        return list(csv.DictReader(l for l in f if not l.lstrip().startswith("#")))


def cle_titre(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def charger_etapes():
    """Instructions de cuisine, recuperees par appariement de titre.

    Le corpus principal (Karo8870) a un champ `steps` corrompu — il contient les
    URLs d'images. On les reconstitue depuis deux sources, par ordre de qualite :

      1. RecipeNLG (2,2 M de recettes, CC-BY-4.0) — apparie 93,3 % du catalogue.
         Texte propre : majuscules et ponctuation.
      2. KingName1/food.com — couvre ~31 %, en minuscules sans ponctuation.
         Sert de repli pour ce que RecipeNLG n'a pas.

    Ensemble : 93,5 % du catalogue. Le dataset Kaggle d'origine
    (irkaal/foodcom-recipes-and-reviews) les aurait toutes : voir README.
    """
    import pandas as pd
    out = {}

    # Repli d'abord : RecipeNLG l'ecrasera la ou il a mieux.
    for f in sorted(glob.glob("data/raw/kn_*.parquet")):
        df = pd.read_parquet(f, columns=["name", "steps"])
        for nom, st in zip(df["name"], df["steps"]):
            k = cle_titre(nom)
            if k and k not in out:
                out[k] = [str(x) for x in st][:25]

    for f in sorted(glob.glob("data/raw/recipenlg_*.parquet")):
        df = pd.read_parquet(f, columns=["title", "directions"])
        for t, d in zip(df["title"], df["directions"]):
            k = cle_titre(t)
            if not k:
                continue
            try:
                etapes = json.loads(d) if isinstance(d, str) else list(d)
            except Exception:
                continue
            etapes = [str(x).strip() for x in etapes if str(x).strip()][:25]
            if etapes:
                out[k] = etapes      # RecipeNLG fait autorite
    return out


def charger_cuisines():
    """Cuisines + moyens de les reconnaitre. Voir data/ref/cuisines.csv."""
    out = []
    for r in lire_ref("cuisines.csv"):
        out.append((
            r["id"], r["label_fr"],
            {t.strip() for t in r["tags"].split(";") if t.strip()},
            [m.strip().lower() for m in r["motifs"].split(";") if m.strip()],
        ))
    return out


def trouver_cuisine(cuisines, tags_recette, texte):
    """Tag d'abord (c'est une donnee), motif ensuite (c'est une deduction)."""
    for i, (_, _, tags, _) in enumerate(cuisines):
        if tags & tags_recette:
            return i
    for i, (_, _, _, motifs) in enumerate(cuisines):
        for m in motifs:
            if m in texte:
                return i
    return -1


def facilite(n_ing, n_etapes, minutes, tags_recette):
    """1 facile, 2 moyen, 3 technique.

    Calculee plutot que lue dans un tag : « Easy » ne couvre que 54 % du
    corpus, et rien ne qualifie les autres. Le nombre d'ingredients, le nombre
    d'etapes et le temps donnent une mesure disponible partout ; le tag ne sert
    que de correctif.
    """
    s = 0
    s += 0 if n_ing <= 5 else 1 if n_ing <= 9 else 2 if n_ing <= 14 else 3
    s += 0 if n_etapes <= 4 else 1 if n_etapes <= 8 else 2 if n_etapes <= 14 else 3
    s += 0 if minutes <= 20 else 1 if minutes <= 45 else 2 if minutes <= 90 else 3
    if tags_recette & {"Easy", "Beginner Cook"}:
        s -= 1
    return 1 if s <= 2 else 2 if s <= 5 else 3


def charger_titres_fr():
    """Titres traduits par l'etape 04.

    DESACTIVE PAR DEFAUT. Compares sur les memes titres, opus-mt-en-fr et
    NLLB-600M produisent tous deux des contresens visibles :
      Blueberry Scones        -> « Ecossais de bleuets »
      Abby's Pecan Apple Cake -> « Cake aux pommes de terre »
      Buttermilk Pie          -> « Tarte de lait de boucherie »
    Les titres de recettes sont des empilements de noms sans verbe, melant
    marques et noms propres : c'est hors de portee d'un petit modele de
    traduction. Mieux vaut l'anglais qu'un contresens.
    Les ingredients, eux, sont a 100 % en francais (etape 04 + table curee) :
    c'est ce qui porte la recherche, le placard, les courses et les prix.
    Passer --titres-fr pour les activer quand un meilleur modele sera passe.
    """
    f = Path("data/work/titres_fr.json")
    return json.loads(f.read_text()) if f.exists() else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titres-fr", action="store_true",
                    help="utiliser les titres traduits (qualite insuffisante, voir docstring)")
    args = ap.parse_args()

    WEB.mkdir(exist_ok=True)
    etapes = charger_etapes()
    cuisines = charger_cuisines()
    titres_fr = charger_titres_fr() if args.titres_fr else {}
    ing = lire_ref("ingredients.csv")

    # 1. Selection.
    gardees = []
    with open(SRC, encoding="utf-8") as f:
        for l in f:
            r = json.loads(l)
            if (r.get("img") and r.get("portions") and r["res"] >= 0.8
                    and 3 <= len(r["ing"]) <= 20 and 0 < r["min"] <= 240):
                gardees.append(r)

    # 2. Vocabulaires internes : on ne stocke que des index.
    cid_utilises = Counter()
    tags_utilises = Counter()
    cats_utilisees = Counter()
    for r in gardees:
        for it in r["ing"]:
            if it.get("cid"):
                cid_utilises[it["cid"]] += 1
        for t in (r.get("tags") or []):
            tags_utilises[t] += 1
        if r.get("cat"):
            cats_utilisees[r["cat"]] += 1

    ing_gardes = [x for x in ing if x["id"] in cid_utilises]
    ING_NOMS.update({x["id"]: x["nom_en"] for x in ing})
    idx_ing = {x["id"]: i for i, x in enumerate(ing_gardes)}
    tags = [t for t, n in tags_utilises.most_common() if n >= 20]
    idx_tag = {t: i for i, t in enumerate(tags)}
    cats = [c for c, _ in cats_utilisees.most_common()]
    idx_cat = {c: i for i, c in enumerate(cats)}

    # 3. Catalogue.
    sortie, pas = [], []
    for i, r in enumerate(gardees):
        img = (r["img"][0] or "")
        if img.startswith(PREFIXE_IMG):
            img = img[len(PREFIXE_IMG):]
        ings = [[idx_ing[it["cid"]], int(it["g"] or 0), it.get("est", 0)]
                for it in r["ing"] if it.get("cid") in idx_ing]
        mes_tags = set(r.get("tags") or [])
        mes_etapes = etapes.get(cle_titre(r["nom_en"]), [])
        texte = (r["nom_en"] + " " + " ".join(
            ING_NOMS.get(it["cid"], "") for it in r["ing"] if it.get("cid"))).lower()
        sortie.append({
            "i": i,
            "t": titres_fr.get(r["nom_en"], r["nom_en"]),
            "t_en": r["nom_en"] if r["nom_en"] in titres_fr else None,
            "m": r["min"],
            "p": r["portions"],
            "c": int(round((r["cout_part"] or 0) * 100)),   # centimes
            "conf": r["conf"],
            "k": int(r["kcal"] or 0),
            "pr": int(r["prot"] or 0),
            "g": idx_cat.get(r.get("cat"), -1),
            "tg": [idx_tag[t] for t in (r.get("tags") or []) if t in idx_tag],
            "im": img,
            "ig": ings,
            "hs": 1 if mes_etapes else 0,
            "cui": trouver_cuisine(cuisines, mes_tags, texte),
            "fac": facilite(len(ings), len(mes_etapes), r["min"], mes_tags),
        })
        pas.append(mes_etapes)

    json.dump({
        "n": len(sortie), "prefixe_img": PREFIXE_IMG,
        "categories": cats, "tags": tags,
        "cuisines": [c[1] for c in cuisines],
        "recipes": sortie,
    }, open(WEB / "recipes.json", "w"), ensure_ascii=False, separators=(",", ":"))

    # Les etapes sont servies a part et chargees en arriere-plan : garder le
    # catalogue leger accelere le premier affichage, et chaque fichier reste
    # sous la limite de 100 Mo de GitHub.
    json.dump({"n": len(pas), "steps": pas},
              open(WEB / "steps.json", "w"), ensure_ascii=False,
              separators=(",", ":"))

    json.dump({
        "n": len(ing_gardes),
        "ing": [{
            "id": x["id"], "fr": x["nom_fr"] or x["nom_en"], "en": x["nom_en"],
            "cat": x["categorie"],
            "prix": round(float(x["prix_eur_kg"]), 2),
            "cure": int(x["prix_cure"]),
            "cons": int(x["conservation_j"]),
            "placard": int(x["fond_placard"]),
            "all": x["allergenes"],
            "gpc": float(x["g_par_piece"]) if x["g_par_piece"] else
                   float(x["g_piece_defaut"]),
        } for x in ing_gardes],
    }, open(WEB / "ingredients.json", "w"), ensure_ascii=False, separators=(",", ":"))

    mo = lambda p: (WEB / p).stat().st_size / 1e6
    print(f"recettes exportees   : {len(sortie):,}")
    print(f"ingredients retenus  : {len(ing_gardes):,}")
    print(f"tags / categories    : {len(tags)} / {len(cats)}")
    avec = sum(1 for x in pas if x)
    fr = sum(1 for r in sortie if r["t_en"])
    print(f"avec instructions    : {avec:,} ({avec/len(sortie)*100:.1f} %)")
    print(f"titres en francais   : {fr:,} ({fr/len(sortie)*100:.1f} %)")
    from collections import Counter as _C
    cu = _C(r["cui"] for r in sortie)
    print(f"\n--- cuisines ({sum(v for k,v in cu.items() if k>=0)/len(sortie)*100:.0f} % reconnues) ---")
    for i, n in cu.most_common():
        nom = cuisines[i][1] if i >= 0 else "(non reconnue)"
        print(f"  {nom:<22} {n:>7,}")
    fa = _C(r["fac"] for r in sortie)
    print("--- facilite ---")
    for k, lib in ((1, "facile"), (2, "moyen"), (3, "technique")):
        print(f"  {lib:<22} {fa[k]:>7,}  ({fa[k]/len(sortie)*100:4.1f} %)")
    print(f"web/recipes.json     : {mo('recipes.json'):.1f} Mo")
    print(f"web/steps.json       : {mo('steps.json'):.1f} Mo")
    print(f"web/ingredients.json : {mo('ingredients.json'):.2f} Mo")


if __name__ == "__main__":
    main()
