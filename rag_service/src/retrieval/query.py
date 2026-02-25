from __future__ import annotations

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# -----------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384
MAX_TOKENS = 512

# Simple rule-based expansion dictionary for medical terminology
EXPANSION_DICT: dict[str, list[str]] = {
    "gout": ["urate", "hyperuricemia", "uric acid"],
    "ra": ["rheumatoid arthritis"],
    "oa": ["osteoarthritis"],
    "sle": ["systemic lupus erythematosus", "lupus"],
    "as": ["ankylosing spondylitis"],
    "psa": ["psoriatic arthritis"],
    "ms": ["multiple sclerosis"],
    "dmard": ["disease modifying antirheumatic drug"],
    "nsaid": ["non-steroidal anti-inflammatory", "anti-inflammatory"],
    "methotrexate": ["mtx", "disease modifying antirheumatic drug"],
}