# MARMITE — pipeline de données pour swipe-repas

## Objectif
Produire les fichiers de données statiques consommés par la PWA `swipe-repas` :
recommandation de repas par swipe, avec estimation du prix et gestion du stock
du garde-manger. Même architecture que IMDBOX → swipe-reco.

## Architecture
- Corpus : Food.com via `Karo8870/food.com-parsed-dataset` (490k recettes,
  ingrédients déjà parsés en `{quantity, unit, name}`) + instructions de cuisine
  depuis le dataset Kaggle original `irkaal/foodcom-recipes-and-reviews`
  (le champ `steps` de Karo8870 est corrompu — il contient les URLs d'images).
  Jointure sur `(name, created_at)`, timestamp exact donc très discriminant.
- **Colonne vertébrale : l'ingrédient canonique.** Une table de ~3-5k entrées
  (`data/ref/ingredients.csv`) à laquelle se rattachent les lignes de recettes,
  les prix au kg et le stock. Rien ne fonctionne sans elle : « 2 cups
  all-purpose flour » n'est ni valorisable ni décomptable tant qu'il n'est pas
  résolu en `flour_wheat_white` + 240 g.
- Prix : table de référence prix/kg par ingrédient canonique, amorcée via
  Open Prices (Open Food Facts) + Statbel, recalée par scraping Colruyt /
  Delhaize. Surcouche de corrections utilisateur stockée côté client.
- Traduction : FR intégral (titres, ingrédients, étapes) par modèle local
  sur GPU — étape la plus longue de la pipeline.
- Vecteurs : sentence-transformers → PCA 256 dims → int8. Contrainte dure :
  GitHub refuse un fichier > 100 Mo et Pages ne sert pas les objets LFS.
- Graphe : kNN composite pré-calculé, score par composante quantifié en uint8,
  pour que le client puisse repondérer les composantes en direct (sliders)
  sans recalcul — même mécanique que `graph.bin` de swipe-reco.
- Pas de backend, pas de base de données : tout est statique + IndexedDB
  côté client.

## Sortie (dossier web/, copié dans le repo swipe-repas)
| Fichier            | Contenu                                               |
|--------------------|-------------------------------------------------------|
| `recipes.json`     | catalogue : titre, temps, portions, nutrition, étapes |
| `ingredients.json` | ontologie canonique + prix/kg de référence            |
| `attrs.json`       | attributs discrets par recette (index aligné)         |
| `vectors.bin`      | embeddings int8, 256 dims                             |
| `graph.bin`        | kNN + détail par composante, uint8                    |
| `graph_meta.json`  | header (K, N, composantes, poids par défaut)          |
| `photos.pack`      | photos concaténées (format IMPK1), importé à la main  |

## Conventions
- Les scripts de `scripts/` sont numérotés et forment la pipeline dans l'ordre.
  Chacun est idempotent et écrit dans `data/work/`.
- `data/ref/` est **versionné** (c'est du travail humain, pas du dérivé).
  `data/raw/` et `data/work/` sont ignorés (régénérables).
- Unités : tout est ramené en grammes ou millilitres en interne.
  L'affichage en unités de cuisine se fait côté client.
