"""Helpers for requesting constrained JSON output across backends.

The CLI talks to two kinds of OpenAI-compatible endpoints:

* **OpenAI** (and anything that speaks OpenAI's native API) — accepts
  ``response_format={"type": "json_schema", "json_schema": {...}}``.
* **Holo** (served by vLLM) — does not accept OpenAI's native
  ``response_format`` shape. The OpenAI-compatible surface exposed by
  vLLM takes the schema through ``extra_body.structured_outputs.json``,
  and vLLM's outlines backend does not resolve JSON Schema ``$ref`` /
  ``$defs``, so references must be inlined.

Callers should pass the model name and the desired schema to
:func:`structured_output_params` and splat the result into the
``openai.chat.completions.create`` kwargs.
"""

from __future__ import annotations

import copy
from typing import Any


def inline_schema_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``schema`` with ``$ref`` occurrences inlined.

    The input is never mutated. Both draft-2020-12 (``$defs``) and
    draft-07 (``definitions``) vocabularies are supported. ``$ref`` nodes
    that carry sibling keys (permitted by JSON Schema) are resolved by
    inlining the referenced definition and letting siblings override.
    """
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", None) or schema.pop("definitions", None) or {}

    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            ref = obj.get("$ref")
            if isinstance(ref, str):
                name = ref.rsplit("/", 1)[-1]
                resolved = walk(defs.get(name, {}))
                siblings = {k: walk(v) for k, v in obj.items() if k != "$ref"}
                return {**resolved, **siblings} if siblings else resolved
            return {k: walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(x) for x in obj]
        return obj

    return walk(schema)


def is_vllm_backend(model: str) -> bool:
    """Heuristic: which backend serves this model name in the current repo.

    Holo models (``holo1``, ``holo1-5``, ...) are served by vLLM. Everything
    else (OpenAI's ``gpt-*``, Anthropic, etc.) is assumed to be
    OpenAI-native. Extend this function if other vLLM-served models are
    added.
    """
    return model.lower().startswith("holo")


def response_format_json_schema(
    schema: dict[str, Any],
    name: str,
    description: str = "",
    strict: bool = True,
) -> dict[str, Any]:
    """Build OpenAI's native ``response_format`` payload for JSON-schema output."""
    return {
        "type": "json_schema",
        "json_schema": {
            "schema": schema,
            "name": name,
            "description": description,
            "strict": strict,
        },
    }


def structured_outputs_extra_body(schema: dict[str, Any]) -> dict[str, Any]:
    """Build vLLM's ``extra_body`` payload for JSON-schema output."""
    return {"structured_outputs": {"json": inline_schema_refs(schema)}}


def structured_output_params(
    model: str, schema: dict[str, Any], name: str
) -> dict[str, Any]:
    """Return the request fields that constrain output to ``schema``.

    Dispatches between OpenAI's native ``response_format`` and vLLM's
    ``extra_body.structured_outputs.json`` based on the model name.
    The returned dict is meant to be splatted into
    ``openai.chat.completions.create`` kwargs, e.g.::

        openai_request = {
            "messages": messages,
            "model": model,
            "temperature": temperature,
            **structured_output_params(model, MyModel.model_json_schema(), "my_model"),
        }
    """
    if is_vllm_backend(model):
        return {"extra_body": structured_outputs_extra_body(schema)}
    return {"response_format": response_format_json_schema(schema, name)}
