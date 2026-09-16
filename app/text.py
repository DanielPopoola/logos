ELLIPSIS = "..."


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncate_at = max_chars - len(ELLIPSIS)
    return text[:truncate_at].rstrip() + ELLIPSIS
