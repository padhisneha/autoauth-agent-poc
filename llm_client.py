"""
Universal LLM Client - Supports multiple AI providers
"""
from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base class for all LLM client errors."""


class LLMAuthError(LLMError):
    """Invalid or missing API key."""


class LLMRateLimitError(LLMError):
    """Provider rate-limit hit; safe to retry after a delay."""


class LLMTimeoutError(LLMError):
    """Request timed out."""


class LLMUnavailableError(LLMError):
    """Provider returned a 5xx / service-unavailable error."""


class LLMResponseError(LLMError):
    """Provider returned an unexpected or empty response."""


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

_RETRYABLE = (LLMRateLimitError, LLMTimeoutError, LLMUnavailableError)

_DEFAULT_RETRY_DELAYS = (1.0, 3.0, 8.0)  # seconds between attempts


def _with_retries(fn, *, retries: int = 3, delays: tuple = _DEFAULT_RETRY_DELAYS):
    """Call *fn()*, retrying on transient errors with exponential back-off."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except _RETRYABLE as exc:
            last_exc = exc
            wait = delays[min(attempt, len(delays) - 1)]
            logger.warning(
                "Transient LLM error on attempt %d/%d (%s). Retrying in %.1fs…",
                attempt + 1,
                retries,
                type(exc).__name__,
                wait,
            )
            time.sleep(wait)
        except LLMError:
            raise  # non-retryable — surface immediately
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI = "openai"


# ---------------------------------------------------------------------------
# Universal client
# ---------------------------------------------------------------------------


