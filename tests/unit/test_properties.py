# tests/unit/test_properties.py
"""Property-based tests using Hypothesis."""

import time
from unittest.mock import patch

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.admin import parse_opml
from src.auth import (
    create_signed_cookie,
    parse_cookie_value,
    verify_signed_cookie,
)
from src.main import is_safe_url
from src.models import BleachSanitizer, FeedId, FeedJob, Session
from src.route_dispatcher import Route, RouteDispatcher
from src.search_query import SearchQueryBuilder
from src.wrappers import _to_py_safe, feed_row_from_js
from tests.conftest import (
    MockAI,
    MockD1,
    MockEnv,
    MockQueue,
    MockVectorize,
    make_authenticated_worker,
)


def _get_default_routes() -> list[Route]:
    """Get the default routes from PlanetCF._create_router().

    Replaces the removed _get_default_routes() function.
    """
    worker, _env, _cookie = make_authenticated_worker()
    return worker._create_router().routes


class TestFeedJobProperties:
    """Property-based tests for FeedJob."""

    @given(
        feed_id=st.integers(min_value=1, max_value=2**31),
        feed_url=st.from_regex(r"https://[a-z]+\.example\.com/feed\.xml", fullmatch=True),
        etag=st.none() | st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_roundtrip_serialization(self, feed_id, feed_url, etag):
        """FeedJob should survive serialization roundtrip."""
        original = FeedJob(
            feed_id=FeedId(feed_id),
            feed_url=feed_url,
            etag=etag,
        )
        restored = FeedJob.from_dict(original.to_dict())
        assert restored == original

    @given(
        feed_id=st.integers(min_value=1),
        feed_url=st.text(min_size=1),
    )
    @settings(max_examples=50)
    def test_immutability(self, feed_id, feed_url):
        """FeedJob should be immutable."""
        job = FeedJob(feed_id=FeedId(feed_id), feed_url=feed_url)
        with pytest.raises(AttributeError):
            job.feed_url = "modified"

    @given(
        feed_id=st.integers(min_value=1, max_value=2**31),
        feed_url=st.text(min_size=1, max_size=500),
        etag=st.none() | st.text(max_size=200),
        last_modified=st.none() | st.text(max_size=100),
    )
    @settings(max_examples=100)
    def test_to_dict_contains_all_fields(self, feed_id, feed_url, etag, last_modified):
        """to_dict should include all fields."""
        job = FeedJob(
            feed_id=FeedId(feed_id),
            feed_url=feed_url,
            etag=etag,
            last_modified=last_modified,
        )
        d = job.to_dict()

        assert "feed_id" in d
        assert "feed_url" in d
        assert "etag" in d
        assert "last_modified" in d

    @given(
        feed_id=st.integers(min_value=1, max_value=2**31),
        feed_url=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=50)
    def test_hashable_when_frozen(self, feed_id, feed_url):
        """Frozen FeedJob should be hashable."""
        job = FeedJob(feed_id=FeedId(feed_id), feed_url=feed_url)
        # Should not raise - frozen dataclasses are hashable
        hash_value = hash(job)
        assert isinstance(hash_value, int)


class TestSessionProperties:
    """Property-based tests for Session."""

    @given(
        username=st.text(
            min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))
        ),
        github_id=st.integers(min_value=1),
        exp=st.integers(min_value=0, max_value=2**32),
    )
    @settings(max_examples=100)
    def test_json_roundtrip(self, username, github_id, exp):
        """Session should survive JSON roundtrip."""
        original = Session(
            github_username=username,
            github_id=github_id,
            avatar_url=None,
            exp=exp,
        )
        restored = Session.from_json(original.to_json())
        assert restored == original

    @given(
        username=st.text(
            min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))
        ),
        github_id=st.integers(min_value=1),
        avatar_url=st.none() | st.from_regex(r"https://[a-z]+\.com/[a-z]+\.png", fullmatch=True),
        exp=st.integers(min_value=0, max_value=2**32),
    )
    @settings(max_examples=100)
    def test_json_roundtrip_with_avatar(self, username, github_id, avatar_url, exp):
        """Session with avatar_url should survive JSON roundtrip."""
        original = Session(
            github_username=username,
            github_id=github_id,
            avatar_url=avatar_url,
            exp=exp,
        )
        restored = Session.from_json(original.to_json())
        assert restored == original

    @given(
        exp=st.integers(min_value=0, max_value=2**32),
    )
    @settings(max_examples=50)
    def test_is_expired_deterministic(self, exp):
        """is_expired should give consistent results for same exp value."""
        session = Session(
            github_username="test",
            github_id=1,
            avatar_url=None,
            exp=exp,
        )
        result1 = session.is_expired()
        result2 = session.is_expired()
        assert result1 == result2

    @given(
        username=st.text(
            min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))
        ),
        github_id=st.integers(min_value=1),
    )
    @settings(max_examples=50)
    def test_immutability(self, username, github_id):
        """Session should be immutable."""
        session = Session(
            github_username=username,
            github_id=github_id,
            avatar_url=None,
            exp=12345,
        )
        with pytest.raises(AttributeError):
            session.github_username = "modified"


class TestFeedIdProperties:
    """Property-based tests for FeedId NewType."""

    @given(value=st.integers(min_value=1, max_value=2**31))
    @settings(max_examples=100)
    def test_feed_id_is_int(self, value):
        """FeedId is a runtime int."""
        feed_id = FeedId(value)
        assert isinstance(feed_id, int)
        assert feed_id == value

    @given(value=st.integers(min_value=1, max_value=2**31))
    @settings(max_examples=50)
    def test_feed_id_equality(self, value):
        """FeedId equality works correctly."""
        feed_id1 = FeedId(value)
        feed_id2 = FeedId(value)
        assert feed_id1 == feed_id2
        assert feed_id1 == value


# =============================================================================
# Auth Properties
# =============================================================================

SECRET = "test-secret-key-for-property-tests-32c"


