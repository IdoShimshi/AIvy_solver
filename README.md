# AIvy Solver

LLM-based invariant synthesis for [Ivy](https://kenmcmil.github.io/ivy/) protocol verification.

Given an Ivy program with a safety property but missing supporting invariants, AIvy uses an LLM to synthesize the invariants, checks them with `ivy_check`, and retries with error feedback on failure.

## Setup

```bash
pip install -e .
```

You also need `ivy_check` on your PATH (see [Ivy installation](https://kenmcmil.github.io/ivy/install.html)).

Copy `.env` and fill in your API key:
```bash
# .env
OPENROUTER_API_KEY=your-openrouter-api-key-here
```

## Usage

```bash
# Run all benchmarks
python -m aivy_solver

# Run all problems in a directory
python -m aivy_solver benchmarks/

# Solve a single problem
python -m aivy_solver benchmarks/toy_consensus
```

The model, max attempts, and other settings are in `aivy_solver/config.py`.

## How It Works

1. Load `stripped.ivy` — the program with the safety property but no supporting invariants
2. Send to LLM with a system prompt explaining the task
3. Extract Ivy code from the response
4. Verify no existing lines were modified (only new `invariant` lines allowed)
5. Write to temp file, run `ivy_check`, collect full output
6. If all checks PASS — done
7. If FAIL — feed the full `ivy_check` output back to the LLM and retry (up to N attempts)
8. Save results as JSON

## Benchmarks

Each benchmark lives in `benchmarks/<name>/` with two files:

- **`ground_truth.ivy`** — the full program with all invariants (for reference)
- **`stripped.ivy`** — the program with supporting invariants removed (the LLM's input)

Current toy benchmarks:

| Problem | Description | # Invariants to find |
|---------|-------------|---------------------|
| `toy_consensus` | Quorum-based consensus | 2 |
| `decentralized_lock` | Decentralized lock passing | 3 |
| `lockserv` | Lock server protocol | 8 |

## Results

Results are saved as JSON to `results/` with timestamps, per-attempt details, and final success/failure status.
