from __future__ import annotations

import re
import sys
import importlib
from dataclasses import dataclass
from pathlib import Path

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

from prompt_shield.core.database import Database


@dataclass
class ReplacementInfo:
    """One replacement performed during anonymization."""
    start: int          # position in the OUTPUT text
    end: int            # position in the OUTPUT text
    placeholder: str
    original_text: str
    category: str


@dataclass
class _Span:
    start: int
    end: int
    text: str
    category: str


def _find_model_data_dir(pkg_dir: Path) -> Path | None:
    """Locate the directory containing config.cfg inside a spaCy model package.
    """
    if (pkg_dir / "config.cfg").exists():
        return pkg_dir
    try:
        for child in pkg_dir.iterdir():
            if child.is_dir() and (child / "config.cfg").exists():
                return child
    except OSError:
        pass
    return None


def _resolve_model_name(lang: str) -> str:
    """Return a loadable spaCy model identifier — package name or filesystem path."""
    import spacy

    candidates = [
        f"{lang}_core_web_sm",
        f"{lang}_core_news_sm",
        f"{lang}_core_web_lg",
        f"{lang}_core_news_lg",
    ]

    # 1) Installed package (works in normal venv / dev mode)
    for name in candidates:
        if spacy.util.is_package(name):
            return name

    # 2) Importable module — covers PyInstaller frozen bundles where
    #    package metadata is missing but the module itself is bundled.
    for name in candidates:
        try:
            mod = importlib.import_module(name)
            data_dir = _find_model_data_dir(Path(mod.__file__).parent)
            if data_dir is not None:
                return str(data_dir)
        except (ImportError, OSError):
            continue

    # 3) Frozen bundle: look inside sys._MEIPASS (PyInstaller onedir/onefile)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for name in candidates:
            data_dir = _find_model_data_dir(Path(meipass) / name)
            if data_dir is not None:
                return str(data_dir)

    # 4) User-managed models in ~/.promptshield/models/
    models_dir = Path.home() / ".promptshield" / "models"
    for name in candidates:
        model_path = models_dir / name
        if model_path.is_dir():
            data_dir = _find_model_data_dir(model_path)
            if data_dir is not None:
                return str(data_dir)

    raise RuntimeError(
        f"No spaCy model found for language '{lang}'.\n"
        f"Please download a model in Settings → Language Models,\n"
        f"or run: python -m spacy download {lang}_core_web_sm"
    )


class AnonymizationEngine:
    def __init__(self, db: Database):
        self.db = db
        self._analyzer: AnalyzerEngine | None = None
        self._loaded_languages: set[str] = set()

    def ensure_analyzer(self, languages: list[str] | None = None):
        """Lazily create the analyzer (heavy operation)."""
        langs = languages or ["en"]
        langs_set = set(langs)
        if self._analyzer is not None and langs_set == self._loaded_languages:
            return

        models = []
        for lang in langs:
            model_id = _resolve_model_name(lang)
            models.append({"lang_code": lang, "model_name": model_id})

        configuration = {
            "nlp_engine_name": "spacy",
            "models": models,
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        nlp_engine = provider.create_engine()
        self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=langs)
        self._loaded_languages = langs_set

    def anonymize(
        self,
        text: str,
        language: str = "en",
        categories: list[str] | None = None,
        threshold: float = 0.35,
    ) -> tuple[str, list[ReplacementInfo]]:
        """Anonymize text with allow/block list support.

        Order: 1) allow-list protects spans, 2) block-list forces masking,
        3) Presidio detects remaining entities.
        """
        self.ensure_analyzer([language])

        # Step 1: Find allow-list spans (these are protected)
        allowed_spans = self._find_list_spans(text, self.db.all_allows())

        # Step 2: Find block-list spans (force-masked)
        block_spans = self._find_list_spans(text, self.db.all_blocks())
        # Remove block spans that overlap with allowed spans
        block_spans = [s for s in block_spans if not any(self._spans_overlap(s, a) for a in allowed_spans)]

        # Step 3: Run Presidio
        results: list[RecognizerResult] = self._analyzer.analyze(
            text=text,
            language=language,
            entities=categories,
            score_threshold=threshold,
        )

        # Convert Presidio results to _Span, removing those that overlap with allowed spans
        presidio_spans = []
        for r in results:
            span = _Span(r.start, r.end, text[r.start:r.end], r.entity_type)
            if any(self._spans_overlap(span, a) for a in allowed_spans):
                continue
            presidio_spans.append(span)

        # Merge block spans + presidio spans, deduplicate overlaps
        all_spans = block_spans + presidio_spans
        all_spans.sort(key=lambda s: (-s.end + s.start, s.start))  # longer spans first for dedup
        all_spans.sort(key=lambda s: s.start)

        # Deduplicate: keep first (leftmost), remove overlapping
        filtered: list[_Span] = []
        for span in all_spans:
            if not any(self._spans_overlap(span, kept) for kept in filtered):
                filtered.append(span)

        # Sort descending by start for replacement
        filtered.sort(key=lambda s: s.start, reverse=True)

        # Replace from end to start
        anonymized = text
        for span in filtered:
            placeholder = self.db.create_mapping(span.text, span.category)
            anonymized = anonymized[:span.start] + placeholder + anonymized[span.end:]

        # Compute output positions (forward pass)
        replacements = self._compute_output_positions(text, filtered)

        return anonymized, replacements

    def _find_list_spans(self, text: str, entries: list) -> list[_Span]:
        """Find all spans in text that match list entries."""
        spans = []
        for entry in entries:
            pattern_text = re.escape(entry["text"])
            if entry["prefix_match"]:
                pattern_text += r'\w*'
            flags = 0 if entry["case_sensitive"] else re.IGNORECASE
            pattern = re.compile(r'\b' + pattern_text + r'\b', flags)
            for m in pattern.finditer(text):
                spans.append(_Span(m.start(), m.end(), m.group(), "BLOCKED"))
        return spans

    def _compute_output_positions(
        self, original_text: str, spans: list[_Span]
    ) -> list[ReplacementInfo]:
        """Compute replacement positions in the anonymized output."""
        sorted_spans = sorted(spans, key=lambda s: s.start)
        replacements = []
        offset = 0

        for span in sorted_spans:
            mapping = self.db.get_mapping_by_text(span.text)
            if mapping is None:
                continue
            placeholder = mapping["placeholder"]
            out_start = span.start + offset
            out_end = out_start + len(placeholder)
            offset += len(placeholder) - (span.end - span.start)
            replacements.append(ReplacementInfo(
                start=out_start,
                end=out_end,
                placeholder=placeholder,
                original_text=span.text,
                category=span.category,
            ))

        return replacements

    @staticmethod
    def _spans_overlap(a: _Span, b: _Span) -> bool:
        return a.start < b.end and b.start < a.end
