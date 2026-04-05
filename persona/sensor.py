"""
sensor.py — Task/environment classifier.

Reads the incoming task and determines what reasoning posture the agent needs.
Uses local embeddings (Ollama nomic-embed-text) against reference descriptions,
plus keyword heuristics for speed.

Returns a task profile that the stance selector uses to configure the agent.
"""

import httpx
import numpy as np
from pathlib import Path

OLLAMA_URL = "http://localhost:11434"

# Task types and what they need from the agent
TASK_PROFILES = {
    "execute": {
        "description": "Simple task execution: capture, save, send, create, move, delete",
        "needs": "speed",
        "default_stance": "supportive",
        "reasoning_depth": "shallow",
    },
    "research": {
        "description": "Investigation, lookup, search, find information, compare options",
        "needs": "thoroughness",
        "default_stance": "analytical",
        "reasoning_depth": "deep",
    },
    "create": {
        "description": "Draft, write, compose, design, build something new from scratch",
        "needs": "creativity",
        "default_stance": "creative",
        "reasoning_depth": "medium",
    },
    "decide": {
        "description": "Should I, which option, evaluate, choose, prioritize, trade-off",
        "needs": "balanced_perspectives",
        "default_stance": "challenger",
        "reasoning_depth": "deep",
    },
    "communicate": {
        "description": "Email, message, pitch, present, explain to someone, persuade",
        "needs": "audience_awareness",
        "default_stance": "adaptive",
        "reasoning_depth": "medium",
    },
    "debug": {
        "description": "Fix, broken, error, not working, investigate failure, troubleshoot",
        "needs": "precision",
        "default_stance": "analytical",
        "reasoning_depth": "deep",
    },
    "reflect": {
        "description": "Review, retrospective, what went well, improve, learn from, feedback",
        "needs": "honesty",
        "default_stance": "challenger",
        "reasoning_depth": "deep",
    },
}

# Fast keyword heuristics (checked before embeddings for common patterns)
KEYWORD_MAP = {
    # ORDER MATTERS — checked first to last, first match wins
    # Put more specific patterns before generic ones
    "decide": ["should i", "should we", "which", "evaluate", "choose", "prioritize",
               "trade-off", "pros and cons", "worth it", "better option",
               "is this a good idea", "what do you think", "i've decided",
               "shut down", "pivot", "kill", "keep going", "abandon"],
    "communicate": ["email", "message to", "reply to", "pitch", "present to",
                    "explain to", "tell them", "respond to", "follow up with",
                    "draft an email", "draft a message", "write to"],
    "debug": ["fix", "broken", "error", "not working", "why does", "bug",
              "troubleshoot", "failing", "crash", "investigate", "still not",
              "keeps breaking", "tried everything", "why won't"],
    "reflect": ["review", "retro", "what went", "improve", "learn from",
                "feedback on", "how did", "assess", "grade my"],
    "research": ["search", "find", "look up", "what is", "who is", "compare",
                 "research", "investigate", "how does", "tell me about"],
    "create": ["draft a", "write a", "compose", "design a", "build a", "generate",
               "create a", "make a", "sketch", "outline a"],
    "execute": ["capture", "save", "add to", "log", "record", "remind me", "set timer",
                "buy", "schedule", "book", "create task", "todo"],
}

# Cache embeddings
_profile_embeddings = {}


def _embed(text: str) -> list[float]:
    """Get embedding from Ollama."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": "nomic-embed-text", "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def _cosine(a, b):
    a, b = np.array(a), np.array(b)
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(dot / norm) if norm > 0 else 0.0


def _keyword_classify(text: str):
    """Fast keyword-based classification. Returns task type or None."""
    lower = text.lower().strip()
    for task_type, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw in lower:
                return task_type
    return None


def _embedding_classify(text: str) -> str:
    """Embedding-based classification against task profile descriptions."""
    global _profile_embeddings
    if not _profile_embeddings:
        for ttype, profile in TASK_PROFILES.items():
            _profile_embeddings[ttype] = _embed(profile["description"])

    input_emb = _embed(text)
    scores = {}
    for ttype, ref_emb in _profile_embeddings.items():
        scores[ttype] = _cosine(input_emb, ref_emb)

    return max(scores, key=scores.get)


def classify_task(text: str) -> tuple[str, dict]:
    """
    Classify a task and return (task_type, profile).

    Uses keyword heuristics first (fast), falls back to embeddings.
    """
    # Try keywords first
    task_type = _keyword_classify(text)

    # Fall back to embeddings
    if task_type is None:
        task_type = _embedding_classify(text)

    profile = TASK_PROFILES.get(task_type, TASK_PROFILES["execute"])
    return task_type, profile


def sense(text: str) -> dict:
    """
    Full sensing pass. Returns everything the stance selector needs.

    Analyzes:
      - Task type (what kind of work)
      - Confidence signals (is the user certain or uncertain?)
      - Emotional tone (frustrated, excited, neutral?)
      - Complexity (simple request or multi-faceted?)
    """
    task_type, profile = classify_task(text)
    lower = text.lower()

    # Confidence detection — is the user asking for validation or genuine input?
    validation_seeking = any(p in lower for p in [
        "right?", "don't you think", "obviously", "clearly",
        "i think we should", "i've decided", "i'm going to",
    ])

    uncertainty = any(p in lower for p in [
        "not sure", "maybe", "what if", "should i", "i don't know",
        "help me think", "what would you", "any ideas",
    ])

    # Frustration detection
    frustrated = any(p in lower for p in [
        "still not", "broken again", "doesn't work", "wtf",
        "why won't", "keep failing", "i've tried everything",
    ])

    # Complexity — rough heuristic based on length and conjunctions
    word_count = len(text.split())
    has_multiple_asks = any(p in lower for p in [" and ", " also ", " plus ", " then "])
    complexity = "complex" if (word_count > 50 or has_multiple_asks) else "simple"

    return {
        "task_type": task_type,
        "profile": profile,
        "default_stance": profile["default_stance"],
        "reasoning_depth": profile["reasoning_depth"],
        # Context signals
        "validation_seeking": validation_seeking,
        "uncertain": uncertainty,
        "frustrated": frustrated,
        "complexity": complexity,
        # Override triggers
        "needs_pushback": validation_seeking and task_type in ("decide", "create", "communicate"),
        "needs_empathy": frustrated,
        "needs_depth": uncertainty or complexity == "complex",
    }


if __name__ == "__main__":
    import sys
    test_inputs = [
        "Capture: pick up dry cleaning",
        "Should I build a SaaS tool for EAP sales intelligence?",
        "Draft an email to the VP of HR at City of Vancouver",
        "Why is the provider dropdown still not saving?",
        "What do you think about pivoting Recon to a multi-tenant product?",
        "Search the vault for Telus Health pricing data",
        "Review my Seam essay on AI agent personality",
        "I've decided to shut down Spectra. Obviously it's not working. Right?",
    ]

    for text in test_inputs:
        result = sense(text)
        pushback = "⚡ PUSHBACK" if result["needs_pushback"] else ""
        empathy = "💛 EMPATHY" if result["needs_empathy"] else ""
        print(f"  {result['task_type']:12s} | {result['default_stance']:12s} | {text[:55]:55s} {pushback} {empathy}")
