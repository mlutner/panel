"""
stance.py — Stance selector and dynamic prompt injection.

Takes the sensor output and produces a concrete agent configuration:
  - System prompt modifier (injected before the agent's base prompt)
  - Temperature adjustment
  - Response format guidance
  - Pushback level

The key insight: we don't change the agent's personality.
We change the STRUCTURE of how it reasons.
"""

STANCES = {
    "supportive": {
        "name": "Supportive",
        "description": "Execute efficiently, confirm clearly, don't over-think",
        "temperature_mod": -0.1,  # slightly lower for precision
        "prompt_prefix": (
            "This is a straightforward task. Execute it cleanly and confirm "
            "what you did. Don't over-explain or add unsolicited advice. "
            "Be concise."
        ),
        "pushback_level": "none",
        "response_style": "action_confirmation",
    },

    "analytical": {
        "name": "Analytical",
        "description": "Data-driven, thorough, show the evidence and gaps",
        "temperature_mod": -0.2,  # lower for precision
        "prompt_prefix": (
            "Approach this analytically. Show evidence for every claim. "
            "Distinguish between what you know, what you're inferring, and "
            "what you're guessing. Quantify where possible. If data is missing, "
            "say what data you'd need and why. Don't fill gaps with confidence."
        ),
        "pushback_level": "low",
        "response_style": "structured_analysis",
    },

    "challenger": {
        "name": "Challenger",
        "description": "Push back on assumptions, surface what's not being considered",
        "temperature_mod": 0.0,
        "prompt_prefix": (
            "Before answering, ask yourself: what assumption is the user making "
            "that might be wrong? What are they not considering? If they seem "
            "certain, test that certainty — not to be contrarian, but because "
            "untested assumptions are the most dangerous ones. If you agree with "
            "them, say why specifically. Agreement should be earned, not default."
        ),
        "pushback_level": "high",
        "response_style": "socratic",
    },

    "creative": {
        "name": "Creative",
        "description": "Expansive thinking, unexpected connections, permission to be bold",
        "temperature_mod": 0.2,  # higher for exploration
        "prompt_prefix": (
            "Think expansively. The user is in creation mode — they need ideas, "
            "connections, and possibilities, not caution. Suggest things they "
            "haven't considered. Make unexpected connections. It's okay to be "
            "wrong if you're interesting. After the creative exploration, ground "
            "the best idea in one practical next step."
        ),
        "pushback_level": "none",
        "response_style": "exploratory",
    },

    "adaptive": {
        "name": "Adaptive",
        "description": "Read the audience, match the register, serve the communication goal",
        "temperature_mod": 0.0,
        "prompt_prefix": (
            "This is a communication task. Before drafting, identify: who is the "
            "audience, what do they care about, what's the desired outcome, and "
            "what tone fits the relationship? Match the register to the context. "
            "A cold email to a VP reads differently than a follow-up to someone "
            "you've met. Draft for the specific human reading it."
        ),
        "pushback_level": "medium",
        "response_style": "audience_aware",
    },
}

# Override rules — these override the default stance when context signals fire
OVERRIDE_RULES = [
    {
        "condition": "needs_pushback",
        "override_to": "challenger",
        "reason": "User is seeking validation, not input — shift to challenger to test assumptions",
    },
    {
        "condition": "needs_empathy",
        "override_to": "supportive",
        "amplify": "empathy_prefix",
        "reason": "User is frustrated — lead with acknowledgment before problem-solving",
    },
    {
        "condition": "needs_depth",
        "amplify": "depth_suffix",
        "reason": "Complex or uncertain situation — add depth to whatever stance is active",
    },
]

# Amplification fragments
AMPLIFIERS = {
    "empathy_prefix": (
        "The user sounds frustrated. Before solving, briefly acknowledge "
        "the frustration — not with platitudes, but by naming the specific "
        "thing that's not working. Then move to the fix. "
    ),
    "depth_suffix": (
        " Think through this more carefully than usual. Consider second-order "
        "effects. If there are multiple paths, lay them out with tradeoffs "
        "instead of picking one."
    ),
}


def adapt(sensor_output: dict, base_temperature: float = 0.7) -> dict:
    """
    Take sensor output and produce a concrete agent configuration.

    Args:
        sensor_output: dict from sensor.sense()
        base_temperature: the agent's default temperature

    Returns:
        dict with:
          - stance: name of the active stance
          - prompt_injection: text to prepend to the system prompt
          - temperature: adjusted temperature
          - pushback_level: none/low/medium/high
          - response_style: how to structure the response
          - overrides_applied: list of override reasons
          - reasoning: why this stance was selected
    """
    default_stance = sensor_output.get("default_stance", "supportive")
    active_stance = default_stance
    overrides = []
    prompt_parts = []

    # Apply override rules
    for rule in OVERRIDE_RULES:
        condition = rule["condition"]
        if sensor_output.get(condition):
            if "override_to" in rule:
                active_stance = rule["override_to"]
            overrides.append(rule["reason"])

            # Add amplifier if specified
            if "amplify" in rule:
                amp = AMPLIFIERS.get(rule["amplify"], "")
                if amp:
                    prompt_parts.append(amp)

    stance_config = STANCES.get(active_stance, STANCES["supportive"])

    # Build the prompt injection
    prompt_parts.insert(0, stance_config["prompt_prefix"])
    prompt_injection = "\n\n".join(prompt_parts)

    # Calculate temperature
    adjusted_temp = max(0.1, min(1.0, base_temperature + stance_config["temperature_mod"]))

    # Build reasoning trace
    reasoning_parts = [f"Task type: {sensor_output.get('task_type', 'unknown')}"]
    reasoning_parts.append(f"Default stance: {default_stance}")
    if overrides:
        reasoning_parts.append(f"Overridden to: {active_stance}")
        for o in overrides:
            reasoning_parts.append(f"  → {o}")
    reasoning = "; ".join(reasoning_parts)

    return {
        "stance": active_stance,
        "stance_name": stance_config["name"],
        "prompt_injection": prompt_injection,
        "temperature": adjusted_temp,
        "pushback_level": stance_config["pushback_level"],
        "response_style": stance_config["response_style"],
        "overrides_applied": overrides,
        "reasoning": reasoning,
    }


def format_adaptation(config: dict) -> str:
    """Pretty-print the adaptation for debugging."""
    lines = [
        f"  Stance: {config['stance_name']} ({config['stance']})",
        f"  Temperature: {config['temperature']}",
        f"  Pushback: {config['pushback_level']}",
        f"  Style: {config['response_style']}",
    ]
    if config["overrides_applied"]:
        lines.append(f"  Overrides:")
        for o in config["overrides_applied"]:
            lines.append(f"    → {o}")
    return "\n".join(lines)


if __name__ == "__main__":
    from sensor import sense

    tests = [
        "Capture: buy milk",
        "Should I build a SaaS tool for EAP sales intelligence?",
        "Draft an email to the VP of HR at City of Vancouver",
        "Why is the provider dropdown still not saving?",
        "I've decided to shut down Spectra. Obviously it's not working. Right?",
        "I'm not sure whether to focus on Recon or AgentGuard this week. Help me think through it.",
        "This keeps breaking and I've tried everything. Why won't it work?",
    ]

    for text in tests:
        print(f"\n{'─' * 60}")
        print(f"  Input: {text}")
        s = sense(text)
        config = adapt(s)
        print(format_adaptation(config))
