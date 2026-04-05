"""
Persona — Algorithmic personality adaptation layer for AI agents.

Three components:
  1. Factory: deterministic persona generation (text → features → config)
     No LLM calls. Same inputs → same output. A/B testable.
  2. Monitor: convergence/groupthink detection for multi-agent systems
  3. Sensor/Stance: legacy interface (kept for compatibility, factory is preferred)

Primary interface:
    from persona import create_persona, monitor_convergence

    config = create_persona("Should I pivot this product?", session_history=["supportive", "supportive"])
    # → PersonaConfig(stance="challenger", temperature=0.6, pushback_level=0.64, ...)
"""

from .factory import create_persona, extract_features, generate_persona, PersonaConfig, TaskFeatures, format_persona
from .monitor import monitor_convergence, format_monitor
