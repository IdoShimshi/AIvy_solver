# AIvy Solver

LLM-based invariant synthesis for [Ivy](https://kenmcmil.github.io/ivy/) protocol verification.

Given an Ivy program with a safety property but missing supporting invariants, AIvy uses an LLM to synthesize the invariants, checks them with `ivy_check`, and retries with error feedback on failure.

## Setup

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
python -m aivy_solver benchmarks/toy_consensus

# Run all problems in a directory
python -m aivy_solver benchmarks/

# Specify a model
python -m aivy_solver --model openai/gpt-4o benchmarks/toy_consensus
```

Run `python -m aivy_solver --help` for all options (model, max attempts, temperature, timeout, etc.).

## How It Works

1. Loads `stripped.ivy` — the program with the safety property but without supporting invariants
2. Sends it to the LLM with a prompt explaining the task
3. Extracts Ivy code from the response
4. Verifies no existing lines were modified (only new `invariant` lines are allowed)
5. Runs `ivy_check` on the candidate solution
6. If all checks pass — done
7. If any check fails — feeds the `ivy_check` output back to the LLM and retries (up to N attempts)
8. Saves results as JSON

## Benchmarks

Each benchmark is a directory under `benchmarks/<name>/` with two files:

- **`ground_truth.ivy`** — the complete program with all invariants (reference solution)
- **`stripped.ivy`** — the program with supporting invariants removed (the LLM's input)

| Problem | Description | Invariants to find |
|---------|-------------|-------------------|
| `toy_consensus` | Quorum-based consensus | 2 |
| `decentralized_lock` | Decentralized lock passing | 3 |
| `lockserv` | Lock server protocol | 8 |

## Results

Results are saved as JSON to `results/` with per-attempt details (ivy_check output, LLM solution) and final success/failure status.
