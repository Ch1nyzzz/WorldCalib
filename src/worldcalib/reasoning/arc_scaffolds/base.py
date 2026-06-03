"""ARC-AGI-2 solver scaffold base — grid helpers + the optimizable surface.

ARC-AGI-2 is a **single-shot reasoning** benchmark: given a task's train
demonstration grid-pairs plus one or more test input grids, the solver must
predict the corresponding output grid(s). There is no agent loop, no memory
retrieval, and no stateful environment — solving a test input is one chat call
to the served target model (via :class:`~worldcalib.model.LocalModelClient`),
exactly like the locomo answer path. Scoring is exact grid match with pass@2.

An :class:`ArcScaffold` is the optimizable policy that turns a task into
predicted grids. It is the ARC analogue of the locomo ``MemoryScaffold`` and the
tau2 ``Tau2Scaffold``: the proposer evolves it to add strategy (better prompts,
multi-attempt sampling, self-consistency, verification, program-style reasoning,
...). The seed (:class:`~worldcalib.reasoning.arc_scaffolds.seed_passthrough.PassthroughArcScaffold`)
adds zero strategy — its :meth:`ArcScaffold.solve_task` is the stock behavior the
optimizer improves on.

Grid helpers live here (not in ``arc_data`` / ``arc_evaluation``) on purpose: the
proposer edits ``seed_passthrough.py`` inside a snapshot that copies **only** the
``arc_scaffolds`` tree plus the locomo base files, so the seed must import its
helpers from ``.base`` and never from ``arc_data`` / ``arc_evaluation`` (which are
not present in the snapshot). This module therefore depends only on the standard
library and ``worldcalib`` ``model`` / ``schemas`` / ``scaffolds.base``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from worldcalib.model import LocalModelClient
from worldcalib.optcore.scaffold_base import ScaffoldMixin
from worldcalib.scaffolds.base import ScaffoldConfig

# A Grid is a rectangular matrix of integer cell values in ``0..9``.
Grid = list[list[int]]


def format_grid(grid: Grid) -> str:
    """Render a grid as text: one row per line, cells space-separated ints."""

    return "\n".join(" ".join(str(int(cell)) for cell in row) for row in grid)


def parse_grid(text: str) -> Grid | None:
    """Parse a grid out of free-form model output.

    Robust to surrounding prose and code fences: strips ``` fences, then takes
    the **maximal trailing block** of consecutive lines that each look like a row
    of space/comma-separated integers. Returns ``None`` if no such block exists.
    """

    if not text:
        return None

    # Drop code fences but keep their contents.
    cleaned = re.sub(r"```[a-zA-Z0-9_]*", "", text).replace("```", "")
    lines = cleaned.splitlines()

    def parse_row(line: str) -> list[int] | None:
        stripped = line.strip()
        if not stripped:
            return None
        tokens = re.split(r"[\s,]+", stripped)
        tokens = [tok for tok in tokens if tok != ""]
        if not tokens:
            return None
        row: list[int] = []
        for tok in tokens:
            if not re.fullmatch(r"-?\d+", tok):
                return None
            row.append(int(tok))
        return row

    parsed: list[list[int] | None] = [parse_row(line) for line in lines]

    # Walk from the bottom, collecting the maximal contiguous run of integer rows.
    block: list[list[int]] = []
    for row in reversed(parsed):
        if row is None:
            if block:
                break
            continue
        block.append(row)
    if not block:
        return None
    block.reverse()
    return block


def grids_equal(a: Grid | None, b: Grid | None) -> bool:
    """Exact equality of two grids; ``None`` never matches anything."""

    if a is None or b is None:
        return False
    if len(a) != len(b):
        return False
    for row_a, row_b in zip(a, b):
        if len(row_a) != len(row_b):
            return False
        for cell_a, cell_b in zip(row_a, row_b):
            if int(cell_a) != int(cell_b):
                return False
    return True


def build_arc_messages(train: list[dict], test_input: Grid) -> list[dict]:
    """Build the seed single-shot prompt for one test input.

    Lays out every train demonstration as an ``Input``/``Output`` grid pair, then
    presents the test input and asks for the output grid as plain rows of
    space-separated digits.
    """

    demo_parts: list[str] = []
    for idx, pair in enumerate(train, start=1):
        demo_parts.append(
            f"Example {idx}:\n"
            f"Input:\n{format_grid(pair['input'])}\n"
            f"Output:\n{format_grid(pair['output'])}"
        )
    demos = "\n\n".join(demo_parts)

    system = (
        "You are solving an ARC-AGI puzzle. Each puzzle has a hidden "
        "transformation rule that maps an input grid to an output grid. Grids are "
        "rectangles of digits 0-9, where each digit is a color. Study the "
        "training examples, infer the single rule that explains all of them, then "
        "apply it to the test input.\n"
        "Respond with ONLY the output grid: one row per line, cells separated by "
        "single spaces, no extra commentary, no labels, no code fences."
    )
    user = (
        f"Training examples:\n\n{demos}\n\n"
        f"Test input:\n{format_grid(test_input)}\n\n"
        "Output grid:"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


@dataclass
class ArcSolveResult:
    """Predicted grids for every test input plus token usage and metadata."""

    attempts: list[list["Grid"]]
    """``len(attempts) == number of test inputs``; ``attempts[i]`` is the ordered
    list of candidate grids for test input ``i`` (empty if parsing failed)."""

    prompt_tokens: int
    completion_tokens: int
    metadata: dict[str, Any] = field(default_factory=dict)


class ArcScaffold(ScaffoldMixin):
    """Base class for an optimizable ARC-AGI-2 solver.

    Subclasses override :meth:`solve_task` to add strategy. The default
    implementation is the seed behavior: one greedy chat call per test input.

    Identity / lifecycle (``name``, ``reference_urls``, ``__init__`` storing a
    :class:`ScaffoldConfig`, and the per-episode ``fresh()`` factory) come from
    :class:`worldcalib.optcore.scaffold_base.ScaffoldMixin`; this class only owns
    the ARC-specific optimizable surface, :meth:`solve_task`.
    """

    name: str = "arc_scaffold"

    # ── the optimizable surface ──────────────────────────────────────────────

    def solve_task(
        self,
        *,
        train: list[dict],
        test_inputs: list["Grid"],
        client: LocalModelClient,
        config: ScaffoldConfig,
        max_tokens: int,
        max_attempts: int,
    ) -> ArcSolveResult:
        """Predict the output grid(s) for a task's test input(s).

        The default (seed) strategy: for each test input, build the prompt via
        :func:`build_arc_messages`, make a single greedy ``client.chat`` call
        (``temperature=0.0``, ``max_tokens=max_tokens``), and parse the response
        with :func:`parse_grid`. ``attempts[i]`` is ``[grid]`` on a successful
        parse or ``[]`` otherwise. Prompt/completion tokens are summed across all
        test inputs.

        Override this to add strategy: multiple sampled attempts (up to
        ``max_attempts`` candidates per test input, used for pass@k scoring),
        self-consistency, verification, or richer prompting.

        Args:
            train: Train demonstration pairs, each ``{"input": Grid, "output": Grid}``.
            test_inputs: The test input grids (outputs are withheld by the runner).
            client: Shared model client for chat calls.
            config: Runtime scaffold configuration.
            max_tokens: Max completion tokens per chat call.
            max_attempts: Max candidate grids per test input to keep (pass@k budget).
        """

        attempts: list[list[Grid]] = []
        prompt_tokens = 0
        completion_tokens = 0
        for test_input in test_inputs:
            messages = build_arc_messages(train, test_input)
            response = client.chat(
                messages,
                max_tokens=max_tokens,
                temperature=0.0,
            )
            prompt_tokens += response.prompt_tokens
            completion_tokens += response.completion_tokens
            grid = parse_grid(response.content)
            attempts.append([grid] if grid is not None else [])
        return ArcSolveResult(
            attempts=attempts,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
