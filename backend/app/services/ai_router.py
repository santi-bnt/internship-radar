from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Callable, TypeVar

import httpx
from openai import OpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.services.ai_privacy import PrivacyPolicyEngine


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AIMode(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    BALANCED = "BALANCED"
    EXTERNAL_ALLOWED = "EXTERNAL_ALLOWED"


class AIProviderError(RuntimeError):
    pass


class AIProvider(ABC):
    name: str
    execution_location: str

    @abstractmethod
    def complete(self, *, instructions: str, context: dict[str, Any], schema: type[SchemaT]) -> SchemaT:
        raise NotImplementedError


class LocalAIProvider(AIProvider):
    """Ollama-compatible implementation behind a provider-neutral interface."""

    name = "ollama_compatible"
    execution_location = "LOCAL"

    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.local_ai_base_url).rstrip("/")
        self.model = model or settings.local_ai_model

    def complete(self, *, instructions: str, context: dict[str, Any], schema: type[SchemaT]) -> SchemaT:
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": schema.model_json_schema(),
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                    ],
                    "options": {"temperature": 0.1},
                },
                timeout=settings.local_ai_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("message", {}).get("content", "")
            return schema.model_validate_json(content)
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise AIProviderError("Local AI is unavailable or returned an invalid structured response.") from exc


class ExternalAIProvider(AIProvider):
    name = "openai"
    execution_location = "EXTERNAL"

    def complete(self, *, instructions: str, context: dict[str, Any], schema: type[SchemaT]) -> SchemaT:
        if not settings.openai_api_key:
            raise AIProviderError("External AI is not configured.")
        try:
            response = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            ).responses.parse(
                model=settings.external_ai_model,
                input=[
                    {"role": "developer", "content": instructions},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                text_format=schema,
            )
            if response.output_parsed is None:
                raise AIProviderError("External AI returned no structured result.")
            return response.output_parsed
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("External AI is temporarily unavailable.") from exc


AuditCallback = Callable[[dict[str, Any]], None]


class AIRouter:
    """Route minimized structured tasks locally first with privacy-gated fallback."""

    def __init__(
        self,
        mode: AIMode | str | None = None,
        *,
        local_provider: AIProvider | None = None,
        external_provider: AIProvider | None = None,
        privacy: PrivacyPolicyEngine | None = None,
    ):
        try:
            self.mode = AIMode(str(mode or settings.ai_mode).upper())
        except ValueError:
            self.mode = AIMode.BALANCED
        self.local = local_provider or LocalAIProvider()
        self.external = external_provider or ExternalAIProvider()
        self.external_configured = external_provider is not None or bool(settings.openai_api_key)
        self.privacy = privacy or PrivacyPolicyEngine()

    @staticmethod
    def _retry(provider: AIProvider, *, instructions: str, context: dict[str, Any], schema: type[SchemaT]) -> SchemaT:
        last_error: Exception | None = None
        attempts = max(1, min(settings.ai_max_attempts, 4))
        for attempt in range(attempts):
            try:
                return provider.complete(instructions=instructions, context=context, schema=schema)
            except AIProviderError as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(min(0.25 * (2**attempt), 1.0))
        raise AIProviderError(str(last_error or "AI provider failed."))

    def complete(
        self,
        *,
        instructions: str,
        context: dict[str, Any],
        schema: type[SchemaT],
        purpose: str,
        allow_external: bool = True,
        audit: AuditCallback | None = None,
    ) -> tuple[SchemaT, str, str]:
        try:
            result = self._retry(self.local, instructions=instructions, context=context, schema=schema)
            return result, self.local.name, self.local.execution_location
        except AIProviderError as local_error:
            if self.mode == AIMode.LOCAL_ONLY:
                raise AIProviderError("Local AI unavailable. LOCAL_ONLY mode forbids external fallback.") from local_error
            if not allow_external or not self.external_configured:
                raise

        safe, included, redacted = self.privacy.prepare_external_payload(context)
        if audit is None:
            raise AIProviderError("External AI calls require a privacy audit callback.")
        audit({
            "provider": self.external.name,
            "purpose": purpose,
            "privacy_classification": "NORMAL",
            "fields_included": included,
            "fields_redacted": redacted,
        })
        result = self._retry(self.external, instructions=instructions, context=safe, schema=schema)
        return result, self.external.name, self.external.execution_location
