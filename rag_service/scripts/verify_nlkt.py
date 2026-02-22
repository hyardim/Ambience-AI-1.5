"""Verify NLTK data integrity after download."""

import hashlib
import pathlib
import sys

import nltk

# SHA-256 checksums of known-good NLTK punkt files
# Update these when intentionally upgrading NLTK data
EXPECTED = {
    "punkt": "expected_sha256_here",
    "punkt_tab": "expected_sha256_here",
}

data_path = pathlib.Path(nltk.data.path[0])

for resource, expected_hash in EXPECTED.items():
    zip_path = data_path / "tokenizers" / f"{resource}.zip"
    if not zip_path.exists():
        print(f"ERROR: {zip_path} not found")
        sys.exit(1)
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if actual != expected_hash:
        print(f"ERROR: {resource} checksum mismatch")
        print(f"  Expected: {expected_hash}")
        print(f"  Got:      {actual}")
        sys.exit(1)

print("NLTK data integrity verified.")
