"""Routers that answer a non-stream completion with an SSE body (``: keep-alive``
plus ``data:`` chunks) are collapsed back into one chat.completion."""

import json

import pytest
from fastapi import HTTPException

import src.llm_core as lc

SSE_BODY = (
    ": keep-alive\n\n"
    'data: {"id":"c1","object":"chat.completion.chunk","model":"deepseek-v4-pro",'
    '"choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}\n\n\n\n'
    'data: {"id":"c1","choices":[{"index":0,"delta":{"reasoning_content":"thinking"}}]}\n\n'
    'data: {"id":"c1","choices":[{"index":0,"delta":{"content":"[{\\"text\\": \\"Mora em SP\\"}"}}]}\n\n'
    'data: {"id":"c1","choices":[{"index":0,"delta":{"content":"]"},"finish_reason":"stop"}],'
    '"usage":{"prompt_tokens":10,"completion_tokens":5}}\n\n'
    "data: [DONE]\n\ndata: [DONE]\n\n"
)


class _Resp:
    def __init__(self, text):
        self.text = text

    def json(self):
        return json.loads(self.text)


def test_collapse_rebuilds_completion():
    data = lc._collapse_sse_completion(SSE_BODY)
    msg = data["choices"][0]["message"]
    assert msg["content"] == '[{"text": "Mora em SP"}]'
    assert msg["reasoning_content"] == "thinking"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["model"] == "deepseek-v4-pro"
    assert data["usage"]["completion_tokens"] == 5


def test_collapse_passes_error_chunk_through():
    data = lc._collapse_sse_completion('data: {"error": {"message": "quota"}}\n\n')
    assert data == {"error": {"message": "quota"}}


def test_decode_prefers_plain_json_and_rejects_garbage():
    assert lc._decode_nonstream_body(_Resp('{"choices": []}'), "u") == {"choices": []}
    assert lc._decode_nonstream_body(_Resp(SSE_BODY), "u")["choices"][0]["message"]["content"]
    with pytest.raises(HTTPException) as empty:
        lc._decode_nonstream_body(_Resp("   "), "u")
    assert "Empty response body" in empty.value.detail
    with pytest.raises(HTTPException) as junk:
        lc._decode_nonstream_body(_Resp("<html>oops</html>"), "u")
    assert "Non-JSON response" in junk.value.detail
