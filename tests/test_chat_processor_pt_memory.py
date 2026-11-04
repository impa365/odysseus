"""Portuguese memory retrieval: accents, stopwords and "quem sou eu"."""

from src import chat_processor as cp
from src.chat_processor import ChatProcessor, _content_tokens


class _Memory:
    def __init__(self, rows):
        self.rows = rows

    def load(self, owner=None):
        return list(self.rows)


class _Docs:
    rag_manager = None


def _processor(rows):
    return ChatProcessor(memory_manager=_Memory(rows), personal_docs_manager=_Docs())


def test_tokens_keep_accented_words_and_drop_pt_stopwords():
    assert _content_tokens("O que você sabe sobre a minha memória?") == ["sabe", "memória"]
    assert _content_tokens("Configuração da VPS ServerImpa") == ["configuração", "vps", "serverimpa"]


def test_pt_identity_question_prefers_identity_memory():
    rows = [
        {"id": "kaiser", "text": "O usuário configurou o agente Kaiser da IMPA 365 para não repetir frases.",
         "category": "fact", "timestamp": 3},
        {"id": "who", "text": "O usuário é Jorrandeson, dono da IMPA 365.", "category": "identity", "timestamp": 1},
        {"id": "food", "text": "Considera que costelinha com barbecue ganha no fator felicidade.",
         "category": "preference", "timestamp": 2},
    ]
    picked = _processor(rows)._hybrid_retrieve("quem sou eu na IMPA 365?", rows, k=1)
    assert [m["id"] for m in picked] == ["who"]


def test_pinned_pt_identity_is_core_memory():
    proc = _processor([])
    assert proc._is_core_memory({"text": "O usuário é Jorrandeson.", "category": "fact"})
    assert proc._is_core_memory({"text": "Meu nome é Ana.", "category": "fact"})
    assert not proc._is_core_memory({"text": "Gosta de batata frita.", "category": "preference"})


def test_memory_context_limit_env(monkeypatch):
    monkeypatch.setenv("ODYSSEUS_MEMORY_CONTEXT_LIMIT", "10")
    assert cp._env_int("ODYSSEUS_MEMORY_CONTEXT_LIMIT", 5) == 10
    monkeypatch.setenv("ODYSSEUS_MEMORY_CONTEXT_LIMIT", "nope")
    assert cp._env_int("ODYSSEUS_MEMORY_CONTEXT_LIMIT", 5) == 5
    monkeypatch.delenv("ODYSSEUS_MEMORY_CONTEXT_LIMIT")
    assert cp._env_int("ODYSSEUS_MEMORY_CONTEXT_LIMIT", 5) == 5