class UniversalLLMClient:
    """
    Universal client that wraps Anthropic, Gemini, and OpenAI behind a single
    ``generate()`` call.  Switch providers by changing config — no code changes.
    """

    def __init__(self, provider: Optional[str] = None):
        from config import settings  # local import avoids circular dependency

        self.provider: str = (provider or settings.llm_provider).strip().lower()
        self.model: str = settings.llm_model
        self.max_tokens: int = settings.max_tokens
        self.temperature: float = settings.temperature
        self._settings = settings

        _init_dispatch = {
            LLMProvider.ANTHROPIC: self._init_anthropic,
            LLMProvider.GEMINI: self._init_gemini,
            LLMProvider.OPENAI: self._init_openai,
        }

        try:
            init_fn = _init_dispatch[LLMProvider(self.provider)]
        except (KeyError, ValueError):
            raise LLMError(
                f"Unsupported LLM provider: '{self.provider}'. "
                f"Choose from: {[p.value for p in LLMProvider]}"
            )

        init_fn()

    # ------------------------------------------------------------------
    # Initializers
    # ------------------------------------------------------------------

    def _init_anthropic(self) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

        api_key = self._settings.anthropic_api_key
        if not api_key:
            raise LLMAuthError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )

        self.client = Anthropic(api_key=api_key)
        if not self.model or self.model == "auto":
            self.model = "claude-sonnet-4-20250514"

    def _init_gemini(self) -> None:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "Google Generative AI SDK not installed. "
                "Run: pip install google-generativeai"
            ) from exc

        api_key = self._settings.gemini_api_key
        if not api_key:
            raise LLMAuthError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )

        genai.configure(api_key=api_key)
        if not self.model or self.model == "auto":
            self.model = "gemini-1.5-pro"
        self.client = genai.GenerativeModel(self.model)

    def _init_openai(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "OpenAI SDK not installed. Run: pip install openai"
            ) from exc

        api_key = self._settings.openai_api_key
        if not api_key:
            raise LLMAuthError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )

        self.client = OpenAI(api_key=api_key)
        if not self.model or self.model == "auto":
            self.model = "gpt-4"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        system_prompt: Optional[str] = None,
        retries: int = 3,
    ) -> str:
        """
        Generate a response from the configured LLM.

        Args:
            prompt:        User-facing prompt.
            max_tokens:    Override the default max-token limit.
            temperature:   Override the default temperature.
            system_prompt: System-level instruction (supported by all providers).
            retries:       How many times to retry on transient errors.

        Returns:
            The model's text response (never empty — raises on empty content).

        Raises:
            LLMAuthError:        Bad or missing API key.
            LLMRateLimitError:   Exhausted after *retries* rate-limit errors.
            LLMTimeoutError:     Exhausted after *retries* timeout errors.
            LLMUnavailableError: Provider returned repeated 5xx errors.
            LLMResponseError:    Model returned an empty or malformed response.
            LLMError:            Any other unclassified provider error.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must not be empty")

        max_tokens = max_tokens or self.max_tokens
        temperature = temperature if temperature is not None else self.temperature

        _dispatch = {
            LLMProvider.ANTHROPIC: self._generate_anthropic,
            LLMProvider.GEMINI: self._generate_gemini,
            LLMProvider.OPENAI: self._generate_openai,
        }
        generate_fn = _dispatch[LLMProvider(self.provider)]

        def _call() -> str:
            return generate_fn(prompt, max_tokens, temperature, system_prompt)

        result = _with_retries(_call, retries=retries)

        if not result or not result.strip():
            raise LLMResponseError(
                f"Provider '{self.provider}' returned an empty response."
            )
        return result

    # ------------------------------------------------------------------
    # Provider-specific generators
    # ------------------------------------------------------------------

    def _generate_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str],
    ) -> str:
        try:
            kwargs: dict = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            if not response.content:
                raise LLMResponseError("Anthropic returned no content blocks.")
            return response.content[0].text

        except LLMError:
            raise
        except Exception as exc:
            _raise_classified(exc, "Anthropic")

    def _generate_gemini(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str],
    ) -> str:
        try:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            response = self.client.generate_content(
                full_prompt, generation_config=generation_config
            )

            if not response.text:
                raise LLMResponseError("Gemini returned an empty text response.")
            return response.text

        except LLMError:
            raise
        except Exception as exc:
            _raise_classified(exc, "Gemini")

    def _generate_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str],
    ) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            content = response.choices[0].message.content
            if not content:
                raise LLMResponseError("OpenAI returned an empty message content.")
            return content

        except LLMError:
            raise
        except Exception as exc:
            _raise_classified(exc, "OpenAI")

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_provider_info(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "max_tokens": str(self.max_tokens),
            "temperature": str(self.temperature),
        }


# ---------------------------------------------------------------------------
# Error classification helper
# ---------------------------------------------------------------------------


def _raise_classified(exc: Exception, provider: str) -> None:
    """
    Convert provider-specific SDK exceptions into our custom hierarchy.
    Always raises — never returns.
    """
    msg = str(exc)
    exc_type = type(exc).__name__

    # Auth errors
    if any(
        kw in msg.lower()
        for kw in ("authentication", "auth", "api_key", "unauthorized", "403", "invalid api key")
    ):
        raise LLMAuthError(
            f"{provider} authentication failed: {msg}. Check your API key."
        ) from exc

    # Rate limits
    if any(kw in msg.lower() for kw in ("rate limit", "rate_limit", "ratelimit", "429", "too many")):
        raise LLMRateLimitError(
            f"{provider} rate limit exceeded: {msg}"
        ) from exc

    # Timeouts
    if any(
        kw in msg.lower()
        for kw in ("timeout", "timed out", "read timeout", "connect timeout")
    ) or "Timeout" in exc_type:
        raise LLMTimeoutError(
            f"{provider} request timed out: {msg}"
        ) from exc

    # Service unavailable / 5xx
    if any(
        kw in msg.lower()
        for kw in ("503", "502", "500", "service unavailable", "overloaded", "internal server")
    ):
        raise LLMUnavailableError(
            f"{provider} service unavailable: {msg}"
        ) from exc

    # Fallback
    raise LLMError(
        f"Unexpected {provider} error ({exc_type}): {msg}"
    ) from exc
