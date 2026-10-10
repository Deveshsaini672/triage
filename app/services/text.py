import hashlib
import re

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s<>]")

# Volatile tokens replaced by placeholders so near-duplicates collide:
# "Order #1234567 not delivered" ~ "order #7654321 not delivered".
# Tradeoff: "$5000" and "$9000" also collide. Accepted; the cache is a cost
# optimisation, not a source of truth.
_MASKS = [
    (re.compile(r"https?://\S+"), " <url> "),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), " <email> "),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), " <id> "),
    (re.compile(r"\d{4,}"), " <num> "),
]


def normalize(subject: str, body: str) -> str:
    text = f"{subject} {body}".lower()
    for pattern, repl in _MASKS:
        text = pattern.sub(repl, text)
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def content_hash(subject: str, body: str) -> str:
    return hashlib.sha256(normalize(subject, body).encode()).hexdigest()
