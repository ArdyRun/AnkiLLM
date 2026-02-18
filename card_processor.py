# Anki LLM Field Generator
# Card detection and field filling logic
#
# Architecture:
# - LLM API calls happen outside the collection lock (via QueryOp)
# - Note saves happen inside the collection lock (via CollectionOp)
# - This prevents blocking Anki during slow LLM network requests

import functools
from typing import TYPE_CHECKING, Optional, List

from anki.collection import Collection, OpChanges
from aqt import mw
from aqt.operations import CollectionOp, QueryOp
from aqt.utils import tooltip, showInfo

from .llm_client import LLMClient, LLMError
from .prompt_builder import build_prompt, get_note_fields_dict

if TYPE_CHECKING:
    from anki.notes import Note
    from aqt.main import AnkiQt

ADDON_NAME = "LLM Field Generator"


# ─── Config Helpers ────────────────────────────────────────────────


def get_config() -> dict:
    """Get addon config from Anki's addon manager."""
    assert mw is not None
    package = __name__.split(".")[0]
    config = mw.addonManager.getConfig(package)
    return config or {}


def get_llm_client(config: dict) -> LLMClient:
    """Create an LLMClient from the addon config."""
    return LLMClient(
        base_url=config.get("api_base_url", "http://localhost:11434"),
        model=config.get("model", "llama3.2"),
        temperature=config.get("temperature", 0.7),
        max_tokens=config.get("max_tokens", 500),
        api_key=config.get("api_key", ""),
        timeout=config.get("timeout", 60),
    )


# ─── Trigger Types ─────────────────────────────────────────────────

ALL_TRIGGERS = ["mining", "add_cards", "browse", "focus_lost", "toolbar"]


# ─── Note Matching ─────────────────────────────────────────────────


def should_process_note(
    note: "Note", config: dict, trigger: str = ""
) -> Optional[dict]:
    """Check if a note should be processed and return its mapping if so.

    Args:
        note: The Anki note to check.
        config: Addon configuration dict.
        trigger: Which trigger is calling (e.g. 'mining', 'add_cards',
                 'browse', 'focus_lost', 'toolbar'). If empty, skip
                 trigger check.

    Returns:
        The mapping dict for this note type, or None if not applicable.
    """
    note_type = note.note_type()
    if note_type is None:
        return None

    note_type_name = note_type["name"]
    mappings = config.get("note_type_mappings", {})

    if note_type_name not in mappings:
        return None

    mapping = mappings[note_type_name]

    # Check trigger permission
    if trigger:
        allowed = mapping.get("triggered_by", ALL_TRIGGERS)
        if trigger not in allowed:
            return None

    # Validate that fields exist on this note type
    field_names = [f["name"] for f in note_type["flds"]]
    source_field = mapping.get("source_field", "")
    target_fields = mapping.get("target_fields", [])

    if source_field not in field_names:
        return None

    valid_targets = [t for t in target_fields if t.get("field_name", "") in field_names]
    if not valid_targets:
        return None

    return mapping


# ─── Core Processing (runs WITHOUT collection lock) ────────────────


def generate_fields_for_note(
    note: "Note", mapping: dict, config: dict, overwrite: bool = False
) -> dict:
    """Generate LLM content for a note's target fields.

    This function does NOT modify the note. It returns a dict of
    {field_name: generated_text} to be applied later inside a CollectionOp.

    Runs outside the collection lock so slow LLM calls don't block Anki.

    Returns:
        Dict of {field_name: generated_text} for fields that were generated.
    """
    client = get_llm_client(config)
    source_field = mapping["source_field"]
    target_fields = mapping.get("target_fields", [])
    system_prompt = mapping.get("system_prompt", "")

    source_content = note[source_field]
    if not source_content.strip():
        return {}

    note_fields = get_note_fields_dict(note)
    generated = {}

    for target in target_fields:
        field_name = target["field_name"]
        prompt_template = target["prompt_template"]

        should_overwrite = overwrite or target.get("overwrite", False)
        if not should_overwrite and note[field_name].strip():
            continue

        prompt = build_prompt(prompt_template, note_fields)

        try:
            if config.get("api_mode", "ollama") == "openai":
                result = client.generate_openai(prompt, system_prompt)
            else:
                result = client.generate(prompt, system_prompt)
            generated[field_name] = result
        except LLMError:
            pass  # Skip failed fields silently

    return generated


