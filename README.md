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

| Source | Rôle | Licence | Remarque |
|---|---|---|---|
| `Karo8870/food.com-parsed-dataset` | corpus principal, 490 457 recettes | — | ingrédients **déjà parsés** en `{quantity, unit, name}` |
| `SandhyaKilari/RecipeNLG_dataset` | instructions de cuisine | CC-BY-4.0 | 2,2 M de recettes ; apparie **93,3 %** du catalogue par titre, texte propre |
| `KingName1/food.com` | instructions, repli | — | couvre 31,5 % ; en minuscules sans ponctuation, sert là où RecipeNLG n'a rien |

Ensemble, les deux sources d'instructions couvrent **93,5 % du catalogue**, sans
aucun identifiant à créer.

Deux pièges rencontrés, à ne pas refaire :

- **`AkashPS11/recipes_data_food.com` est inutilisable** : il annonce 1 048 543
  lignes mais n'en contient que 1 228 de remplies. Le reste est du vide.
- **Le champ `steps` de `Karo8870` est corrompu sur tout le dataset** : il
  contient les URLs d'images au lieu des instructions.

> Les 6,5 % de recettes encore sans instructions se trouveraient dans le
> dataset Kaggle `irkaal/foodcom-recipes-and-reviews` (jointure sur
> `(name, created_at)`), mais il demande un compte et un token API — et le gain
> ne le justifie plus depuis que RecipeNLG couvre l'essentiel.

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

## Traduction française

Deux niveaux, parce que la traduction automatique se trompe lourdement sur le
vocabulaire culinaire :

1. **`data/ref/fr_ingredients.csv`** — 275 traductions curées à la main, qui
   font autorité. Sans elles, `all-purpose flour` devient « farine tout usage »
   (du québécois) et `nut` devient… « écrou ».
2. **`Helsinki-NLP/opus-mt-en-fr`** pour la traîne. Chaque nom est enchâssé
   dans une phrase qui impose le sens culinaire
   (`Shopping list: 500 g of X.`) avant d'être traduit, puis l'amorce est
   retirée. C'est ce qui fait passer `nut` de « écrou » à « noix ».

Résultat : **2 897 ingrédients sur 2 897 en français**, ce qui porte la
recherche, le garde-manger, la liste de courses et l'affichage des prix.

### Les titres de recettes restent en anglais

Testé sur les mêmes titres, `opus-mt-en-fr` **et** `NLLB-200-distilled-600M`
produisent tous deux des contresens visibles :

| Titre | opus-mt | NLLB-600M |
|---|---|---|
| Blueberry Scones | Écossais de bleuets | Les coquilles de bleu |
| Abby's Pecan Apple Cake | Cake aux **pommes de terre** | Le gâteau de pommes Pecan |
| Buttermilk Pie | Tarte de lait de **boucherie** | Pie à beurre |

Un titre de recette est un empilement de noms sans verbe, mêlant marques et
noms propres : c'est hors de portée d'un petit modèle de traduction. Mieux vaut
l'anglais qu'un contresens. Le travail est conservé
(`data/work/titres_fr.json`) et s'active avec
`python3 scripts/09_export_web.py --titres-fr` quand un meilleur modèle sera
passé.

## Résolution en trois tentatives

Un nom d'ingrédient brut est résolu ainsi, dans l'ordre :

1. **alias direct** — le nom exact est connu ;
2. **forme repliée** — après nettoyage lexical (`marmite.normalize.text`) ;
3. **repli sur le nom de tête** — on cherche le plus long groupe de mots connu,
   en partant de la fin du nom.

La troisième est indispensable. `shelled pecan halves` ne figure pas dans le
top-N de l'ontologie et était **purement et simplement jeté**, alors qu'il
contient `pecan`. Sur une recette de noix de pécan, cela faisait tomber le coût
estimé de 10 € à 0,77 €. Ce repli fait passer la résolution de 95,1 % à
**99,3 %** des lignes, et les recettes intégralement résolues de 67,9 % à
**93,8 %**.

## Attribution des catégories : la règle du nom de tête

`plus_long()` applique deux règles, dans cet ordre :

1. **un motif qui termine le nom l'emporte** — en cuisine, le nom de tête porte
   la nature du produit : « olive oil » est une huile, pas une olive ;
   « chicken broth » est un bouillon, pas de la volaille ;
2. à position égale, le motif le plus long gagne — ce qui permet d'écrire une
   règle générale (`butter`) puis son exception (`peanut butter`).

Sans la première règle, l'huile d'olive héritait d'une conservation de 7 jours
au lieu de 120 et sortait du fond de placard.

## Prix

Les prix sont des **ordres de grandeur**, pas des relevés. L'app permet de
corriger chaque prix ; les corrections sont stockées côté client et rendent
l'estimation juste pour son utilisateur.

Sur le relevé automatique en Belgique : **Colruyt renvoie HTTP 456 avec une page
anti-bot** — la contourner n'est pas envisagé. **Delhaize** charge ses produits
en XHR et son API refuse les requêtes directes (403). Open Prices (Open Food
Facts) existe mais indexe des codes-barres, pas des ingrédients bruts : la
couverture sur « farine » ou « blanc de poulet » est quasi nulle.
