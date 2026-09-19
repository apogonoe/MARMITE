"""
Resout les 4,6 M de lignes d'ingredients du corpus vers l'ontologie canonique
et convertit chaque quantite en grammes.

Sortie : data/work/recipes.jsonl — une recette par ligne, avec pour chaque
ingredient son id canonique et sa masse. C'est ce fichier qui rend possibles
l'estimation de prix (etape 06) et le decompte du garde-manger.

Usage : python3 scripts/03_normalize_recipes.py [--limit N]
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marmite.normalize.text import normalise, COMPOSES          # noqa: E402
from marmite.normalize.units import parse_quantite, en_grammes  # noqa: E402

CSV_IN = "data/raw/foodcom_parsed.csv"
JSONL_OUT = "data/work/recipes.jsonl"


def lire_ref(nom):
    with open(f"data/ref/{nom}", encoding="utf-8") as f:
        return list(csv.DictReader(l for l in f if not l.lstrip().startswith("#")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=JSONL_OUT)
    args = ap.parse_args()

    ing = {r["id"]: r for r in lire_ref("ingredients.csv")}
    alias = {r["brut"]: r["canonique"] for r in lire_ref("aliases.csv")}
    # Repli : si le nom brut est inconnu, on retente sur sa forme repliee.
    replie2id = {}
    for brut, cid in alias.items():
        replie2id.setdefault(normalise(brut), cid)

    def resoudre(nom, _cache={}):
        """Nom brut -> id(s) canonique(s), en trois tentatives.

        La troisieme est indispensable : une forme composee rare comme
        « shelled pecan halves » n'entre pas dans le top-N de l'ontologie et
        etait purement et simplement jetee — alors qu'elle contient « pecan ».
        Sur une recette de noix de pecan, cela faisait tomber le cout de 10 EUR
        a 0,77 EUR. On cherche donc le plus long groupe de mots connu, en
        partant de la fin du nom : en cuisine le nom de tete porte le produit.
        """
        if nom in _cache:
            return _cache[nom]
        r = alias.get(nom.lower())
        if r is None:
            f = normalise(nom)
            r = replie2id.get(f)
            if r is None and f:
                mots = f.split()
                for n in range(len(mots) - 1, 0, -1):
                    for d in range(len(mots) - n, -1, -1):
                        cid = replie2id.get(" ".join(mots[d:d + n]))
                        if cid:
                            r = cid
                            break
                    if r:
                        break
        if len(_cache) < 400_000:
            _cache[nom] = r
        return r

    stats = Counter()
    par_recette = []
    sortie = open(args.out, "w", encoding="utf-8")
    n = 0

    cols = ["name", "cooking_time", "preparation_time", "description", "images",
            "RecipeCategory", "tags", "calories", "protein", "carbohydrates",
            "total_fat", "servings", "ingredients"]

    for bloc in __import__("pandas").read_csv(
            CSV_IN, usecols=cols, chunksize=20_000, low_memory=False):
        for _, row in bloc.iterrows():
            if args.limit and n >= args.limit:
                break
            try:
                lignes = json.loads(row["ingredients"])
            except Exception:
                stats["recette_ingredients_illisibles"] += 1
                continue

            sortis, resolus = [], 0
            for it in lignes:
                nom = (it.get("name") or "").strip()
                if not nom:
                    continue
                stats["lignes"] += 1
                cids = resoudre(nom)
                if not cids:
                    stats["non_resolu"] += 1
                    sortis.append({"brut": nom[:60], "cid": None, "g": None})
                    continue
                resolus += 1
                q = parse_quantite(it.get("quantity"))
                u = it.get("unit") or it.get("unitUnit")
                for cid in cids.split(";"):
                    fiche = ing.get(cid)
                    if not fiche:
                        continue
                    g, methode = en_grammes(
                        q, u,
                        float(fiche["g_par_ml"]) if fiche["g_par_ml"] else None,
                        float(fiche["g_par_piece"]) if fiche["g_par_piece"] else None,
                        float(fiche["g_ml_defaut"]) if fiche["g_ml_defaut"] else None,
                        float(fiche["g_piece_defaut"]) if fiche["g_piece_defaut"] else None)
                    stats[f"m_{methode}"] += 1
                    if g is not None:
                        stats["avec_masse"] += 1
                    sortis.append({"brut": nom[:60], "cid": cid,
                                   "g": round(g, 1) if g else None,
                                   "est": 1 if methode.endswith("_estime") else 0})

            if not sortis:
                continue
            taux = resolus / max(len(lignes), 1)
            par_recette.append(taux)
            avec_g = sum(1 for s in sortis if s["g"] is not None)

            sortie.write(json.dumps({
                "i": n,
                "nom_en": str(row["name"]),
                "min": _entier(row["cooking_time"]) + _entier(row["preparation_time"]),
                "portions": _entier(row["servings"]) or None,
                "cat": str(row["RecipeCategory"]) if row["RecipeCategory"] == row["RecipeCategory"] else None,
                "tags": _liste(row["tags"]),
                "img": _liste(row["images"])[:1],
                "kcal": _flottant(row["calories"]),
                "prot": _flottant(row["protein"]),
                "gluc": _flottant(row["carbohydrates"]),
                "lip": _flottant(row["total_fat"]),
                "ing": sortis,
                "res": round(taux, 3),
                "res_g": round(avec_g / max(len(sortis), 1), 3),
            }, ensure_ascii=False) + "\n")
            n += 1
        if args.limit and n >= args.limit:
            break

    sortie.close()
    total = stats["lignes"]
    print(f"recettes ecrites       : {n:,}")
    print(f"lignes d'ingredients   : {total:,}")
    print(f"  resolues vers l'onto : {total - stats['non_resolu']:,} "
          f"({(total-stats['non_resolu'])/total*100:.1f} %)")
    print(f"  converties en grammes: {stats['avec_masse']:,} "
          f"({stats['avec_masse']/total*100:.1f} %)")
    moy = sum(par_recette) / len(par_recette)
    complet = sum(1 for t in par_recette if t == 1.0) / len(par_recette)
    print(f"resolution moyenne/recette : {moy*100:.1f} %")
    print(f"recettes 100 % resolues    : {complet*100:.1f} %")
    print("\n--- methodes de conversion ---")
    for k, v in stats.most_common():
        if k.startswith("m_"):
            print(f"  {k[2:]:<22} {v:>9,}  ({v/total*100:4.1f} %)")


def _entier(v):
    try:
        return int(float(v))
    except Exception:
        return 0


def _flottant(v):
    try:
        f = float(v)
        return round(f, 1) if f == f else None
    except Exception:
        return None


def _liste(v):
    try:
        x = json.loads(v)
        return x if isinstance(x, list) else []
    except Exception:
        return []


if __name__ == "__main__":
    main()