# ─── CollectionOp: Apply generated fields (WITH collection lock) ───


def _apply_and_save_op(col: Collection, note: "Note", generated: dict) -> OpChanges:
    """Apply generated field values to a note and save with undo support."""
    pos = col.add_custom_undo_entry(f"{ADDON_NAME}: Fill fields")
    if generated:
        for field_name, value in generated.items():
            note[field_name] = value
        col.update_note(note)
    return col.merge_undo_entries(pos)


def _apply_and_save_batch_op(
    col: Collection, results: List[tuple]
) -> OpChanges:
    """Apply generated fields to multiple notes and save with undo."""
    count = len(results)
    pos = col.add_custom_undo_entry(f"{ADDON_NAME}: Batch fill {count} notes")
    to_update = []
    for note, generated in results:
        if generated:
            for field_name, value in generated.items():
                note[field_name] = value
            to_update.append(note)
    if to_update:
        col.update_notes(to_update)
    return col.merge_undo_entries(pos)


# ─── Hook Handler: Auto-fill on new card ──────────────────────────


def _run_async_fill(note: "Note", trigger: str):
    """Common async fill: QueryOp (LLM) → CollectionOp (save+undo)."""
    assert mw is not None
    config = get_config()

    mapping = should_process_note(note, config, trigger=trigger)
    if mapping is None:
        return

    def do_llm_call(_col) -> dict:
        return generate_fields_for_note(note, mapping, config)

    def on_llm_done(generated: dict):
        if not generated:
            return
        CollectionOp(
            parent=mw,
            op=lambda col: _apply_and_save_op(col, note, generated),
        ).success(
            lambda out: tooltip("LLM fields filled!", parent=mw),
        ).run_in_background()

    def on_llm_error(exc: Exception):
        tooltip(f"LLM Fill error: {exc}", parent=mw)

    QueryOp(
        parent=mw,
        op=do_llm_call,
        success=on_llm_done,
    ).failure(
        on_llm_error,
    ).without_collection().run_in_background()


def on_note_added(note: "Note"):
    """Hook: add_cards_did_add_note (manual Add Cards dialog)."""
    _run_async_fill(note, trigger="add_cards")


# ─── Hook Handler: Mining (Yomitan / AnkiConnect) ─────────────────


def on_note_will_be_added(
    _col: "Collection", note: "Note", _deck_id
) -> None:
    """Hook: note_will_be_added.

    Fires for ALL note additions including AnkiConnect/Yomitan.
    Since this is synchronous, we schedule async LLM processing
    to run after the note is saved.
    """
    assert mw is not None
    # Schedule on main thread after current operation completes
    mw.taskman.run_on_main(lambda: _run_async_fill(note, trigger="mining"))


# ─── Hook Handler: Live fill on focus lost ─────────────────────────

# We need to track the current editor reference for loadNoteKeepingFocus
_current_editor = None


def set_editor(editor) -> None:
    """Track the current editor instance (set via editor_did_init hook)."""
    global _current_editor
    _current_editor = editor


def clear_editor(editor) -> None:
    """Clear editor reference when editor closes."""
    global _current_editor
    if _current_editor is editor:
        _current_editor = None


def on_focus_lost(changed: bool, note: "Note", field_idx: int) -> bool:
    """Hook handler: editor_did_unfocus_field.

    Called when user tabs out of a field in the editor. If the field is
    a source field in our mappings, trigger async LLM generation.

    Returns changed flag immediately (does not block for LLM).
    """
    assert mw is not None
    config = get_config()

    mapping = should_process_note(note, config, trigger="focus_lost")
    if mapping is None:
        return changed

    # Only trigger if the unfocused field is the source field
    source_field = mapping.get("source_field", "")
    try:
        field_names = note.keys()
        unfocused_field = field_names[field_idx]
    except (IndexError, KeyError):
        return changed

    if unfocused_field != source_field:
        return changed

    # Don't trigger if source is empty
    if not note[source_field].strip():
        return changed

    # Check if at least one target field needs filling
    target_fields = mapping.get("target_fields", [])
    has_empty = False
    for target in target_fields:
        fname = target.get("field_name", "")
        if fname in field_names:
            should_overwrite = target.get("overwrite", False)
            if should_overwrite or not note[fname].strip():
                has_empty = True
                break

    if not has_empty:
        return changed

    # Async LLM call: two-phase approach
    editor_ref = _current_editor

    def do_llm(_col) -> dict:
        return generate_fields_for_note(note, mapping, config)

    def on_done(generated: dict):
        if not generated:
            return

        def save_op(col: Collection) -> OpChanges:
            return _apply_and_save_op(col, note, generated)

        def on_saved(out):
            tooltip("LLM fields filled!", parent=mw)
            # Reload the editor to show updated fields
            if editor_ref and hasattr(editor_ref, 'loadNoteKeepingFocus'):
                try:
                    editor_ref.loadNoteKeepingFocus()
                except Exception:
                    pass

        CollectionOp(parent=mw, op=save_op).success(on_saved).run_in_background()

    QueryOp(
        parent=mw,
        op=do_llm,
        success=on_done,
    ).failure(
        lambda exc: tooltip(f"LLM Fill error: {exc}", parent=mw),
    ).without_collection().run_in_background()

    return changed


