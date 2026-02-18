# Anki LLM Field Generator
# Settings dialog — QDialog-based settings with field mapping

from typing import TYPE_CHECKING, Optional

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
)
from aqt.utils import restoreGeom, saveGeom, tooltip, showInfo

if TYPE_CHECKING:
    from aqt.main import AnkiQt


class SettingsDialog(QDialog):
    """Main settings dialog for LLM Field Generator."""

    def __init__(self, mw: "AnkiQt", parent=None):
        super().__init__(parent or mw)
        self.mw = mw
        self._package = __name__.split(".")[0]
        self.config = self.mw.addonManager.getConfig(self._package) or {}

        self.setWindowTitle("LLM Field Generator — Settings")
        self.setMinimumSize(600, 500)

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
        group = QGroupBox("Ollama Connection")
        form = QFormLayout()
        group.setLayout(form)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("http://localhost:11434")
        form.addRow("Base URL:", self.base_url_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("(optional, for OpenAI-compatible APIs)")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API Key:", self.api_key_edit)

        # Model selection
        model_layout = QHBoxLayout()
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("llama3.2")
        model_layout.addWidget(self.model_edit)

        self.refresh_models_btn = QPushButton("Refresh")
        self.refresh_models_btn.setFixedWidth(80)
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        model_layout.addWidget(self.refresh_models_btn)

        form.addRow("Model:", model_layout)

        # Model list (loaded from Ollama)
        self.model_combo = QComboBox()
        self.model_combo.addItem("(click Refresh to load models)")
        self.model_combo.currentTextChanged.connect(self._on_model_selected)
        form.addRow("Available Models:", self.model_combo)

        self.api_mode_combo = QComboBox()
        self.api_mode_combo.addItems(["ollama", "openai"])
        form.addRow("API Mode:", self.api_mode_combo)

        layout.addWidget(group)

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
            "source_field": fields[0],
            "system_prompt": "You are a helpful assistant that generates Anki flashcard content.",
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

        # Source field
        source_combo = QComboBox()
        source_combo.addItems(fields)
        current_source = mapping.get("source_field", "")
        if current_source in fields:
            source_combo.setCurrentText(current_source)
        source_combo.setProperty("mapping_key", "source_field")
        source_combo.setProperty("note_type", note_type_name)
        source_combo.currentTextChanged.connect(
            lambda text: self._update_mapping_value(note_type_name, "source_field", text)
        )
        form.addRow("Source Field (input):", source_combo)

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

        group = QGroupBox("Auto-Fill Behavior")
        form = QFormLayout()
        group.setLayout(form)

        self.auto_fill_cb = QCheckBox("Automatically fill fields when a new card is added")
        form.addRow(self.auto_fill_cb)

        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 10000)
        self.delay_spin.setSuffix(" ms")
        self.delay_spin.setSingleStep(100)
        form.addRow("Delay between batch requests:", self.delay_spin)

        layout.addWidget(group)
        layout.addStretch()

        self.tabs.addTab(tab, "Behavior")

    # ─── Load / Save ──────────────────────────────────────────────

    def _load_config(self):
        c = self.config
        self.base_url_edit.setText(c.get("api_base_url", "http://localhost:11434"))
        self.api_key_edit.setText(c.get("api_key", ""))
        self.model_edit.setText(c.get("model", "llama3.2"))
        self.api_mode_combo.setCurrentText(c.get("api_mode", "ollama"))
        self.temperature_spin.setValue(c.get("temperature", 0.7))
        self.max_tokens_spin.setValue(c.get("max_tokens", 500))
        self.timeout_spin.setValue(c.get("timeout", 60))
        self.auto_fill_cb.setChecked(c.get("auto_fill_on_new_card", True))
        self.delay_spin.setValue(c.get("delay_between_requests_ms", 500))

        # Load first note type mapping if available
        note_type = self.note_type_combo.currentText()
        if note_type:
            self._load_mapping_ui(note_type)

    def _save_config(self):
        self.config["api_base_url"] = self.base_url_edit.text().strip()
        self.config["api_key"] = self.api_key_edit.text().strip()
        self.config["model"] = self.model_edit.text().strip()
        self.config["api_mode"] = self.api_mode_combo.currentText()
        self.config["temperature"] = self.temperature_spin.value()
        self.config["max_tokens"] = self.max_tokens_spin.value()
        self.config["timeout"] = self.timeout_spin.value()
        self.config["auto_fill_on_new_card"] = self.auto_fill_cb.isChecked()
        self.config["delay_between_requests_ms"] = self.delay_spin.value()

        self.mw.addonManager.writeConfig(self._package, self.config)
        tooltip("Settings saved!", parent=self)
        self.accept()

    # ─── Actions ──────────────────────────────────────────────────

    def _test_connection(self):
        from ..llm_client import LLMClient

        client = LLMClient(
            base_url=self.base_url_edit.text().strip() or "http://localhost:11434",
            api_key=self.api_key_edit.text().strip(),
        )
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")

        if client.test_connection():
            models = client.list_models()
            model_list = ", ".join(models[:5]) if models else "(none found)"
            showInfo(
                f"Connection successful!\n\nAvailable models: {model_list}",
                parent=self,
            )
            self._populate_model_combo(models)
        else:
            showInfo(
                "Connection failed!\n\n"
                "Make sure Ollama is running:\n"
                "  ollama serve\n\n"
                f"URL: {self.base_url_edit.text()}",
                parent=self,
            )

        self.test_btn.setEnabled(True)
        self.test_btn.setText("Test Connection")

    def _refresh_models(self):
        from ..llm_client import LLMClient

        client = LLMClient(
            base_url=self.base_url_edit.text().strip() or "http://localhost:11434",
            api_key=self.api_key_edit.text().strip(),
        )
        models = client.list_models()
        if models:
            self._populate_model_combo(models)
            tooltip(f"Found {len(models)} model(s)", parent=self)
        else:
            tooltip("No models found. Is Ollama running?", parent=self)

    def _populate_model_combo(self, models: list):
        self.model_combo.clear()
        if models:
            for m in models:
                self.model_combo.addItem(m)
        else:
            self.model_combo.addItem("(no models available)")

    def _on_model_selected(self, text: str):
        if text and not text.startswith("("):
            self.model_edit.setText(text)

    # ─── Lifecycle ────────────────────────────────────────────────

    def _on_close(self):
        saveGeom(self, "llmFieldGenSettings")
        self._teardown_hooks()

    def reject(self):
        self._on_close()
        super().reject()

    def accept(self):
        self._on_close()
        super().accept()
