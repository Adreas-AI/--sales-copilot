"""A deliberately small LLM interface: system + user prompt in, schema-checked JSON out."""

from __future__ import annotations

import json
from typing import Any, Protocol


class LLMError(Exception):
    """The model could not produce a usable answer. Callers fall back to rules/templates."""


class LLMClient(Protocol):
    model: str

    def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class OpenAIJSONClient:
    """OpenAI chat completions with strict JSON-schema structured output."""

    def __init__(self, *, api_key: str, model: str, timeout: float) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model

    def complete_json(
        self, *, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        import openai

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMError(f"Model refused: {message.refusal}")
        if not message.content:
            raise LLMError("Model returned an empty response")
        try:
            data = json.loads(message.content)
        except json.JSONDecodeError as exc:
            raise LLMError("Model returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("Model returned JSON that is not an object")
        return data
