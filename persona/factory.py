"""
factory.py — Algorithmic persona generation.

No LLM in the loop. Pure Python functions that take measurable inputs
and produce deterministic persona configurations.

Input: task features (type, complexity, confidence signals, frustration, history)
Algorithm: weighted vector scoring across 5 stance dimensions
Output: deterministic config (temperature, pushback, prompt modifiers, response format)

Every decision is traceable. Same inputs → same output. A/B testable.
"""

import math
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# ═══════════════════════════════════════════════════════════════
# § 1. Persona Configuration (the output)
# ═══════════════════════════════════════════════════════════════

@dataclass
class PersonaConfig:
    """Deterministic output of the persona factory. Fully serializable."""
    # Identity
    stance: str                     # supportive, analytical, challenger, creative, adaptive
    temperature: float              # 0.1 - 1.0
    pushback_level: float           # 0.0 (none) to 1.0 (maximum)

    # Behavioral modifiers
    prompt_prefix: str              # Injected before the agent's base prompt
    response_format: str            # action, analysis, socratic, exploratory, audience_aware
    depth: str                      # shallow, medium, deep
    empathy_lead: bool              # Start with acknowledgment before content

    # Traceability
    reasoning: List[str]            # Why each decision was made
    input_hash: str                 # Hash of inputs for reproducibility
    version: str = "1.0.0"         # Factory version for A/B testing

    def to_dict(self):
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# § 2. Task Features (the input)
# ═══════════════════════════════════════════════════════════════

@dataclass
class TaskFeatures:
    """Measurable features extracted from the task. No interpretation."""
    # Classification
    task_type: str                  # execute, research, create, decide, communicate, debug, reflect

    # Text signals (all 0.0 - 1.0)
    word_count: int = 0
    question_marks: int = 0
    exclamation_marks: int = 0

    # Confidence signals
    validation_seeking: float = 0.0  # 0=not seeking, 1=strongly seeking validation
    uncertainty: float = 0.0         # 0=certain, 1=very uncertain
    frustration: float = 0.0         # 0=calm, 1=very frustrated

    # Complexity
    has_multiple_asks: bool = False
    references_prior_context: bool = False

    # History (from session/calibration)
    consecutive_agreements: int = 0  # How many times agent has agreed in a row
    session_stance_history: List[str] = field(default_factory=list)  # recent stances used


# ═══════════════════════════════════════════════════════════════
# § 3. Feature Extraction (text → numbers)
# ═══════════════════════════════════════════════════════════════

# Keyword sets — scored by presence, not by LLM interpretation
VALIDATION_MARKERS = [
    "right?", "don't you think", "obviously", "clearly",
    "i think we should", "i've decided", "i'm going to",
    "makes sense", "agreed?", "correct?",
]

UNCERTAINTY_MARKERS = [
    "not sure", "maybe", "what if", "should i", "i don't know",
    "help me think", "what would you", "any ideas", "torn between",
    "on the fence", "could go either way",
]

FRUSTRATION_MARKERS = [
    "still not", "broken again", "doesn't work", "not working",
    "why won't", "keep failing", "tried everything", "wtf",
    "for the third time", "i already told you", "this is ridiculous",
]

TASK_KEYWORDS = {
    "decide": ["should i", "should we", "which", "evaluate", "choose", "prioritize",
               "trade-off", "pros and cons", "worth it", "better option",
               "what do you think", "i've decided", "shut down", "pivot", "kill",
               "focus on", "whether to", "help me think", "torn between"],
    "communicate": ["email", "message to", "reply to", "pitch", "present to",
                    "draft an email", "draft a message", "write to", "follow up with"],
    "debug": ["fix", "broken", "error", "not working", "why does", "bug",
              "troubleshoot", "failing", "crash", "still not", "keeps breaking"],
    "reflect": ["review", "retro", "what went", "improve", "learn from",
                "feedback on", "how did", "assess", "grade my", "be honest",
                "your personality", "your weaknesses", "your strengths",
                "self-assess", "how are you doing", "what are you", "tell me about yourself",
                "where are you weak", "where do you struggle", "critique yourself"],
    "research": ["search", "find", "look up", "what is", "who is", "compare",
                 "research", "investigate", "how does", "tell me about",
                 "how to", "how can", "how do", "what are the", "what would",
                 "can you review", "can you check", "strengthen", "improve"],
    "create": ["draft a", "write a", "compose", "design a", "build a", "generate",
               "create a", "make a", "sketch", "outline a"],
    "execute": ["capture", "save", "add to", "log", "record", "remind me",
                "buy", "schedule", "book", "todo"],
}


