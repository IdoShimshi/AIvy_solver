"""Convert ivybench Ivy files into the benchmarks/ stripped+ground_truth format.

Walks ``temp/problems/ivybench/<category>/ivy/*.ivy`` and produces
``benchmarks/<name>/{stripped.ivy, ground_truth.ivy}``.

For each source file we extract every top-level ``invariant`` / ``conjecture``
statement (live or commented out, possibly multi-line), classify it as either
the safety property of the protocol or an inductive helper, and emit:

* ``stripped.ivy``  -- source minus *all* helper invariants (live or commented).
* ``ground_truth.ivy`` -- safety + every helper uncommented and live.

Safety vs. helper heuristic (live invariants only):
  * label ``[safety]``                    -> safety
  * label starts with ``ic3po`` / ``manual`` (case-insensitive) -> helper
  * any other label, or no label          -> safety

Commented-out invariants are always treated as helpers.

Safety label normalization:
  * ``[safety]`` is kept as is.
  * Any other existing label ``[X]`` is rewritten to ``[safety_X]``.
  * Unlabeled safety invariants get ``[safety_1]``, ``[safety_2]``, ...

Naming: directory name is always ``<category>_<basename>`` (lowercased with
``-`` replaced by ``_``) so the source category is preserved in the name.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "temp" / "problems" / "ivybench"
DEFAULT_OUTPUT = REPO_ROOT / "benchmarks"

INVARIANT_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<hash>#+\s*)?(?P<kw>invariant|conjecture)\b(?P<rest>.*)$"
)
DISABLED_HASH_RE = re.compile(r"^\s*##")
LABEL_RE = re.compile(r"^\s*\[(?P<label>[^\]]+)\]\s*(?P<body>.*)$", re.DOTALL)
CONTINUATION_TOKENS = ("->", "&", "|", ",", "(")
LEADING_CONTINUATION_RE = re.compile(r"^\s*(->|&|\||,)")
HELPER_LABEL_PREFIXES = ("ic3po", "manual")


@dataclass
class InvariantBlock:
    """A single invariant/conjecture statement, possibly spanning multiple lines."""

    start: int
    end: int
    commented: bool
    label: str | None
    body: str
    role: str = "unclassified"
    disabled: bool = False


@dataclass
class ParsedFile:
    lines: list[str]
    blocks: list[InvariantBlock]


def _strip_comment_prefix(line: str) -> tuple[bool, str]:
    """Strip a single leading ``#`` (with optional trailing space) from ``line``.

    Returns ``(was_commented, content_without_hash)``.
    """
    stripped = line.lstrip()
    if stripped.startswith("#"):
        rest = stripped[1:]
        if rest.startswith(" "):
            rest = rest[1:]
        leading_ws = line[: len(line) - len(stripped)]
        return True, leading_ws + rest
    return False, line


def _line_is_blank_or_pure_comment(line: str) -> bool:
    s = line.strip()
    return s == "" or s.startswith("#")


def _last_meaningful_token(line: str) -> str:
    """Return the last few non-whitespace characters of ``line``."""
    return line.rstrip().rstrip("\r\n").rstrip()


def _ends_with_continuation(line: str) -> bool:
    s = _last_meaningful_token(line)
    if not s:
        return False
    for tok in CONTINUATION_TOKENS:
        if s.endswith(tok):
            return True
    return False


def _paren_balance(text: str) -> int:
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
    return depth


def parse_invariants(source: str) -> ParsedFile:
    """Locate every (live or commented) invariant/conjecture block in ``source``.

    Multi-line statements are stitched back together based on parenthesis
    balance and trailing continuation operators (``->``, ``&``, ``|``, ``,``,
    ``(``). The original source lines are preserved verbatim.

    Commented invariants that appear *before the first live invariant* in the
    file are marked ``disabled``: in the ivybench corpus these are always
    template/preamble code (e.g. inside a fully-commented module definition or
    a leftover predecessor of the live safety property), never real helpers.
    """
    lines = source.splitlines(keepends=True)
    blocks: list[InvariantBlock] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        m = INVARIANT_LINE_RE.match(line)
        if not m:
            i += 1
            continue

        commented = m.group("hash") is not None
        disabled = DISABLED_HASH_RE.match(line) is not None
        rest = m.group("rest")
        body_chunks = [rest]

        depth = _paren_balance(rest)
        last_line_for_continuation = rest
        end = i

        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            if commented:
                next_stripped = next_line.lstrip()
                if not next_stripped.startswith("#"):
                    break
                _, uncommented = _strip_comment_prefix(next_line)
                next_content = uncommented
            else:
                if next_line.strip().startswith("#"):
                    break
                next_content = next_line

            need_continue = (
                depth > 0
                or _ends_with_continuation(last_line_for_continuation)
                or LEADING_CONTINUATION_RE.match(next_content) is not None
            )
            if not need_continue:
                break

            body_chunks.append(next_content)
            depth += _paren_balance(next_content)
            last_line_for_continuation = next_content
            end = j
            j += 1

        body = "".join(body_chunks).strip()
        label, body_no_label = _split_label(body)
        blocks.append(
            InvariantBlock(
                start=i,
                end=end,
                commented=commented,
                label=label,
                body=body_no_label,
                disabled=disabled,
            )
        )
        i = end + 1

    first_live_idx = next(
        (idx for idx, b in enumerate(blocks) if not b.commented),
        None,
    )
    if first_live_idx is not None:
        for b in blocks[:first_live_idx]:
            if b.commented:
                b.disabled = True

    return ParsedFile(lines=lines, blocks=blocks)


def _split_label(body: str) -> tuple[str | None, str]:
    m = LABEL_RE.match(body)
    if not m:
        return None, body.strip()
    return m.group("label").strip(), m.group("body").strip()


def classify(blocks: Iterable[InvariantBlock]) -> None:
    """Tag each block with role ``safety`` or ``helper``."""
    for blk in blocks:
        if blk.disabled:
            blk.role = "disabled"
            continue
        if blk.commented:
            blk.role = "helper"
            continue
        label = (blk.label or "").lower()
        if label == "safety":
            blk.role = "safety"
            continue
        if any(label.startswith(p) for p in HELPER_LABEL_PREFIXES):
            blk.role = "helper"
            continue
        blk.role = "safety"


def _normalize_safety_label(original: str | None, safety_index: int) -> str:
    if original is None:
        return f"safety_{safety_index}"
    cleaned = original.strip()
    if cleaned.lower() == "safety":
        return "safety"
    if cleaned.lower().startswith("safety_"):
        return cleaned
    return f"safety_{cleaned}"


def _render_safety_lines(
    blk: InvariantBlock, original_lines: list[str], new_label: str
) -> list[str]:
    """Return the line(s) for ``blk`` rewritten as ``invariant [new_label] body``.

    Preserves the original indentation of the first line.
    """
    first = original_lines[blk.start]
    indent_match = re.match(r"^(\s*)", first)
    indent = indent_match.group(1) if indent_match else ""
    line = f"{indent}invariant [{new_label}] {blk.body}\n"
    return [line]


def _render_helper_lines(blk: InvariantBlock, original_lines: list[str]) -> list[str]:
    """Render a (live) helper invariant from its block, preserving its label."""
    first = original_lines[blk.start]
    indent_match = re.match(r"^(\s*)", first)
    indent = indent_match.group(1) if indent_match else ""
    label_part = f" [{blk.label}]" if blk.label else ""
    line = f"{indent}invariant{label_part} {blk.body}\n"
    return [line]


def build_outputs(parsed: ParsedFile) -> tuple[str, str]:
    """Return ``(stripped, ground_truth)`` text for a parsed file.

    The stripped file is truncated immediately after the last safety
    invariant: the corpus never has meaningful Ivy declarations below the
    invariant block, and truncating wipes out every leaky tail (descriptive
    comments above commented helpers, ``### proof certificate ###`` style
    section markers, leftover ``##conjecture`` hints, etc.).
    """
    classify(parsed.blocks)

    lines = parsed.lines
    n = len(lines)

    block_by_start: dict[int, InvariantBlock] = {b.start: b for b in parsed.blocks}
    block_end_by_start: dict[int, int] = {b.start: b.end for b in parsed.blocks}

    safety_blocks = [b for b in parsed.blocks if b.role == "safety"]
    last_safety_end = max(b.end for b in safety_blocks)

    safety_index = 0

    def emit_safety_replacement(blk: InvariantBlock) -> list[str]:
        nonlocal safety_index
        if blk.label is None:
            safety_index += 1
            new_label = f"safety_{safety_index}"
        else:
            new_label = _normalize_safety_label(blk.label, safety_index)
        return _render_safety_lines(blk, lines, new_label)

    stripped_out: list[str] = []
    gt_out: list[str] = []

    i = 0
    while i < n:
        if i in block_by_start:
            blk = block_by_start[i]
            end = block_end_by_start[i]
            if blk.disabled:
                pass
            elif blk.role == "safety":
                replacement = emit_safety_replacement(blk)
                if i <= last_safety_end:
                    stripped_out.extend(replacement)
                gt_out.extend(replacement)
            else:
                gt_out.extend(_render_helper_lines(blk, lines))
            i = end + 1
            continue
        if i <= last_safety_end:
            stripped_out.append(lines[i])
        gt_out.append(lines[i])
        i += 1

    stripped_text = _cleanup_blank_runs("".join(stripped_out))
    if stripped_text and not stripped_text.endswith("\n"):
        stripped_text += "\n"
    gt_text = _cleanup_blank_runs("".join(gt_out))
    return stripped_text, gt_text


def _cleanup_blank_runs(text: str) -> str:
    """Collapse runs of 3+ blank lines into 2 to keep output tidy."""
    return re.sub(r"\n{4,}", "\n\n\n", text)


def _slugify(name: str) -> str:
    return name.lower().replace("-", "_")


@dataclass
class WorkItem:
    source: Path
    category: str
    base_name: str
    slug: str
    final_name: str = ""


@dataclass
class SkipReport:
    items: list[tuple[Path, str]] = field(default_factory=list)

    def add(self, path: Path, reason: str) -> None:
        self.items.append((path, reason))


def collect_work(source_root: Path) -> list[WorkItem]:
    """Discover every source file and assign output directory names.

    The directory name is always ``<category>_<basename>`` so that the
    provenance is visible in the name and there are never collisions.
    """
    items: list[WorkItem] = []
    for cat_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        ivy_dir = cat_dir / "ivy"
        if not ivy_dir.is_dir():
            continue
        for src in sorted(ivy_dir.glob("*.ivy")):
            base = src.stem
            slug = _slugify(base)
            items.append(
                WorkItem(
                    source=src,
                    category=cat_dir.name,
                    base_name=base,
                    slug=slug,
                    final_name=f"{_slugify(cat_dir.name)}_{slug}",
                )
            )
    return items


def process_one(
    item: WorkItem, output_root: Path, force: bool, skipped: SkipReport
) -> bool:
    text = item.source.read_text()
    parsed = parse_invariants(text)
    if not parsed.blocks:
        skipped.add(item.source, "no invariant or conjecture found")
        return False

    classify(parsed.blocks)
    safety_blocks = [b for b in parsed.blocks if b.role == "safety"]
    if not safety_blocks:
        skipped.add(item.source, "no safety invariant identified")
        return False

    stripped_text, gt_text = build_outputs(parsed)

    out_dir = output_root / item.final_name
    if out_dir.exists() and not force:
        skipped.add(
            item.source, f"output directory already exists: {out_dir} (use --force)"
        )
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "stripped.ivy").write_text(stripped_text)
    (out_dir / "ground_truth.ivy").write_text(gt_text)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing output directories generated by this script",
    )
    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"source not found: {args.source}", file=sys.stderr)
        return 2

    work = collect_work(args.source)
    skipped = SkipReport()
    written = 0
    for item in work:
        if process_one(item, args.output, args.force, skipped):
            written += 1

    print(f"wrote {written} benchmark(s) to {args.output}")
    if skipped.items:
        print(f"\nskipped {len(skipped.items)} file(s):")
        for path, reason in skipped.items:
            rel = path.relative_to(REPO_ROOT) if REPO_ROOT in path.parents else path
            print(f"  {rel}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
