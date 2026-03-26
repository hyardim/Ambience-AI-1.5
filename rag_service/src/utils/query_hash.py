from __future__ import annotations

import hashlib

QUERY_FINGERPRINT_LENGTH = 12


def query_fingerprint(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[
        :QUERY_FINGERPRINT_LENGTH
    ]
