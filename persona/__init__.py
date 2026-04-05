"""
Persona — Dynamic personality adaptation layer for AI agents.

Three components:
  1. Sensor: classifies the task/environment to determine what's needed
  2. Stance: selects and configures the reasoning posture
  3. Monitor: detects convergence/groupthink in multi-agent settings

Usage:
    from persona import sense, adapt, monitor_convergence

    # Single agent: sense task, get adapted config
    stance = sense("Draft an email to a prospect who ghosted us")
    # → returns: {stance: "challenger", temperature: 0.7, pushback_level: "high", ...}

    # Multi-agent: monitor outputs for groupthink
    drift = monitor_convergence(agent_outputs)
    # → returns: {converging: True, diversity_score: 0.3, recommendation: "inject_dissent"}
"""

from .sensor import sense, classify_task
from .stance import adapt, STANCES
from .monitor import monitor_convergence
