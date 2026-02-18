# Anki LLM Field Generator
# Prompt template engine

import re
from typing import Dict


def build_prompt(template: str, note_fields: Dict[str, str]) -> str:
    """Replace {{field_name}} placeholders with note field values.

    Args:
        template: Prompt template with {{field_name}} placeholders.
        note_fields: Dict mapping field names to their values.

    Returns:
        Prompt string with placeholders replaced.

    Example:
        >>> build_prompt(
        ...     'Define "{{Front}}" in Japanese.',
        ...     {"Front": "食べる", "Back": ""}
        ... )
        'Define "食べる" in Japanese.'
    """
    result = template
    for field_name, field_value in note_fields.items():
        placeholder = "{{" + field_name + "}}"
        result = result.replace(placeholder, field_value)
    return result


def get_note_fields_dict(note) -> Dict[str, str]:
    """Extract a {field_name: field_value} dict from an Anki Note object.

    Args:
        note: An Anki Note object (from mw.col.get_note() or similar).

    Returns:
        Dict mapping field names to their string values.
    """
    field_names = [f["name"] for f in note.note_type()["flds"]]
    return {name: note[name] for name in field_names}


def validate_template(template: str, available_fields: list) -> list:
    """Check that all placeholders in the template match available fields.

    Returns:
        List of invalid placeholder names (empty if all are valid).
    """
    placeholders = re.findall(r"\{\{(\w+)\}\}", template)
    invalid = [p for p in placeholders if p not in available_fields]
    return invalid
