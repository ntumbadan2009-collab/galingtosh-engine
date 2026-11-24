"""Cross-checked safety rules for level-2 procedural explanation diagrams.

All visible factual labels are exact, ordered excerpts from the narration;
no graphs, projections, arbitrary icons, datasets or inferred dates are
permitted. Structure is explanatory, not proof of the narration's factuality.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

KINDS = {"focus", "steps", "timeline", "comparison", "cause_effect", "cube_rotation", "sphere_rotation"}
ROTATION = re.compile(r"\b(?:rotation|tourne|tournent|rotates|rotating|spins|spin)\b",re.IGNORECASE)
SHAPES = {"cube_rotation": re.compile(r"\bcube\b",re.IGNORECASE), "sphere_rotation": re.compile(r"\b(?:sphère|sphere)\b",re.IGNORECASE)}
CAUSAL = re.compile(r"\b(?:donc|entraîne|provoque|conduit à|en conséquence|therefore|causes|leads to)\b", re.IGNORECASE)
TEMPORAL = re.compile(
    r"\b(?:puis|ensuite|après|avant|d'abord|premièrement|secondement|"
    r"troisièmement|initialement|finalement|au début|à la fin|"
    r"then|before|after|first|next|finally)\b|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)
CONTRAST = re.compile(
    r"\b(?:mais|cependant|pourtant|tandis que|alors que|contrairement|"
    r"différent|différence|par contre|en revanche|but|while|unlike|versus)\b",
    re.IGNORECASE,
)


def _norm(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def motion_spec_issues(narration: Any, quote: Any, spec: Any) -> list[str]:
    if spec is None:
        return []
    if not isinstance(spec, dict) or set(spec) != {"type", "items"}:
        return ["Spécification graphique : champs type et items requis uniquement."]
    kind = spec.get("type")
    items = spec.get("items")
    if not isinstance(kind, str) or kind not in KINDS or not isinstance(items, list):
        return ["Type graphique ou liste d'éléments invalide."]
    count = len(items)
    if ((kind in {"focus", "cube_rotation", "sphere_rotation"} and count != 1)
        or (kind in {"comparison", "cause_effect"} and count != 2)
        or (kind in {"steps", "timeline"} and not 2 <= count <= 4)):
        return ["Nombre de blocs narratifs non pris en charge."]
    source = _norm(narration)
    quoted = _norm(quote)
    if not quoted or quoted not in source:
        return ["L'illustration ne cite pas la narration en cours."]
    if kind in SHAPES and (not SHAPES[kind].search(quoted) or not ROTATION.search(quoted)):
        return ["La rotation et la forme géométrique doivent être explicitement citées."]
    if kind == "timeline" and not TEMPORAL.search(quoted):
        return ["La chronologie exige un ordre temporel explicite dans la narration."]
    if kind == "comparison" and not CONTRAST.search(quoted):
        return ["La comparaison exige un contraste explicite dans la narration."]
    if kind == "cause_effect" and not CAUSAL.search(quoted):
        return ["La relation de cause à effet doit être explicitement narrée dans cet ordre."]
    cursor = 0
    for i, element in enumerate(items):
        if not isinstance(element, dict) or set(element) != {"text"}:
            return [f"Bloc {i+1} : un seul champ text est autorisé."]
        text = _norm(element["text"])
        if not 5 <= len(text) <= 125:
            return [f"Bloc {i+1} : texte de 5 à 125 caractères requis."]
        pos = quoted.find(text, cursor)
        if pos < 0:
            return [f"Bloc {i+1} : citation absente ou désordonnée dans le récit."]
        if kind == "cause_effect" and i == 1 and not CAUSAL.fullmatch(quoted[cursor:pos].strip(" ,;:")):
            return ["Le connecteur causal doit se trouver exactement entre les deux fragments."]
        cursor = pos + len(text)
    return []
