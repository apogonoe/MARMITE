"""Normalisation lexicale des noms d'ingredients bruts.

Le but n'est PAS de resoudre l'ingredient (c'est le role de l'ontologie), mais
de replier les variantes d'ecriture pour que l'ontologie reste de taille humaine.
Mesure sur le corpus Food.com : 421 874 noms distincts en entree.
"""
import re

# Le corpus contient des echappements JSON casses a la source.
_ESCAPES = {
    "u0027": "'", "u0026": "&", "u00e9": "e", "u00e8": "e",
    "u00ae": "", "u2019": "'", "u201c": "", "u201d": "", "u00bd": "1/2",
}

# Descripteurs culinaires qui ne changent pas l'identite de l'ingredient.
_MODIF = (
    "fresh|freshly|frozen|dried|dry|canned|cooked|uncooked|raw|whole|ground|grated|"
    "chopped|minced|sliced|diced|shredded|crushed|melted|softened|beaten|peeled|"
    "seeded|cubed|boneless|skinless|lean|low-fat|lowfat|low fat|nonfat|non-fat|"
    "fat-free|reduced-fat|reduced fat|light|lite|extra|large|medium|small|jumbo|"
    "baby|mini|ripe|unripe|organic|unsalted|salted|sweetened|unsweetened|plain|"
    "prepared|packed|firmly|hot|cold|warm|room temperature|store-bought|homemade|"
    "good quality|quality|finely|coarsely|thinly|roughly|coarse|fine|thick|thin|"
    "new|old|young|halved|quartered|trimmed|rinsed|drained|divided|optional|"
    "boiling|warmed|chilled|toasted|roasted|blanched|pitted|stemmed|deveined|"
    # decoupes et portions : ne changent pas l'identite de l'ingredient
    "shelled|unshelled|halves|half|pieces|piece|chunks|chunk|strips|strip|"
    "wedges|wedge|rings|ring|florets|floret|sprigs|sprig|cubes|cube|tips|tip|"
    "bite size|bite-size|rounds|shredded|julienned|matchstick"
)
_MODIF_RE = re.compile(r"\b(" + _MODIF + r")\b")

# Pluriels irreguliers frequents en cuisine.
_IRREG = {
    "leaves": "leaf", "halves": "half", "loaves": "loaf", "knives": "knife",
    "potatoes": "potato", "tomatoes": "tomato", "chilies": "chili",
    "chillies": "chili", "berries": "berry", "cherries": "cherry",
    "anchovies": "anchovy", "geese": "goose", "feet": "foot", "teeth": "tooth",
}
# Mots en -s/-us/-is qui sont deja au singulier : ne jamais les amputer.
_INVARIANT = {
    "molasses", "asparagus", "hummus", "couscous", "watercress", "cress",
    "bass", "swiss", "gras", "anis", "hominy", "citrus", "harissa",
    "focaccia", "brussels", "worcestershire",
}

# Mots de contenant/portion : "sprigs of mint" -> "mint".
# N'inclut PAS cream/heart : "cream of tartar", "hearts of palm" sont des
# ingredients a part entiere.
_PORTION = (
    "sprig|sprigs|bunch|bunches|pinch|pinches|dash|dashes|handful|handfuls|"
    "piece|pieces|slice|slices|can|cans|jar|jars|package|packages|bottle|"
    "bottles|stalk|stalks|sheet|sheets|strip|strips|drop|drops|clove|cloves|"
    "head|heads|stick|sticks|cube|cubes|pound|pounds|ounce|ounces|cup|cups|"
    "tablespoon|tablespoons|teaspoon|teaspoons|box|boxes|bag|bags|tin|tins"
)
_PORTION_RE = re.compile(r"^(" + _PORTION + r")\s+of\s+")


def normalise(s: str) -> str:
    """Replie un nom d'ingredient brut vers sa forme lexicale canonique."""
    if not s:
        return ""
    s = s.lower().strip()
    for k, v in _ESCAPES.items():
        s = s.replace(k, v)
    s = re.sub(r"\([^)]*\)", " ", s)        # "potatoes (peeled)" -> "potatoes"
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[(\[].*$", " ", s)         # parenthese jamais refermee
    s = s.replace("'", "")                   # "confectioners' sugar"
    s = s.split(",")[0]                      # "tomatoes, peeled" -> "tomatoes"
    s = re.sub(r"\bor\b.*$", " ", s)         # "butter or margarine" -> "butter"
    s = _MODIF_RE.sub(" ", s)
    s = re.sub(r"[^a-z0-9%&\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -'")
    s = _PORTION_RE.sub("", s)               # "sprigs of mint" -> "mint"
    s = re.sub(r"^(of|the|a|an)\s+", "", s)  # "of mint" -> "mint"
    s = re.sub(r"\s+(of|the)$", "", s)
    return " ".join(_singulier(w) for w in s.split()) if s else ""


def _singulier(w: str) -> str:
    if w in _IRREG:
        return _IRREG[w]
    if w in _INVARIANT or len(w) <= 3:
        return w
    if w.endswith(("ss", "us", "is")):
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("shes", "ches", "xes", "zes")):
        return w[:-2]
    if w.endswith("s"):
        return w[:-1]
    return w


# Lignes qui designent plusieurs ingredients a la fois.
COMPOSES = {
    "salt and pepper": ["salt", "black pepper"],
    "salt & pepper": ["salt", "black pepper"],
    "salt & black pepper": ["salt", "black pepper"],
    "salt and black pepper": ["salt", "black pepper"],
    "salt and freshly pepper": ["salt", "black pepper"],
    "oil and vinegar": ["vegetable oil", "vinegar"],
}


def slug(s: str) -> str:
    """Identifiant stable pour un ingredient canonique."""
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:48]
