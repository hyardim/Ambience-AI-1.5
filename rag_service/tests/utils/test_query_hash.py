"""Tests for src/utils/query_hash.py."""

from __future__ import annotations

from src.utils.query_hash import QUERY_FINGERPRINT_LENGTH, query_fingerprint


class TestQueryFingerprint:
    def test_returns_string(self):
        assert isinstance(query_fingerprint("methotrexate dosage"), str)

    def test_length_matches_constant(self):
        result = query_fingerprint("some query")
        assert len(result) == QUERY_FINGERPRINT_LENGTH

    def test_same_query_returns_same_fingerprint(self):
        q = "polymyalgia rheumatica steroids"
        assert query_fingerprint(q) == query_fingerprint(q)

    def test_different_queries_return_different_fingerprints(self):
        assert query_fingerprint("migraine") != query_fingerprint("stroke")

    def test_empty_string_does_not_raise(self):
        result = query_fingerprint("")
        assert isinstance(result, str)
        assert len(result) == QUERY_FINGERPRINT_LENGTH

    def test_fingerprint_is_hex(self):
        result = query_fingerprint("test query")
        assert all(c in "0123456789abcdef" for c in result)
