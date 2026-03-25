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

_DEFAULT_RETRY_DELAYS = (1.0, 3.0, 8.0)


def _with_retries(fn, *, retries: int = 3, delays: tuple = _DEFAULT_RETRY_DELAYS):
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
            raise
    raise last_exc


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
    def __init__(self, provider: Optional[str] = None):
        from config import settings

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
        from anthropic import Anthropic

        api_key = self._settings.anthropic_api_key
        if not api_key:
            raise LLMAuthError("ANTHROPIC_API_KEY is not set.")

        self.client = Anthropic(api_key=api_key)
        if not self.model or self.model == "auto":
            self.model = "claude-sonnet-4-20250514"

    def _init_gemini(self) -> None:
        import google.generativeai as genai

        api_key = self._settings.gemini_api_key
        if not api_key:
            raise LLMAuthError("GEMINI_API_KEY is not set.")

        genai.configure(api_key=api_key)
        if not self.model or self.model == "auto":
            self.model = "gemini-1.5-pro"

        self.client = genai.GenerativeModel(self.model)

    def _init_openai(self) -> None:
        from openai import OpenAI

        api_key = self._settings.openai_api_key
        if not api_key:
            raise LLMAuthError("OPENAI_API_KEY is not set.")

        self.client = OpenAI(api_key=api_key)

        if not self.model or self.model == "auto":
            self.model = "gpt-5-mini"

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

        def _call():
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
        self, prompt: str, max_tokens: int, temperature: float, system_prompt: Optional[str]
    ) -> str:
        try:
            kwargs = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            if not response.content:
                raise LLMResponseError("Anthropic returned no content.")
            return response.content[0].text

        except Exception as exc:
            _raise_classified(exc, "Anthropic")

    def _generate_gemini(
        self, prompt: str, max_tokens: int, temperature: float, system_prompt: Optional[str]
    ) -> str:
        try:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

            response = self.client.generate_content(
                full_prompt,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                },
            )

            if not response.text:
                raise LLMResponseError("Gemini returned empty response.")
            return response.text

        except Exception as exc:
            _raise_classified(exc, "Gemini")

    def _generate_openai(
        self, prompt: str, max_tokens: int, temperature: float, system_prompt: Optional[str]
    ) -> str:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_completion_tokens=max_tokens,  # ✅ FIXED HERE
                temperature=temperature,
            )

            content = response.choices[0].message.content
            if not content:
                raise LLMResponseError("OpenAI returned empty response.")

            return content

        except Exception as exc:
            _raise_classified(exc, "OpenAI")

    # ------------------------------------------------------------------
    # Debug info
    # ------------------------------------------------------------------

    def get_provider_info(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


def _raise_classified(exc: Exception, provider: str):
    msg = str(exc).lower()

    if "api key" in msg or "unauthorized" in msg:
        raise LLMAuthError(msg)

    if "rate limit" in msg or "429" in msg:
        raise LLMRateLimitError(msg)

    if "timeout" in msg:
        raise LLMTimeoutError(msg)

    if "503" in msg or "unavailable" in msg:
        raise LLMUnavailableError(msg)

    raise LLMError(f"{provider} error: {exc}")