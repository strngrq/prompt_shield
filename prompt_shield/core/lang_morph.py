"""Morphological helpers around pymorphy3 for Russian word-form handling.

Gracefully degrades (returns None / []) when pymorphy3 is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CYR_RE = re.compile(r"[\u0400-\u04FF]")
_SINGLE_WORD_RE = re.compile(r"^\S+$")

_morph = None


def _get_morph():
    global _morph
    if _morph is None:
        try:
            import pymorphy3
            _morph = pymorphy3.MorphAnalyzer()
        except Exception:
            _morph = False
    return _morph if _morph else None


@dataclass
class LemmatizeResult:
    primary: str | None = None
    alternatives: list[str] = field(default_factory=list)
    original: str = ""


def is_russian_word(text: str) -> bool:
    """True if *text* is a single word containing at least one Cyrillic letter."""
    return bool(_SINGLE_WORD_RE.match(text) and _CYR_RE.search(text))


def lemmatize(word: str) -> LemmatizeResult:
    """Return the most probable lemma and alternatives for a Russian word."""
    result = LemmatizeResult(original=word)
    if not is_russian_word(word):
        return result

    morph = _get_morph()
    if morph is None:
        return result

    try:
        parsed = morph.parse(word)
        if not parsed:
            return result

        seen: list[str] = []
        for p in parsed:
            nf = p.normal_form
            if nf not in seen:
                seen.append(nf)

        result.primary = seen[0] if seen else None
        result.alternatives = seen[1:]
    except Exception:
        pass

    return result


def enumerate_forms(word: str, limit: int = 15) -> list[str]:
    """Return representative inflected forms from pymorphy3's paradigm."""
    if not is_russian_word(word):
        return []

    morph = _get_morph()
    if morph is None:
        return []

    try:
        parsed = morph.parse(word)
        if not parsed:
            return []

        best = parsed[0]
        forms: list[str] = []
        seen: set[str] = set()
        for form in best.lexeme:
            w = form.word
            if w not in seen:
                seen.add(w)
                forms.append(w)
                if len(forms) >= limit:
                    break
        return forms
    except Exception:
        return []
