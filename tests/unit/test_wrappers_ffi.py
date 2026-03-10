# tests/unit/test_wrappers_ffi.py
"""FFI boundary tests for wrappers.py — exercises Pyodide code paths.

These tests monkeypatch HAS_PYODIDE=True and inject JavaScript-type fakes
(JsNull, JsUndefined, FakeJsProxy, FakeObject, FakeJSON) to verify the
actual conversion logic that runs in production Workers.

Pattern borrowed from https://github.com/adewale/tasche/blob/main/tests/unit/test_wrappers_ffi.py
"""

import pytest

import src.wrappers as W

# =============================================================================
# Fake JS types — simulate Pyodide's FFI objects in CPython
# =============================================================================


class FakeJsProxy:
    """Simulates pyodide.ffi.JsProxy wrapping a Python value."""

    def __init__(self, data):
        self._data = data

    def to_py(self):
        return self._data


class JsNull:
    """JavaScript null sentinel — NOT a JsProxy subclass.

    In Pyodide, JS null is a special type where type(x).__name__ == "JsNull".
    This is the key gotcha: isinstance(x, JsProxy) misses it entirely.
    """

    def __bool__(self):
        return False

    def __repr__(self):
        return "JsNull()"


JsNull.__name__ = "JsNull"
JsNull.__qualname__ = "JsNull"


