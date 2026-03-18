"""
Utility functions for AutoAuth Agent
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class JSONParseError(ValueError):
    """
    Raised when we cannot extract valid JSON from an LLM response.

    Carries the raw response text so callers can log it without having
    to re-capture it themselves.
    """

    def __init__(self, message: str, raw_response: str = "") -> None:
        super().__init__(message)
        self.raw_response = raw_response

    def __str__(self) -> str:
        base = super().__str__()
        preview = self.raw_response[:300].replace("\n", " ")
        return f"{base} | Response preview: {preview!r}" if preview else base


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


def extract_json_from_response(response_text: str) -> Optional[dict[str, Any]]:
    """
    Robustly extract and parse a JSON *object* from an LLM response.

    Strategies tried in order:
    1. Direct parse of the whole string.
    2. First JSON code-block (```json ... ``` or ``` ... ```).
    3. Substring between the first ``{`` and last ``}``.
    4. Same substring after light cleaning (trailing commas).

    Returns ``None`` only if every strategy fails.
    """
    if not response_text or not response_text.strip():
        return None

    text = response_text.strip()

    # 1 — direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2 — markdown code blocks
    for pattern in (
        r"```json\s*\n?(.*?)\n?```",
        r"```\s*\n?(.*?)\n?```",
    ):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                result = json.loads(candidate)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

    # 3 — brace extraction (raw)
    raw_obj = _extract_brace_substring(text)
    if raw_obj:
        try:
            result = json.loads(raw_obj)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # 4 — brace extraction after cleaning
        cleaned = _fix_json_issues(raw_obj)
        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None


def extract_json_array_from_response(response_text: str) -> Optional[list]:
    """
    Extract a JSON *array* from an LLM response.  Mirrors the logic of
    ``extract_json_from_response`` but looks for ``[…]`` delimiters.
    """
    if not response_text or not response_text.strip():
        return None

    text = response_text.strip()

    # 1 — direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 2 — markdown code blocks
    for pattern in (
        r"```json\s*\n?(.*?)\n?```",
        r"```\s*\n?(.*?)\n?```",
    ):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            try:
                result = json.loads(candidate)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass

    # 3 — bracket extraction
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return None


def safe_json_parse(
    response_text: str,
    fallback: Optional[dict[str, Any]] = None,
    context: str = "",
) -> dict[str, Any]:
    """
    Parse JSON from *response_text*, returning *fallback* on failure (if
    provided) or raising ``JSONParseError``.

    Args:
        response_text: Raw LLM response.
        fallback:      Value to return instead of raising if parsing fails.
                       Pass ``None`` (default) to raise on failure.
        context:       Optional label (e.g. "ClinicalReader") included in the
                       error message to aid debugging.

    Raises:
        JSONParseError: When parsing fails and no fallback is given.
    """
    result = extract_json_from_response(response_text)

    if result is not None:
        return result

    if fallback is not None:
        logger.warning(
            "[%s] JSON parse failed — using fallback. Response: %.300s",
            context or "safe_json_parse",
            response_text,
        )
        return fallback

    prefix = f"[{context}] " if context else ""
    raise JSONParseError(
        f"{prefix}Failed to extract valid JSON from LLM response. "
        "Ensure the prompt instructs the model to return ONLY a JSON object "
        "with no markdown fences or extra text.",
        raw_response=response_text,
    )


def validate_json_structure(data: dict[str, Any], required_keys: list[str]) -> bool:
    """Return ``True`` if all *required_keys* are present in *data*."""
    return all(key in data for key in required_keys)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_brace_substring(text: str) -> Optional[str]:
    """Return the substring from the first ``{`` to the last ``}``."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return None


def _fix_json_issues(json_str: str) -> str:
    """
    Attempt light-touch repairs on malformed JSON.

    Current fixes:
    * Trailing commas before ``}`` or ``]``.
    * Unescaped literal newlines inside string values.
    """
    # Remove trailing commas before closing delimiters
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    # Replace literal newlines *inside* JSON strings with \\n.
    # We target content between double-quotes that hasn't already been escaped.
    def _escape_newlines_in_strings(m: re.Match) -> str:
        return m.group(0).replace("\n", "\\n").replace("\r", "\\r")

    json_str = re.sub(
        r'"(?:[^"\\]|\\.)*"',
        _escape_newlines_in_strings,
        json_str,
        flags=re.DOTALL,
    )

    return json_str
