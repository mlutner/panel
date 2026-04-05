"""
runner.py — Parallel OpenRouter API calls for the panel.

Takes the cast (model+role assignments) and runs all 5 panelists
concurrently via httpx async. Each panelist gets a system prompt
(role definition) and the user's input, and must return structured JSON.
"""

import asyncio
import json
import os
import time
import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Structured output schema all panelists must follow
PANELIST_SCHEMA = {
    "score": "integer 1-10 (overall quality of the idea)",
    "strongest_point": "string (the single best thing about this idea)",
    "weakest_point": "string (the single biggest flaw or risk)",
    "unanswered_question": "string (the most important question not addressed)",
    "would_you_build_this": "boolean (would you invest time/money in this?)",
    "confidence": "float 0.0-1.0 (how confident are you in your assessment?)",
}

SCHEMA_INSTRUCTION = """
You MUST respond with valid JSON matching this exact schema:
{
  "score": <integer 1-10>,
  "strongest_point": "<string>",
  "weakest_point": "<string>",
  "unanswered_question": "<string>",
  "would_you_build_this": <true|false>,
  "confidence": <float 0.0-1.0>
}

No markdown, no explanation, no preamble. Just the JSON object.
"""


async def _call_panelist(
    client: httpx.AsyncClient,
    model_id: str,
    role_name: str,
    role_prompt: str,
    user_input: str,
    temperature: float = 0.7,
    stance: str = "neutral",
) -> dict:
    """Call a single panelist via OpenRouter and parse structured response."""
    stance_instruction = {
        "constructive": "Your stance is CONSTRUCTIVE — argue FOR this idea with evidence. Find genuine strengths. But don't cheerlead — if it's weak, say so.",
        "adversarial": "Your stance is ADVERSARIAL — argue AGAINST this idea with specifics. Name companies, dates, numbers. Generic warnings are worthless.",
        "neutral": "Your stance is NEUTRAL — analyze with data and evidence only. No opinions. Show the math.",
        "wild_card": "Your stance is OUTSIDER — bring a perspective nobody else on this panel has. Be genuinely surprising.",
    }.get(stance, "Evaluate honestly.")

    system_prompt = f"""You are serving on a 7-member evaluation panel in the role of: {role_name}

{stance_instruction}

{role_prompt}

IMPORTANT: Use the FULL 1-10 scale. A 5 means mediocre. A 7 means genuinely good.
A 3 means seriously flawed. A 9 means exceptional. Don't cluster around 4-6.

{SCHEMA_INSTRUCTION}"""

    try:
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://localpixel.ca",
                "X-Title": "Panel v1",
            },
            json={
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                "temperature": temperature,
                "max_tokens": 1000,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not raw_content:
            raise ValueError("Empty response from model")
        content = raw_content.strip()

        # Strip thinking model tags (DeepSeek R1, Qwen thinking mode)
        if "<think>" in content:
            think_end = content.rfind("</think>")
            if think_end >= 0:
                content = content[think_end + 8:].strip()

        # Parse JSON from response — handle various wrapping formats
        # Strip markdown code fences
        if "```" in content:
            # Extract content between first pair of ```
            parts = content.split("```")
            for part in parts[1:]:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{"):
                    content = candidate
                    break

        # Strip any leading/trailing non-JSON text
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            content = content[start:end]

        result = json.loads(content)

        # Validate and coerce required fields
        for key in ["score", "strongest_point", "weakest_point", "unanswered_question"]:
            if key not in result:
                result[key] = "N/A" if key != "score" else 5
        # Ensure score is int in range
        try:
            result["score"] = max(1, min(10, int(result["score"])))
        except (ValueError, TypeError):
            result["score"] = 5
        # Ensure boolean
        if "would_you_build_this" not in result:
            result["would_you_build_this"] = result.get("score", 5) >= 7
        # Ensure confidence
        if "confidence" not in result:
            result["confidence"] = 0.5

        return {
            "role": role_name,
            "model": model_id,
            "model_name": data.get("model", model_id),
            "response": result,
            "tokens": data.get("usage", {}),
            "error": None,
        }

    except json.JSONDecodeError as e:
        return {
            "role": role_name,
            "model": model_id,
            "model_name": model_id,
            "response": {
                "score": 0,
                "strongest_point": "Failed to parse response",
                "weakest_point": f"JSON parse error: {e}",
                "unanswered_question": "N/A",
                "would_you_build_this": False,
                "confidence": 0.0,
            },
            "tokens": {},
            "error": f"JSON parse error: {e}",
        }
    except Exception as e:
        return {
            "role": role_name,
            "model": model_id,
            "model_name": model_id,
            "response": {
                "score": 0,
                "strongest_point": "Failed to get response",
                "weakest_point": str(e),
                "unanswered_question": "N/A",
                "would_you_build_this": False,
                "confidence": 0.0,
            },
            "tokens": {},
            "error": str(e),
        }


async def run_panel(assignments: list[dict], user_input: str) -> list[dict]:
    """
    Run all panelists in parallel.

    Args:
        assignments: output from caster.cast() — list of {model, role, role_prompt}
        user_input: the idea/text being evaluated

    Returns:
        list of panelist results with structured responses
    """
    if not OPENROUTER_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY not set. Export it or add to ~/.zshrc"
        )

    start = time.time()

    FALLBACK_MODEL = "qwen/qwen3.6-plus:free"

    async with httpx.AsyncClient() as client:
        tasks = [
            _call_panelist(
                client,
                a["model"]["id"],
                a["role"],
                a["role_prompt"],
                user_input,
                temperature=a.get("temperature", 0.7),
                stance=a.get("stance", "neutral"),
            )
            for a in assignments
        ]
        results = await asyncio.gather(*tasks)

        # Retry failed panelists with Qwen 3.6 fallback
        retry_tasks = []
        retry_indices = []
        for i, r in enumerate(results):
            if r.get("error"):
                retry_indices.append(i)
                a = assignments[i]
                retry_tasks.append(
                    _call_panelist(
                        client,
                        FALLBACK_MODEL,
                        a["role"],
                        a["role_prompt"],
                        user_input,
                        temperature=a.get("temperature", 0.7),
                        stance=a.get("stance", "neutral"),
                    )
                )

        if retry_tasks:
            retries = await asyncio.gather(*retry_tasks)
            for idx, retry_result in zip(retry_indices, retries):
                if not retry_result.get("error"):
                    retry_result["model_name"] = f"{retry_result.get('model_name', FALLBACK_MODEL)} (fallback)"
                    results[idx] = retry_result

    elapsed = round(time.time() - start, 1)

    for r in results:
        r["elapsed_total"] = elapsed

    return list(results)


def run_panel_sync(assignments: list[dict], user_input: str) -> list[dict]:
    """Synchronous wrapper for run_panel."""
    return asyncio.run(run_panel(assignments, user_input))


if __name__ == "__main__":
    # Quick test with a single model
    test_assignments = [{
        "model": {"id": "qwen/qwen3-235b-a22b", "name": "Qwen 3"},
        "role": "CFO",
        "role_prompt": "Evaluate financial viability. Where does the money come from?",
    }]
    results = run_panel_sync(test_assignments, "An AI tool that grades startup ideas")
    print(json.dumps(results, indent=2))