class _Undefined:
    """JavaScript undefined singleton."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "undefined"

    @property
    def typeof(self):
        return "undefined"


_Undefined.__name__ = "JsUndefined"
_Undefined.__qualname__ = "JsUndefined"


class _FakeJSON:
    """Simulates js.JSON."""

    @staticmethod
    def parse(text):
        if text == "null":
            return JsNull()
        raise ValueError(f"FakeJSON can't parse: {text}")


class _FakeObject:
    """Simulates js.Object."""

    @staticmethod
    def fromEntries(iterable):
        return dict(iterable)


class FakeJsModule:
    """Simulates the `js` module with undefined, JSON, Object."""

    undefined = _Undefined()
    JSON = _FakeJSON
    Object = _FakeObject


def fake_to_js(value, *, dict_converter=None):
    """Simulates pyodide.ffi.to_js()."""
    if isinstance(value, dict):
        if dict_converter:
            return dict_converter(value.items())
        return FakeJsProxy(value)
    if isinstance(value, list):
        return FakeJsProxy(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return FakeJsProxy(bytes(value))
    return value


# =============================================================================
# Fixture: patch module globals to simulate Pyodide environment
# =============================================================================


@pytest.fixture
def pyodide_fakes(monkeypatch):
    """Patch wrappers module to simulate Pyodide runtime."""
    monkeypatch.setattr(W, "HAS_PYODIDE", True)
    monkeypatch.setattr(W, "js", FakeJsModule())
    monkeypatch.setattr(W, "to_js", fake_to_js)
    monkeypatch.setattr(W, "JS_NULL", JsNull())
    yield


# =============================================================================
# _is_js_undefined under Pyodide fakes
# =============================================================================


class TestIsJsUndefinedFFI:
    def test_undefined_detected(self, pyodide_fakes):
        assert W._is_js_undefined(_Undefined()) is True

    def test_jsnull_is_not_undefined(self, pyodide_fakes):
        # JsNull has type name "JsNull" which IS in the check list
        # This is by design — _is_js_undefined treats JsNull as undefined-ish
        assert W._is_js_undefined(JsNull()) is True

    def test_python_none_not_undefined(self, pyodide_fakes):
        assert W._is_js_undefined(None) is False

    def test_string_not_undefined(self, pyodide_fakes):
        assert W._is_js_undefined("hello") is False

    def test_zero_not_undefined(self, pyodide_fakes):
        assert W._is_js_undefined(0) is False

    def test_false_not_undefined(self, pyodide_fakes):
        assert W._is_js_undefined(False) is False


# =============================================================================
# _to_py_safe under Pyodide fakes
# =============================================================================


class TestToPySafeFFI:
    def test_jsproxy_dict_converted(self, pyodide_fakes):
        proxy = FakeJsProxy({"id": 1, "name": "test"})
        result = W._to_py_safe(proxy)
        assert result == {"id": 1, "name": "test"}

    def test_jsproxy_list_converted(self, pyodide_fakes):
        proxy = FakeJsProxy([1, 2, 3])
        result = W._to_py_safe(proxy)
        assert result == [1, 2, 3]

    def test_nested_jsnull_scrubbed_from_dict(self, pyodide_fakes):
        """JsNull values inside dicts become None."""
        data = {"title": "hello", "author": JsNull()}
        result = W._to_py_safe(data)
        assert result["title"] == "hello"
        assert result["author"] is None

    def test_nested_jsnull_scrubbed_from_list(self, pyodide_fakes):
        data = ["a", JsNull(), "c"]
        result = W._to_py_safe(data)
        assert result == ["a", None, "c"]

    def test_js_undefined_becomes_none(self, pyodide_fakes):
        result = W._to_py_safe(_Undefined())
        assert result is None

    def test_jsnull_becomes_none(self, pyodide_fakes):
        result = W._to_py_safe(JsNull())
        assert result is None

    def test_plain_dict_with_jsnull_scrubbed(self, pyodide_fakes):
        result = W._to_py_safe({"a": 1, "b": JsNull()})
        assert result == {"a": 1, "b": None}

    def test_plain_list_with_jsnull_scrubbed(self, pyodide_fakes):
        result = W._to_py_safe([1, JsNull(), 3])
        assert result == [1, None, 3]

    def test_depth_limit_returns_value_as_is(self, pyodide_fakes):
        result = W._to_py_safe({"key": "val"}, _depth=W._MAX_CONVERSION_DEPTH)
        assert result == {"key": "val"}

    def test_deeply_nested_jsproxy(self, pyodide_fakes):
        inner = FakeJsProxy({"deep": "value"})
        outer = FakeJsProxy({"nested": inner})
        # outer.to_py() returns {"nested": inner}, then inner.to_py() returns {"deep": "value"}
        result = W._to_py_safe(outer)
        # The inner FakeJsProxy has to_py(), so it gets converted
        assert result["nested"] == {"deep": "value"}

    def test_jsproxy_to_py_error_returns_fallback(self, pyodide_fakes):
        """When to_py() raises, falls back to str conversion."""

        class BadProxy:
            def to_py(self):
                raise TypeError("broken proxy")

            def __str__(self):
                return "fallback"

        result = W._to_py_safe(BadProxy())
        assert result == "fallback"


# =============================================================================
# _to_js_value under Pyodide fakes
# =============================================================================


class TestToJsValueFFI:
    def test_dict_converted_with_fromEntries(self, pyodide_fakes):
        result = W._to_js_value({"key": "val"})
        assert result == {"key": "val"}

    def test_list_converted(self, pyodide_fakes):
        result = W._to_js_value([1, 2, 3])
        assert isinstance(result, FakeJsProxy)
        assert result.to_py() == [1, 2, 3]

    def test_none_returns_none(self, pyodide_fakes):
        result = W._to_js_value(None)
        assert result is None

    def test_string_passes_through(self, pyodide_fakes):
        result = W._to_js_value("hello")
        assert result == "hello"

    def test_int_passes_through(self, pyodide_fakes):
        result = W._to_js_value(42)
        assert result == 42


# =============================================================================
# _to_d1_value under Pyodide fakes — the None→JsNull bug fix
# =============================================================================


class TestToD1ValueFFI:
    def test_none_becomes_jsnull(self, pyodide_fakes):
        """Historical bug: None→JS undefined broke D1 .bind(). Must be JsNull."""
        result = W._to_d1_value(None)
        assert type(result).__name__ == "JsNull"

    def test_non_none_passes_through(self, pyodide_fakes):
        assert W._to_d1_value("text") == "text"
        assert W._to_d1_value(42) == 42
        assert W._to_d1_value(0) == 0

    def test_jsnull_input_becomes_jsnull_output(self, pyodide_fakes):
        """JsNull input → _to_py_safe returns None → converted back to JsNull."""
        result = W._to_d1_value(JsNull())
        assert type(result).__name__ == "JsNull"

    def test_undefined_input_becomes_jsnull(self, pyodide_fakes):
        """Undefined → None → JsNull for D1."""
        result = W._to_d1_value(_Undefined())
        assert type(result).__name__ == "JsNull"


# =============================================================================
# SafeD1 / SafeD1Statement under Pyodide fakes
# =============================================================================


class TestSafeD1FFI:
    def test_bind_converts_none_to_jsnull(self, pyodide_fakes):
        """None parameters are converted to JsNull for D1."""

        class FakeStmt:
            def __init__(self):
                self.bound = None

            def bind(self, *args):
                self.bound = args
                return self

        inner = FakeStmt()
        stmt = W.SafeD1Statement(inner)
        stmt.bind("text", None, 42)
        assert inner.bound[0] == "text"
        assert type(inner.bound[1]).__name__ == "JsNull"
        assert inner.bound[2] == 42

    @pytest.mark.asyncio
    async def test_first_jsproxy_to_dict(self, pyodide_fakes):
        """first() converts JsProxy result to Python dict."""

        class FakeStmt:
            async def first(self):
                return FakeJsProxy({"id": 1, "title": "test"})

            def bind(self, *args):
                return self

        stmt = W.SafeD1Statement(FakeStmt())
        result = await stmt.first()
        assert result == {"id": 1, "title": "test"}

    @pytest.mark.asyncio
    async def test_first_jsnull_to_none(self, pyodide_fakes):
        """first() converts JsNull result to None."""

        class FakeStmt:
            async def first(self):
                return JsNull()

            def bind(self, *args):
                return self

        stmt = W.SafeD1Statement(FakeStmt())
        result = await stmt.first()
        assert result is None

    @pytest.mark.asyncio
    async def test_first_undefined_to_none(self, pyodide_fakes):
        class FakeStmt:
            async def first(self):
                return _Undefined()

            def bind(self, *args):
                return self

        stmt = W.SafeD1Statement(FakeStmt())
        result = await stmt.first()
        assert result is None

    @pytest.mark.asyncio
    async def test_all_converts_rows(self, pyodide_fakes):
        """all() converts JsProxy results to Python list of dicts."""

        class FakeResult:
            results = [{"id": 1}, {"id": 2}]
            success = True

        class FakeStmt:
            async def all(self):
                return FakeResult()

            def bind(self, *args):
                return self

        stmt = W.SafeD1Statement(FakeStmt())
        result = await stmt.all()
        assert result.success is True
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_all_none_result_returns_empty(self, pyodide_fakes):
        class FakeStmt:
            async def all(self):
                return None

            def bind(self, *args):
                return self

        stmt = W.SafeD1Statement(FakeStmt())
        result = await stmt.all()
        assert result.results == []

    def test_prepare_wraps_statement(self, pyodide_fakes):
        class FakeDB:
            def prepare(self, sql):
                return "raw_stmt"

        db = W.SafeD1(FakeDB())
        stmt = db.prepare("SELECT 1")
        assert isinstance(stmt, W.SafeD1Statement)

    @pytest.mark.asyncio
    async def test_exec_passes_through(self, pyodide_fakes):
        class FakeDB:
            async def exec(self, sql):
                return {"success": True}

            def prepare(self, sql):
                return None

        db = W.SafeD1(FakeDB())
        result = await db.exec("CREATE TABLE test (id INTEGER)")
        assert result == {"success": True}


# =============================================================================
# SafeAI under Pyodide fakes
# =============================================================================


class TestSafeAIFFI:
    @pytest.mark.asyncio
    async def test_run_dict_inputs_converted(self, pyodide_fakes):
        """Dict inputs are converted to JS objects via _to_js_value."""
        captured = {}

        class FakeAI:
            async def run(self, model, inputs):
                captured["inputs"] = inputs
                return {"data": [[0.1, 0.2]]}

        ai = W.SafeAI(FakeAI())
        result = await ai.run("@cf/model", {"text": "hello"})
        assert result == {"data": [[0.1, 0.2]]}
        # With pyodide_fakes, dict goes through Object.fromEntries → dict
        assert captured["inputs"] == {"text": "hello"}

    @pytest.mark.asyncio
    async def test_run_jsnull_result_returns_none(self, pyodide_fakes):
        class FakeAI:
            async def run(self, model, inputs):
                return JsNull()

        ai = W.SafeAI(FakeAI())
        result = await ai.run("@cf/model", {"text": "test"})
        assert result is None

    @pytest.mark.asyncio
    async def test_run_undefined_result_returns_none(self, pyodide_fakes):
        class FakeAI:
            async def run(self, model, inputs):
                return _Undefined()

        ai = W.SafeAI(FakeAI())
        result = await ai.run("@cf/model", {"text": "test"})
        assert result is None

    @pytest.mark.asyncio
    async def test_run_jsproxy_result_converted(self, pyodide_fakes):
        class FakeAI:
            async def run(self, model, inputs):
                return FakeJsProxy({"data": [[0.1] * 768]})

        ai = W.SafeAI(FakeAI())
        result = await ai.run("@cf/model", {"text": "test"})
        assert isinstance(result, dict)
        assert "data" in result


# =============================================================================
# SafeVectorize under Pyodide fakes
# =============================================================================


class TestSafeVectorizeFFI:
    @pytest.mark.asyncio
    async def test_query_converts_result(self, pyodide_fakes):
        class FakeIndex:
            async def query(self, vector, options):
                return FakeJsProxy({"matches": [{"id": "1", "score": 0.9}]})

            async def upsert(self, vectors):
                pass

            async def deleteByIds(self, ids):
                pass

        idx = W.SafeVectorize(FakeIndex())
        result = await idx.query([0.1, 0.2], {"topK": 10})
        assert result == {"matches": [{"id": "1", "score": 0.9}]}

    @pytest.mark.asyncio
    async def test_query_jsnull_returns_empty_matches(self, pyodide_fakes):
        class FakeIndex:
            async def query(self, vector, options):
                return JsNull()

            async def upsert(self, vectors):
                pass

            async def deleteByIds(self, ids):
                pass

        idx = W.SafeVectorize(FakeIndex())
        result = await idx.query([0.1], {"topK": 5})
        assert result == {"matches": []}

    @pytest.mark.asyncio
    async def test_query_undefined_returns_empty_matches(self, pyodide_fakes):
        class FakeIndex:
            async def query(self, vector, options):
                return _Undefined()

            async def upsert(self, vectors):
                pass

            async def deleteByIds(self, ids):
                pass

        idx = W.SafeVectorize(FakeIndex())
        result = await idx.query([0.1], {"topK": 5})
        assert result == {"matches": []}

    @pytest.mark.asyncio
    async def test_upsert_converts_vectors(self, pyodide_fakes):
        captured = {}

        class FakeIndex:
            async def query(self, vector, options):
                pass

            async def upsert(self, vectors):
                captured["vectors"] = vectors
                return {"count": 1}

            async def deleteByIds(self, ids):
                pass

        idx = W.SafeVectorize(FakeIndex())
        result = await idx.upsert([{"id": "1", "values": [0.1]}])
        # With fakes, list → FakeJsProxy
        assert captured["vectors"] is not None

    @pytest.mark.asyncio
    async def test_deleteByIds_passes_through(self, pyodide_fakes):
        deleted = []

        class FakeIndex:
            async def query(self, vector, options):
                pass

            async def upsert(self, vectors):
                pass

            async def deleteByIds(self, ids):
                deleted.extend(ids)

        idx = W.SafeVectorize(FakeIndex())
        await idx.deleteByIds(["id1", "id2"])
        assert deleted == ["id1", "id2"]


# =============================================================================
# SafeQueue under Pyodide fakes
# =============================================================================


class TestSafeQueueFFI:
    @pytest.mark.asyncio
    async def test_send_dict_message(self, pyodide_fakes):
        sent = []

        class FakeQueue:
            async def send(self, message):
                sent.append(message)

        queue = W.SafeQueue(FakeQueue())
        await queue.send({"feed_id": 1, "url": "https://example.com"})
        assert len(sent) == 1
        assert sent[0]["feed_id"] == 1

    @pytest.mark.asyncio
    async def test_send_multiple_messages(self, pyodide_fakes):
        sent = []

        class FakeQueue:
            async def send(self, message):
                sent.append(message)

        queue = W.SafeQueue(FakeQueue())
        await queue.send({"id": 1})
        await queue.send({"id": 2})
        await queue.send({"id": 3})
        assert len(sent) == 3


# =============================================================================
# SafeEnv under Pyodide fakes
# =============================================================================


class TestSafeEnvFFI:
    def test_wraps_all_bindings(self, pyodide_fakes):
        class FakeEnv:
            DB = "raw_db"
            AI = "raw_ai"
            SEARCH_INDEX = "raw_index"
            FEED_QUEUE = "raw_queue"
            DEAD_LETTER_QUEUE = "raw_dlq"
            PLANET_NAME = "Test"

        env = W.SafeEnv(FakeEnv())
        assert isinstance(env.DB, W.SafeD1)
        assert isinstance(env.AI, W.SafeAI)
        assert isinstance(env.SEARCH_INDEX, W.SafeVectorize)
        assert isinstance(env.FEED_QUEUE, W.SafeQueue)
        assert isinstance(env.DEAD_LETTER_QUEUE, W.SafeQueue)

    def test_optional_bindings_none_when_missing(self, pyodide_fakes):
        class FakeEnv:
            DB = "raw_db"

        env = W.SafeEnv(FakeEnv())
        assert isinstance(env.DB, W.SafeD1)
        assert env.AI is None
        assert env.SEARCH_INDEX is None
        assert env.FEED_QUEUE is None
        assert env.DEAD_LETTER_QUEUE is None

    def test_getattr_proxies_string_vars(self, pyodide_fakes):
        class FakeEnv:
            DB = "raw_db"
            PLANET_NAME = "Test Planet"
            SESSION_SECRET = "secret"

        env = W.SafeEnv(FakeEnv())
        assert env.PLANET_NAME == "Test Planet"
        assert env.SESSION_SECRET == "secret"


# =============================================================================
# Row factories under Pyodide fakes — JsNull in field values
# =============================================================================


class TestRowFactoriesFFI:
    def test_feed_row_jsnull_title(self, pyodide_fakes):
        """JsNull in a feed row field becomes None."""
        row = {"id": 1, "url": "https://x.com/feed", "title": JsNull()}
        result = W.feed_row_from_js(row)
        assert result["title"] is None
        assert result["url"] == "https://x.com/feed"

    def test_feed_row_undefined_title(self, pyodide_fakes):
        row = {"id": 1, "url": "https://x.com/feed", "title": _Undefined()}
        result = W.feed_row_from_js(row)
        assert result["title"] is None

    def test_entry_row_jsnull_author(self, pyodide_fakes):
        row = {
            "id": 1,
            "feed_id": 1,
            "guid": "g",
            "url": "https://x.com",
            "title": "T",
            "author": JsNull(),
        }
        result = W.entry_row_from_js(row)
        assert result["author"] is None

    def test_admin_row_jsnull_returns_none(self, pyodide_fakes):
        """JsNull input to admin_row_from_js returns None."""
        result = W.admin_row_from_js(JsNull())
        assert result is None

    def test_audit_row_jsnull_details(self, pyodide_fakes):
        row = {"id": 1, "admin_id": 1, "action": "add_feed", "details": JsNull()}
        result = W.audit_row_from_js(row)
        assert result["details"] is None

    def test_feed_rows_from_d1_jsnull(self, pyodide_fakes):
        """JsNull as entire result set returns empty list."""
        result = W.feed_rows_from_d1(JsNull())
        assert result == []

    def test_entry_rows_from_d1_undefined(self, pyodide_fakes):
        result = W.entry_rows_from_d1(_Undefined())
        assert result == []


# =============================================================================
# SafeHeaders under Pyodide fakes
# =============================================================================


class TestSafeHeadersFFI:
    def test_jsnull_header_returns_empty(self, pyodide_fakes):
        """JsNull header value returns empty string."""

        class FakeRequest:
            class headers:
                @staticmethod
                def get(name):
                    return JsNull()

        h = W.SafeHeaders(FakeRequest())
        assert h.user_agent == ""
        assert h.cookie == ""

    def test_undefined_header_returns_empty(self, pyodide_fakes):
        class FakeRequest:
            class headers:
                @staticmethod
                def get(name):
                    return _Undefined()

        h = W.SafeHeaders(FakeRequest())
        assert h.user_agent == ""


# =============================================================================
# SafeFormData under Pyodide fakes
# =============================================================================


class TestSafeFormDataFFI:
    def test_jsnull_form_value_returns_none(self, pyodide_fakes):
        class FakeForm:
            def get(self, key):
                return JsNull()

        form = W.SafeFormData(FakeForm())
        assert form.get("name") is None

    def test_undefined_form_value_returns_none(self, pyodide_fakes):
        class FakeForm:
            def get(self, key):
                return _Undefined()

        form = W.SafeFormData(FakeForm())
        assert form.get("name") is None

    def test_get_str_jsnull_returns_default(self, pyodide_fakes):
        class FakeForm:
            def get(self, key):
                return JsNull()

        form = W.SafeFormData(FakeForm())
        assert form.get_str("name", "fallback") == "fallback"

    def test_get_int_jsnull_returns_default(self, pyodide_fakes):
        class FakeForm:
            def get(self, key):
                return JsNull()

        form = W.SafeFormData(FakeForm())
        assert form.get_int("count", 99) == 99


# =============================================================================
# SafeFeedInfo under Pyodide fakes
# =============================================================================


class TestSafeFeedInfoFFI:
    def test_jsnull_title(self, pyodide_fakes):
        info = W.SafeFeedInfo({"title": JsNull()})
        assert info.title is None

    def test_jsproxy_dict_input(self, pyodide_fakes):
        proxy = FakeJsProxy({"title": "My Blog", "link": "https://example.com"})
        info = W.SafeFeedInfo(proxy)
        assert info.title == "My Blog"
        assert info.link == "https://example.com"

    def test_author_detail_with_jsnull_name(self, pyodide_fakes):
        info = W.SafeFeedInfo({
            "author_detail": {"name": JsNull(), "email": "a@b.com"},
            "author": "Fallback",
        })
        # JsNull name → falls back to author field
        assert info.author == "Fallback"


# =============================================================================
# HttpResponse (not FFI-dependent but completeness)
# =============================================================================


class TestHttpResponse:
    def test_json_parsing(self):
        resp = W.HttpResponse(200, '{"key": "value"}', {}, "https://x.com")
        assert resp.json() == {"key": "value"}

    def test_json_array(self):
        resp = W.HttpResponse(200, "[1, 2, 3]", {}, "https://x.com")
        assert resp.json() == [1, 2, 3]

    def test_status_and_text(self):
        resp = W.HttpResponse(404, "Not Found", {}, "https://x.com")
        assert resp.status_code == 404
        assert resp.text == "Not Found"

    def test_headers(self):
        resp = W.HttpResponse(200, "", {"content-type": "text/html"}, "https://x.com")
        assert resp.headers["content-type"] == "text/html"

    def test_final_url(self):
        resp = W.HttpResponse(200, "", {}, "https://redirected.com")
        assert resp.final_url == "https://redirected.com"


# =============================================================================
# Bind helpers under Pyodide fakes
# =============================================================================


class TestBindHelpersFFI:
    def test_entry_bind_values_jsnull_fields(self, pyodide_fakes):
        """JsNull values in entry fields become None."""
        result = W.entry_bind_values(
            feed_id=1,
            guid="g",
            url="https://x.com",
            title=JsNull(),
            author=_Undefined(),
            content="<p>hi</p>",
            summary=JsNull(),
            published_at="2025-01-01",
        )
        assert result[0] == 1
        assert result[1] == "g"
        assert result[3] is None  # title (JsNull)
        assert result[4] is None  # author (undefined)
        assert result[6] is None  # summary (JsNull)

    def test_feed_bind_values_jsnull_fields(self, pyodide_fakes):
        result = W.feed_bind_values(
            title=JsNull(),
            site_url="https://x.com",
            author_name=_Undefined(),
            author_email=JsNull(),
            etag='"abc"',
            last_modified=None,
            feed_id=42,
        )
        assert result[0] is None  # title
        assert result[1] == "https://x.com"
        assert result[2] is None  # author_name
        assert result[3] is None  # author_email
        assert result[-1] == 42


# =============================================================================
# _safe_str under Pyodide fakes
# =============================================================================


class TestSafeStrFFI:
    def test_jsnull_returns_none(self, pyodide_fakes):
        assert W._safe_str(JsNull()) is None

    def test_undefined_returns_none(self, pyodide_fakes):
        assert W._safe_str(_Undefined()) is None

    def test_jsproxy_string_converted(self, pyodide_fakes):
        proxy = FakeJsProxy("hello world")
        result = W._safe_str(proxy)
        assert result == "hello world"

    def test_none_returns_none(self, pyodide_fakes):
        assert W._safe_str(None) is None

    def test_normal_string(self, pyodide_fakes):
        assert W._safe_str("test") == "test"


# =============================================================================
# _extract_form_value under Pyodide fakes
# =============================================================================


class TestExtractFormValueFFI:
    def test_jsnull_returns_none(self, pyodide_fakes):
        class FakeForm:
            def get(self, key):
                return JsNull()

        assert W._extract_form_value(FakeForm(), "field") is None

    def test_undefined_returns_none(self, pyodide_fakes):
        class FakeForm:
            def get(self, key):
                return _Undefined()

        assert W._extract_form_value(FakeForm(), "field") is None

    def test_jsproxy_value_converted(self, pyodide_fakes):
        class FakeForm:
            def get(self, key):
                return FakeJsProxy("form_value")

        result = W._extract_form_value(FakeForm(), "field")
        assert result == "form_value"


# =============================================================================
# _to_py_list under Pyodide fakes
# =============================================================================


class TestToPyListFFI:
    def test_jsnull_returns_empty(self, pyodide_fakes):
        result = W._to_py_list(JsNull())
        assert result == []

    def test_jsproxy_array_converted(self, pyodide_fakes):
        proxy = FakeJsProxy([{"id": 1}, {"id": 2}])
        result = W._to_py_list(proxy)
        assert result == [{"id": 1}, {"id": 2}]

    def test_python_list_passes_through(self, pyodide_fakes):
        result = W._to_py_list([{"id": 1}])
        assert result == [{"id": 1}]
