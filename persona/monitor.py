"""
monitor.py — Convergence/groupthink detection for multi-agent systems.

Watches the outputs of multiple agents working together and detects when
they're converging too fast (groupthink) or diverging too far (chaos).

Acts as a thermostat for disagreement:
  - Too much agreement → inject dissent
  - Too much conflict → inject synthesis
  - Healthy tension → leave alone

Uses embedding similarity between agent outputs to measure diversity.
"""

import httpx
import numpy as np
from collections import Counter

OLLAMA_URL = "http://localhost:11434"


def _embed(text: str) -> list[float]:
    """Get embedding from Ollama."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": "nomic-embed-text", "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def _pairwise_similarities(embeddings: list[list[float]]) -> list[float]:
    """Compute all pairwise cosine similarities."""
    sims = []
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            a, b = np.array(embeddings[i]), np.array(embeddings[j])
            dot = np.dot(a, b)
            norm = np.linalg.norm(a) * np.linalg.norm(b)
            sim = float(dot / norm) if norm > 0 else 0.0
            sims.append(sim)
    return sims


def _sentiment_diversity(outputs: list[dict]) -> float:
    """
    Measure diversity of sentiment/stance across outputs.
    Returns 0.0 (all same) to 1.0 (maximum diversity).
    """
    if not outputs:
        return 0.0

    # Extract sentiment signals
    sentiments = []
    for out in outputs:
        text = out.get("text", out.get("content", str(out))).lower()
        # Simple positive/negative/neutral classification
        pos_words = sum(1 for w in ["good", "strong", "yes", "build", "viable", "opportunity",
                                     "promising", "elegant", "genuine", "real"] if w in text)
        neg_words = sum(1 for w in ["weak", "no", "fail", "risk", "problem", "crowded",
                                     "flaw", "thin", "redundant", "naive"] if w in text)
        if pos_words > neg_words:
            sentiments.append("positive")
        elif neg_words > pos_words:
            sentiments.append("negative")
        else:
            sentiments.append("neutral")

    # Diversity = how spread out are the sentiments?
    counter = Counter(sentiments)
    total = len(sentiments)
    if total <= 1:
        return 0.0

    # Shannon entropy normalized to 0-1
    entropy = 0.0
    for count in counter.values():
        p = count / total
        if p > 0:
            entropy -= p * np.log2(p)

    max_entropy = np.log2(min(3, total))  # max 3 categories
    return float(entropy / max_entropy) if max_entropy > 0 else 0.0


def monitor_convergence(
    agent_outputs: list[dict],
    convergence_threshold: float = 0.85,
    divergence_threshold: float = 0.40,
) -> dict:
    """
    Monitor multi-agent outputs for convergence/divergence.

    Args:
        agent_outputs: list of dicts with at minimum a "text" or "content" key
        convergence_threshold: similarity above this = groupthink warning
        divergence_threshold: similarity below this = chaos warning

    Returns:
        dict with:
          - diversity_score: 0.0 (identical) to 1.0 (maximally diverse)
          - semantic_similarity: average pairwise embedding similarity
          - sentiment_diversity: diversity of positive/negative stances
          - status: "healthy" | "converging" | "diverging"
          - recommendation: what to do about it
          - details: per-pair similarity breakdown
    """
    if len(agent_outputs) < 2:
        return {
            "diversity_score": 0.5,
            "semantic_similarity": 0.5,
            "sentiment_diversity": 0.5,
            "status": "insufficient_data",
            "recommendation": "Need at least 2 agent outputs to monitor",
            "details": [],
        }

    # Extract text from outputs
    texts = []
    for out in agent_outputs:
        if isinstance(out, str):
            texts.append(out)
        elif isinstance(out, dict):
            texts.append(out.get("text", out.get("content", out.get("strongest_point", str(out)))))
        else:
            texts.append(str(out))

    # Compute embeddings
    embeddings = [_embed(t) for t in texts]

    # Pairwise similarities
    sims = _pairwise_similarities(embeddings)
    avg_similarity = np.mean(sims) if sims else 0.5

    # Sentiment diversity
    sent_diversity = _sentiment_diversity(agent_outputs)

    # Combined diversity score (inverse of similarity, weighted with sentiment)
    diversity_score = (1.0 - avg_similarity) * 0.6 + sent_diversity * 0.4

    # Determine status and recommendation
    if avg_similarity >= convergence_threshold:
        status = "converging"
        recommendation = (
            "GROUPTHINK WARNING: Agent outputs are too similar "
            f"(avg similarity: {avg_similarity:.2f}). "
            "Inject a dissenting agent with adversarial stance and higher temperature. "
            "Consider routing the next sub-task to a model from a different provider."
        )
    elif avg_similarity <= divergence_threshold:
        status = "diverging"
        recommendation = (
            "CHAOS WARNING: Agent outputs have very low agreement "
            f"(avg similarity: {avg_similarity:.2f}). "
            "Inject a synthesis agent to find common ground. "
            "Consider reducing temperature or adding an analytical arbiter."
        )
    else:
        status = "healthy"
        recommendation = (
            f"Healthy tension (avg similarity: {avg_similarity:.2f}, "
            f"diversity: {diversity_score:.2f}). No intervention needed."
        )

    # Per-pair details
    details = []
    idx = 0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            agent_i = agent_outputs[i].get("role", agent_outputs[i].get("agent", f"Agent {i}"))
            agent_j = agent_outputs[j].get("role", agent_outputs[j].get("agent", f"Agent {j}"))
            details.append({
                "pair": f"{agent_i} ↔ {agent_j}",
                "similarity": round(sims[idx], 3),
                "status": "similar" if sims[idx] > convergence_threshold else
                         "divergent" if sims[idx] < divergence_threshold else "healthy",
            })
            idx += 1

    return {
        "diversity_score": round(diversity_score, 3),
        "semantic_similarity": round(avg_similarity, 3),
        "sentiment_diversity": round(sent_diversity, 3),
        "status": status,
        "recommendation": recommendation,
        "details": details,
        "agent_count": len(agent_outputs),
    }


def format_monitor(result: dict) -> str:
    """Pretty-print the convergence monitor output."""
    status_emoji = {
        "healthy": "🟢",
        "converging": "🔴 GROUPTHINK",
        "diverging": "🟡 CHAOS",
        "insufficient_data": "⚪",
    }
    lines = [
        f"CONVERGENCE MONITOR",
        f"{'=' * 50}",
        f"  Status: {status_emoji.get(result['status'], '?')} {result['status']}",
        f"  Diversity Score: {result['diversity_score']}",
        f"  Semantic Similarity: {result['semantic_similarity']}",
        f"  Sentiment Diversity: {result['sentiment_diversity']}",
        f"  Agents: {result['agent_count']}",
        f"",
        f"  {result['recommendation']}",
    ]

    if result.get("details"):
        lines.append(f"\n  Pairwise:")
        for d in result["details"]:
            indicator = "🔴" if d["status"] == "similar" else "🟡" if d["status"] == "divergent" else "🟢"
            lines.append(f"    {indicator} {d['pair']:30s} {d['similarity']:.3f}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Test with fake agent outputs showing groupthink
    print("=== Test: Groupthink ===")
    groupthink_outputs = [
        {"role": "Agent A", "text": "This is a great idea with strong market potential and clear value proposition"},
        {"role": "Agent B", "text": "The idea has excellent market potential and a compelling value proposition"},
        {"role": "Agent C", "text": "Strong market opportunity with a clear and compelling value proposition"},
    ]
    result = monitor_convergence(groupthink_outputs)
    print(format_monitor(result))

    print("\n=== Test: Healthy Tension ===")
    healthy_outputs = [
        {"role": "Champion", "text": "This solves a real pain point for engineering teams managing runaway agents"},
        {"role": "Killer", "text": "LangSmith will clone this in one quarter with their existing distribution"},
        {"role": "Analyst", "text": "Base rate for developer tools reaching adoption is 5-8%, unit economics unclear"},
    ]
    result = monitor_convergence(healthy_outputs)
    print(format_monitor(result))
