import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aivy_solver.prompts import TIMEOUT_FEEDBACK


@dataclass
class CheckResult:
    passed: bool
    raw_output: str
    timed_out: bool = False

    @property
    def feedback(self) -> str:
        if self.timed_out:
            return TIMEOUT_FEEDBACK
        if self.passed:
            return "All checks passed."
        return self.raw_output


def _parse_check_output(stdout: str, stderr: str) -> CheckResult:
    combined = (stdout + "\n" + stderr).strip()

    if not combined:
        return CheckResult(passed=False, raw_output="ivy_check produced no output.")

    has_fail = "FAIL" in combined or "error" in combined.lower()
    has_pass = "OK" in combined or "PASS" in combined

    if has_fail:
        return CheckResult(passed=False, raw_output=combined)

    if has_pass:
        return CheckResult(passed=True, raw_output=combined)

    return CheckResult(passed=False, raw_output=combined)


async def check_ivy(
    program: str,
    ivy_check_cmd: str = "ivy_check",
    timeout: int = 30,
) -> CheckResult:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ivy", delete=False) as f:
        f.write(program)
        tmp_path = Path(f.name)

    try:
        proc = await asyncio.create_subprocess_exec(
            ivy_check_cmd, str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return CheckResult(passed=False, raw_output="", timed_out=True)

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        stdout = _mask_paths(stdout, tmp_path)
        stderr = _mask_paths(stderr, tmp_path)

        return _parse_check_output(stdout, stderr)
    finally:
        tmp_path.unlink(missing_ok=True)


def _mask_paths(text: str, tmp_path: Path) -> str:
    return text.replace(str(tmp_path), "solution.ivy")
