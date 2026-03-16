def _build_manual_citations(sources: list[str] | None) -> list[dict] | None:
    if not sources:
        return None

    cleaned = [
        source.strip()
        for source in sources
        if isinstance(source, str) and source.strip()
    ]
    if not cleaned:
        return None

    return [
        {
            "title": source,
            "source_name": "Manual source",
            "metadata": {
                "title": source,
                "source_name": "Manual source",
            },
        }
        for source in cleaned
    ]