# ─── Batch Fill ────────────────────────────────────────────────────


def run_batch_fill(parent=None, overwrite: bool = False):
    """Find notes with empty target fields and fill via LLM.

    Two-phase approach:
    1. QueryOp: Process all notes (LLM calls, no lock)
    2. CollectionOp: Save all results (with lock + undo)
    """
    assert mw is not None

    config = get_config()
    notes_and_mappings = find_notes_with_empty_targets(config)
    _parent = parent or mw

    if not notes_and_mappings:
        showInfo(
            "No notes found with empty target fields.\n\n"
            "Make sure you have:\n"
            "1. Configured field mappings in Settings\n"
            "2. Notes with non-empty source fields and empty target fields",
            parent=_parent,
        )
        return

    count = len(notes_and_mappings)
    tooltip(f"Starting LLM batch fill for {count} note(s)...", parent=_parent)

    def do_batch_llm(_col) -> List[tuple]:
        """Phase 1: Generate all fields via LLM (no collection lock)."""
        results = []
        for note, mapping in notes_and_mappings:
            generated = generate_fields_for_note(note, mapping, config, overwrite=overwrite)
            results.append((note, generated))
        return results

    def on_batch_done(results: List[tuple]):
        """Phase 2: Save all results with undo."""
        filled = sum(1 for _, g in results if g)
        if not filled:
            showInfo("No fields were generated.", parent=_parent)
            return

        CollectionOp(
            parent=_parent,
            op=lambda col: _apply_and_save_batch_op(col, results),
        ).success(
            lambda out: showInfo(
                f"Batch fill complete!\n\n"
                f"Notes processed: {len(results)}\n"
                f"Notes filled: {filled}",
                parent=_parent,
            ),
        ).run_in_background()

    def on_batch_error(exc: Exception):
        showInfo(f"Batch fill failed:\n{exc}", parent=_parent)

    QueryOp(
        parent=_parent,
        op=do_batch_llm,
        success=on_batch_done,
    ).failure(
        on_batch_error,
    ).without_collection().run_in_background()


# ─── Note Discovery ───────────────────────────────────────────────


def find_notes_with_empty_targets(
    config: dict, deck_id: Optional[int] = None
) -> List[tuple]:
    """Find notes with empty target fields and matching mappings."""
    assert mw is not None
    mappings = config.get("note_type_mappings", {})
    if not mappings:
        return []

    results = []

    for note_type_name, mapping in mappings.items():
        source_field = mapping.get("source_field", "")
        target_fields = mapping.get("target_fields", [])

        if not source_field or not target_fields:
            continue

        for target in target_fields:
            field_name = target.get("field_name", "")
            if not field_name:
                continue

            query = f'"note:{note_type_name}" "{field_name}:"'
            if deck_id is not None:
                deck = mw.col.decks.get(deck_id)
                if deck:
                    query = f'"deck:{deck["name"]}" {query}'

            try:
                note_ids = mw.col.find_notes(query)
            except Exception:
                continue

            for nid in note_ids:
                try:
                    note = mw.col.get_note(nid)
                    if note[source_field].strip():
                        results.append((note, mapping))
                except Exception:
                    continue

    # Deduplicate by note id
    seen_ids: set = set()
    unique_results = []
    for note, mapping in results:
        if note.id not in seen_ids:
            seen_ids.add(note.id)
            unique_results.append((note, mapping))

    return unique_results
