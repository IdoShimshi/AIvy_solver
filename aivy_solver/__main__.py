import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from aivy_solver.config import Config
from aivy_solver.problem import Problem
from aivy_solver.runner import run_benchmark, solve_problem


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
        level=logging.DEBUG if verbose else logging.INFO,
        stream=sys.stderr,
    )


def _is_single_problem(path: Path) -> bool:
    return (path / "stripped.ivy").exists()


def _build_parser() -> argparse.ArgumentParser:
    defaults = Config()
    p = argparse.ArgumentParser(
        description="AIvy — LLM-based invariant synthesis for Ivy verification.",
    )
    p.add_argument(
        "path", nargs="?", default="benchmarks",
        help="Path to a single problem dir or a directory of problems (default: benchmarks/)",
    )
    p.add_argument("--model", default=defaults.model, help=f"LLM model in litellm format (default: {defaults.model})")
    p.add_argument("--max-attempts", type=int, default=defaults.max_attempts, help=f"Max retries per problem (default: {defaults.max_attempts})")
    p.add_argument("--temperature", type=float, default=defaults.temperature, help=f"LLM sampling temperature (default: {defaults.temperature})")
    p.add_argument("--results-dir", default=str(defaults.results_dir), help=f"Directory to save results (default: {defaults.results_dir})")
    p.add_argument("--ivy-check-command", default=defaults.ivy_check_command, help=f"Path to ivy_check binary (default: {defaults.ivy_check_command})")
    p.add_argument("--ivy-check-timeout", type=int, default=defaults.ivy_check_timeout, help=f"Timeout in seconds for ivy_check (default: {defaults.ivy_check_timeout})")
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return p


def main() -> None:
    load_dotenv()

    args = _build_parser().parse_args()
    _setup_logging(args.verbose)

    target = Path(args.path)
    if not target.exists():
        print(f"Error: path does not exist: {target}")
        sys.exit(1)

    config = Config(
        model=args.model,
        max_attempts=args.max_attempts,
        temperature=args.temperature,
        results_dir=Path(args.results_dir),
        ivy_check_command=args.ivy_check_command,
        ivy_check_timeout=args.ivy_check_timeout,
    )

    if _is_single_problem(target):
        problem = Problem.load(target)
        result = asyncio.run(solve_problem(problem, config))
        if result.success:
            print(f"\nPASSED on attempt {result.success_on_attempt}")
            winning = result.attempts[result.success_on_attempt - 1]
            print("\n--- Winning solution ---")
            print(winning.llm_solution)
        else:
            print(f"\nFAILED after {result.total_attempts} attempts")
            if result.attempts:
                print(f"\nLast ivy_check output:\n{result.attempts[-1].ivy_output}")
    else:
        problems = Problem.load_all(target)
        if not problems:
            print(f"Error: no problems found in {target}")
            sys.exit(1)

        run_result = asyncio.run(run_benchmark(problems, config))
        out_path = run_result.save(config.results_dir)
        n_passed = sum(1 for p in run_result.problems if p.success)
        print(f"\nResults saved to {out_path}")
        print(f"Success rate: {run_result.success_rate:.0%} ({n_passed}/{len(run_result.problems)})")


if __name__ == "__main__":
    main()
