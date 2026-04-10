import re
from prompt_shield.core.database import Database

# ASCII-only word boundaries: forbid adjacent ASCII letter/digit/underscore
# but allow non-ASCII neighbours (Cyrillic, Greek, CJK …) so that
# "INFO_12е" matches while "INFO_12X" / "XINFO_12" do not.
# See docs/02-mask_improvements.md §1 for rationale (Python's \b treats
# Unicode letters as word chars, preventing matches like PERSON_1ы).
PLACEHOLDER_RE = re.compile(
    r'(?<![A-Za-z0-9_])([A-Z][A-Z_]*?)_(\d+)(?![A-Za-z0-9_])'
)


def deanonymize(text: str, db: Database) -> str:
    """Replace all placeholder tokens in text with their original values from the DB."""
    def replacer(match: re.Match) -> str:
        placeholder = match.group(0)
        mapping = db.get_mapping_by_placeholder(placeholder)
        if mapping:
            return mapping["original_text"]
        return placeholder  # leave unknown placeholders as-is

    return PLACEHOLDER_RE.sub(replacer, text)
