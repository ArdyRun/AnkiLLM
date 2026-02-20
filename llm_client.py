# Anki LLM Field Generator
# LLM client using urllib (no external dependencies)

import json
import urllib.request
import urllib.error
from typing import Optional, Tuple


# API endpoint configurations
API_ENDPOINTS = {
    "ollama": "/api/chat",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}


class LLMClient:
    """HTTP client for multiple LLM API providers.

    Supports:
    - Ollama (local)
    - Groq
    - Google Gemini
    - OpenRouter
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.2",
        temperature: float = 0.7,
        max_tokens: int = 500,
        api_key: str = "",
        timeout: int = 60,
        api_mode: str = "ollama",
    ):
        # Set default base_url for Ollama if empty
        if api_mode == "ollama":
            self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        else:
            self.base_url = base_url.rstrip("/") if base_url else ""
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.timeout = timeout
        self.api_mode = api_mode

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Generate text from the LLM using Ollama API."""
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

    def generate_groq(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Generate text using Groq API."""
        # Validate API key
        if not self.api_key:
            raise LLMError(
                "Groq API key is missing.\n\n"
                "Get your API key from: https://console.groq.com/keys"
            )
        
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

        url = API_ENDPOINTS["groq"]
        return self._post(url, payload, parse_ollama=False, use_auth=True)

    def generate_gemini(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Generate text using Google Gemini API."""
        # Validate API key
        if not self.api_key:
            raise LLMError(
                "Gemini API key is missing.\n\n"
                "Get your API key from: https://aistudio.google.com/apikey"
            )
        
        # Gemini format with system_instruction separate from contents
        contents = [
            {"role": "user", "parts": [{"text": prompt}]}
        ]

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }

        # Add system instruction if provided
        # FIX: Format yang benar menurut Gemini API docs harus include "role": "system"
        if system_prompt:
            payload["systemInstruction"] = {
                "role": "system",
                "parts": [{"text": system_prompt}]
            }

        # Gemini URL format: /models/{model}:generateContent
        # API key dikirim via header, bukan query parameter
        url = f"{API_ENDPOINTS['gemini']}/{self.model}:generateContent"
        return self._post_gemini(url, payload)

    def generate_openrouter(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Generate text using OpenRouter API."""
        # Validate API key
        if not self.api_key:
            raise LLMError(
                "OpenRouter API key is missing.\n\n"
                "Get your API key from: https://openrouter.ai/keys"
            )
        
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

        url = API_ENDPOINTS["openrouter"]
        return self._post_openrouter(url, payload)

    def _post(self, url: str, payload: dict, parse_ollama: bool = True, use_auth: bool = False) -> str:
        """Execute HTTP POST and parse the response."""
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
        }
        if use_auth and self.api_key:
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
                f"Connection failed: {e.reason}\nURL: {url}"
            ) from e
        except Exception as e:
            raise LLMError(f"Request failed: {str(e)}") from e

        try:
            if parse_ollama:
                return response_data["message"]["content"].strip()
            else:
                return response_data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise LLMError(
                f"Unexpected response format: {json.dumps(response_data, indent=2)}"
            ) from e

    def _post_gemini(self, url: str, payload: dict) -> str:
        """Execute HTTP POST for Gemini API and parse the response.
        
        Gemini API key harus dikirim via header: X-Goog-Api-Key
        """
        data = json.dumps(payload).encode("utf-8")

        # Gemini requires API key in header, not query parameter
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
        }

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
                f"Check your API key and model name."
            ) from e
        except Exception as e:
            raise LLMError(f"Request failed: {str(e)}") from e

        # Gemini format: {"candidates": [{"content": {"parts": [{"text": "..."}]}}]}
        try:
            candidates = response_data.get("candidates", [])
            if not candidates:
                raise LLMError("No candidates in Gemini response")
            return candidates[0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError) as e:
            raise LLMError(
                f"Unexpected response format: {json.dumps(response_data, indent=2)}"
            ) from e

    def _post_openrouter(self, url: str, payload: dict) -> str:
        """Execute HTTP POST for OpenRouter API and parse the response."""
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/anki-llm-fill",
            "X-Title": "Anki LLM Field Generator",
        }

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
                f"Check your OpenRouter API key."
            ) from e
        except Exception as e:
            raise LLMError(f"Request failed: {str(e)}") from e

        try:
            return response_data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise LLMError(
                f"Unexpected response format: {json.dumps(response_data, indent=2)}"
            ) from e

    def test_connection(self) -> Tuple[bool, str]:
        """Test if the LLM server is reachable and model works.

        Returns:
            Tuple of (success: bool, message: str)
        """
        if self.api_mode == "gemini":
            return self._test_gemini()
        elif self.api_mode == "groq":
            return self._test_groq()
        elif self.api_mode == "openrouter":
            return self._test_openrouter()
        else:
            return self._test_ollama()

    def _test_ollama(self) -> Tuple[bool, str]:
        """Test Ollama connection."""
        try:
            # First check if server is up
            url = f"{self.base_url}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10):
                pass

            # Then test the model
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": False,
                "max_tokens": 5,
            }
            url = f"{self.base_url}/api/chat"
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "message" in result:
                    return True, f"Ollama connected. Model '{self.model}' is working."
                return False, "Unexpected response from Ollama"
        except urllib.error.URLError as e:
            error_msg = f"Cannot connect to Ollama at {self.base_url}\nError: {e.reason}"
            
            # Provide helpful troubleshooting tips
            if "timed out" in str(e.reason).lower() or "timeout" in str(e.reason).lower():
                error_msg += "\n\nTroubleshooting:\n"
                error_msg += "1. Make sure Ollama is running\n"
                error_msg += "   → Run: ollama serve\n"
                error_msg += "2. Check if model is pulled\n"
                error_msg += f"   → Run: ollama pull {self.model}\n"
                error_msg += "3. Try http://127.0.0.1:11434 instead of localhost\n"
                error_msg += "4. Check Windows Firewall settings"
            elif "refused" in str(e.reason).lower():
                error_msg += "\n\nTroubleshooting:\n"
                error_msg += "1. Ollama server is not running\n"
                error_msg += "   → Run: ollama serve\n"
                error_msg += "2. Check if Ollama is installed\n"
                error_msg += "   → Download from: https://ollama.ai"
            
            return False, error_msg
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _test_groq(self) -> Tuple[bool, str]:
        """Test Groq connection."""
        # Validate API key first
        if not self.api_key:
            return False, "Groq API key is missing.\n\nGet your API key from: https://console.groq.com/keys"
        
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }
            url = API_ENDPOINTS["groq"]
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "choices" in result:
                    return True, f"Groq connected. Model '{self.model}' is working."
                return False, "Unexpected response from Groq"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            
            # Parse Groq error codes
            if e.code == 401:
                return False, "Invalid Groq API key.\n\nPlease check your API key at: https://console.groq.com/keys"
            elif e.code == 403:
                # Check for specific error messages
                error_body = body.lower()
                if "invalid_api_key" in error_body or "authentication" in error_body:
                    return False, "Invalid Groq API key.\n\nPlease check your API key at: https://console.groq.com/keys"
                elif "permission" in error_body:
                    return False, "API key does not have permission.\n\nMake sure your API key is active and has access to the model."
                elif "1010" in body or "cloudflare" in error_body:
                    return False, (
                        "Groq API Error (403 - Code 1010)\n\n"
                        "This is a Cloudflare protection error. Possible causes:\n\n"
                        "1. Your Groq account needs verification\n"
                        "   → Check your email for verification link\n"
                        "   → Complete phone verification at https://console.groq.com\n\n"
                        "2. API key not yet activated\n"
                        "   → Wait 5-10 minutes after creating the key\n\n"
                        "3. Your IP/location is rate-limited\n"
                        "   → Try again later or use a different network\n\n"
                        "4. Account requires approval\n"
                        "   → Contact Groq support: https://console.groq.com/support\n\n"
                        "Alternative: Use OpenRouter or Gemini API instead.\n"
                        f"\nResponse: {body}"
                    )
                else:
                    return False, (
                        f"Groq API Error (403)\n\n"
                        f"Possible causes:\n"
                        f"1. API key is invalid or expired\n"
                        f"2. API key is not activated (wait 5-10 min)\n"
                        f"3. Account needs verification\n"
                        f"4. Model '{self.model}' is not available for your account\n\n"
                        f"Check your API key at: https://console.groq.com/keys\n\n"
                        f"Response: {body}"
                    )
            elif e.code == 404:
                return False, f"Model '{self.model}' not found.\n\nCheck available models at: https://console.groq.com/docs/models"
            elif e.code == 429:
                return False, "Rate limit exceeded.\n\nPlease wait and try again later."
            
            return False, f"HTTP {e.code}: {e.reason}\n{body}"
        except urllib.error.URLError as e:
            return False, f"Connection failed: {e.reason}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _test_gemini(self) -> Tuple[bool, str]:
        """Test Gemini connection."""
        # Validate API key first
        if not self.api_key:
            return False, "Gemini API key is missing.\n\nGet your API key from: https://aistudio.google.com/apikey"
        
        try:
            payload = {
                "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
                "generationConfig": {"maxOutputTokens": 5},
            }
            # URL tanpa query parameter, API key dikirim via header
            url = f"{API_ENDPOINTS['gemini']}/{self.model}:generateContent"
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
            }
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "candidates" in result and len(result["candidates"]) > 0:
                    return True, f"Gemini connected. Model '{self.model}' is working."
                return False, "No candidates in response"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            if e.code == 403:
                return False, "Invalid API key or model name"
            elif e.code == 404:
                return False, f"Model '{self.model}' not found"
            return False, f"HTTP {e.code}: {e.reason}\n{body}"
        except urllib.error.URLError as e:
            return False, f"Connection failed: {e.reason}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def _test_openrouter(self) -> Tuple[bool, str]:
        """Test OpenRouter connection."""
        # Validate API key first
        if not self.api_key:
            return False, "OpenRouter API key is missing.\n\nGet your API key from: https://openrouter.ai/keys"
        
        try:
            # First verify API key
            url = "https://openrouter.ai/api/v1/auth/key"
            headers = {"Authorization": f"Bearer {self.api_key}"}
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10) as response:
                auth_result = json.loads(response.read().decode("utf-8"))
                if "data" not in auth_result:
                    return False, "Invalid OpenRouter API key"

            # Then test the model
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            }
            url = API_ENDPOINTS["openrouter"]
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/anki-llm-fill",
            }
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "choices" in result:
                    return True, f"OpenRouter connected. Model '{self.model}' is working."
                return False, "Unexpected response from OpenRouter"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass

            if e.code == 401:
                return False, "Invalid OpenRouter API key"

            # Check for specific OpenRouter errors
            if e.code == 404:
                if "privacy" in body.lower() or "data policy" in body.lower():
                    return False, (
                        "OpenRouter Privacy Settings Required\n\n"
                        "You need to configure privacy settings before using free models.\n\n"
                        "Steps to fix:\n"
                        "1. Go to: https://openrouter.ai/settings/privacy\n"
                        "2. Enable these options:\n"
                        "   ✓ Enable free endpoints that may train on inputs\n"
                        "   ✓ Enable free endpoints that may publish prompts"
                    )

            return False, f"HTTP {e.code}: {e.reason}\n{body}"
        except urllib.error.URLError as e:
            return False, f"Connection failed: {e.reason}"
        except Exception as e:
            return False, f"Error: {str(e)}"


class LLMError(Exception):
    """Raised when the LLM API call fails."""
    pass
