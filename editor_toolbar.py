# Anki LLM Field Generator
# Editor toolbar buttons for generate/regenerate actions.
#
# Adds toolbar buttons to the Anki card editor:
# - "LLM Fill" — generate empty target fields
# - "LLM Regen" — regenerate all target fields (overwrite)
#
# Pattern adapted from AJT Japanese's editor_toolbar.py:
# - editor_did_init_buttons hook for registration
# - CollectionOp + QueryOp for async undo-safe processing

from typing import TYPE_CHECKING, Callable, NamedTuple, Optional

from anki.collection import Collection, OpChanges
from aqt import mw, gui_hooks
from aqt.editor import Editor
from aqt.operations import CollectionOp, QueryOp
from aqt.utils import tooltip

from .card_processor import (
    ADDON_NAME,
    get_config,
    should_process_note,
    generate_fields_for_note,
)

if TYPE_CHECKING:
    pass


class ToolbarButtonDef(NamedTuple):
    """Definition for a toolbar button."""
    id: str
    label: str
    tip: str
    shortcut: str
    on_press: Callable[[Editor], None]


# ─── Button Actions ───────────────────────────────────────────────


def _carefully_update_note(col: Collection, note) -> OpChanges:
    """Update a note only if it has been saved to the collection."""
    if note.id > 0:
        return col.update_note(note)
    return OpChanges()


def _llm_fill_note(editor: Editor, overwrite: bool = False) -> None:
    """Generate LLM content for the editor's current note.

    Two-phase async:
    1. QueryOp: LLM API call (no collection lock)
    2. CollectionOp: save results + undo
    """
    from .card_processor import _is_processing, reset_processing
    
    # Prevent re-entrancy
    if _is_processing:
        return
    
    note = editor.note
    if note is None:
        return

    assert mw is not None
    config = get_config()
    mapping = should_process_note(note, config, trigger="toolbar")
    if mapping is None:
        tooltip("No field mapping configured for this note type.", parent=editor.widget)
        return

    action = "Regenerate" if overwrite else "Fill"
    tooltip(f"LLM {action}: generating...", parent=editor.widget)

    def do_llm(_col) -> dict:
        return generate_fields_for_note(note, mapping, config, overwrite=overwrite)

    def on_done(generated: dict):
        if not generated:
            tooltip("Nothing to generate (all fields already filled).", parent=editor.widget)
            reset_processing()
            return

        def save_op(col: Collection) -> OpChanges:
            pos = col.add_custom_undo_entry(f"{ADDON_NAME}: {action} fields")
            for field_name, value in generated.items():
                note[field_name] = value
            _carefully_update_note(col, note)
            return col.merge_undo_entries(pos)

        def on_saved(out):
            tooltip(f"LLM {action}: done!", parent=editor.widget)
            # Reload editor to show updated fields
            if editor.currentField is None:
                editor.loadNote(focusTo=0)
            else:
                editor.loadNoteKeepingFocus()
            reset_processing()

        CollectionOp(
            parent=editor.widget,
            op=save_op,
        ).success(on_saved).run_in_background()

    def on_error(exc: Exception):
        tooltip(f"LLM {action} error: {exc}", parent=editor.widget)
        reset_processing()

    QueryOp(
        parent=editor.widget,
        op=do_llm,
        success=on_done,
    ).failure(on_error).without_collection().run_in_background()


# ─── Button Definitions ───────────────────────────────────────────


def _get_buttons() -> list[ToolbarButtonDef]:
    """Return the list of toolbar buttons to add."""
    config = get_config()
    toolbar_cfg = config.get("toolbar_buttons", {})

    buttons = []

    # Fill button (generate empty fields only)
    fill_cfg = toolbar_cfg.get("fill", {})
    if fill_cfg.get("enabled", True):
        buttons.append(ToolbarButtonDef(
            id="llm_fill",
            label=fill_cfg.get("text", "LLM Fill"),
            tip="Generate LLM content for empty fields",
            shortcut=fill_cfg.get("shortcut", ""),
            on_press=lambda editor: _llm_fill_note(editor, overwrite=False),
        ))

    # Regen button (overwrite all fields)
    regen_cfg = toolbar_cfg.get("regenerate", {})
    if regen_cfg.get("enabled", True):
        buttons.append(ToolbarButtonDef(
            id="llm_regen",
            label=regen_cfg.get("text", "LLM Regen"),
            tip="Regenerate all LLM fields (overwrite existing)",
            shortcut=regen_cfg.get("shortcut", ""),
            on_press=lambda editor: _llm_fill_note(editor, overwrite=True),
        ))

    return buttons


# ─── Hook Registration ────────────────────────────────────────────


def add_toolbar_buttons(html_buttons: list[str], editor: Editor) -> None:
    """Add LLM buttons to the editor toolbar."""
    for btn in _get_buttons():
        html_buttons.append(
            editor.addButton(
                icon=None,
                cmd=f"llm__{btn.id}",
                func=btn.on_press,
                tip=f"{btn.tip} ({btn.shortcut})" if btn.shortcut else btn.tip,
                keys=btn.shortcut or None,
                label=btn.label,
            )
        )


def init() -> None:
    """Register toolbar button hook."""
    gui_hooks.editor_did_init_buttons.append(add_toolbar_buttons)
