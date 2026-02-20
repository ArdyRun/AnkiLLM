# Anki LLM Field Generator
# Settings dialog — QDialog-based settings with field mapping

from typing import TYPE_CHECKING, Optional, List

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QCheckBox,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QWidget,
    QScrollArea,
    QMessageBox,
    QSizePolicy,
    Qt,
    QFrame,
    QListWidget,
    QListWidgetItem,
)
from aqt.utils import restoreGeom, saveGeom, tooltip, showInfo

if TYPE_CHECKING:
    from aqt.main import AnkiQt


# ─── Custom Widgets ────────────────────────────────────────────────


class CheckComboBox(QComboBox):
    """ComboBox with checklist functionality for multiple selection.
    
    Displays selected items as comma-separated values.
    Opens a dropdown list with checkboxes when clicked.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_items: List[str] = []
        self._all_items: List[str] = []
        
        # Create popup with list widget
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        
        # Connect item changed signal
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        
        self.setModel(self.list_widget.model())
        self.setView(self.list_widget)
        
        # Prevent popup from closing on item click
        self.installEventFilter(self)
    
    def eventFilter(self, obj, event):
        """Prevent popup from closing when clicking items."""
        from aqt.qt import QEvent, QMouseEvent
        if event.type() == QEvent.Type.MouseButtonPress:
            # Don't close on mouse press
            pass
        elif event.type() == QEvent.Type.Wheel:
            # Disable mouse wheel scrolling
            return True
        return super().eventFilter(obj, event)
    
    def _on_item_clicked(self, item: QListWidgetItem):
        """Toggle item selection when clicked."""
        row = self.list_widget.row(item)
        widget = self.list_widget.itemWidget(item)
        
        if widget and isinstance(widget, QCheckBox):
            widget.setChecked(not widget.isChecked())
            self._update_selected()
            self._update_display_text()
    
    def _update_selected(self):
        """Update the list of selected items."""
        self._selected_items = []
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            widget = self.list_widget.itemWidget(item)
            if widget and isinstance(widget, QCheckBox) and widget.isChecked():
                self._selected_items.append(item.text())
    
    def _update_display_text(self):
        """Update the display text to show selected items."""
        if self._selected_items:
            self.setText(", ".join(self._selected_items))
        else:
            self.setText("(Select fields)")
    
    def setItems(self, items: List[str]):
        """Set the list of available items."""
        self._all_items = items
        self._selected_items = []
        self.clear()
        
        for item_text in items:
            item = QListWidgetItem(item_text)
            checkbox = QCheckBox(item_text)
            checkbox.setChecked(False)
            checkbox.setStyleSheet("background: transparent;")
            
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, checkbox)
            
            # Adjust item height
            item.setSizeHint(checkbox.sizeHint())
        
        self._update_display_text()
    
    def setCheckedItems(self, items: List[str]):
        """Set which items should be checked."""
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            widget = self.list_widget.itemWidget(item)
            if widget and isinstance(widget, QCheckBox):
                is_checked = item.text() in items
                widget.setChecked(is_checked)
        
        self._update_selected()
        self._update_display_text()
    
    def getCheckedItems(self) -> List[str]:
        """Get list of checked items."""
        return self._selected_items.copy()
    
    def showPopup(self):
        """Override to ensure popup shows properly."""
        super().showPopup()
        # Set focus to list widget
        self.list_widget.setFocus()
    
    def hidePopup(self):
        """Override to update display when popup closes."""
        self._update_selected()
        self._update_display_text()
        super().hidePopup()


class SettingsDialog(QDialog):
    """Main settings dialog for LLM Field Generator."""

    def __init__(self, mw: "AnkiQt", parent=None):
        super().__init__(parent or mw)
        self.mw = mw
        self._package = __name__.split(".")[0]
        self.config = self.mw.addonManager.getConfig(self._package) or {}

        self.setWindowTitle("LLM Field Generator — Settings")
        self.setMinimumSize(600, 500)

        # Store settings per API mode
        self._api_settings = {}

        self._setup_ui()
        self._load_config()
        self._setup_hooks()

        restoreGeom(self, "llmFieldGenSettings")

    def _setup_hooks(self):
        from aqt.gui_hooks import profile_will_close
        profile_will_close.append(self.close)

    def _teardown_hooks(self):
        from aqt.gui_hooks import profile_will_close
        try:
            profile_will_close.remove(self.close)
        except ValueError:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: Connection
        self._setup_connection_tab()

        # Tab 2: Note Type Mappings
        self._setup_mappings_tab()

        # Tab 3: Behavior
        self._setup_behavior_tab()

        # Bottom buttons
        btn_layout = QHBoxLayout()

        self.test_btn = QPushButton("Test Connection")
        self.test_btn.clicked.connect(self._test_connection)
        btn_layout.addWidget(self.test_btn)

        btn_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    # ─── Tab 1: Connection ─────────────────────────────────────────

    def _setup_connection_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        # API Settings Group
        self.api_group = QGroupBox("API Connection")
        form = QFormLayout()
        self.api_group.setLayout(form)

        self.api_mode_combo = QComboBox()
        self.api_mode_combo.addItems(["ollama", "groq", "gemini", "openrouter"])
        self.api_mode_combo.currentTextChanged.connect(self._on_api_mode_changed)
        form.addRow("API Mode:", self.api_mode_combo)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("http://localhost:11434")
        form.addRow("Base URL:", self.base_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("(required for Groq, Gemini, OpenRouter)")
        # Show API key as plain text (not masked) so user can verify it
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        form.addRow("API Key:", self.api_key_edit)

        # Model input (user types manually)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("llama3.2")
        self.model_edit.setToolTip(
            "Enter model name manually.\n\n"
            "Examples:\n"
            "Ollama: llama3.2, mistral\n"
            "Groq: llama-3.3-70b-versatile, mixtral-8x7b-32768\n"
            "Gemini: gemini-2.0-flash, gemini-1.5-pro\n"
            "OpenRouter: anthropic/claude-3.5-sonnet, meta-llama/llama-3-70b-instruct"
        )
        form.addRow("Model:", self.model_edit)

        layout.addWidget(self.api_group)

        # Generation Settings
        gen_group = QGroupBox("Generation Settings")
        gen_form = QFormLayout()
        gen_group.setLayout(gen_form)

        self.temperature_spin = QDoubleSpinBox()
        self.temperature_spin.setRange(0.0, 2.0)
        self.temperature_spin.setSingleStep(0.1)
        self.temperature_spin.setDecimals(1)
        gen_form.addRow("Temperature:", self.temperature_spin)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(50, 4096)
        self.max_tokens_spin.setSingleStep(50)
        gen_form.addRow("Max Tokens:", self.max_tokens_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setSuffix(" seconds")
        gen_form.addRow("Timeout:", self.timeout_spin)

        layout.addWidget(gen_group)
        layout.addStretch()

        self.tabs.addTab(tab, "Connection")

    # ─── Tab 2: Mappings ───────────────────────────────────────────

    def _setup_mappings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        # Note type selector
        top_layout = QHBoxLayout()

        top_layout.addWidget(QLabel("Note Type:"))
        self.note_type_combo = QComboBox()
        self.note_type_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._populate_note_types()
        self.note_type_combo.currentTextChanged.connect(self._on_note_type_changed)
        top_layout.addWidget(self.note_type_combo)

        self.add_mapping_btn = QPushButton("Add Mapping")
        self.add_mapping_btn.clicked.connect(self._add_mapping_for_current_type)
        top_layout.addWidget(self.add_mapping_btn)

        layout.addLayout(top_layout)

        # Scroll area for mapping details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.mapping_container = QWidget()
        self.mapping_layout = QVBoxLayout()
        self.mapping_container.setLayout(self.mapping_layout)
        scroll.setWidget(self.mapping_container)
        layout.addWidget(scroll)

        self.tabs.addTab(tab, "Field Mappings")

    def _populate_note_types(self):
        self.note_type_combo.clear()
        models = self.mw.col.models.all()
        for model in models:
            self.note_type_combo.addItem(model["name"])

    def _get_fields_for_note_type(self, note_type_name: str) -> list:
        models = self.mw.col.models.all()
        for model in models:
            if model["name"] == note_type_name:
                return [f["name"] for f in model["flds"]]
        return []

    def _on_note_type_changed(self, note_type_name: str):
        self._load_mapping_ui(note_type_name)

    def _add_mapping_for_current_type(self):
        note_type_name = self.note_type_combo.currentText()
        if not note_type_name:
            return

        mappings = self.config.setdefault("note_type_mappings", {})
        if note_type_name in mappings:
            showInfo(f"Mapping for '{note_type_name}' already exists.")
            return

        fields = self._get_fields_for_note_type(note_type_name)
        if len(fields) < 2:
            showInfo("Note type needs at least 2 fields.")
            return

        mappings[note_type_name] = {
            "source_fields": [fields[0]],  # New format: array of source fields
            "system_prompt": "You are a helpful assistant that generates Anki flashcard content.",
            "triggered_by": ["mining", "add_cards", "browse", "focus_lost", "toolbar"],
            "target_fields": [
                {
                    "field_name": fields[1] if len(fields) > 1 else fields[0],
                    "prompt_template": f"Generate content for the field based on: {{{{{fields[0]}}}}}",
                    "overwrite": False,
                }
            ],
        }
        self._load_mapping_ui(note_type_name)

    def _load_mapping_ui(self, note_type_name: str):
        # Clear existing UI
        while self.mapping_layout.count():
            item = self.mapping_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        mappings = self.config.get("note_type_mappings", {})
        if note_type_name not in mappings:
            label = QLabel(
                'No mapping configured for this note type.\nClick "Add Mapping" to create one.'
            )
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.mapping_layout.addWidget(label)
            self.mapping_layout.addStretch()
            return

        mapping = mappings[note_type_name]
        fields = self._get_fields_for_note_type(note_type_name)

        # Mapping config group
        group = QGroupBox(f"Mapping: {note_type_name}")
        form = QFormLayout()
        group.setLayout(form)

        # Source fields (multiple selection with CheckComboBox)
        source_combo = CheckComboBox()
        source_combo.setItems(fields)
        
        # Support both old (source_field) and new (source_fields) format
        current_source = mapping.get("source_field", "")
        current_sources = mapping.get("source_fields", [])
        
        # Convert old format to new format for backward compatibility
        if current_source and not current_sources:
            current_sources = [current_source]
        
        source_combo.setCheckedItems(current_sources)
        source_combo.setToolTip("Select one or more source fields. Hold Ctrl to select multiple.")
        source_combo.currentTextChanged.connect(
            lambda: self._update_source_fields(note_type_name, source_combo.getCheckedItems())
        )
        form.addRow("Source Fields (input):", source_combo)

        # System prompt
        system_prompt_edit = QPlainTextEdit()
        system_prompt_edit.setMaximumHeight(80)
        system_prompt_edit.setPlainText(mapping.get("system_prompt", ""))
        system_prompt_edit.textChanged.connect(
            lambda: self._update_mapping_value(
                note_type_name, "system_prompt", system_prompt_edit.toPlainText()
            )
        )
        form.addRow("System Prompt:", system_prompt_edit)

        # Trigger checkboxes
        trigger_group = QGroupBox("Active Triggers")
        trigger_layout = QHBoxLayout()
        trigger_group.setLayout(trigger_layout)

        current_triggers = mapping.get("triggered_by", ["mining", "add_cards", "browse", "focus_lost", "toolbar"])

        trigger_defs = [
            ("mining", "Mining (Yomitan)"),
            ("add_cards", "Add Cards"),
            ("browse", "Browse"),
            ("focus_lost", "Focus Lost"),
            ("toolbar", "Toolbar"),
        ]

        self._trigger_checkboxes = {}
        for trigger_id, trigger_label in trigger_defs:
            cb = QCheckBox(trigger_label)
            cb.setChecked(trigger_id in current_triggers)
            cb.toggled.connect(
                lambda checked, tid=trigger_id: self._update_triggers(note_type_name, tid, checked)
            )
            trigger_layout.addWidget(cb)
            self._trigger_checkboxes[trigger_id] = cb

        form.addRow(trigger_group)

        self.mapping_layout.addWidget(group)

        # Target fields
        target_fields = mapping.get("target_fields", [])
        for idx, target in enumerate(target_fields):
            tgroup = QGroupBox(f"Target Field {idx + 1}")
            tform = QFormLayout()
            tgroup.setLayout(tform)

            # Target field selector
            target_combo = QComboBox()
            target_combo.addItems(fields)
            tf_name = target.get("field_name", "")
            if tf_name in fields:
                target_combo.setCurrentText(tf_name)
            target_combo.currentTextChanged.connect(
                lambda text, i=idx: self._update_target_field(
                    note_type_name, i, "field_name", text
                )
            )
            tform.addRow("Field:", target_combo)

            # Prompt template
            prompt_edit = QPlainTextEdit()
            prompt_edit.setMaximumHeight(120)
            prompt_edit.setPlainText(target.get("prompt_template", ""))
            prompt_edit.setPlaceholderText(
                "Use {{FieldName}} to reference note fields.\n"
                "Example: Define the word '{{Front}}' with examples."
            )
            prompt_edit.textChanged.connect(
                lambda te=prompt_edit, i=idx: self._update_target_field(
                    note_type_name, i, "prompt_template", te.toPlainText()
                )
            )
            tform.addRow("Prompt Template:", prompt_edit)

            # Overwrite checkbox
            overwrite_cb = QCheckBox("Overwrite existing content")
            overwrite_cb.setChecked(target.get("overwrite", False))
            overwrite_cb.toggled.connect(
                lambda checked, i=idx: self._update_target_field(
                    note_type_name, i, "overwrite", checked
                )
            )
            tform.addRow("", overwrite_cb)

            # Remove button
            remove_btn = QPushButton("Remove Target Field")
            remove_btn.clicked.connect(
                lambda _, i=idx: self._remove_target_field(note_type_name, i)
            )
            tform.addRow("", remove_btn)

            self.mapping_layout.addWidget(tgroup)

        # Add target field button
        add_target_btn = QPushButton("+ Add Target Field")
        add_target_btn.clicked.connect(
            lambda: self._add_target_field(note_type_name)
        )
        self.mapping_layout.addWidget(add_target_btn)

        # Delete mapping button
        delete_btn = QPushButton("Delete Entire Mapping")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(
            lambda: self._delete_mapping(note_type_name)
        )
        self.mapping_layout.addWidget(delete_btn)

        self.mapping_layout.addStretch()

    def _update_mapping_value(self, note_type_name: str, key: str, value):
        mappings = self.config.setdefault("note_type_mappings", {})
        if note_type_name in mappings:
            mappings[note_type_name][key] = value

    def _update_source_fields(self, note_type_name: str, fields: List[str]):
        """Update source_fields array in mapping config."""
        mappings = self.config.setdefault("note_type_mappings", {})
        if note_type_name in mappings:
            # Store as array (new format)
            mappings[note_type_name]["source_fields"] = fields
            # Remove old format key if exists
            if "source_field" in mappings[note_type_name]:
                del mappings[note_type_name]["source_field"]

    def _update_triggers(self, note_type_name: str, trigger_id: str, enabled: bool):
        mappings = self.config.get("note_type_mappings", {})
        if note_type_name not in mappings:
            return
        triggers = mappings[note_type_name].setdefault(
            "triggered_by", ["mining", "add_cards", "browse", "focus_lost", "toolbar"]
        )
        if enabled and trigger_id not in triggers:
            triggers.append(trigger_id)
        elif not enabled and trigger_id in triggers:
            triggers.remove(trigger_id)

    def _update_target_field(self, note_type_name: str, idx: int, key: str, value):
        mappings = self.config.get("note_type_mappings", {})
        if note_type_name in mappings:
            targets = mappings[note_type_name].get("target_fields", [])
            if idx < len(targets):
                targets[idx][key] = value

    def _add_target_field(self, note_type_name: str):
        mappings = self.config.get("note_type_mappings", {})
        if note_type_name not in mappings:
            return

        fields = self._get_fields_for_note_type(note_type_name)
        mappings[note_type_name].setdefault("target_fields", []).append(
            {
                "field_name": fields[0] if fields else "",
                "prompt_template": "",
                "overwrite": False,
            }
        )
        self._load_mapping_ui(note_type_name)

    def _remove_target_field(self, note_type_name: str, idx: int):
        mappings = self.config.get("note_type_mappings", {})
        if note_type_name in mappings:
            targets = mappings[note_type_name].get("target_fields", [])
            if idx < len(targets):
                targets.pop(idx)
                self._load_mapping_ui(note_type_name)

    def _delete_mapping(self, note_type_name: str):
        reply = QMessageBox.question(
            self,
            "Delete Mapping",
            f"Delete the entire mapping for '{note_type_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config.get("note_type_mappings", {}).pop(note_type_name, None)
            self._load_mapping_ui(note_type_name)

    # ─── Tab 3: Behavior ──────────────────────────────────────────

    def _setup_behavior_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        tab.setLayout(layout)

        group = QGroupBox("Batch Behavior")
        form = QFormLayout()
        group.setLayout(form)

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 10000)
        self.delay_spin.setSuffix(" ms")
        self.delay_spin.setSingleStep(100)
        form.addRow("Delay between batch requests:", self.delay_spin)

        layout.addWidget(group)

        info_label = QLabel(
            "Trigger control is now per-mapping.\n"
            "Go to Field Mappings tab to enable/disable triggers\n"
            "(Mining, Add Cards, Browse, Focus Lost, Toolbar)"
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        layout.addStretch()

        self.tabs.addTab(tab, "Behavior")

    # ─── Load / Save ──────────────────────────────────────────────

    def _load_config(self):
        c = self.config
        api_mode = c.get("api_mode", "ollama")
        
        # Initialize API settings storage with current config
        self._api_settings[api_mode] = {
            "base_url": c.get("api_base_url", "http://localhost:11434"),
            "api_key": c.get("api_key", ""),
            "model": c.get("model", "llama3.2"),
        }
        
        self.api_mode_combo.setCurrentText(api_mode)
        self.base_url_edit.setText(c.get("api_base_url", "http://localhost:11434"))
        self.api_key_edit.setText(c.get("api_key", ""))
        self.model_edit.setText(c.get("model", "llama3.2"))
        self.temperature_spin.setValue(c.get("temperature", 0.7))
        self.max_tokens_spin.setValue(c.get("max_tokens", 500))
        self.timeout_spin.setValue(c.get("timeout", 60))
        self.delay_spin.setValue(c.get("delay_between_requests_ms", 500))

        # Trigger UI update based on API mode
        self._on_api_mode_changed(api_mode)

        # Load first note type mapping if available
        note_type = self.note_type_combo.currentText()
        if note_type:
            self._load_mapping_ui(note_type)

    def _save_config(self):
        """Save config and close dialog. Called by Save button."""
        self._save_all_settings()
        self.accept()

    # ─── Actions ──────────────────────────────────────────────────

    def _on_api_mode_changed(self, api_mode: str):
        """Update UI based on selected API mode and save/load settings."""
        # Save current settings before switching
        current_mode = self.api_mode_combo.currentText()
        if current_mode and hasattr(self, '_api_settings'):
            self._save_current_api_settings()
        
        # Update group title
        self.api_group.setTitle(f"{api_mode.capitalize()} Connection")
        
        # Load saved settings for this API mode, or use defaults
        saved = self._api_settings.get(api_mode, {})
        
        if api_mode == "ollama":
            self.base_url_edit.setEnabled(True)
            self.base_url_edit.setText(saved.get("base_url", "http://localhost:11434"))
            self.base_url_edit.setPlaceholderText("http://localhost:11434")
            self.model_edit.setText(saved.get("model", "llama3.2"))
            self.model_edit.setPlaceholderText("llama3.2")
            self.api_key_edit.setText(saved.get("api_key", ""))
        else:
            self.base_url_edit.setEnabled(False)
            self.base_url_edit.clear()
            self.api_key_edit.setText(saved.get("api_key", ""))
            self.model_edit.setText(saved.get("model", ""))
            if api_mode == "groq":
                self.model_edit.setPlaceholderText("llama-3.3-70b-versatile")
            elif api_mode == "gemini":
                self.model_edit.setPlaceholderText("gemini-2.0-flash")
            elif api_mode == "openrouter":
                self.model_edit.setPlaceholderText("anthropic/claude-3.5-sonnet")
    
    def _save_current_api_settings(self):
        """Save current API settings to memory."""
        current_mode = self.api_mode_combo.currentText()
        if not current_mode:
            return
        
        self._api_settings[current_mode] = {
            "base_url": self.base_url_edit.text().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "model": self.model_edit.text().strip(),
        }

    def _test_connection(self):
        from ..llm_client import LLMClient

        api_mode = self.api_mode_combo.currentText()
        base_url = self.base_url_edit.text().strip()
        
        # Set default base URL for Ollama
        if api_mode == "ollama":
            base_url = base_url or "http://localhost:11434"
        
        client = LLMClient(
            base_url=base_url,
            api_key=self.api_key_edit.text().strip(),
            api_mode=api_mode,
            model=self.model_edit.text().strip() or "llama3.2",
        )
        
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")
        
        # Run test in background to avoid UI freeze
        from aqt.operations import QueryOp
        from aqt import mw
        
        def do_test(_col) -> tuple:
            return client.test_connection()
        
        def on_done(result: tuple):
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Test Connection")
            
            success, message = result
            if success:
                showInfo(
                    f"✓ Connection Successful!\n\n{message}",
                    parent=self,
                )
            else:
                showInfo(
                    f"✗ Connection Failed\n\n{message}",
                    parent=self,
                )
        
        def on_error(exc: Exception):
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Test Connection")
            showInfo(
                f"✗ Test Error\n\n{str(exc)}",
                parent=self,
            )
        
        QueryOp(
            parent=self,
            op=do_test,
            success=on_done,
        ).failure(on_error).without_collection().run_in_background()

    # ─── Lifecycle ────────────────────────────────────────────────

    def _on_close(self):
        """Cleanup hooks and save window geometry."""
        saveGeom(self, "llmFieldGenSettings")
        self._teardown_hooks()

    def _save_all_settings(self):
        """Save all settings to config file. Only called on explicit Save."""
        # Save current API settings
        self._save_current_api_settings()
        
        # Get the currently selected API mode's settings
        api_mode = self.api_mode_combo.currentText()
        saved = self._api_settings.get(api_mode, {})
        
        self.config["api_base_url"] = saved.get("base_url", "")
        self.config["api_key"] = saved.get("api_key", "")
        self.config["model"] = saved.get("model", "")
        self.config["api_mode"] = api_mode
        self.config["temperature"] = self.temperature_spin.value()
        self.config["max_tokens"] = self.max_tokens_spin.value()
        self.config["timeout"] = self.timeout_spin.value()
        self.config["delay_between_requests_ms"] = self.delay_spin.value()
        
        # Write to config file
        self.mw.addonManager.writeConfig(self._package, self.config)

    def reject(self):
        """Called when user clicks Cancel. Don't save config."""
        self._on_close()
        super().reject()

    def accept(self):
        """Called when user clicks Save. Save config and close."""
        self._save_all_settings()
        tooltip("Settings saved!", parent=self)
        self._on_close()
        super().accept()
