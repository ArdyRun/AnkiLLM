# Anki LLM Field Generator
# Ollama-compatible LLM client using urllib (no external dependencies)

import json
import urllib.request
import urllib.error
from typing import Optional


class LLMClient:
    """HTTP client for Ollama-compatible LLM APIs.

    Supports any OpenAI-compatible /api/generate or /api/chat endpoint,
    with Ollama as the primary target.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        temperature: float = 0.7,
        max_tokens: int = 500,
        api_key: str = "",
        timeout: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Generate text from the LLM.

        Uses Ollama's /api/chat endpoint (compatible with most local LLM servers).

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system instruction.

        Returns:
            The generated text string.

        Raises:
            LLMError: If the API call fails.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        url = f"{self.base_url}/api/chat"
        return self._post(url, payload, parse_ollama=True)

    def generate_openai(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Generate text using OpenAI-compatible /v1/chat/completions endpoint.

        Use this for non-Ollama servers (OpenAI, Groq, LM Studio, etc.).

        Args:
            prompt: The user prompt to send.
            system_prompt: Optional system instruction.

        Returns:
            The generated text string.

        Raises:
            LLMError: If the API call fails.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        url = f"{self.base_url}/v1/chat/completions"
        return self._post(url, payload, parse_ollama=False)

    def _post(self, url: str, payload: dict, parse_ollama: bool = True) -> str:
        """Execute HTTP POST and parse the response.

        Args:
            url: Full URL to POST to.
            payload: JSON-serializable dict.
            parse_ollama: If True, parse Ollama response format.
                          If False, parse OpenAI response format.

        Returns:
            Generated text string.
        """
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            raise LLMError(
                f"HTTP {e.code}: {e.reason}\n{body}"
            ) from e
        except urllib.error.URLError as e:
            raise LLMError(
                f"Connection failed: {e.reason}\n"
                f"Make sure Ollama is running at {self.base_url}"
            ) from e
        except Exception as e:
            raise LLMError(f"Request failed: {str(e)}") from e

        # Parse response based on API format
        try:
            if parse_ollama:
                # Ollama format: {"message": {"content": "..."}}
                return response_data["message"]["content"].strip()
            else:
                # OpenAI format: {"choices": [{"message": {"content": "..."}}]}
                return response_data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise LLMError(
                f"Unexpected response format: {json.dumps(response_data, indent=2)}"
            ) from e

    def test_connection(self) -> bool:
        """Test if the LLM server is reachable.

        Returns:
            True if server responds, False otherwise.
        """
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception:
            # Try OpenAI-style health check
            try:
                url = f"{self.base_url}/v1/models"
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=10):
                    return True
            except Exception:
                return False

    def list_models(self) -> list:
        """List available models from Ollama.

        Returns:
            List of model name strings, or empty list on failure.
        """
        try:
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []


class LLMError(Exception):
    """Raised when the LLM API call fails."""
    pass
