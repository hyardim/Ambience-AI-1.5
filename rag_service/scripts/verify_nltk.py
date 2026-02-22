"""Verify NLTK data integrity after download."""

import hashlib
import pathlib
import sys

import nltk

# SHA-256 checksums of known-good NLTK punkt files
# Update these when intentionally upgrading NLTK data
EXPECTED = {
    "punkt": "51c3078994aeaf650bfc8e028be4fb42b4a0d177d41c012b6a983979653660ec",
    "punkt_tab": "e57f64187974277726a3417ca6f181ec5403676c717672eef6a748a7b20e0106",
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
