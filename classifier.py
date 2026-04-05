"""
classifier.py — Domain detection via Ollama nomic-embed-text embeddings.

Embeds the input text and compares cosine similarity against domain
reference embeddings (pre-computed from domain descriptions).
Returns sorted domain scores.
"""

import httpx
import numpy as np
import yaml
import os
from pathlib import Path

OLLAMA_URL = "http://localhost:11434"
DOMAINS_DIR = Path(__file__).parent / "config" / "domains"

# Cache domain embeddings across calls
_domain_cache = {}


def _embed(text: str) -> list[float]:
    """Get embedding vector from Ollama nomic-embed-text."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": "nomic-embed-text", "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    # Ollama returns {"embeddings": [[...]]} for /api/embed
    return data["embeddings"][0]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    return float(dot / norm) if norm > 0 else 0.0


def _load_domain_descriptions() -> dict[str, str]:
    """Load domain name → description from YAML files."""
    domains = {}
    for f in DOMAINS_DIR.glob("*.yaml"):
        with open(f) as fh:
            data = yaml.safe_load(fh)
            if data and "domain" in data:
                domains[data["domain"]] = data.get("description", data["domain"])
    return domains


def _get_domain_embeddings() -> dict[str, list[float]]:
    """Get or compute domain reference embeddings (cached)."""
    global _domain_cache
    if _domain_cache:
        return _domain_cache

    descriptions = _load_domain_descriptions()
    for domain, desc in descriptions.items():
        _domain_cache[domain] = _embed(desc)

    return _domain_cache


def classify(text: str) -> list[tuple[str, float]]:
    """
    Classify input text into domains by embedding similarity.

    Returns list of (domain, score) tuples sorted by score descending.
    Score is cosine similarity (0.0 - 1.0).
    """
    input_embedding = _embed(text)
    domain_embeddings = _get_domain_embeddings()

    scores = []
    for domain, ref_embedding in domain_embeddings.items():
        sim = _cosine_similarity(input_embedding, ref_embedding)
        scores.append((domain, round(sim, 3)))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def classify_primary(text: str) -> str:
    """Return the single best-matching domain name."""
    scores = classify(text)
    return scores[0][0] if scores else "strategy"


if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or "Should I build an AI agent that does sales prospecting?"
    print(f"Input: {text}\n")
    for domain, score in classify(text):
        bar = "█" * int(score * 30)
        print(f"  {domain:12s} {score:.3f} {bar}")
    print(f"\n  Primary: {classify_primary(text)}")
