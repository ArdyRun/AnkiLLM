# Anki LLM Field Generator
#
# Automatically fill Anki card fields using LLM (Ollama / OpenAI-compatible).
# Detects new cards and generates content based on configurable prompt templates.
#
# Architecture inspired by AJT Japanese addon:
# - Modular init() pattern
# - CollectionOp for undo-safe operations
# - Hook-based triggers (note added, focus lost, editor toolbar)

from typing import TYPE_CHECKING

from aqt import mw, gui_hooks
from aqt.qt import QAction
from aqt.gui_hooks import add_cards_did_add_note

from ._version import __version__  # noqa: F401

if TYPE_CHECKING:
    assert mw is not None
    from anki.notes import Note
    from aqt.editor import Editor


# ─── Hook: Auto-fill on new card (Add Cards dialog) ──────────────

def _on_note_added(note: "Note"):
    """Hook handler for add_cards_did_add_note."""
    from .card_processor import on_note_added
    on_note_added(note)


add_cards_did_add_note.append(_on_note_added)


# ─── Hook: Mining (Yomitan / AnkiConnect) ─────────────────────────

import anki.hooks

def _on_note_will_be_added(_col, note: "Note", _deck_id):
    """Hook: note_will_be_added — fires for ALL note additions."""
    from .card_processor import on_note_will_be_added
    on_note_will_be_added(_col, note, _deck_id)


anki.hooks.note_will_be_added.append(_on_note_will_be_added)


# ─── Hook: Live fill on focus lost ────────────────────────────────

def _on_focus_lost(changed: bool, note: "Note", field_idx: int) -> bool:
    """Hook handler for editor_did_unfocus_field."""
    from .card_processor import on_focus_lost
    return on_focus_lost(changed, note, field_idx)


def _on_editor_init(editor: "Editor"):
    """Track current editor for field reload after LLM fill."""
    from .card_processor import set_editor
    set_editor(editor)


gui_hooks.editor_did_unfocus_field.append(_on_focus_lost)
gui_hooks.editor_did_load_note.append(lambda editor: _on_editor_init(editor))


# ─── Browser Menu: Bulk Fill Selected Notes ───────────────────────

from .bulk_add import init as _init_bulk_add
_init_bulk_add()


# ─── Editor Toolbar Buttons ───────────────────────────────────────

from .editor_toolbar import init as _init_toolbar
_init_toolbar()


# ─── Menu: Settings Dialog ────────────────────────────────────────

def _open_settings():
    """Open the LLM Field Generator settings dialog."""
    from .gui.settings_dialog import SettingsDialog
    dialog = SettingsDialog(mw)
    dialog.exec()


# ─── Menu: Batch Fill ──────────────────────────────────────────────

def _batch_fill():
    """Batch fill empty target fields using LLM (CollectionOp, undo-safe)."""
    from .card_processor import run_batch_fill
    run_batch_fill(parent=mw)


# ─── Register Menu Actions ────────────────────────────────────────

action_settings = QAction("LLM Field Generator Settings", mw)
action_settings.triggered.connect(lambda: _open_settings())
mw.form.menuTools.addAction(action_settings)

action_batch = QAction("LLM Fill Empty Fields", mw)
action_batch.triggered.connect(lambda: _batch_fill())
mw.form.menuTools.addAction(action_batch)

