from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from typing import Any

from ..utils.logger import setup_logger

logger = setup_logger(__name__)

# A4 page height in points (NICE/BSR guidelines are A4)
PAGE_HEIGHT = 842.0
HEADER_THRESHOLD = 0.15
FOOTER_THRESHOLD = 0.85
REPEAT_THRESHOLD = 0.6
Y_BUCKET_SIZE = 10