**LLM Field Generator** supports the following config values:

**api_base_url** [string]: Base URL for the LLM API. Default: `http://localhost:11434` (Ollama).

**api_key** [string]: API key for authentication. Leave empty for Ollama (no auth needed). Required for OpenAI and similar services.

**model** [string]: Name of the LLM model to use. For Ollama, use model names like `llama3.2`, `mistral`, `gemma2`. Default: `llama3.2`.

**api_mode** [string]: API protocol. `ollama` for Ollama's native API, `openai` for OpenAI-compatible APIs (OpenAI, Groq, LM Studio, etc.). Default: `ollama`.

**temperature** [number]: Controls randomness (0.0 = deterministic, 2.0 = very random). Default: `0.7`.

**max_tokens** [integer]: Maximum length of generated response. Default: `500`.

**timeout** [integer]: HTTP timeout in seconds. Increase for slower models. Default: `60`.

**auto_fill_on_new_card** [boolean]: Auto-generate content when adding new cards. Default: `true`.

**delay_between_requests_ms** [integer]: Delay between requests during batch processing (ms). Default: `500`.

**note_type_mappings** [object]: Per-note-type field mapping configuration. Best configured via the Settings dialog (Tools → LLM Field Generator Settings).

### Field Mappings Structure

Each note type mapping contains:

**source_fields** [array]: List of field names used as input for LLM generation. Multiple fields can be selected and all will be available in prompt templates via `{{FieldName}}`.

**target_fields** [array]: List of target field configurations, each containing:
- `field_name`: The target field to fill
- `prompt_template`: Template with `{{FieldName}}` placeholders
- `overwrite`: Whether to overwrite existing content

**system_prompt** [string]: System prompt for the LLM.

**triggered_by** [array]: List of triggers that activate this mapping. Options: `mining`, `add_cards`, `browse`, `focus_lost`, `toolbar`.

---

### Quick Start

1. Install and run [Ollama](https://ollama.ai/)
2. Pull a model: `ollama pull llama3.2`
3. Open Tools → LLM Field Generator Settings
4. Click "Test Connection" to verify Ollama is running
5. Go to "Field Mappings" tab, select your note type, click "Add Mapping"
6. Configure source fields (multiple selection supported), target field(s), and prompt templates
7. Save and start adding cards!

### Multiple Source Fields Example

For a note type with fields: `Word`, `Context`, `Definition`, `Examples`

You can select multiple source fields like `Word` and `Context`, then use them in the prompt:

```
Generate a definition for the word "{{Word}}" used in this context: "{{Context}}".
Also provide 2 example sentences.
```

All configured fields are available in prompt templates, even if not selected as source fields.