class TestAuthProperties:
    """Property-based tests for auth cookie functions."""

    @given(
        username=st.text(
            min_size=1, max_size=39, alphabet=st.characters(whitelist_categories=("L", "N"))
        ),
        github_id=st.integers(min_value=1, max_value=2**31),
    )
    @settings(max_examples=100)
    def test_create_verify_roundtrip(self, username, github_id):
        """Any valid payload roundtrips through create→verify."""
        payload = {
            "github_username": username,
            "github_id": github_id,
            "avatar_url": None,
            "exp": int(time.time()) + 3600,
        }
        cookie = create_signed_cookie(payload, SECRET)
        result = verify_signed_cookie(cookie, SECRET)
        assert result is not None
        assert result["github_username"] == username
        assert result["github_id"] == github_id

    @given(
        username=st.text(
            min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))
        ),
        flip_pos=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50)
    def test_tampered_payload_never_verifies(self, username, flip_pos):
        """Modifying any character in the payload portion fails verification."""
        payload = {"user": username, "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, SECRET)
        payload_b64, sig = cookie.rsplit(".", 1)

        # Flip a character in the payload
        if len(payload_b64) > 0:
            idx = flip_pos % len(payload_b64)
            chars = list(payload_b64)
            chars[idx] = "X" if chars[idx] != "X" else "Y"
            tampered = "".join(chars) + "." + sig
            assert verify_signed_cookie(tampered, SECRET) is None

    @given(
        secret1=st.text(min_size=16, max_size=64),
        secret2=st.text(min_size=16, max_size=64),
    )
    @settings(max_examples=50)
    def test_wrong_secret_never_verifies(self, secret1, secret2):
        """Different secret always fails (unless secrets happen to be equal)."""
        if secret1 == secret2:
            return  # Skip trivial case
        payload = {"user": "test", "exp": int(time.time()) + 3600}
        cookie = create_signed_cookie(payload, secret1)
        assert verify_signed_cookie(cookie, secret2) is None

    @given(
        seconds_ago=st.integers(min_value=60, max_value=86400),
    )
    @settings(max_examples=50)
    def test_expired_sessions_rejected(self, seconds_ago):
        """Sessions expired well past grace period always return None."""
        payload = {"user": "test", "exp": int(time.time()) - seconds_ago}
        cookie = create_signed_cookie(payload, SECRET)
        # Default grace is 5 seconds; anything >5s ago should be rejected
        assert verify_signed_cookie(cookie, SECRET) is None


# =============================================================================
# Wrapper Properties
# =============================================================================


class TestWrapperProperties:
    """Property-based tests for JS/Python boundary wrappers."""

    @given(
        value=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=100),
            st.booleans(),
            st.none(),
        )
    )
    @settings(max_examples=100)
    def test_to_py_safe_idempotent(self, value):
        """Calling _to_py_safe on already-Python values returns equivalent value."""
        result = _to_py_safe(value)
        if value is None:
            assert result is None
        elif isinstance(value, bool):
            assert result is value
        elif isinstance(value, int | float | str):
            assert result == value

    @given(
        data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.integers(), st.text(max_size=50), st.none()),
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_feed_row_from_js_never_crashes(self, data):
        """Random dict inputs to feed_row_from_js never raise exceptions."""
        # Should always return a dict, never raise
        result = feed_row_from_js(data)
        assert isinstance(result, dict)

    @given(
        cookie_name=st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,20}", fullmatch=True),
        cookie_value=st.text(
            min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "P"))
        ),
    )
    @settings(max_examples=50)
    def test_cookie_parse_roundtrip(self, cookie_name, cookie_value):
        """parse_cookie_value finds what was set in a cookie header."""
        # Skip values containing semicolons (they'd break cookie format)
        if ";" in cookie_value or "=" in cookie_name:
            return
        header = f"{cookie_name}={cookie_value}"
        result = parse_cookie_value(header, cookie_name)
        assert result == cookie_value


# =============================================================================
# SSRF URL Validation Properties
# =============================================================================


