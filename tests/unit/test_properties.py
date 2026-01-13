# tests/unit/test_properties.py
"""Property-based tests using Hypothesis."""

import pytest
from hypothesis import given, settings, strategies as st

from src.types import FeedId, FeedJob, Session


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
        username=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
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
        username=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
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
        username=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
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
