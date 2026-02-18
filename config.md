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

---

### Quick Start

1. Install and run [Ollama](https://ollama.ai/)
2. Pull a model: `ollama pull llama3.2`
3. Open Tools → LLM Field Generator Settings
4. Click "Test Connection" to verify Ollama is running
5. Go to "Field Mappings" tab, select your note type, click "Add Mapping"
6. Configure source field, target field(s), and prompt templates
7. Save and start adding cards!