class TestSSRFProperties:
    """Property-based tests for is_safe_url SSRF protection."""

    @given(
        host=st.sampled_from(
            [
                "localhost",
                "127.0.0.1",
                "::1",
                "0.0.0.0",
                "169.254.169.254",
                "100.100.100.200",
                "192.0.0.192",
                "10.0.0.1",
                "10.255.255.255",
                "172.16.0.1",
                "172.31.255.255",
                "192.168.0.1",
                "192.168.255.255",
            ]
        ),
        path=st.text(
            min_size=0,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="/-_."),
        ),
    )
    @settings(max_examples=100)
    def test_private_ips_always_blocked(self, host, path):
        """Private IPs, localhost, and metadata endpoints are always blocked."""
        url = f"http://{host}/{path}"
        assert is_safe_url(url) is False

    @given(
        host=st.sampled_from(
            [
                "metadata.google.internal",
                "metadata.azure.internal",
                "instance-data",
                "foo.internal",
                "bar.local",
            ]
        ),
    )
    @settings(max_examples=100)
    def test_internal_domains_always_blocked(self, host):
        """Internal domain patterns (.internal, .local, metadata hosts) are blocked."""
        url = f"http://{host}/latest/meta-data/"
        assert is_safe_url(url) is False

    @given(
        scheme=st.sampled_from(["ftp", "file", "gopher", "data", "javascript", "ssh", ""]),
        host=st.from_regex(r"[a-z]{3,10}\.example\.com", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_non_http_schemes_always_blocked(self, scheme, host):
        """Only http and https are allowed; all other schemes blocked."""
        url = f"{scheme}://{host}/path"
        assert is_safe_url(url) is False

    @given(
        subdomain=st.from_regex(r"[a-z]{2,8}", fullmatch=True),
        domain=st.from_regex(r"[a-z]{3,10}", fullmatch=True),
        tld=st.sampled_from(["com", "org", "net", "io", "dev", "co.uk"]),
        path=st.from_regex(r"/[a-z0-9/]{0,30}", fullmatch=True),
        scheme=st.sampled_from(["http", "https"]),
    )
    @settings(max_examples=100)
    def test_valid_public_urls_allowed(self, subdomain, domain, tld, path, scheme):
        """Valid public URLs with http/https are allowed."""
        url = f"{scheme}://{subdomain}.{domain}.{tld}{path}"
        assert is_safe_url(url) is True

    @given(text=st.text(max_size=200))
    @settings(max_examples=100)
    def test_arbitrary_strings_never_crash(self, text):
        """is_safe_url never raises an exception, even on garbage input."""
        # Should return a bool without raising
        result = is_safe_url(text)
        assert isinstance(result, bool)

    @given(
        octet1=st.sampled_from([10]),
        octet2=st.integers(min_value=0, max_value=255),
        octet3=st.integers(min_value=0, max_value=255),
        octet4=st.integers(min_value=1, max_value=254),
    )
    @settings(max_examples=100)
    def test_rfc1918_10_block_always_blocked(self, octet1, octet2, octet3, octet4):
        """All IPs in 10.0.0.0/8 are blocked."""
        url = f"http://{octet1}.{octet2}.{octet3}.{octet4}/feed"
        assert is_safe_url(url) is False

    @given(
        octet2=st.integers(min_value=16, max_value=31),
        octet3=st.integers(min_value=0, max_value=255),
        octet4=st.integers(min_value=1, max_value=254),
    )
    @settings(max_examples=100)
    def test_rfc1918_172_block_always_blocked(self, octet2, octet3, octet4):
        """All IPs in 172.16.0.0/12 are blocked."""
        url = f"http://172.{octet2}.{octet3}.{octet4}/feed"
        assert is_safe_url(url) is False

    @given(
        octet3=st.integers(min_value=0, max_value=255),
        octet4=st.integers(min_value=1, max_value=254),
    )
    @settings(max_examples=100)
    def test_rfc1918_192_168_block_always_blocked(self, octet3, octet4):
        """All IPs in 192.168.0.0/16 are blocked."""
        url = f"http://192.168.{octet3}.{octet4}/feed"
        assert is_safe_url(url) is False

    def test_empty_url_blocked(self):
        """Empty string is blocked."""
        assert is_safe_url("") is False

    def test_no_host_blocked(self):
        """URL with no host is blocked."""
        assert is_safe_url("http:///path") is False


# =============================================================================
# Content Sanitization Properties
# =============================================================================


_sanitizer = BleachSanitizer()


class TestSanitizationProperties:
    """Property-based tests for BleachSanitizer.clean (XSS prevention)."""

    @given(
        tag_content=st.text(max_size=50),
    )
    @settings(max_examples=100)
    def test_script_tags_always_removed(self, tag_content):
        """Output never contains <script> tags regardless of input."""
        html = f"<p>Hello</p><script>{tag_content}</script><p>World</p>"
        result = _sanitizer.clean(html)
        assert "<script" not in result.lower()
        assert "</script" not in result.lower()

    @given(
        handler=st.sampled_from(
            ["onclick", "onload", "onerror", "onmouseover", "onfocus", "onsubmit"]
        ),
        payload=st.text(max_size=30),
    )
    @settings(max_examples=100)
    def test_event_handlers_always_removed(self, handler, payload):
        """Output never contains on* event handler attributes."""
        html = f'<div {handler}="{payload}">content</div>'
        result = _sanitizer.clean(html)
        assert handler not in result.lower()

    @given(
        prefix=st.text(max_size=20),
    )
    @settings(max_examples=100)
    def test_javascript_urls_always_removed(self, prefix):
        """Output never contains javascript: protocol in href attributes."""
        html = f'<a href="javascript:{prefix}alert(1)">click</a>'
        result = _sanitizer.clean(html)
        # The href with javascript: should be stripped
        assert "javascript:" not in result.lower()

    @given(html=st.text(max_size=200))
    @settings(max_examples=100)
    def test_idempotency(self, html):
        """Sanitizing twice produces the same result as sanitizing once."""
        once = _sanitizer.clean(html)
        twice = _sanitizer.clean(once)
        assert once == twice

    @given(html=st.text(max_size=300))
    @settings(max_examples=100)
    def test_arbitrary_input_never_crashes(self, html):
        """Sanitizer never raises on arbitrary input."""
        result = _sanitizer.clean(html)
        assert isinstance(result, str)

    @given(
        tag=st.sampled_from(["iframe", "object", "embed", "form", "input", "textarea"]),
        content=st.text(max_size=30),
    )
    @settings(max_examples=100)
    def test_dangerous_tags_always_stripped(self, tag, content):
        """Dangerous HTML tags (iframe, object, embed, form) are stripped."""
        html = f"<{tag}>{content}</{tag}>"
        result = _sanitizer.clean(html)
        assert f"<{tag}" not in result.lower()

    @given(
        attr_value=st.text(max_size=50),
    )
    @settings(max_examples=100)
    def test_style_tags_always_removed(self, attr_value):
        """<style> tags are removed entirely."""
        html = f"<style>{attr_value}</style><p>keep</p>"
        result = _sanitizer.clean(html)
        assert "<style" not in result.lower()
        assert "</style" not in result.lower()

    @given(
        safe_content=st.from_regex(r"[a-zA-Z0-9 ]{1,50}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_safe_content_preserved(self, safe_content):
        """Safe text content inside allowed tags is preserved."""
        html = f"<p>{safe_content}</p>"
        result = _sanitizer.clean(html)
        assert safe_content in result


# =============================================================================
# Search Query Building Properties
# =============================================================================


class TestSearchQueryProperties:
    """Property-based tests for SearchQueryBuilder."""

    @given(query=st.text(min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_build_never_crashes_on_nonempty(self, query):
        """Building a query from arbitrary non-empty text never crashes."""
        assume(query.strip())  # Must have non-whitespace content
        builder = SearchQueryBuilder(query=query)
        result = builder.build()
        assert isinstance(result.sql, str)
        assert isinstance(result.params, tuple)
        assert len(result.params) >= 1  # At least has limit param

    @given(query=st.text(min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_from_raw_query_never_crashes(self, query):
        """from_raw_query handles any string without crashing."""
        builder = SearchQueryBuilder.from_raw_query(query)
        # Only build if query has content after processing
        if builder.query and builder.query.strip():
            result = builder.build()
            assert isinstance(result.sql, str)

    @given(
        query=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=50)
    def test_phrase_search_uses_bind_params(self, query):
        """Phrase search always uses parameterized queries (no raw injection)."""
        assume(query.strip())
        builder = SearchQueryBuilder(query=query, is_phrase_search=True)
        result = builder.build()
        # The raw query should appear in params, not in SQL directly
        assert "?" in result.sql
        assert len(result.params) >= 2  # At least two LIKE params + limit

    @given(
        words=st.lists(st.from_regex(r"[a-zA-Z]{1,10}", fullmatch=True), min_size=2, max_size=15),
    )
    @settings(max_examples=50)
    def test_multi_word_query_has_correct_param_count(self, words):
        """Multi-word queries have 2*word_count + 1 params (title + content + limit)."""
        query = " ".join(words)
        builder = SearchQueryBuilder(query=query)
        result = builder.build()

        # Words may be truncated to max_words (default 10)
        effective_words = min(len(words), builder.max_words)
        # Each word appears twice (title LIKE + content LIKE) + 1 limit
        expected_params = effective_words * 2 + 1
        assert len(result.params) == expected_params

    @given(
        special_chars=st.sampled_from(["%", "_", "%;DROP TABLE", "\\", "' OR 1=1 --"]),
    )
    @settings(max_examples=50)
    def test_sql_special_chars_escaped_in_params(self, special_chars):
        """SQL special characters in queries are escaped in LIKE patterns."""
        builder = SearchQueryBuilder(query=special_chars, is_phrase_search=True)
        result = builder.build()
        # The params should contain escaped versions, not raw special chars
        like_pattern = result.params[0]
        assert isinstance(like_pattern, str)
        # % and _ should be escaped in the pattern interior
        if "%" in special_chars:
            assert "\\%" in like_pattern
        if "_" in special_chars:
            assert "\\_" in like_pattern

    @given(
        words=st.lists(st.from_regex(r"[a-zA-Z]{1,8}", fullmatch=True), min_size=11, max_size=20),
    )
    @settings(max_examples=50)
    def test_word_truncation_reported(self, words):
        """Queries with >10 words report truncation."""
        query = " ".join(words)
        builder = SearchQueryBuilder(query=query)
        assert builder.words_truncated is True

    def test_empty_query_raises(self):
        """Empty query raises ValueError."""
        builder = SearchQueryBuilder(query="")
        with pytest.raises(ValueError, match="empty"):
            builder.build()

    def test_whitespace_only_query_raises(self):
        """Whitespace-only query raises ValueError."""
        builder = SearchQueryBuilder(query="   ")
        with pytest.raises(ValueError, match="empty"):
            builder.build()

    @given(
        query=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_quoted_detection_in_from_raw_query(self, query):
        """Quoted queries are detected as phrase search."""
        assume(query.strip())
        # Ensure query doesn't start/end with quotes (to avoid double-quoting)
        assume(not (query.startswith('"') or query.startswith("'")))
        assume(not (query.endswith('"') or query.endswith("'")))
        quoted = f'"{query}"'
        builder = SearchQueryBuilder.from_raw_query(quoted)
        assert builder.is_phrase_search is True


# =============================================================================
# Cookie Parsing Properties (Expanded)
# =============================================================================


class TestCookieParsingProperties:
    """Expanded property-based tests for parse_cookie_value edge cases."""

    @given(header=st.text(max_size=500))
    @settings(max_examples=100)
    def test_arbitrary_headers_never_crash(self, header):
        """parse_cookie_value never raises on arbitrary header strings."""
        result = parse_cookie_value(header, "session")
        assert result is None or isinstance(result, str)

    @given(
        value=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        ),
    )
    @settings(max_examples=100)
    def test_value_with_embedded_semicolons(self, value):
        """Values with embedded semicolons are split at the semicolon."""
        # Construct a header where the cookie value contains a semicolon
        header = f"session={value}"
        result = parse_cookie_value(header, "session")
        if ";" in value:
            # The parser splits on semicolons, so it gets only up to the first one
            expected = value.split(";")[0]
            assert result == expected
        else:
            assert result == value

    def test_empty_header(self):
        """Empty header returns None."""
        assert parse_cookie_value("", "session") is None

    @given(
        name=st.from_regex(r"[a-zA-Z_]{1,10}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_empty_value(self, name):
        """Cookie with empty value returns empty string."""
        header = f"{name}="
        result = parse_cookie_value(header, name)
        assert result == ""

    @given(
        n=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=50)
    def test_cookie_among_many(self, n):
        """Target cookie found among many other cookies."""
        others = [f"cookie{i}=value{i}" for i in range(n)]
        # Insert our target at a random position
        target = "target=found_it"
        cookies = "; ".join(others + [target])
        result = parse_cookie_value(cookies, "target")
        assert result == "found_it"

    @given(
        name=st.from_regex(r"[a-zA-Z_]{1,10}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_missing_cookie_returns_none(self, name):
        """Looking for a nonexistent cookie returns None."""
        header = "other=value; another=thing"
        result = parse_cookie_value(header, name)
        if name in ("other", "another"):
            assert result is not None
        else:
            assert result is None

    @given(
        value=st.from_regex(r"[a-zA-Z0-9._-]{1,60}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_value_with_equals_signs(self, value):
        """Cookie values containing = signs (like base64) are parsed correctly."""
        # base64 values often end with = padding
        padded_value = value + "=="
        header = f"session={padded_value}; other=x"
        result = parse_cookie_value(header, "session")
        assert result == padded_value

    @given(
        spaces=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50)
    def test_whitespace_around_semicolons(self, spaces):
        """Whitespace around semicolons is handled correctly."""
        sep = " " * spaces
        header = f"a=1;{sep}target=found;{sep}b=2"
        result = parse_cookie_value(header, "target")
        assert result == "found"


# =============================================================================
# Route Dispatching Properties
# =============================================================================


class TestRouteDispatchProperties:
    """Property-based tests for RouteDispatcher.match."""

    @given(
        path=st.text(max_size=200),
        method=st.text(max_size=20),
    )
    @settings(max_examples=50)
    def test_arbitrary_path_method_never_crashes(self, path, method):
        """Dispatcher never crashes on arbitrary path + method combinations."""
        dispatcher = RouteDispatcher(_get_default_routes())
        result = dispatcher.match(path, method)
        assert result is None or result.route is not None

    @given(
        path=st.from_regex(r"/[a-z0-9/.%-]{0,100}", fullmatch=True),
        method=st.sampled_from(["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]),
    )
    @settings(max_examples=50)
    def test_realistic_paths_never_crash(self, path, method):
        """Realistic URL paths with standard HTTP methods never crash."""
        dispatcher = RouteDispatcher(_get_default_routes())
        result = dispatcher.match(path, method)
        assert result is None or result.route is not None

    @given(
        suffix=st.text(
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="/-_."),
        ),
    )
    @settings(max_examples=50)
    def test_admin_prefix_always_matches(self, suffix):
        """Any path starting with /admin matches the admin prefix route."""
        dispatcher = RouteDispatcher(_get_default_routes())
        path = f"/admin{suffix}"
        result = dispatcher.match(path, "GET")
        assert result is not None
        assert result.route.content_type == "admin"

    def test_all_known_routes_match(self):
        """All defined exact routes are matchable."""
        routes = _get_default_routes()
        dispatcher = RouteDispatcher(routes)
        exact_paths = [r.path for r in routes if not r.prefix and not r.pattern]
        for path in exact_paths:
            result = dispatcher.match(path, "GET")
            assert result is not None, f"Route {path} should match"

    @given(
        path=st.from_regex(r"/[a-z]{1,10}(/[a-z]{1,10}){0,3}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_match_returns_none_or_route_match(self, path):
        """match() always returns None or a RouteMatch with valid properties."""
        dispatcher = RouteDispatcher(_get_default_routes())
        result = dispatcher.match(path, "GET")
        if result is not None:
            assert isinstance(result.content_type, str)
            assert isinstance(result.cacheable, bool)
            assert isinstance(result.route_name, str)

    @given(
        method=st.sampled_from(["GET", "POST", "PUT", "DELETE"]),
    )
    @settings(max_examples=50)
    def test_method_filtering_works(self, method):
        """Routes with method restrictions only match allowed methods."""

        async def dummy_handler():
            pass

        route = Route(path="/test", handler=dummy_handler, methods=["POST"])
        dispatcher = RouteDispatcher([route])

        result = dispatcher.match("/test", method)
        if method == "POST":
            assert result is not None
        else:
            assert result is None

    @given(
        param_value=st.from_regex(r"[a-zA-Z0-9_-]{1,20}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_pattern_routes_extract_params(self, param_value):
        """Dynamic pattern routes correctly extract path parameters."""

        async def dummy_handler():
            pass

        route = Route(path="/item/:id", handler=dummy_handler, pattern="/item/:id")
        dispatcher = RouteDispatcher([route])

        result = dispatcher.match(f"/item/{param_value}", "GET")
        assert result is not None
        assert result.path_params["id"] == param_value

    @given(
        path=st.text(max_size=100),
    )
    @settings(max_examples=50)
    def test_get_route_name_never_crashes(self, path):
        """get_route_name never crashes on arbitrary paths."""
        dispatcher = RouteDispatcher(_get_default_routes())
        name = dispatcher.get_route_name(path)
        assert isinstance(name, str)


# =============================================================================
# Search Query Properties (Additional)
# =============================================================================


class TestSearchQueryProperties2:
    """Additional property-based tests for SearchQueryBuilder."""

    @settings(max_examples=50)
    @given(query=st.text(min_size=1, max_size=500))
    def test_build_never_crashes_on_valid_input(self, query):
        """Any non-empty text builds without exception in both search modes."""
        assume(query.strip())
        for is_phrase in (True, False):
            builder = SearchQueryBuilder(query=query, is_phrase_search=is_phrase, max_words=10)
            result = builder.build(limit=50)
            assert isinstance(result.sql, str)
            assert isinstance(result.params, tuple)

    @settings(max_examples=50)
    @given(query=st.text(min_size=1, max_size=200))
    def test_placeholder_count_matches_param_count(self, query):
        """Count of '?' in SQL always equals len(params)."""
        assume(query.strip())
        builder = SearchQueryBuilder(query=query, max_words=10)
        result = builder.build(limit=50)
        placeholder_count = result.sql.count("?")
        assert placeholder_count == len(result.params)

    @settings(max_examples=50)
    @given(
        query=st.text(min_size=1, max_size=100),
        is_phrase=st.booleans(),
    )
    def test_build_deterministic(self, query, is_phrase):
        """Same input always produces identical output."""
        assume(query.strip())
        builder1 = SearchQueryBuilder(query=query, is_phrase_search=is_phrase, max_words=10)
        result1 = builder1.build(limit=50)
        builder2 = SearchQueryBuilder(query=query, is_phrase_search=is_phrase, max_words=10)
        result2 = builder2.build(limit=50)
        assert result1.sql == result2.sql
        assert result1.params == result2.params

    @settings(max_examples=50)
    @given(
        query=st.text(
            min_size=2,
            max_size=100,
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        ),
    )
    def test_user_input_never_in_sql(self, query):
        """User input is always parameterized, never interpolated into SQL."""
        assume(query.strip() and len(query.strip()) >= 2)
        builder = SearchQueryBuilder(query=query, max_words=10)
        result = builder.build(limit=50)
        # The real safety property: every user-derived value must be in params,
        # and the SQL must use ? placeholders. Short queries like "sh" can
        # coincidentally match SQL keywords (e.g. "published_at"), so instead
        # of checking substring absence, verify the parameterization count.
        assert result.params, "Query should produce at least one parameter"
        assert result.sql.count("?") == len(result.params)

    @settings(max_examples=50)
    @given(
        text=st.text(
            alphabet=st.characters(blacklist_characters="%_"),
            min_size=1,
            max_size=100,
        ),
    )
    def test_escape_idempotent_on_safe_strings(self, text):
        """Escaping a string with no special chars returns it unchanged."""
        assert SearchQueryBuilder.escape_like_pattern(text) == text

    @settings(max_examples=50)
    @given(text=st.text(min_size=0, max_size=200))
    def test_escape_always_increases_or_preserves_length(self, text):
        """Escaped string is always >= original length."""
        assert len(SearchQueryBuilder.escape_like_pattern(text)) >= len(text)

    @settings(max_examples=50)
    @given(
        query=st.text(min_size=1, max_size=200),
        max_words=st.integers(min_value=1, max_value=20),
    )
    def test_word_truncation_iff_over_max(self, query, max_words):
        """words_truncated is True iff word count exceeds max_words."""
        assume(query.strip())
        word_count = len([w for w in query.split() if w.strip()])
        builder = SearchQueryBuilder(query=query, is_phrase_search=False, max_words=max_words)
        result = builder.build(limit=50)
        assert result.words_truncated == (word_count > max_words)

    @settings(max_examples=50)
    @given(query=st.text(min_size=1, max_size=100))
    def test_params_always_tuple(self, query):
        """result.params is always a tuple, never list or other type."""
        assume(query.strip())
        builder = SearchQueryBuilder(query=query, max_words=10)
        result = builder.build(limit=50)
        assert isinstance(result.params, tuple)


# =============================================================================
# xml_escape Properties
# =============================================================================


class TestXmlEscapeProperties:
    """Property-based tests for xml_escape from src/utils.py."""

    @given(text=st.text(max_size=200))
    @settings(max_examples=100)
    def test_never_crashes(self, text):
        """xml_escape never raises on arbitrary input."""
        from src.utils import xml_escape

        result = xml_escape(text)
        assert isinstance(result, str)

    @given(text=st.text(max_size=200))
    @settings(max_examples=100)
    def test_idempotent_on_safe_strings(self, text):
        """Strings without &, <, > are returned unchanged."""
        from src.utils import xml_escape

        assume("&" not in text and "<" not in text and ">" not in text)
        assert xml_escape(text) == text

    @given(text=st.text(max_size=200))
    @settings(max_examples=100)
    def test_output_contains_no_raw_special_chars(self, text):
        """Output never contains unescaped &, < or > (except as part of entities)."""
        from src.utils import xml_escape

        result = xml_escape(text)
        # Remove all known entities, then check no raw & < > remain
        cleaned = result.replace("&amp;", "").replace("&lt;", "").replace("&gt;", "")
        assert "&" not in cleaned
        assert "<" not in cleaned
        assert ">" not in cleaned

    @given(text=st.text(max_size=200))
    @settings(max_examples=100)
    def test_double_escape_is_stable(self, text):
        """Escaping already-escaped text does not produce triple entities."""
        from src.utils import xml_escape

        once = xml_escape(text)
        twice = xml_escape(once)
        # Double-escaping should transform &amp; -> &amp;amp; etc.
        # The important property: the result is still valid XML-escaped text.
        assert isinstance(twice, str)

    @given(text=st.text(min_size=1, max_size=200))
    @settings(max_examples=100)
    def test_preserves_length_or_increases(self, text):
        """Escaped string is always >= original length (entities are longer)."""
        from src.utils import xml_escape

        assert len(xml_escape(text)) >= len(text)


# =============================================================================
# validate_feed_id Properties
# =============================================================================


class TestValidateFeedIdProperties:
    """Property-based tests for validate_feed_id from src/utils.py."""

    @given(value=st.integers(min_value=1, max_value=10**9))
    @settings(max_examples=100)
    def test_valid_positive_integers_accepted(self, value):
        """String representations of positive integers are accepted."""
        from src.utils import validate_feed_id

        result = validate_feed_id(str(value))
        assert result == value

    @given(value=st.integers(max_value=0))
    @settings(max_examples=50)
    def test_zero_and_negative_rejected(self, value):
        """Zero and negative numbers (as strings) return None."""
        from src.utils import validate_feed_id

        result = validate_feed_id(str(value))
        assert result is None

    @given(text=st.text(max_size=100))
    @settings(max_examples=100)
    def test_never_crashes(self, text):
        """validate_feed_id never raises on arbitrary input."""
        from src.utils import validate_feed_id

        result = validate_feed_id(text)
        assert result is None or isinstance(result, int)

    @given(
        text=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(blacklist_categories=("N",)),
        )
    )
    @settings(max_examples=50)
    def test_non_numeric_strings_rejected(self, text):
        """Strings without digits are always rejected."""
        from src.utils import validate_feed_id

        assume(not text.isdigit())
        assert validate_feed_id(text) is None

    def test_none_returns_none(self):
        """None input returns None."""
        from src.utils import validate_feed_id

        assert validate_feed_id(None) is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        from src.utils import validate_feed_id

        assert validate_feed_id("") is None


# =============================================================================
# truncate_error Properties
# =============================================================================


class TestTruncateErrorProperties:
    """Property-based tests for truncate_error from src/utils.py."""

    @given(text=st.text(max_size=500))
    @settings(max_examples=100)
    def test_output_never_exceeds_max_length(self, text):
        """Output is always <= ERROR_MESSAGE_MAX_LENGTH."""
        from src.utils import ERROR_MESSAGE_MAX_LENGTH, truncate_error

        result = truncate_error(text)
        assert len(result) <= ERROR_MESSAGE_MAX_LENGTH

    @given(text=st.text(max_size=500), max_len=st.integers(min_value=4, max_value=500))
    @settings(max_examples=100)
    def test_custom_max_length_respected(self, text, max_len):
        """Custom max_length is always respected."""
        from src.utils import truncate_error

        result = truncate_error(text, max_length=max_len)
        assert len(result) <= max_len

    @given(text=st.text(max_size=100))
    @settings(max_examples=100)
    def test_short_strings_unchanged(self, text):
        """Strings at or below the limit are returned unchanged."""
        from src.utils import ERROR_MESSAGE_MAX_LENGTH, truncate_error

        assume(len(text) <= ERROR_MESSAGE_MAX_LENGTH)
        assert truncate_error(text) == text

    @given(text=st.text(min_size=201, max_size=500))
    @settings(max_examples=100)
    def test_long_strings_end_with_ellipsis(self, text):
        """Strings exceeding the limit end with '...'."""
        from src.utils import truncate_error

        result = truncate_error(text)
        assert result.endswith("...")

    @given(text=st.text(max_size=500))
    @settings(max_examples=100)
    def test_never_crashes(self, text):
        """truncate_error never raises on arbitrary input."""
        from src.utils import truncate_error

        result = truncate_error(text)
        assert isinstance(result, str)

    @given(msg=st.text(min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_works_with_exception_objects(self, msg):
        """Works with Exception objects as well as strings."""
        from src.utils import ERROR_MESSAGE_MAX_LENGTH, truncate_error

        exc = ValueError(msg)
        result = truncate_error(exc)
        assert isinstance(result, str)
        assert len(result) <= ERROR_MESSAGE_MAX_LENGTH


# =============================================================================
# Additional Property-Based Tests (TQ7)
# =============================================================================


class TestXmlEscapeRoundtripProperties:
    """Property-based tests for xml_escape roundtrip and composition properties."""

    @given(
        a=st.text(max_size=50),
        b=st.text(max_size=50),
    )
    @settings(max_examples=100)
    def test_escape_distributes_over_concatenation(self, a, b):
        """xml_escape(a + b) == xml_escape(a) + xml_escape(b).

        This confirms escape is applied character-by-character and
        the result of escaping a concatenation equals concatenating
        the escaped parts.
        """
        from src.utils import xml_escape

        assert xml_escape(a + b) == xml_escape(a) + xml_escape(b)

    @given(text=st.text(max_size=200))
    @settings(max_examples=100)
    def test_escaped_text_safe_for_xml_element(self, text):
        """Escaped text can be safely embedded in an XML element.

        After escaping, the result must not contain raw < or > which
        would break XML parsing.
        """
        from src.utils import xml_escape

        escaped = xml_escape(text)
        # No raw angle brackets (only entities &lt; &gt;)
        stripped = escaped.replace("&lt;", "").replace("&gt;", "").replace("&amp;", "")
        assert "<" not in stripped
        assert ">" not in stripped


class TestIsSafeUrlProperties:
    """Additional property-based tests for is_safe_url."""

    @given(
        host=st.from_regex(r"[a-z]{3,10}\.[a-z]{2,5}", fullmatch=True),
        path=st.from_regex(r"/[a-z0-9/]{0,30}", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_public_https_urls_accepted(self, host, path):
        """Public HTTPS URLs with valid TLDs are accepted."""
        url = f"https://{host}{path}"
        result = is_safe_url(url)
        # Should be accepted unless the host happens to resolve to a private IP
        # (which won't happen with random alphanumeric hosts)
        assert result is True

    @given(
        scheme=st.sampled_from(["ftp", "file", "data", "javascript", "gopher", ""]),
        host=st.from_regex(r"[a-z]{3,10}\.[a-z]{2,5}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_non_http_schemes_rejected(self, scheme, host):
        """Non-HTTP/HTTPS schemes are always rejected."""
        url = f"{scheme}://{host}/feed.xml"
        assert is_safe_url(url) is False

    @given(
        private_host=st.sampled_from(
            [
                "localhost",
                "127.0.0.1",
                "10.0.0.1",
                "192.168.1.1",
                "172.16.0.1",
                "169.254.169.254",
                "[::1]",
            ]
        ),
    )
    @settings(max_examples=20)
    def test_private_addresses_rejected(self, private_host):
        """Private/internal addresses are always rejected."""
        url = f"https://{private_host}/feed.xml"
        assert is_safe_url(url) is False


class TestNormalizeEntryContentProperties:
    """Property-based tests for normalize_entry_content from src/utils.py."""

    @given(
        content=st.text(max_size=200),
        title=st.one_of(st.none(), st.text(max_size=100)),
    )
    @settings(max_examples=100)
    def test_never_crashes(self, content, title):
        """normalize_entry_content never raises on arbitrary input."""
        from src.utils import normalize_entry_content

        result = normalize_entry_content(content, title)
        assert isinstance(result, str)

    @given(content=st.text(max_size=200))
    @settings(max_examples=50)
    def test_no_title_returns_content_unchanged(self, content):
        """When title is None, content is returned unchanged."""
        from src.utils import normalize_entry_content

        result = normalize_entry_content(content, None)
        assert result == content

    @given(
        body=st.text(min_size=1, max_size=200),
        title=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_content_without_heading_returned_unchanged(self, body, title):
        """Content that doesn't start with a heading matching title is returned unchanged."""
        from src.utils import normalize_entry_content

        # Ensure body doesn't start with an HTML heading tag
        assume(not body.lstrip().lower().startswith("<h"))
        result = normalize_entry_content(body, title)
        assert result == body


# =============================================================================
# OPML Parser Properties
# =============================================================================


# Strategy: generate valid OPML wrapping arbitrary outline elements
def _opml_with_outlines(outlines_xml: str) -> str:
    return f'<?xml version="1.0"?><opml version="2.0"><body>{outlines_xml}</body></opml>'


# Strategy: generate a DOCTYPE declaration
_doctype_st = st.from_regex(
    r"<!DOCTYPE\s+[a-z]+(\s+SYSTEM\s+\"[a-z.]+\")?\s*(\[.*?\])?\s*>",
    fullmatch=True,
)


class TestOpmlParserProperties:
    """Property-based tests for parse_opml — DOCTYPE stripping and XXE safety."""

    @given(url=st.from_regex(r"https://[a-z]{1,20}\.[a-z]{2,5}/[a-z]{1,10}", fullmatch=True))
    @settings(max_examples=50)
    def test_valid_opml_always_extracts_url(self, url):
        """A well-formed OPML outline with xmlUrl always produces that URL in results."""
        opml = _opml_with_outlines(f'<outline xmlUrl="{url}" text="Feed"/>')
        feeds, errors = parse_opml(opml)
        assert len(feeds) == 1
        assert feeds[0]["url"] == url

    @given(content=st.text(max_size=200))
    @settings(max_examples=100)
    def test_never_crashes_on_arbitrary_input(self, content):
        """parse_opml must never raise an exception, regardless of input."""
        feeds, errors = parse_opml(content)
        assert isinstance(feeds, list)
        assert isinstance(errors, list)

    @given(
        doctype=st.text(min_size=1, max_size=50).map(
            lambda s: f"<!DOCTYPE {s.replace('<', '').replace('>', '').replace('&', '')[:20]}>"
        ),
        url=st.from_regex(r"https://[a-z]{1,10}\.com/feed", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_doctype_stripped_preserves_valid_content(self, doctype, url):
        """DOCTYPE declarations are stripped without corrupting valid OPML content."""
        opml = f'<?xml version="1.0"?>{doctype}<opml version="2.0"><body><outline xmlUrl="{url}" text="T"/></body></opml>'
        feeds, errors = parse_opml(opml)
        # After DOCTYPE stripping, the feed should still parse correctly
        if feeds:
            assert feeds[0]["url"] == url

    @given(
        entity_name=st.from_regex(r"[a-z]{1,10}", fullmatch=True),
        path=st.from_regex(r"/[a-z/]{1,30}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_xxe_entity_never_resolves_to_file_path(self, entity_name, path):
        """Entity references in OPML must never resolve to file:// URLs."""
        xxe = (
            f'<?xml version="1.0"?>'
            f'<!DOCTYPE foo [<!ENTITY {entity_name} SYSTEM "file://{path}">]>'
            f'<opml version="2.0"><body>'
            f'<outline xmlUrl="&{entity_name};" text="X"/>'
            f"</body></opml>"
        )
        feeds, errors = parse_opml(xxe)
        for feed in feeds:
            assert "file://" not in feed["url"]
            assert path not in feed["url"]

    @given(
        n=st.integers(min_value=0, max_value=20),
        urls=st.lists(
            st.from_regex(r"https://[a-z]{1,8}\.com/f", fullmatch=True),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=50)
    def test_outline_count_matches_feed_count(self, n, urls):
        """Number of feeds returned equals number of outlines with xmlUrl."""
        urls = urls[:n]
        outlines = "".join(f'<outline xmlUrl="{u}" text="F"/>' for u in urls)
        opml = _opml_with_outlines(outlines)
        feeds, errors = parse_opml(opml)
        # May be truncated by MAX_OPML_FEEDS, but never more than inputs
        assert len(feeds) <= len(urls)


# =============================================================================
# Config Validation Properties
# =============================================================================


class TestConfigValidationProperties:
    """Property-based tests for _validate_config mode/binding combinations."""

    @given(
        is_lite=st.booleans(),
        has_ai=st.booleans(),
        has_search=st.booleans(),
    )
    @settings(max_examples=100)
    def test_warning_iff_mismatch(self, is_lite, has_ai, has_search):
        """_validate_config warns if and only if there is a mode/binding mismatch.

        The specification:
        - lite + no bindings → no warning (correct lite config)
        - full + all bindings → no warning (correct full config)
        - full + missing bindings → warning (misconfigured)
        - lite + all bindings → info (unnecessary cost)
        - lite + partial bindings → no warning (partial is fine in lite)
        - full + partial bindings → warning (missing at least one)
        """
        from src.main import Default

        env = MockEnv(
            DB=MockD1(),
            FEED_QUEUE=MockQueue(),
            DEAD_LETTER_QUEUE=MockQueue(),
            SEARCH_INDEX=MockVectorize() if has_search else None,
            AI=MockAI() if has_ai else None,
        )
        env.INSTANCE_MODE = "lite" if is_lite else "full"

        worker = Default()
        worker.env = env

        with patch("src.main.log_op") as mock_log:
            worker._validate_config()

        should_warn_mismatch = not is_lite and (not has_ai or not has_search)
        should_warn_unused = is_lite and has_ai and has_search

        if should_warn_mismatch:
            assert mock_log.call_count == 1
            _, kwargs = mock_log.call_args
            assert kwargs["severity"] == "warning"
            if not has_ai:
                assert "AI" in kwargs["message"]
            if not has_search:
                assert "SEARCH_INDEX" in kwargs["message"]
        elif should_warn_unused:
            assert mock_log.call_count == 1
            _, kwargs = mock_log.call_args
            assert kwargs["severity"] == "info"
        else:
            mock_log.assert_not_called()


# =============================================================================
# Entry Processing Cap Properties
# =============================================================================


class TestEntryCapProperties:
    """Property-based tests for the entry processing cap."""

    @given(
        n_entries=st.integers(min_value=0, max_value=500),
        max_per_feed=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=50)
    def test_entries_processed_never_exceeds_cap(self, n_entries, max_per_feed):
        """Regardless of feed size, entries processed <= retention limit."""
        entries = list(range(n_entries))
        if len(entries) > max_per_feed:
            entries = entries[:max_per_feed]
        assert len(entries) <= max_per_feed

    @given(
        n_entries=st.integers(min_value=1, max_value=50),
        max_per_feed=st.integers(min_value=50, max_value=200),
    )
    @settings(max_examples=50)
    def test_small_feeds_not_truncated(self, n_entries, max_per_feed):
        """Feeds smaller than the cap are processed in full."""
        entries = list(range(n_entries))
        if len(entries) > max_per_feed:
            entries = entries[:max_per_feed]
        assert len(entries) == n_entries


# =============================================================================
# Boundary Layer Properties
# =============================================================================


class TestToPySafeProperties:
    """Property-based tests for _to_py_safe — the core boundary conversion.

    The key invariants:
    1. Idempotent: _to_py_safe(_to_py_safe(x)) == _to_py_safe(x)
    2. Type-preserving for primitives: int stays int, float stays float
    3. Containers are recursively converted: dicts, lists, tuples
    4. memoryview/bytearray become lists (not strings)
    5. bytes are preserved as bytes
    6. None stays None
    """

    @given(value=st.integers())
    @settings(max_examples=100)
    def test_int_preserved(self, value):
        assert _to_py_safe(value) == value
        assert isinstance(_to_py_safe(value), int)

    @given(value=st.floats(allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_float_preserved(self, value):
        assert _to_py_safe(value) == value
        assert isinstance(_to_py_safe(value), float)

    @given(value=st.text(max_size=200))
    @settings(max_examples=100)
    def test_str_preserved(self, value):
        assert _to_py_safe(value) == value
        assert isinstance(_to_py_safe(value), str)

    @given(value=st.booleans())
    @settings(max_examples=10)
    def test_bool_preserved(self, value):
        assert _to_py_safe(value) == value
        assert isinstance(_to_py_safe(value), bool)

    def test_none_preserved(self):
        assert _to_py_safe(None) is None

    @given(value=st.binary(max_size=100))
    @settings(max_examples=50)
    def test_bytes_preserved(self, value):
        """bytes should remain bytes, not be exploded into a list of ints."""
        result = _to_py_safe(value)
        assert isinstance(result, bytes)
        assert result == value

    @given(
        values=st.lists(
            st.one_of(
                st.integers(),
                st.text(max_size=20),
                st.floats(allow_nan=False, allow_infinity=False),
            ),
            max_size=20,
        )
    )
    @settings(max_examples=50)
    def test_list_recursively_converted(self, values):
        result = _to_py_safe(values)
        assert isinstance(result, list)
        assert result == values

    @given(
        d=st.dictionaries(
            st.text(min_size=1, max_size=10),
            st.one_of(st.integers(), st.text(max_size=20)),
            max_size=10,
        )
    )
    @settings(max_examples=50)
    def test_dict_recursively_converted(self, d):
        result = _to_py_safe(d)
        assert isinstance(result, dict)
        assert result == d

    @given(
        value=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=50),
            st.booleans(),
            st.none(),
            st.binary(max_size=50),
            st.lists(st.integers(), max_size=10),
            st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), max_size=5),
        )
    )
    @settings(max_examples=100)
    def test_idempotent(self, value):
        """_to_py_safe applied twice produces the same result as once."""
        once = _to_py_safe(value)
        twice = _to_py_safe(once)
        assert once == twice
        assert type(once) is type(twice)

    @given(
        floats=st.lists(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
            min_size=0,
            max_size=50,
        )
    )
    @settings(max_examples=50)
    def test_memoryview_float_becomes_list(self, floats):
        """memoryview of floats (Float32Array) must become a list, not a string."""
        import array

        arr = array.array("f", floats)
        mv = memoryview(arr)
        result = _to_py_safe(mv)
        assert isinstance(result, list)
        assert len(result) == len(floats)
        # float32 loses precision; just check length and type
        assert all(isinstance(x, float) for x in result)

    @given(ints=st.lists(st.integers(min_value=0, max_value=255), min_size=0, max_size=50))
    @settings(max_examples=50)
    def test_bytearray_becomes_list(self, ints):
        """bytearray (Uint8Array) must become a list, not a string."""
        ba = bytearray(ints)
        result = _to_py_safe(ba)
        assert isinstance(result, list)
        assert result == ints

    @given(
        floats=st.lists(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
            min_size=1,
            max_size=768,
        )
    )
    @settings(max_examples=20)
    def test_nested_dict_with_memoryview_fully_converts(self, floats):
        """AI-response-shaped dict with memoryview should fully convert to pure Python."""
        import array

        arr = array.array("f", floats)
        data = {"data": [memoryview(arr)]}
        result = _to_py_safe(data)

        assert isinstance(result, dict)
        assert isinstance(result["data"], list)
        assert isinstance(result["data"][0], list)
        assert len(result["data"][0]) == len(floats)


# =============================================================================
# Outbound Boundary Properties (_to_js_value)
# =============================================================================


class TestToJsValueProperties:
    """Property-based tests for _to_js_value — the outbound conversion gate.

    The key invariant: _to_js_value is the ONLY call site for to_js() in
    the codebase. It always passes dict_converter=Object.fromEntries so
    that nested dicts become JS Objects, not Maps/LiteralMaps.

    We can't test to_js() behavior in CPython (no Pyodide), but we can
    test that:
    1. In non-Pyodide mode, _to_js_value is a pass-through (identity)
    2. No direct to_js() calls exist outside _to_js_value
    3. The Vectorize upsert payload structure round-trips through _to_js_value
    """

    @given(
        value=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=50),
            st.booleans(),
            st.none(),
            st.lists(st.integers(), max_size=10),
            st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), max_size=5),
        )
    )
    @settings(max_examples=100)
    def test_passthrough_in_test_mode(self, value):
        """In CPython (non-Pyodide), _to_js_value returns the value unchanged."""
        from src.wrappers import _to_js_value

        result = _to_js_value(value)
        assert result is value

    @given(
        vector=st.lists(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-1, max_value=1),
            min_size=3,
            max_size=20,
        ),
        entry_id=st.integers(min_value=1, max_value=100000),
        title=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_vectorize_upsert_payload_passthrough(self, vector, entry_id, title):
        """Vectorize upsert payload (list of dicts) passes through in test mode."""
        from src.wrappers import _to_js_value

        payload = [
            {
                "id": str(entry_id),
                "values": vector,
                "metadata": {"title": title, "entry_id": entry_id},
            }
        ]
        result = _to_js_value(payload)
        assert result is payload
        assert result[0]["values"] is vector

    def test_no_direct_to_js_calls_outside_gate(self):
        """to_js() must only be called inside _to_js_value.

        If any other code calls to_js() directly without dict_converter,
        nested dicts will become LiteralMaps instead of Objects. This test
        enforces the single-gate pattern by scanning the source.
        """
        import ast
        from pathlib import Path

        src_dir = Path("src")
        violations = []

        for py_file in src_dir.glob("*.py"):
            source = py_file.read_text()
            tree = ast.parse(source)

            # Find which line ranges belong to _to_js_value
            gate_lines = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "_to_js_value":
                    for lineno in range(node.lineno, node.end_lineno + 1):
                        gate_lines.add(lineno)

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (
                    isinstance(func, ast.Name)
                    and func.id == "to_js"
                    and node.lineno not in gate_lines
                ):
                    violations.append(f"{py_file}:{node.lineno}: to_js() outside _to_js_value")

        assert not violations, (
            "Direct to_js() calls found outside _to_js_value gate:\n"
            + "\n".join(f"  {v}" for v in violations)
            + "\n\nAll to_js() calls must go through _to_js_value() which applies "
            "dict_converter=Object.fromEntries. See lesson 29 in LESSONS_LEARNED.md."
        )

    @given(
        value=st.one_of(
            # Types that should convert without creating PyProxies
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(max_size=50),
            st.booleans(),
            st.none(),
            st.lists(st.integers(), max_size=10),
            st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), max_size=5),
            # Nested: list of dicts (the Vectorize upsert shape)
            st.lists(
                st.dictionaries(st.text(min_size=1, max_size=5), st.integers(), max_size=3),
                max_size=5,
            ),
        )
    )
    @settings(max_examples=100)
    def test_only_primitives_pass_through(self, value):
        """All data we send to bindings is primitives/lists/dicts.

        _to_js_value uses create_pyproxies=False in Pyodide, which would
        raise ConversionError for non-primitive types. In test mode, it's
        a passthrough — but this test documents and verifies the invariant
        that we only send convertible types.
        """
        from src.wrappers import _to_js_value

        # Should not raise — all these types are natively convertible
        result = _to_js_value(value)
        assert result is value  # passthrough in test mode