def extract_features(text: str, session_history: list = None) -> TaskFeatures:
    """
    Pure function. Text → measurable numbers. No LLM, no interpretation.
    """
    lower = text.lower().strip()
    words = text.split()

    # Task type — first keyword match wins (order = priority)
    task_type = "execute"  # default
    for ttype in ["decide", "communicate", "debug", "reflect", "research", "create", "execute"]:
        for kw in TASK_KEYWORDS.get(ttype, []):
            if kw in lower:
                task_type = ttype
                break
        else:
            continue
        break

    # Signal scoring — count matches, normalize to 0-1
    def _score(markers):
        hits = sum(1 for m in markers if m in lower)
        return min(1.0, hits / max(1, len(markers) * 0.15))  # saturates at ~15% match rate

    validation = _score(VALIDATION_MARKERS)
    uncertainty = _score(UNCERTAINTY_MARKERS)
    frustration = _score(FRUSTRATION_MARKERS)

    # Complexity signals
    has_multiple = any(p in lower for p in [" and ", " also ", " plus ", " then ", " both "])
    has_prior = any(p in lower for p in ["as i said", "like before", "we discussed",
                                          "remember when", "last time", "earlier"])

    # Session history
    history = session_history or []
    consecutive_agrees = 0
    for stance in reversed(history):
        if stance == "supportive":
            consecutive_agrees += 1
        else:
            break

    return TaskFeatures(
        task_type=task_type,
        word_count=len(words),
        question_marks=text.count("?"),
        exclamation_marks=text.count("!"),
        validation_seeking=validation,
        uncertainty=uncertainty,
        frustration=frustration,
        has_multiple_asks=has_multiple,
        references_prior_context=has_prior,
        consecutive_agreements=consecutive_agrees,
        session_stance_history=history[-10:],  # keep last 10
    )


# ═══════════════════════════════════════════════════════════════
# § 4. Persona Algorithm (features → config)
# ═══════════════════════════════════════════════════════════════

# Stance vectors: each task type has a base weight for each stance dimension
# Format: {task_type: [supportive, analytical, challenger, creative, adaptive]}
STANCE_WEIGHTS = {
    "execute":     [0.9, 0.0, 0.0, 0.0, 0.1],
    "research":    [0.1, 0.7, 0.1, 0.0, 0.1],
    "create":      [0.1, 0.1, 0.0, 0.7, 0.1],
    "decide":      [0.0, 0.3, 0.5, 0.0, 0.2],
    "communicate": [0.1, 0.1, 0.1, 0.1, 0.6],
    "debug":       [0.2, 0.6, 0.1, 0.0, 0.1],
    "reflect":     [0.0, 0.3, 0.5, 0.1, 0.1],
}

STANCE_NAMES = ["supportive", "analytical", "challenger", "creative", "adaptive"]

# Prompt templates — deterministic, not generated
PROMPT_TEMPLATES = {
    "supportive": (
        "Execute cleanly and confirm what you did. Be concise. "
        "Don't over-explain or add unsolicited advice."
    ),
    "analytical": (
        "Show evidence for every claim. Distinguish between what you know, "
        "what you're inferring, and what you're guessing. Quantify where possible. "
        "If data is missing, say what data you'd need."
    ),
    "challenger": (
        "Before answering, identify the assumption the user is making that might "
        "be wrong. Test certainty — not to be contrarian, but because untested "
        "assumptions are dangerous. Agreement should be earned, not default."
    ),
    "creative": (
        "Think expansively. Suggest things not yet considered. Make unexpected "
        "connections. It's okay to be wrong if you're interesting. After exploring, "
        "ground the best idea in one practical next step."
    ),
    "adaptive": (
        "Identify the audience, what they care about, and what outcome is desired. "
        "Match the register to the relationship. Draft for the specific human reading it."
    ),
}

