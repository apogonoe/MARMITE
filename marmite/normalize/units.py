"""Conversion des quantites de recette vers des grammes.

Regle : tout est ramene en grammes. Quand c'est impossible (densite inconnue
pour un volume, poids/piece inconnu pour un compte), on renvoie None plutot
que de deviner — une estimation de prix fausse est pire qu'une absence.
"""
import csv
import re
from pathlib import Path

REF = Path(__file__).resolve().parents[2] / "data" / "ref"

# Masses forfaitaires pour les quantites vagues.
VAGUE_G = {"pinch": 0.4, "dash": 0.6, "handful": 30.0, "to_taste": 0.5}


def _lire(nom):
    with open(REF / nom, encoding="utf-8") as f:
        return list(csv.DictReader(l for l in f if not l.lstrip().startswith("#")))


def charger_unites():
    """unite normalisee -> (genre, to_g, to_ml)."""
    table = {}
    for r in _lire("units.csv"):
        to_g = float(r["to_g"]) if r["to_g"] else None
        to_ml = float(r["to_ml"]) if r["to_ml"] else None
        entree = (r["kind"], to_g, to_ml)
        table[r["unit"]] = entree
        for a in (r["aliases"] or "").split(";"):
            if a.strip():
                table[a.strip().lower()] = entree
    return table


def charger_contenants():
    return {r["unite"]: float(r["g_defaut"]) for r in _lire("containers.csv")}


UNITES = charger_unites()
CONTENANTS = charger_contenants()

# Qualificatifs de taille employes comme unites dans le corpus ("2 large eggs").
TAILLES = {"large": 1.25, "medium": 1.0, "small": 0.75, "jumbo": 1.5,
           "extra large": 1.4, "baby": 0.5}

_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1/3, "⅔": 2/3,
              "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}


def parse_quantite(s):
    """'1 1/2' -> 1.5 ; '3 -4' -> 3.5 (milieu de fourchette) ; '1/4' -> 0.25."""
    if s is None:
        return None
    s = str(s).strip().lower()
    if not s:
        return None
    for car, val in _FRACTIONS.items():
        s = s.replace(car, f" {val} ")
    s = s.replace("-", " - ")
    bornes = [b.strip() for b in s.split(" - ") if b.strip()]
    valeurs = [v for v in (_somme(b) for b in bornes) if v is not None]
    if not valeurs:
        return None
    return sum(valeurs) / len(valeurs)      # fourchette -> milieu


def _somme(expr):
    """'1 1/2' -> 1.5 : les nombres juxtaposes s'additionnent."""
    total, vu = 0.0, False
    for jeton in expr.split():
        if re.fullmatch(r"\d+/\d+", jeton):
            a, b = jeton.split("/")
            if float(b):
                total += float(a) / float(b); vu = True
        elif re.fullmatch(r"\d*\.?\d+", jeton):
            total += float(jeton); vu = True
    return total if vu else None


def normalise_unite(u):
    if not u:
        return None
    u = re.sub(r"[^a-z ]", "", str(u).lower()).strip()
    return u or None


def en_grammes(quantite, unite, g_par_ml=None, g_par_piece=None,
               g_ml_defaut=None, g_piece_defaut=None):
    """Convertit (quantite, unite) en grammes. Renvoie (grammes, methode).

    Les valeurs `*_defaut` (moyennes de categorie) ne servent qu'en dernier
    recours ; la methode retournee se termine alors par `_estime`, pour que
    l'app puisse afficher un prix comme approximatif.
    """
    u = normalise_unite(unite)
    exact_ml, exact_pc = g_par_ml, g_par_piece
    g_par_ml = g_par_ml or g_ml_defaut
    g_par_piece = g_par_piece or g_piece_defaut

    def _m(nom, exact):
        return nom if exact else nom + "_estime"

    # Pas d'unite : c'est un compte ("2 onions").
    if u is None or u in ("", "piece"):
        if quantite is None:
            return ((g_par_piece, _m("piece_unique", exact_pc))
                    if g_par_piece else (None, "inconnu"))
        return ((quantite * g_par_piece, _m("piece", exact_pc))
                if g_par_piece else (None, "sans_unite"))

    if u in TAILLES:                       # "2 large eggs"
        if g_par_piece and quantite is not None:
            return quantite * g_par_piece * TAILLES[u], _m("piece_taille", exact_pc)
        return None, "taille_sans_poids"

    entree = UNITES.get(u)
    if entree:
        genre, to_g, to_ml = entree
        if genre == "vague":
            return VAGUE_G.get(u, 0.5), "vague"
        if quantite is None:
            return None, "quantite_absente"
        if genre == "mass":
            return quantite * to_g, "masse"
        if genre == "volume":
            ml = quantite * to_ml
            if g_par_ml:
                return ml * g_par_ml, _m("volume", exact_ml)
            return None, "densite_inconnue"
        if genre == "count":
            if u in CONTENANTS:
                return quantite * CONTENANTS[u], "contenant"
            if g_par_piece:
                return quantite * g_par_piece, _m("piece", exact_pc)
            return None, "piece_inconnue"

    if u in CONTENANTS:
        return (quantite or 1) * CONTENANTS[u], "contenant"
    return None, "unite_inconnue"
