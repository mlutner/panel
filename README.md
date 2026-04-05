# Panel

**Multi-model idea evaluation. 7 AI panelists debate your idea from different stances, producing a dissent map and letter grade.**

Panel is a CLI tool that takes an idea and runs it through a structured evaluation process inspired by [Delphi panels](https://ijds.org/Volume11/IJDSv11p305-321Avella2434.pdf), [Red-Blue Team exercises](https://neurofied.com/red-blue-team-intervention/), and Tetlock's [superforecasting research](https://www.econtalk.org/philip-tetlock-on-superforecasting/). The result is a balanced assessment with genuine push-and-pull — not a single model's opinion, but a structured disagreement.

---

## Philosophy

**The problem:** When you ask one AI for feedback on an idea, you get one perspective shaped by one training set, one alignment process, and one reasoning style. If you ask the same model five times with different prompts, you get five variations of the same perspective. That's not a panel — that's an echo chamber with costume changes.

**The solution:** Panel routes your idea to 7 different language models from different providers, each assigned a distinct **stance** and **persona**. The models don't know about each other. They can't coordinate. Their training data, reasoning styles, and cultural biases are genuinely different. The result is structured dissent — not consensus.

**The composition (based on research):**

| Stance | Count | Purpose |
|--------|-------|---------|
| **Constructive** | 2 | Argue FOR the idea with evidence. Find genuine strengths. |
| **Analytical** | 2 | Neutral. Data, math, base rates. No opinions. |
| **Adversarial** | 2 | Argue AGAINST with specifics. Name competitors, dates, numbers. |
| **Wild Card** | 1 | Outside perspective. Different industry, culture, frame. |

This 2-2-2-1 balance ensures no stance gets a majority. The constructive panelists can't outvote the adversarial ones, and vice versa. The wild card breaks ties with perspectives nobody else can provide.

**Why 7 members:** Delphi method research shows 7-12 is optimal for heterogeneous expert panels — enough cognitive diversity to surface blind spots, small enough to avoid coordination decay. Tetlock's superforecasting teams used ~12 members but found that **diversity of thinking style matters more than raw ability**.

**Why different models:** Claude, GPT, Gemini, DeepSeek, and Qwen are trained on different data, by different teams, with different alignment philosophies. DeepSeek and Qwen bring Chinese training data and cultural perspective. Open-source models (GPT-OSS, Step, GLM) add further divergence. This isn't prompt engineering — it's genuine epistemic diversity.

---

## Quick Start

```bash
git clone https://github.com/mlutner/panel.git
cd panel
python3 -m venv .venv
source .venv/bin/activate
pip install pyyaml httpx numpy

export OPENROUTER_API_KEY=sk-or-...

python panel.py "Your idea here" --domain auto
```

---

## Usage

```bash
# Auto-detect domain, 7-member panel (default)
panel "An AI tool that evaluates startup ideas"

# Force a domain
panel "An AI tool that evaluates startup ideas" --domain strategy

# Add context so panelists understand the framing
panel "Recon sales intelligence tool" --context "Internal tool for a 4-person team, not a product"

# Compact panel (5 members, faster)
panel "My idea" --size 5

# Swarm mode (9 members, more perspectives)
panel "My idea" --size 9

# From a file
panel --file ~/ideas/my-concept.md --domain creative

# Skip interactive feedback
panel "My idea" --no-feedback

# JSON output for piping
panel "My idea" --json --quiet

# View calibration data
panel --calibration
```

---

## Domains

Each domain has 7 personas tailored to that evaluation context:

| Domain | Personas |
|--------|----------|
| **strategy** | Champion, First Customer, Analyst, Data Scientist, Killer, Incumbent, Outsider |
| **coding** | Architect, Builder, Perf Engineer, Security Reviewer, Tech Debt Collector, Nihilist, User Zero |
| **writing** | Amplifier, Reader, Structure Editor, Fact Checker, Cutter, Bullshit Detector, Wrong Audience |
| **creative** | Visionary, First User, Originality Analyst, Design Critic, Attention Economist, Graveyard Keeper, Outsider |

---

## Models

Panel uses 8 models across 8 providers for maximum diversity:

| Model | Provider | Default Role | Why |
|-------|----------|-------------|-----|
| Claude 4.6 | Anthropic | Data Scientist | Careful, does the math, honest about uncertainty |
| GPT-5.4 | OpenAI | Incumbent | Structured, confident, strong at role-playing CEOs |
| Gemini 3.1 Pro | Google | Champion | Exploratory reasoning, finds genuine strengths |
| DeepSeek R1 | DeepSeek | Killer | Aggressive reasoning, natural contrarian |
| Qwen 3.6 Plus | Qwen | Fallback + primary | Reliable, free, global perspective |
| GPT-OSS 120B | OpenAI OSS | First Customer | Balanced, practical |
| Step 3.5 | StepFun | Outsider | Chinese startup, different cultural frame |
| GLM 4.5 | Zhipu | Analyst | Methodical, mathematical |

If a model fails (rate limits, bad JSON), Qwen 3.6 automatically fills the seat as fallback.

---

## Output

Every run produces a markdown report saved to `output/`:

- **Grade:** A through F (average of all panelist scores)
- **Variance:** How much panelists disagree (high = polarizing)
- **Build Votes:** How many panelists would invest time/money
- **Flags:**
  - `FIXABLE FLAW` — multiple panelists independently flagged the same weakness
  - `FRAGILE` — every panelist found a different weakness (wide attack surface)
  - `POLARIZING` — high score variance (panelists strongly disagree)
  - `WEAK DISSENT` — adversarial panelists agree with the majority (not enough challenge)
- **Dissent Map:** Where the panel agrees vs. disagrees
- **Individual Responses:** Each panelist's score, strongest point, weakest point, unanswered question, and confidence

---

## Example Output

This is a real panel run evaluating [AgentGuard](https://github.com/mlutner/agentguard) — a Python SDK for AI agent safety:

### Grade: C (4.7/10) — POLARIZING

| Metric | Value |
|--------|-------|
| Average Score | 4.7/10 |
| Variance | 4.9 |
| Build Votes | 3/7 |
| Avg Confidence | 79% |

**Flags:**
- FIXABLE FLAW: Multiple panelists flagged zero users + production trust gap
- FIXABLE FLAW: Multiple panelists flagged LangSmith bundling risk
- POLARIZING: Score variance is 4.9 — panelists strongly disagree

### Dissent Map

**Agreement:** 4/7 panelists scored this below 5 — serious concerns about defensibility.

**Disagreement:** Champion (8/10) and First Customer (7/10) vs Killer, Incumbent, Analyst, Outsider (all 3/10) — fundamental split between "this solves real pain" and "this gets cloned in a quarter."

### Selected Panelist Responses

**Champion (Gemini 3.1 Pro) — 8/10 👍**
> Strongest: The acute, universal pain point of agent infinite loops and runaway API costs is perfectly solved by a simple, framework-agnostic @guard decorator.

**First Customer (Qwen 3.6) — 7/10 👍**
> As Head of AI Engineering at an 85-person fintech, this solves my exact Tuesday panic: debugging async agent loops that burned $412 over the weekend.

**Data Scientist (Claude 4.6) — 6/10 👍**
> Base rate for developer tools reaching meaningful adoption within 18 months is roughly 5-8% of launched projects. Need n>=384 agent runs per condition (80% power, p<0.05) to validate the safety value proposition.

**Incumbent (GPT-5.4) — 3/10 👎**
> As David Cancel, CEO of Drift: The product is too thin and too easy to copy. LangSmith already provides tracing/evaluations, Helicone has spend monitoring, Humanloop and Arize cover drift/evals.

**Outsider (Qwen 3.6) — 3/10 👎**
> A Python decorator is structurally too soft for safety enforcement; it assumes agents play by framework rules, ignoring cross-process escapes and self-modifying code.

---

## Calibration

After each run, you can rate which panelists gave the most useful feedback (1-5). This trains the casting algorithm over time — models that consistently give high-quality responses in specific roles get assigned to those roles more often.

```bash
# View calibration data
panel --calibration

# Ratings are stored in config/calibration.json
```

---

## How It Works

```
INPUT ("Your idea")
  │
  ├─ 1. CLASSIFY — Ollama nomic-embed-text embeds the input,
  │     cosine similarity against domain descriptions → best domain
  │
  ├─ 2. CAST — Load domain roles + model profiles,
  │     score each model for each role based on:
  │       • Domain strength
  │       • Historical calibration
  │       • Provider diversity (max 1 per provider)
  │       • Stance alignment (contrarian → adversarial, etc.)
  │     Assign 7 (model, role) pairs
  │
  ├─ 3. RUN — 7 parallel async calls to OpenRouter,
  │     each gets: stance instruction + role prompt + input
  │     each returns: structured JSON (score, strengths, weaknesses)
  │     failed models auto-retry with Qwen 3.6 fallback
  │
  ├─ 4. SYNTHESIZE — Dissent map, consensus analysis, flags,
  │     letter grade, full markdown report
  │
  └─ 5. SAVE — Report to output/{timestamp}-{domain}.md
```

---

## Design Decisions

**Why not just use one model with different system prompts?**
Claude playing a "devil's advocate" is still Claude. It hedges. It finds the safe middle. It produces what [one panelist called](output/) "prompt theater — synthetic disagreement that's predictable rather than reflecting real epistemic differences." Different models trained by different teams on different data produce genuinely different reasoning patterns.

**Why OpenRouter instead of direct API calls?**
Single API key, unified interface, access to free-tier models from multiple providers. Panel uses ~$0.02-0.05 per run when mixing paid and free models.

**Why local embeddings for classification?**
The classifier runs Ollama nomic-embed-text locally (274MB model). This means classification is instant, free, and works offline. Only the panel run itself needs OpenRouter.

**Why 2-2-2-1 instead of equal distribution?**
Equal distribution (all neutral) produces lukewarm consensus. The research on Red-Blue Team exercises shows that **assigned adversarial roles produce better outcomes than "just be honest" instructions**. People (and models) argue harder when given permission to dissent. The 2-2-2-1 structure ensures genuine tension without one side dominating.

---

## Requirements

- Python 3.9+
- [Ollama](https://ollama.ai) with `nomic-embed-text` model (for classification)
- [OpenRouter API key](https://openrouter.ai) (free tier works for most models)

```bash
# Install Ollama and pull embedding model
ollama pull nomic-embed-text
```

---

## File Structure

```
panel/
├── panel.py           # CLI entry point
├── classifier.py      # Domain detection via local embeddings
├── caster.py          # Model selection + role assignment
├── runner.py          # Parallel OpenRouter calls with fallback
├── synthesis.py       # Dissent map + consensus report
├── feedback.py        # Post-run rating → calibration update
├── config/
│   ├── models.yaml    # Model profiles (8 models, 8 providers)
│   ├── calibration.json  # Learned performance scores (starts empty)
│   └── domains/
│       ├── strategy.yaml  # 7 personas: Champion → Outsider
│       ├── coding.yaml    # 7 personas: Architect → User Zero
│       ├── writing.yaml   # 7 personas: Amplifier → Wrong Audience
│       └── creative.yaml  # 7 personas: Visionary → Outsider
└── output/            # Saved reports (gitignored)
```

---

## License

MIT