EMPATHY_PREFIX = (
    "The user sounds frustrated. Briefly name the specific thing that's not working "
    "before solving. No platitudes — just acknowledgment, then the fix."
)

DEPTH_SUFFIX = (
    " Consider second-order effects. If there are multiple paths, lay them out "
    "with tradeoffs instead of picking one."
)

ANTI_SYCOPHANCY_INJECTION = (
    " You have agreed with the user {n} times in a row. Before responding, "
    "ask yourself: am I agreeing because the evidence supports it, or because "
    "agreeing is easier? If you genuinely agree, state the specific evidence. "
    "If you're not sure, say so."
)

# Response format mapping
FORMAT_MAP = {
    "supportive": "action",
    "analytical": "analysis",
    "challenger": "socratic",
    "creative": "exploratory",
    "adaptive": "audience_aware",
}

# Depth mapping based on task type and complexity
DEPTH_MAP = {
    "execute": "shallow",
    "research": "deep",
    "create": "medium",
    "decide": "deep",
    "communicate": "medium",
    "debug": "deep",
    "reflect": "deep",
}


def generate_persona(features: TaskFeatures) -> PersonaConfig:
    """
    Pure algorithm. TaskFeatures → PersonaConfig. Deterministic.

    Steps:
    1. Start with base stance weights from task type
    2. Apply modifiers based on measured signals
    3. Select winning stance (highest weight)
    4. Calculate temperature from stance + signals
    5. Build prompt from templates + modifiers
    6. Generate reasoning trace
    """
    reasoning = []

    # ── Step 1: Base weights from task type ──
    weights = list(STANCE_WEIGHTS.get(features.task_type, STANCE_WEIGHTS["execute"]))
    reasoning.append(f"Base weights for '{features.task_type}': {dict(zip(STANCE_NAMES, [round(w,2) for w in weights]))}")

    # ── Step 2: Apply signal modifiers ──

    # Validation-seeking: boost challenger, suppress supportive
    if features.validation_seeking > 0.3:
        weights[2] += 0.4 * features.validation_seeking   # challenger
        weights[0] -= 0.3 * features.validation_seeking   # supportive
        reasoning.append(f"Validation-seeking ({features.validation_seeking:.2f}): boosted challenger +{0.4*features.validation_seeking:.2f}")

    # Uncertainty: boost analytical, boost depth
    if features.uncertainty > 0.3:
        weights[1] += 0.3 * features.uncertainty   # analytical
        reasoning.append(f"Uncertainty ({features.uncertainty:.2f}): boosted analytical +{0.3*features.uncertainty:.2f}")

    # Frustration: boost supportive empathy
    if features.frustration > 0.3:
        weights[0] += 0.3 * features.frustration   # supportive
        reasoning.append(f"Frustration ({features.frustration:.2f}): boosted supportive +{0.3*features.frustration:.2f}")

    # Anti-sycophancy: if agent has agreed too many times, force challenger
    if features.consecutive_agreements >= 3:
        boost = min(0.9, 0.5 + (features.consecutive_agreements - 3) * 0.1)  # escalates with streak length
        weights[2] += boost   # challenger
        weights[0] -= 0.5     # suppress supportive harder
        reasoning.append(f"Anti-sycophancy: {features.consecutive_agreements} consecutive agreements, forced challenger boost +{boost:.1f}")

    # Complexity: boost analytical for complex tasks
    if features.has_multiple_asks or features.word_count > 50:
        weights[1] += 0.15  # analytical
        reasoning.append(f"Complex task: boosted analytical +0.15")

    # ── Step 3: Select winning stance ──
    # Normalize weights (clamp negatives to 0)
    weights = [max(0, w) for w in weights]
    total = sum(weights)
    if total > 0:
        weights = [w / total for w in weights]

    winning_idx = weights.index(max(weights))
    stance = STANCE_NAMES[winning_idx]
    confidence = weights[winning_idx]
    reasoning.append(f"Final weights: {dict(zip(STANCE_NAMES, [round(w,3) for w in weights]))}")
    reasoning.append(f"Selected: {stance} (confidence: {confidence:.3f})")

    # ── Step 4: Calculate temperature ──
    # Base temperature per stance
    temp_base = {
        "supportive": 0.5,
        "analytical": 0.4,
        "challenger": 0.6,
        "creative": 0.8,
        "adaptive": 0.6,
    }
    temperature = temp_base[stance]

    # Uncertainty increases temperature slightly (more exploration needed)
    if features.uncertainty > 0.5:
        temperature += 0.1
    # Frustration decreases temperature (precision needed)
    if features.frustration > 0.5:
        temperature -= 0.1

    temperature = round(max(0.1, min(1.0, temperature)), 2)

    # ── Step 5: Build prompt ──
    prompt_parts = [PROMPT_TEMPLATES[stance]]

    # Add empathy lead if frustrated
    empathy_lead = False
    if features.frustration > 0.3:
        prompt_parts.insert(0, EMPATHY_PREFIX)
        empathy_lead = True
        reasoning.append("Added empathy prefix (frustration detected)")

    # Add depth suffix for complex/uncertain tasks
    depth = DEPTH_MAP.get(features.task_type, "medium")
    if features.uncertainty > 0.5 or features.has_multiple_asks:
        depth = "deep"
        prompt_parts.append(DEPTH_SUFFIX)
        reasoning.append("Increased depth (uncertainty or complexity)")

    # Add anti-sycophancy injection
    if features.consecutive_agreements >= 3:
        prompt_parts.append(
            ANTI_SYCOPHANCY_INJECTION.format(n=features.consecutive_agreements)
        )
        reasoning.append(f"Added anti-sycophancy injection ({features.consecutive_agreements} consecutive agreements)")

    # Pushback level — continuous, not categorical
    pushback = weights[2]  # challenger weight = pushback level
    pushback = round(min(1.0, pushback + (0.2 if features.validation_seeking > 0.3 else 0)), 3)

    # Input hash for reproducibility
    import hashlib
    input_str = f"{features.task_type}|{features.validation_seeking}|{features.uncertainty}|{features.frustration}|{features.consecutive_agreements}|{features.word_count}"
    input_hash = hashlib.md5(input_str.encode()).hexdigest()[:12]

    return PersonaConfig(
        stance=stance,
        temperature=temperature,
        pushback_level=pushback,
        prompt_prefix="\n\n".join(prompt_parts),
        response_format=FORMAT_MAP[stance],
        depth=depth,
        empathy_lead=empathy_lead,
        reasoning=reasoning,
        input_hash=input_hash,
    )


