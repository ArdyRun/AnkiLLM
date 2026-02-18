# Anki LLM Field Generator
# Browser bulk-generate menu integration.
#
# Adds "LLM Fill Selected Notes" to the Browser's Edit menu.
# Shows a progress dialog during LLM processing.

from typing import TYPE_CHECKING, Sequence, List

from anki.collection import Collection, OpChanges
from aqt import mw, gui_hooks
from aqt.operations import CollectionOp
from aqt.qt import QAction, QThread, pyqtSignal, qconnect, QProgressDialog
from aqt.utils import showInfo, tooltip

from .card_processor import (
    ADDON_NAME,
    get_config,
    should_process_note,
    generate_fields_for_note,
)

if TYPE_CHECKING:
    from anki.notes import Note, NoteId
    from aqt.browser import Browser

ACTION_NAME = f"{ADDON_NAME}: Fill selected notes"


# ─── Background Worker with Progress ──────────────────────────────


class BulkLLMWorker(QThread):
    """Background thread for batch LLM processing with progress signals."""

    tick = pyqtSignal(int, int, str)       # (current, total, status_text)
    finished_ok = pyqtSignal(list)         # list of (note, generated_dict)
    finished_err = pyqtSignal(str)         # error message

    def __init__(self, notes_and_mappings: list, config: dict, **kwargs):
        super().__init__(**kwargs)
        self._notes_and_mappings = notes_and_mappings
        self._config = config
        self._cancel = False

    def run(self):
        try:
            results = []
            total = len(self._notes_and_mappings)

            for i, (note, mapping) in enumerate(self._notes_and_mappings):
                if self._cancel:
                    self.tick.emit(i, total, "Cancelled.")
                    return

                source = note[mapping["source_field"]]
                # Truncate long source text for display
                preview = source[:30] + "..." if len(source) > 30 else source
                self.tick.emit(i, total, f"[{i+1}/{total}] Generating: {preview}")

                generated = generate_fields_for_note(
                    note, mapping, self._config
                )
                results.append((note, generated))

            self.finished_ok.emit(results)
        except Exception as e:
            self.finished_err.emit(str(e))

    def cancel(self):
        self._cancel = True


# ─── Main Entry Point ─────────────────────────────────────────────


def _fill_selected_notes(nids: Sequence["NoteId"], parent: "Browser") -> None:
    """Process selected notes in Browser with progress dialog."""
    assert mw is not None
    config = get_config()

    if not nids:
        tooltip("No notes selected.", parent=parent)
        return

    # Collect notes with valid mappings
    notes_and_mappings = []
    for nid in nids:
        try:
            note = mw.col.get_note(nid)
            mapping = should_process_note(note, config, trigger="browse")
            if mapping is not None:
                notes_and_mappings.append((note, mapping))
        except Exception:
            continue

    if not notes_and_mappings:
        showInfo(
            "No selected notes match configured field mappings.\n\n"
            "Make sure you have:\n"
            "1. Configured field mappings in Settings\n"
            "2. Selected notes with the right note type",
            parent=parent,
        )
        return

    count = len(notes_and_mappings)

    # ── Create progress dialog ──
    progress = QProgressDialog(
        f"Processing 0/{count} notes with LLM...",
        "Cancel",
        0,
        count,
        mw,  # parent=mw so it survives browser close
    )
    progress.setWindowTitle(f"{ADDON_NAME} — Bulk Fill")
    progress.setMinimumDuration(0)  # show immediately
    progress.setValue(0)

    # ── Create worker thread ──
    worker = BulkLLMWorker(notes_and_mappings, config)

    def on_tick(current, total, status):
        if progress.wasCanceled():
            worker.cancel()
            return
        progress.setValue(current)
        progress.setLabelText(status)

    def on_done(results: list):
        progress.close()
        filled = sum(1 for _, g in results if g)

        if not filled:
            showInfo("LLM returned no content for any note.", parent=mw)
            worker.deleteLater()
            return

        # Phase 2: Save with undo via CollectionOp
        def save_op(col: Collection) -> OpChanges:
            pos = col.add_custom_undo_entry(
                f"{ADDON_NAME}: Fill {filled} of {count} selected notes"
            )
            to_update = []
            for note, generated in results:
                if generated:
                    for field_name, value in generated.items():
                        note[field_name] = value
                    to_update.append(note)
            if to_update:
                col.update_notes(to_update)
            return col.merge_undo_entries(pos)

        CollectionOp(
            parent=mw,
            op=save_op,
        ).success(
            lambda out: showInfo(
                f"Bulk fill complete!\n\n"
                f"Selected: {count}\n"
                f"Filled: {filled}",
                parent=mw,
            ),
        ).run_in_background()

        worker.deleteLater()

    def on_error(msg: str):
        progress.close()
        showInfo(f"LLM bulk fill failed:\n{msg}", parent=mw)
        worker.deleteLater()

    # Connect signals
    worker.tick.connect(on_tick)
    worker.finished_ok.connect(on_done)
    worker.finished_err.connect(on_error)
    progress.canceled.connect(worker.cancel)

    # Start
    worker.start()


# ─── Browser Menu Registration ─────────────────────────────────────


def setup_browser_menu(browser: "Browser") -> None:
    """Add LLM fill action to Browser's Edit menu."""
    action = QAction(ACTION_NAME, browser)
    qconnect(
        action.triggered,
        lambda: _fill_selected_notes(browser.selectedNotes(), parent=browser),
    )
    browser.form.menuEdit.addAction(action)


def init() -> None:
    """Register the browser menu hook."""
    gui_hooks.browser_menus_did_init.append(setup_browser_menu)
