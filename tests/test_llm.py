"""OpenRouter client against a mocked HTTP transport: no network, no cost."""

import json

import httpx
import pytest

from jobpipe.config import Settings
from jobpipe.llm import OpenRouterChat, resolve_model


def mock_client(requests: list):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "object": "chat.completion",
                "created": 0,
                "model": "microsoft/phi-4",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": " Accountant \n"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 42,
                    "completion_tokens": 3,
                    "total_tokens": 45,
                    "cost": 0.0000123,
                },
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def settings():
    return Settings(openrouter_api_key="test-key", _env_file=None)


def test_result_carries_text_tokens_cost_and_latency(settings):
    sent = []
    llm = OpenRouterChat("phi-4", settings, http_client=mock_client(sent))
    r = llm.complete("system prompt", "Λογιστής")

    assert r.text == "Accountant"
    assert (r.prompt_tokens, r.completion_tokens) == (42, 3)
    assert r.cost_usd == pytest.approx(0.0000123)
    assert r.latency_ms >= 0
    assert sent[0]["model"] == "microsoft/phi-4"
    assert sent[0]["temperature"] == 0
    assert sent[0]["messages"][1] == {"role": "user", "content": "Λογιστής"}
    assert "reasoning" not in sent[0]


def test_reasoning_model_gets_low_effort(settings):
    sent = []
    OpenRouterChat("gpt-oss-120b", settings, http_client=mock_client(sent)).complete("s", "u")
    assert sent[0]["model"] == "openai/gpt-oss-120b"
    assert sent[0]["reasoning"] == {"effort": "low"}


def test_model_aliases_and_full_ids():
    assert resolve_model("qwen-2.5-7b") == "qwen/qwen-2.5-7b-instruct"
    assert resolve_model("mistral-7b") == "mistralai/mistral-7b-instruct"
    assert resolve_model("google/gemma-3-12b-it") == "google/gemma-3-12b-it"


def test_missing_api_key_fails_clearly():
    with pytest.raises(SystemExit, match="OPENROUTER_API_KEY"):
        OpenRouterChat("phi-4", Settings(openrouter_api_key="", _env_file=None))
