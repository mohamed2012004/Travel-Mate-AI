def sanitize_text(text):
    if not text:
        return "", []
    cleaned = "".join(ch for ch in str(text) if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    findings = ["control_chars_removed"] if cleaned != text else []
    return cleaned.strip(), findings


def wrap_untrusted(text, tag="user_input"):
    if not tag.replace("_", "").islower():
        tag = "user_input"
    cleaned, _ = sanitize_text(text or "")
    cleaned = cleaned.replace(f"</{tag}>", f"<\\/{tag}>").replace(f"<{tag}>", f"<\\{tag}>")
    return f"<{tag}>\n{cleaned}\n</{tag}>"
