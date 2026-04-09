import re
from prompt_shield.core.database import Database

# Matches placeholders like PERSON_1, ORGANIZATION_12, INFO_3
PLACEHOLDER_RE = re.compile(r'\b([A-Z][A-Z_]*?)_(\d+)\b')


def deanonymize(text: str, db: Database) -> str:
    """Replace all placeholder tokens in text with their original values from the DB."""
    def replacer(match: re.Match) -> str:
        placeholder = match.group(0)
        mapping = db.get_mapping_by_placeholder(placeholder)
        if mapping:
            return mapping["original_text"]
        return placeholder  # leave unknown placeholders as-is

    return PLACEHOLDER_RE.sub(replacer, text)
