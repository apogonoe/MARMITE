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
import csv
import glob
import json
import re
from collections import Counter
from pathlib import Path

SRC = "data/work/recipes_prices.jsonl"
WEB = Path("web")
PREFIXE_IMG = "https://img.sndimg.com/food/image/upload/"


def cle_titre(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def charger_etapes():
    """Instructions de cuisine, recuperees par appariement de titre.

    Le corpus principal (Karo8870) a un champ `steps` corrompu — il contient les
    URLs d'images. On recupere donc les etapes depuis KingName1/food.com, qui ne
    couvre qu'une partie du catalogue (~31 %). Le dataset Kaggle d'origine
    (irkaal/foodcom-recipes-and-reviews) les aurait toutes : voir README.
    """
    fichiers = sorted(glob.glob("data/raw/kn_*.parquet"))
    if not fichiers:
        return {}
    import pandas as pd
    df = pd.concat([pd.read_parquet(f, columns=["name", "steps"])
                    for f in fichiers], ignore_index=True)
    out = {}
    for nom, st in zip(df["name"], df["steps"]):
        k = cle_titre(nom)
        if k and k not in out:
            out[k] = [str(x) for x in st][:25]
    return out


def main():
    WEB.mkdir(exist_ok=True)
    etapes = charger_etapes()
    with open("data/ref/ingredients.csv", encoding="utf-8") as f:
        ing = list(csv.DictReader(l for l in f if not l.lstrip().startswith("#")))

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
    idx_ing = {x["id"]: i for i, x in enumerate(ing_gardes)}
    tags = [t for t, n in tags_utilises.most_common() if n >= 20]
    idx_tag = {t: i for i, t in enumerate(tags)}
    cats = [c for c, _ in cats_utilisees.most_common()]
    idx_cat = {c: i for i, c in enumerate(cats)}

    # 3. Catalogue.
    sortie = []
    for i, r in enumerate(gardees):
        img = (r["img"][0] or "")
        if img.startswith(PREFIXE_IMG):
            img = img[len(PREFIXE_IMG):]
        ings = [[idx_ing[it["cid"]], int(it["g"] or 0), it.get("est", 0)]
                for it in r["ing"] if it.get("cid") in idx_ing]
        sortie.append({
            "i": i,
            "t": r["nom_en"],
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
            "st": etapes.get(cle_titre(r["nom_en"]), []),
        })

    json.dump({
        "n": len(sortie), "prefixe_img": PREFIXE_IMG,
        "categories": cats, "tags": tags, "recipes": sortie,
    }, open(WEB / "recipes.json", "w"), ensure_ascii=False, separators=(",", ":"))

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
    avec = sum(1 for r in sortie if r["st"])
    print(f"avec instructions    : {avec:,} ({avec/len(sortie)*100:.1f} %)")
    print(f"web/recipes.json     : {mo('recipes.json'):.1f} Mo")
    print(f"web/ingredients.json : {mo('ingredients.json'):.2f} Mo")


if __name__ == "__main__":
    main()