# ═══════════════════════════════════════════════════════════════
# § 5. Convenience function (text → config in one call)
# ═══════════════════════════════════════════════════════════════

def create_persona(text: str, session_history: list = None) -> PersonaConfig:
    """
    Full pipeline: text → features → persona config.
    Pure function. No LLM calls. Deterministic.
    """
    features = extract_features(text, session_history)
    return generate_persona(features)


def format_persona(config: PersonaConfig) -> str:
    """Pretty-print for debugging."""
    lines = [
        f"  Stance: {config.stance}",
        f"  Temperature: {config.temperature}",
        f"  Pushback: {config.pushback_level}",
        f"  Depth: {config.depth}",
        f"  Format: {config.response_format}",
        f"  Empathy lead: {config.empathy_lead}",
        f"  Hash: {config.input_hash}",
        f"  Reasoning:",
    ]
    for r in config.reasoning:
        lines.append(f"    → {r}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# § 6. Test
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        ("Capture: buy milk", []),
        ("Should I build a SaaS tool for EAP sales intelligence?", []),
        ("Draft an email to the VP of HR at City of Vancouver", []),
        ("Why is the provider dropdown still not saving?", []),
        ("I've decided to shut down Spectra. Obviously it's not working. Right?", []),
        ("Sounds good, let's do that", ["supportive", "supportive", "supportive"]),
        ("Yes I agree, go ahead", ["supportive", "supportive", "supportive", "supportive"]),
        ("I'm not sure whether to focus on Recon or AgentGuard. Help me think.", []),
        ("This keeps breaking and I've tried everything. Why won't it work?", []),
    ]

    for text, history in tests:
        print(f"\n{'─' * 60}")
        print(f"  Input: {text}")
        if history:
            print(f"  History: {history}")
        config = create_persona(text, history)
        print(format_persona(config))
