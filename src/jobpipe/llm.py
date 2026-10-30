"""LLM access through OpenRouter, with latency/cost capture and optional Opik tracing."""

import time
from dataclasses import dataclass
from typing import Protocol

from openai import OpenAI

from jobpipe import tracing
from jobpipe.config import Settings

# Short aliases for the models we support out of the box; any full OpenRouter id also works.
MODELS = {
    "phi-4": "microsoft/phi-4",
    "qwen-2.5-7b": "qwen/qwen-2.5-7b-instruct",
    "mistral-7b": "mistralai/mistral-7b-instruct",
    "gpt-oss-120b": "openai/gpt-oss-120b",
}

# Reasoning models spend tokens "thinking"; for translation keep that minimal
REASONING_EFFORT = {"openai/gpt-oss-120b": "low"}


def resolve_model(name: str) -> str:
    return MODELS.get(name, name)


@dataclass(frozen=True)
class LLMResult:
    text: str
    model: str
    latency_ms: int
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int


class ChatModel(Protocol):
    """What the pipeline stages need from an LLM. Tests pass a fake that implements this."""

    model: str

    def complete(self, system: str, user: str) -> LLMResult: ...


class OpenRouterChat:
    def __init__(self, model: str, settings: Settings, http_client=None):
        if not settings.openrouter_api_key:
            raise SystemExit("OPENROUTER_API_KEY is not set (see .env.example)")
        self.model = resolve_model(model)
        self._client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            timeout=settings.llm_timeout_s,
            max_retries=settings.llm_max_retries,  # exponential backoff on 429/5xx
            http_client=http_client,  # tests inject a mock transport
        )

    @tracing.track(name="llm_call", type="llm")
    def complete(self, system: str, user: str) -> LLMResult:
        extra = {}
        if effort := REASONING_EFFORT.get(self.model):
            extra["reasoning"] = {"effort": effort}

        start = time.perf_counter()
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            extra_body=extra or None,
        )
        latency_ms = round((time.perf_counter() - start) * 1000)

        usage = resp.usage
        # OpenRouter adds the actual charged cost (USD) to every response's usage block
        cost = float(getattr(usage, "cost", 0) or 0) if usage else 0.0
        result = LLMResult(
            text=(resp.choices[0].message.content or "").strip(),
            model=resp.model or self.model,
            latency_ms=latency_ms,
            cost_usd=cost,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
        tracing.update_span(
            model=result.model,
            provider="openrouter",
            total_cost=result.cost_usd,
            usage={
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.prompt_tokens + result.completion_tokens,
            },
            metadata={"latency_ms": latency_ms},
        )
        return result
