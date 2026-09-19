"""
Construit le graphe de similarite composite entre recettes.

Meme principe que graph.bin de MovieMatch : pour chaque recette on pre-calcule
ses K plus proches voisins ET le detail du score par composante, quantifie en
uint8. Le client peut ainsi repondrer les composantes en direct (curseurs)
sans jamais recalculer de similarite.

Composantes :
  ingredient  Jaccard pondere par la rarete des ingredients (coeur du moteur)
  tag         Jaccard sur les tags Food.com
  categorie   meme categorie de plat
  temps       proximite du temps total
  cout        proximite du cout par portion
  nutri       proximite du profil calories / proteines
  (embed sera ajoute quand les embeddings de texte seront calcules)

Sorties : web/graph.bin, web/graph_meta.json, web/attrs.json
Usage   : python3 scripts/08_build_graph.py [--k 24]
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy import sparse

WEB = Path("web")
COMPOSANTES = ["ingredient", "tag", "categorie", "temps", "cout", "nutri"]
POIDS_DEFAUT = {"ingredient": 0.42, "tag": 0.20, "categorie": 0.12,
                "temps": 0.10, "cout": 0.10, "nutri": 0.06}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def matrice_idf(listes, n_colonnes, n_lignes):
    """Matrice creuse lignes x colonnes, ponderee IDF puis normalisee L2.

    L'IDF est ce qui fait la difference : sans elle, deux recettes se
    ressembleraient parce qu'elles contiennent toutes deux du sel.
    """
    indices = np.concatenate(listes) if listes else np.array([], dtype=np.int32)
    ptr = np.zeros(n_lignes + 1, dtype=np.int64)
    np.cumsum([len(x) for x in listes], out=ptr[1:])
    df = np.bincount(indices, minlength=n_colonnes).astype(np.float32)
    idf = np.log((n_lignes + 1) / (df + 1)).astype(np.float32)
    donnees = idf[indices]
    M = sparse.csr_matrix((donnees, indices, ptr),
                          shape=(n_lignes, n_colonnes), dtype=np.float32)
    normes = np.sqrt(M.multiply(M).sum(axis=1)).A.ravel()
    normes[normes == 0] = 1.0
    return sparse.diags(1.0 / normes) @ M


def proximite(a, b, echelle):
    """1 quand identique, decroit avec l'ecart relatif."""
    return np.exp(-np.abs(a - b) / echelle)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=24)
    ap.add_argument("--bloc", type=int, default=512)
    args = ap.parse_args()

    log("lecture du catalogue…")
    cat = json.load(open(WEB / "recipes.json"))
    R = cat["recipes"]
    N = len(R)
    n_ing = max(max((x[0] for r in R for x in r["ig"]), default=0) + 1, 1)
    n_tag = len(cat["tags"])

    ings = [np.array(sorted({x[0] for x in r["ig"]}), dtype=np.int32) for r in R]
    tags = [np.array(sorted(set(r["tg"])), dtype=np.int32) for r in R]
    cats = np.array([r["g"] for r in R], dtype=np.int32)
    mins = np.array([r["m"] for r in R], dtype=np.float32)
    couts = np.array([r["c"] for r in R], dtype=np.float32) / 100.0
    kcal = np.array([r["k"] for r in R], dtype=np.float32)
    prot = np.array([r["pr"] for r in R], dtype=np.float32)

    log(f"{N:,} recettes · {n_ing:,} ingredients · {n_tag} tags")
    log("matrices creuses ingredient / tag…")
    MI = matrice_idf(ings, n_ing, N)
    MT = matrice_idf(tags, n_tag, N)
    MIT = MI.T.tocsr()
    MTT = MT.T.tocsr()

    K = args.k
    idx_out = np.full((N, K), -1, dtype=np.int32)
    comp_out = np.zeros((N, K, len(COMPOSANTES)), dtype=np.uint8)
    poids = np.array([POIDS_DEFAUT[c] for c in COMPOSANTES], dtype=np.float32)

    log(f"voisins (K={K}) par blocs de {args.bloc}…")
    t0 = time.time()
    for debut in range(0, N, args.bloc):
        fin = min(debut + args.bloc, N)
        S = (MI[debut:fin] @ MIT).toarray()          # similarite ingredient
        for r in range(fin - debut):
            S[r, debut + r] = -1.0                    # jamais soi-meme
        # on ne score finement que les meilleurs candidats par ingredient
        garde = min(160, N - 1)
        pres = np.argpartition(-S, garde, axis=1)[:, :garde]

        T = (MT[debut:fin] @ MTT).toarray()
        for r in range(fin - debut):
            i = debut + r
            c = pres[r]
            s_ing = S[r, c]
            s_tag = T[r, c]
            s_cat = (cats[c] == cats[i]).astype(np.float32)
            s_tps = proximite(mins[c], mins[i], 30.0)
            s_cout = proximite(couts[c], couts[i], 1.5)
            s_nut = 0.5 * (proximite(kcal[c], kcal[i], 250.0)
                           + proximite(prot[c], prot[i], 20.0))
            comps = np.stack([s_ing, s_tag, s_cat, s_tps, s_cout, s_nut], axis=1)
            total = comps @ poids
            meilleurs = np.argsort(-total)[:K]
            idx_out[i] = c[meilleurs]
            comp_out[i] = np.clip(comps[meilleurs] * 255.0, 0, 255).astype(np.uint8)
        if debut % (args.bloc * 20) == 0 and debut:
            fait = fin / N
            log(f"  {fin:>7,}/{N:,}  ({fait*100:4.1f} %)  "
                f"reste ~{(time.time()-t0)*(1-fait)/fait/60:.0f} min")

    log("ecriture…")
    with open(WEB / "graph.bin", "wb") as f:
        f.write(idx_out.tobytes())
        f.write(comp_out.tobytes())
    json.dump({"n": N, "k": K, "components": COMPOSANTES,
               "default_weights": POIDS_DEFAUT,
               "idx_dtype": "int32", "comp_dtype": "uint8"},
              open(WEB / "graph_meta.json", "w"), indent=2)

    mo = lambda p: (WEB / p).stat().st_size / 1e6
    log(f"graph.bin {mo('graph.bin'):.1f} Mo")
    log(f"termine en {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
