# MARMITE

Pipeline de données pour **MarmiteMatch** (repo `swipe-repas`) : recommandation
de repas par swipe, avec estimation du prix et gestion du garde-manger.

Même architecture que `IMDBOX` → `swipe-reco` : une pipeline Python produit des
fichiers statiques, une PWA les consomme. Pas de backend, pas de base de données.

## Chiffres

| | |
|---|---|
| Corpus brut | 490 457 recettes (Food.com) |
| Lignes d'ingrédients | 4 629 272 |
| Ingrédients canoniques | 2 897 |
| Lignes résolues vers l'ontologie | 95,1 % |
| Lignes converties en grammes | 95,5 % |
| Catalogue exporté | 87 925 recettes |
| Coût médian par portion | 0,96 € |

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Pipeline

Les scripts sont numérotés et s'exécutent dans l'ordre. Chacun est idempotent.

```bash
# 00  mesure le vocabulaire d'ingrédients (diagnostic, facultatif)
python3 scripts/00_analyse_vocabulaire.py

# 02  construit l'ontologie canonique — la colonne vertébrale du projet
python3 scripts/02_build_ingredient_ontology.py --top 3000

# 03  résout les 4,6 M de lignes vers l'ontologie et convertit en grammes
python3 scripts/03_normalize_recipes.py

# 06  calcule le coût de chaque recette
python3 scripts/06_price_recipes.py

# 08  construit le graphe de similarité composite
python3 scripts/08_build_graph.py --k 24

# 09  exporte le catalogue filtré vers web/
python3 scripts/09_export_web.py
```

Puis copier `web/*` dans le repo `swipe-repas` et **incrémenter `DATA_CACHE`**
dans son `index.html` pour invalider le cache des clients.

## Données sources

| Source | Rôle | Remarque |
|---|---|---|
| `Karo8870/food.com-parsed-dataset` | corpus principal, 490 457 recettes | ingrédients **déjà parsés** en `{quantity, unit, name}` |
| `KingName1/food.com` | instructions de cuisine | ne couvre que 31,5 % du catalogue |

Deux pièges rencontrés, à ne pas refaire :

- **`AkashPS11/recipes_data_food.com` est inutilisable** : il annonce 1 048 543
  lignes mais n'en contient que 1 228 de remplies. Le reste est du vide.
- **Le champ `steps` de `Karo8870` est corrompu sur tout le dataset** : il
  contient les URLs d'images au lieu des instructions.

> **Pour avoir les instructions des 490 457 recettes**, il faut le dataset
> Kaggle d'origine `irkaal/foodcom-recipes-and-reviews`, qui demande un token
> API (kaggle.com → Settings → API → Create New Token, puis
> `~/.kaggle/kaggle.json`). La jointure se fait sur `(name, created_at)`.

## L'ontologie d'ingrédients

C'est la pièce centrale : elle relie les recettes, les prix et le stock.
Sans elle, « 2 cups all-purpose flour » n'est ni valorisable ni décomptable.

Tables de référence dans `data/ref/`, **versionnées** parce que c'est du travail
humain et non du dérivé :

| Fichier | Contenu |
|---|---|
| `ingredients.csv` | l'ontologie produite (2 897 entrées) |
| `aliases.csv` | 280 895 noms bruts → id canonique |
| `synonyms.csv` | fusions curées à la main (325 variantes) |
| `categories.csv` | 23 catégories : conservation, fond de placard, prix moyen |
| `category_rules.csv` | attribution automatique par motif (269 règles) |
| `densities.csv` | g/ml — convertit les volumes de cuisine en masse |
| `piece_weights.csv` | g/pièce — « 2 oignons » → 300 g |
| `containers.csv` | contenances (1 can = 400 g) |
| `units.csv` | conversions d'unités |
| `prices.csv` | 237 prix/kg curés, supermarché belge |

Mesure de couverture : après repliement lexical, **2 000 ingrédients canoniques
couvrent 93,6 %** des lignes du corpus, 3 000 en couvrent 95,4 %.

## Prix

Les prix sont des **ordres de grandeur**, pas des relevés. L'app permet de
corriger chaque prix ; les corrections sont stockées côté client et rendent
l'estimation juste pour son utilisateur.

Sur le relevé automatique en Belgique : **Colruyt renvoie HTTP 456 avec une page
anti-bot** — la contourner n'est pas envisagé. **Delhaize** charge ses produits
en XHR et son API refuse les requêtes directes (403). Open Prices (Open Food
Facts) existe mais indexe des codes-barres, pas des ingrédients bruts : la
couverture sur « farine » ou « blanc de poulet » est quasi nulle.
