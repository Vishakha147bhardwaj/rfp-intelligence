from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from rfp.llm.client import LLMClient, LLMError
from rfp.settings import Settings
import anthropic
import httpx


class Out(BaseModel):
    value: str


def fake_response(tool_input: dict, input_tokens: int = 100, output_tokens: int = 10):
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id="toolu_1", input=tool_input)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


def make_client() -> LLMClient:
    return LLMClient(Settings(anthropic_api_key="test-key"))


def test_missing_key_gives_clear_error():
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        LLMClient(Settings(anthropic_api_key=""))


def test_valid_output_and_usage(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_call", lambda *a, **k: fake_response({"value": "ok"}, 120, 15))

    result, usage = client.structured(agent="t", system="s", user="u", response_model=Out)

    assert result.value == "ok"
    assert (usage.input_tokens, usage.output_tokens, usage.attempts) == (120, 15, 1)
    assert usage.model == client.models["fast"]


def test_invalid_output_is_re_asked(monkeypatch):
    client = make_client()
    responses = iter([fake_response({}), fake_response({"value": "fixed"})])
    message_counts = []

    def fake_call(model, system, messages, tool, max_tokens, force=True):
        message_counts.append(len(messages))
        return next(responses)

    monkeypatch.setattr(client, "_call", fake_call)
    result, usage = client.structured(agent="t", system="s", user="u", response_model=Out)

    assert result.value == "fixed"
    assert message_counts == [1, 3]       # retry carries Claude's answer + our error message
    assert (usage.attempts, usage.input_tokens) == (2, 200)


def test_gives_up_after_retries(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_call", lambda *a, **k: fake_response({}))
    with pytest.raises(LLMError, match="still invalid after 3 attempts"):
        client.structured(agent="t", system="s", user="u", response_model=Out)


def test_other_failures_become_llm_error(monkeypatch):
    client = make_client()

    def boom(*args, **kwargs):
        raise ValueError("connection reset")

    monkeypatch.setattr(client, "_call", boom)
    with pytest.raises(LLMError, match="t: connection reset"):
        client.structured(agent="t", system="s", user="u", response_model=Out)

def test_falls_back_to_auto_when_forced_tool_unsupported(monkeypatch):
    client = make_client()
    forced_flags = []

    def fake_call(model, system, messages, tool, max_tokens, force=True):
        forced_flags.append(force)
        if force:
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.BadRequestError(
                'tool_choice: type "tool" and "any" are not supported for this model.',
                response=httpx.Response(400, request=request), body=None,
            )
        return fake_response({"value": "ok"})

    monkeypatch.setattr(client, "_call", fake_call)
    first, _ = client.structured(agent="t", system="s", user="u", response_model=Out, tier="smart")
    second, _ = client.structured(agent="t", system="s", user="u", response_model=Out, tier="smart")

    assert first.value == second.value == "ok"
    assert forced_flags == [True, False, False]     # fallback is remembered for this model