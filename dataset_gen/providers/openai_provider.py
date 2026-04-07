"""OpenAI-compatible provider backend.

Uses a chat-completions-compatible API for:
- SQL candidate generation
- SQL repair
- EN -> RO translation
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from dataset_gen.prompts import (
    build_generation_messages,
    build_repair_messages,
    build_translation_messages,
)
from dataset_gen.providers.base import AgenticProvider, ProviderError
from dataset_gen.schema import SchemaSnapshot
from dataset_gen.types import QueryCandidate


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_obj(text: str) -> Dict[str, object]:
    """Parse JSON from strict or markdown-wrapped model responses."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try fenced block fallback.
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.lower().startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue

    # Try greedy object extraction.
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return json.loads(match.group(0))
    raise ValueError("Could not parse JSON object from model response.")


class OpenAICompatibleProvider(AgenticProvider):
    """Provider implementation backed by OpenAI-compatible HTTP API."""

    def __init__(
        self,
        base_url: str,
        api_key_env: str,
        teacher_model: str,
        translator_model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.teacher_model = teacher_model
        self.translator_model = translator_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def _api_key(self) -> str:
        """Read API key from environment configured in app config."""
        key = os.getenv(self.api_key_env, "").strip()
        if not key:
            raise ProviderError(
                f"Missing API key in env var '{self.api_key_env}'. "
                "Set it before running openai_compatible mode."
            )
        return key

    def _chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        expect_json: bool = False,
        temperature: Optional[float] = None,
    ) -> str:
        """Call chat completions endpoint and return assistant message text."""
        payload: Dict[str, object] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens,
        }
        if expect_json:
            payload["response_format"] = {"type": "json_object"}

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key()}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"HTTP {exc.code}: {details}") from exc
        except Exception as exc:
            raise ProviderError(f"Chat request failed: {exc}") from exc

        try:
            data = json.loads(raw)
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise ProviderError(f"Unexpected chat response: {raw}") from exc

    def generate_candidate(
        self,
        domain: str,
        snapshot: SchemaSnapshot,
        difficulty: int,
        min_rows: int,
        strict_non_empty: bool,
        feedback: List[str],
    ) -> QueryCandidate:
        """Generate one candidate JSON object for a target domain/difficulty."""
        messages = build_generation_messages(
            domain=domain,
            snapshot=snapshot,
            difficulty=difficulty,
            min_rows=min_rows,
            strict_non_empty=strict_non_empty,
            feedback=feedback,
        )
        content = self._chat(model=self.teacher_model, messages=messages, expect_json=True)
        data = _extract_json_obj(content)
        return QueryCandidate.from_dict(data)

    def repair_candidate(
        self,
        domain: str,
        snapshot: SchemaSnapshot,
        previous: QueryCandidate,
        error_message: str,
        min_rows: int,
        strict_non_empty: bool,
    ) -> QueryCandidate:
        """Repair previously failed candidate based on validation feedback."""
        messages = build_repair_messages(
            snapshot=snapshot,
            candidate=previous,
            error_message=error_message,
            min_rows=min_rows,
            strict_non_empty=strict_non_empty,
        )
        content = self._chat(model=self.teacher_model, messages=messages, expect_json=True)
        data = _extract_json_obj(content)
        return QueryCandidate.from_dict(data)

    def translate_to_romanian(
        self, question_en: str, domain: str, question_ro_hint: Optional[str] = None
    ) -> str:
        """Translate EN question to RO, respecting optional pre-filled hint."""
        if question_ro_hint:
            return question_ro_hint
        messages = build_translation_messages(question_en=question_en, domain=domain)
        content = self._chat(
            model=self.translator_model, messages=messages, expect_json=False, temperature=0.0
        )
        return content.strip()
