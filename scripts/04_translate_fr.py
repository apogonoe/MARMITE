"""
Traduit le catalogue en francais.

Deux niveaux, parce que la traduction automatique se trompe sur le vocabulaire
culinaire ("all-purpose flour" -> "farine tout usage", qui est du quebecois) :
  1. data/ref/fr_ingredients.csv  — 238 traductions curees, font autorite
  2. Helsinki-NLP/opus-mt-en-fr   — pour la traine des ingredients et les titres

Le cache (data/work/cache_fr.json) rend le script reprenable : relancer ne
retraduit que ce qui manque.

Sorties :
  data/ref/ingredients.csv  colonne nom_fr remplie
  data/work/titres_fr.json  titre anglais -> titre francais

Usage : python3 scripts/04_translate_fr.py [--titres] [--lot 64]
"""
import argparse
import csv
import json
import re
import time
from pathlib import Path

CACHE = Path("data/work/cache_fr.json")
ING = Path("data/ref/ingredients.csv")
TITRES = Path("data/work/titres_fr.json")
MODELE = "Helsinki-NLP/opus-mt-en-fr"


def lire_ref(nom):
    with open(f"data/ref/{nom}", encoding="utf-8") as f:
        return list(csv.DictReader(l for l in f if not l.lstrip().startswith("#")))


def charger_cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


class Traducteur:
    def __init__(self, lot):
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"modele {MODELE} sur {self.dev}…", flush=True)
        self.tok = AutoTokenizer.from_pretrained(MODELE)
        self.mod = AutoModelForSeq2SeqLM.from_pretrained(MODELE).to(self.dev).eval()
        if self.dev == "cuda":
            self.mod = self.mod.half()
        self.lot = lot

    # Traduire un nom d'ingredient seul donne des contresens : « nut » devient
    # « ecrou », « date » devient une date du calendrier. On l'enchasse donc
    # dans une phrase qui impose le sens culinaire, puis on retire l'amorce.
    CADRE = "Shopping list: 500 g of {}."
    AMORCE = re.compile(r"^.*?\b500\s*g\.?\s*(?:de\s+|d\'\s*)(?:la\s+|l\'\s*|le\s+|les\s+)?", re.I)

    def ingredients(self, noms):
        """Traduit des noms d'ingredients, avec cadre culinaire."""
        bruts = self([self.CADRE.format(n) for n in noms])
        simples = None
        out = []
        for i, (nom, b) in enumerate(zip(noms, bruts)):
            decoupe = self.AMORCE.sub("", b).strip(" .")
            if not decoupe or len(decoupe) > 80:
                # l'amorce n'a pas ete reconnue : on retombe sur la traduction nue
                if simples is None:
                    simples = self(noms)
                decoupe = simples[i]
            out.append(decoupe.lower())
        return out

    def __call__(self, textes):
        out = []
        t0 = time.time()
        for d in range(0, len(textes), self.lot):
            paquet = textes[d:d + self.lot]
            enc = self.tok(paquet, return_tensors="pt", padding=True,
                           truncation=True, max_length=96).to(self.dev)
            with self.torch.no_grad():
                gen = self.mod.generate(**enc, max_new_tokens=96, num_beams=1)
            out += self.tok.batch_decode(gen, skip_special_tokens=True)
            if d and d % (self.lot * 40) == 0:
                fait = d / len(textes)
                print(f"   {d:,}/{len(textes):,} ({fait*100:4.1f} %) "
                      f"reste ~{(time.time()-t0)*(1-fait)/fait/60:.0f} min", flush=True)
        return out


def nettoie_titre(s):
    """Le modele laisse parfois une majuscule parasite ou des espaces doubles."""
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:1].upper() + s[1:] if s else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titres", action="store_true", help="traduire aussi les titres")
    ap.add_argument("--lot", type=int, default=64)
    args = ap.parse_args()

    cache = charger_cache()
    cures = {r["id"]: r["fr"] for r in lire_ref("fr_ingredients.csv")}
    lignes = lire_ref("ingredients.csv")

    a_traduire = sorted({x["nom_en"] for x in lignes
                         if x["id"] not in cures and x["nom_en"] not in cache})
    todo_titres = []
    if args.titres:
        cat = json.load(open("web/recipes.json"))
        todo_titres = sorted({r["t"] for r in cat["recipes"] if r["t"] not in cache})

    total = len(a_traduire) + len(todo_titres)
    print(f"ingredients cures     : {len(cures)}")
    print(f"ingredients a traduire: {len(a_traduire):,}")
    print(f"titres a traduire     : {len(todo_titres):,}")
    if not total:
        print("rien a faire.")
    else:
        tr = Traducteur(args.lot)
        if a_traduire:
            print("ingredients…", flush=True)
            for s, f in zip(a_traduire, tr.ingredients(a_traduire)):
                cache[s] = f
            CACHE.write_text(json.dumps(cache, ensure_ascii=False))
        if todo_titres:
            print("titres…", flush=True)
            for s, f in zip(todo_titres, tr(todo_titres)):
                cache[s] = nettoie_titre(f)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False))

    # 1. colonne nom_fr de l'ontologie
    champs = list(lignes[0].keys())
    for x in lignes:
        x["nom_fr"] = cures.get(x["id"]) or cache.get(x["nom_en"], "")
    with open(ING, "w", newline="", encoding="utf-8") as f:
        f.write("# Ontologie canonique des ingredients. nom_fr et prix_eur_kg\n"
                "# sont remplis par les etapes 04 (traduction) et 05 (prix).\n")
        w = csv.DictWriter(f, fieldnames=champs)
        w.writeheader()
        w.writerows(lignes)

    # 2. table des titres
    if args.titres:
        cat = json.load(open("web/recipes.json"))
        t = {r["t"]: cache[r["t"]] for r in cat["recipes"] if r["t"] in cache}
        TITRES.write_text(json.dumps(t, ensure_ascii=False))
        print(f"titres traduits  : {len(t):,}")

    remplis = sum(1 for x in lignes if x["nom_fr"])
    print(f"ingredients en FR: {remplis:,}/{len(lignes):,} "
          f"({remplis/len(lignes)*100:.1f} %)")


if __name__ == "__main__":
    main()
