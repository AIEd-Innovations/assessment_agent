from types import SimpleNamespace

import anthropic
import openai
import pytest
from google.genai import errors

from assessment_agent.llm import SUPPORTED_MODELS, LLMAuthError, get_llm_provider
from assessment_agent.llm.anthropic_api import AnthropicProvider
from assessment_agent.llm.fake import FakeLLMProvider
from assessment_agent.llm.gemini_api import GeminiProvider
from assessment_agent.llm.openai_api import OpenAIProvider


def returns(value):
    async def call(**kwargs):
        return value
    return call


def raises(exc):
    async def call(**kwargs):
        raise exc
    return call


def bare(exc_type):
    """An SDK exception instance without the HTTP response its constructor wants."""
    return exc_type.__new__(exc_type)


def test_no_key_gives_the_mock():
    assert isinstance(get_llm_provider("claude-sonnet-5-5", None), FakeLLMProvider)
    assert isinstance(get_llm_provider("gpt-6-luna", ""), FakeLLMProvider)


@pytest.mark.parametrize("model, provider_type", [
    ("claude-opus-5-5", AnthropicProvider),
    ("gpt-6.1-sol", OpenAIProvider),
    ("gemini-3.8-flash", GeminiProvider),
])
def test_key_selects_the_vendor(model, provider_type):
    provider = get_llm_provider(model, "sk-test")
    assert isinstance(provider, provider_type)
    assert provider.model_id == model


def test_every_vendor_is_offered():
    assert {m.vendor for m in SUPPORTED_MODELS.values()} == {"anthropic", "openai", "gemini"}


async def test_anthropic_reads_only_text_blocks():
    provider = AnthropicProvider("claude-sonnet-5-5", "sk-test")
    message = SimpleNamespace(stop_reason="end_turn", content=[
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text='{"score": 3}'),
    ])
    provider._client = SimpleNamespace(messages=SimpleNamespace(create=returns(message)))
    data, raw, _ = await provider.complete_with_raw("grade this")
    assert data == {"score": 3}
    assert raw == '{"score": 3}'


async def test_anthropic_refusal_is_an_error():
    provider = AnthropicProvider("claude-sonnet-5-5", "sk-test")
    message = SimpleNamespace(stop_reason="refusal", content=[])
    provider._client = SimpleNamespace(messages=SimpleNamespace(create=returns(message)))
    with pytest.raises(RuntimeError, match="declined"):
        await provider.complete_with_raw("grade this")


async def test_openai_reads_output_text():
    provider = OpenAIProvider("gpt-6-luna", "sk-test")
    response = SimpleNamespace(output_text='{"score": 2}')
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=returns(response)))
    data, _, _ = await provider.complete_with_raw("grade this")
    assert data == {"score": 2}


async def test_gemini_reads_text():
    provider = GeminiProvider("gemini-3.5-flash-lite", "sk-test")
    response = SimpleNamespace(text='{"score": 1}')
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=returns(response))))
    data, _, _ = await provider.complete_with_raw("grade this")
    assert data == {"score": 1}


@pytest.mark.parametrize("exc", [bare(anthropic.AuthenticationError), bare(anthropic.PermissionDeniedError)])
async def test_anthropic_rejected_key(exc):
    provider = AnthropicProvider("claude-haiku-5-5", "sk-bad")
    provider._client = SimpleNamespace(messages=SimpleNamespace(create=raises(exc)))
    with pytest.raises(LLMAuthError):
        await provider.complete_with_raw("grade this")


@pytest.mark.parametrize("exc", [bare(openai.AuthenticationError), bare(openai.PermissionDeniedError)])
async def test_openai_rejected_key(exc):
    provider = OpenAIProvider("gpt-6-astra", "sk-bad")
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=raises(exc)))
    with pytest.raises(LLMAuthError):
        await provider.complete_with_raw("grade this")


@pytest.mark.parametrize("code, status, details", [
    (401, "UNAUTHENTICATED", []),
    (400, "INVALID_ARGUMENT", [{"reason": "API_KEY_INVALID"}]),
])
async def test_gemini_rejected_key(code, status, details):
    exc = errors.ClientError(code, {"error": {"code": code, "message": "bad key", "status": status, "details": details}})
    provider = GeminiProvider("gemini-4-argon", "sk-bad")
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=raises(exc))))
    with pytest.raises(LLMAuthError):
        await provider.complete_with_raw("grade this")


async def test_gemini_other_client_errors_are_not_key_errors():
    exc = errors.ClientError(404, {"error": {"code": 404, "message": "no such model", "status": "NOT_FOUND"}})
    provider = GeminiProvider("gemini-4-argon", "sk-test")
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=raises(exc))))
    with pytest.raises(errors.ClientError):
        await provider.complete_with_raw("grade this")
