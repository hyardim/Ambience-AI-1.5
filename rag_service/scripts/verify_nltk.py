"""Verify NLTK tokenizer data is installed and loadable."""

import sys


def verify() -> None:
    failed = False

    try:
        import nltk
    except ImportError:
        print("ERROR: nltk is not installed — run: pip install nltk")
        sys.exit(1)

    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
            print(f"OK: {resource} found")
        except LookupError:
            print(
                f"ERROR: {resource} not found — run: "
                f"python -m nltk.downloader {resource}"
            )
            failed = True

    # Verify punkt actually works by tokenizing a test string
    try:
        from nltk.tokenize import sent_tokenize

        result = sent_tokenize("This is a test. It should tokenize correctly.")
        assert len(result) == 2, f"Expected 2 sentences, got {len(result)}"
        print("OK: tokenizer functional")
    except Exception as e:
        print(f"ERROR: tokenizer failed: {e}")
        failed = True

    if failed:
        sys.exit(1)

    print("NLTK data verified.")


if __name__ == "__main__":
    verify()
