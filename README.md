# AIvy Solver

LLM-based invariant synthesis for [Ivy](https://kenmcmil.github.io/ivy/) protocol verification.

Given an Ivy program with a safety property but missing supporting invariants, AIvy uses an LLM to synthesize the invariants, checks them with `ivy_check`, and retries with error feedback on failure.

## Setup

Requires Python 3.10+.

```bash
pip install -e .
```

### LLM Provider

AIvy uses [litellm](https://docs.litellm.ai/docs/providers) under the hood, so it works with any provider litellm supports (OpenAI, Anthropic, Google Gemini, OpenRouter, etc.).

Set the appropriate API key as an environment variable or in a `.env` file in the project root:

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# OpenRouter
export OPENROUTER_API_KEY=sk-or-...

# Google Gemini
export GEMINI_API_KEY=...
```

The model string you pass with `--model` determines which provider and key are used. See the [litellm docs](https://docs.litellm.ai/docs/providers) for the full list.

### ivy_check

You need the `ivy_check` binary installed ([Ivy installation guide](https://kenmcmil.github.io/ivy/install.html)).

The binary is resolved in this order:

1. `--ivy-check-command` CLI flag
2. `IVY_CHECK_COMMAND` environment variable (or in `.env`)
3. `ivy_check` on your `PATH`

## Usage

```bash
# Solve a single problem
python -m aivy_solver benchmarks/ex_toy_consensus

# Run all problems in a directory
python -m aivy_solver benchmarks/

# Pick a model (any litellm-compatible string)
python -m aivy_solver --model openrouter/anthropic/claude-sonnet-4 benchmarks/ex_toy_consensus

# Control reasoning effort on reasoning-capable models
python -m aivy_solver --model openai/o3 --reasoning-effort high benchmarks/ex_toy_consensus

# Run multiple problems in parallel (e.g. 4 at a time)
python -m aivy_solver -j 4 benchmarks/
```

Run `python -m aivy_solver --help` for all options (model, max attempts, temperature, reasoning effort, timeout, concurrency, etc.).

## How It Works

1. Load `stripped.ivy` — the program with the safety property but no supporting invariants.
2. Run `ivy_check` on the stripped program first. If it already verifies, mark the problem as passed on attempt 0 (no LLM call).
3. Otherwise, send the stripped program plus the `ivy_check` output to the LLM, asking it to propose supporting invariants.
4. Extract the invariants from the model's reply (from a code block or `<answer>` tags).
5. Append them to the stripped program and run `ivy_check` again.
6. If all checks pass — done.
7. If any check fails — feed the `ivy_check` output back to the LLM and retry, up to N attempts.
8. Save results as JSON.

## Benchmarks

Each benchmark is a directory under `benchmarks/<name>/` with two files:

- **`ground_truth.ivy`** — the complete program with all invariants (reference solution).
- **`stripped.ivy`** — the program with supporting invariants removed (the LLM's input).

Benchmarks are grouped by source — directory prefixes indicate origin:

| Prefix | Source |
|--------|--------|
| `ex_` | Ivy distribution examples |
| `i4_` | I4 invariant inference benchmarks |
| `mypyv_` | mypyvy benchmarks |
| `paxos_` | Paxos / consensus protocols |
| `tla_` | TLA+ examples ported to Ivy |
| `multisig_` | Multisig protocols |
| `distai_` | DistAI benchmarks |

Run `ls benchmarks/` to see the full list.

## Results

Results are saved as JSON to `results/<model>_<timestamp>.json` and include, per run:

- The model and reasoning effort used.
- Per-problem success/failure and the attempt the solution was found on.
- For each attempt: the candidate invariants, full `ivy_check` output, the model's reasoning trace (if exposed), and token usage.
