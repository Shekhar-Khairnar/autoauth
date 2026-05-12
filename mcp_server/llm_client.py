"""LLM access layer for the AutoAuth tools.

Uses the OpenAI Python SDK against OpenRouter's OpenAI-compatible chat
completions endpoint. All AutoAuth tools route their LLM calls through the
single `chat()` function here so model selection, JSON-mode enforcement, and
output-length caps stay centralized.
"""
import os
from typing import Any

from openai import OpenAI

_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "anthropic/claude-haiku-4.5"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Return a cached OpenAI client pointed at OpenRouter.

    Lazily instantiated so import-time failures do not block tools that never
    actually call the LLM (e.g. CRD, DTR, PAS).

    Returns:
        An `openai.OpenAI` instance configured with the OpenRouter base URL
        and the OPENROUTER_API_KEY from the environment.

    Example:
        >>> client = _get_client()
        >>> client.base_url
        'https://openrouter.ai/api/v1'
    """
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set in environment")
        _client = OpenAI(api_key=api_key, base_url=_OPENROUTER_BASE_URL)
    return _client


def chat(
    messages: list[dict[str, str]],
    model: str | None = None,
    response_format: dict[str, Any] | None = None,
    max_tokens: int | None = None,
) -> str:
    """Send chat messages to OpenRouter and return the assistant's text.

    Wraps `chat.completions.create` and unwraps the first choice's content.
    Used by `synthesize_clinical_justification` and `appeal_denial` to drive
    JSON-mode responses against the FHIR bundle.

    Args:
        messages: OpenAI-format role/content dicts; role is "system" |
            "user" | "assistant".
        model: optional OpenRouter model slug override. Defaults to the
            LLM_MODEL env var, falling back to `anthropic/claude-haiku-4.5`.
        response_format: pass `{"type": "json_object"}` to force the model
            to return strict JSON.
        max_tokens: optional cap on output length. Useful for keeping
            iterative tool calls fast during demos.

    Returns:
        The string content of `response.choices[0].message.content`, or an
        empty string if the provider returned no content.

    Example:
        >>> answer = chat(
        ...     messages=[
        ...         {"role": "system", "content": "Reply with JSON only."},
        ...         {"role": "user", "content": "Return {\\"ok\\": true}"},
        ...     ],
        ...     response_format={"type": "json_object"},
        ... )
        >>> answer
        '{"ok": true}'
    """
    chosen_model = model or os.getenv("LLM_MODEL", _DEFAULT_MODEL)
    request_kwargs: dict[str, Any] = {"model": chosen_model, "messages": messages}
    if response_format is not None:
        request_kwargs["response_format"] = response_format
    if max_tokens is not None:
        request_kwargs["max_tokens"] = max_tokens
    completion = _get_client().chat.completions.create(**request_kwargs)
    return completion.choices[0].message.content or ""
