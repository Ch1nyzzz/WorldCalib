"""Seed ARC-AGI-2 scaffold — pure pass-through == the stock single-shot solver.

This is the proposer's starting point. It adds no strategy: :meth:`solve_task`
is inherited unchanged from :class:`~worldcalib.reasoning.arc_scaffolds.base.ArcScaffold`,
which makes one greedy chat call per test input and parses the response into a
single candidate grid. The optimizer evolves this into a smarter solver — e.g. by
overriding :meth:`solve_task` to sample multiple attempts (for pass@2), add
self-consistency or verification, or reshape the prompt with explicit rule
induction.

This file is the proposer's editable seed surface: it is snapshot-copied and
rewritten by the proposer, kept separate from ``base.py`` so the grid helpers and
base plumbing stay stable. It therefore imports helpers only from ``.base`` and
never from ``arc_data`` / ``arc_evaluation`` (absent in the candidate snapshot).

A worked example of the kind of override a candidate might write::

    from worldcalib.reasoning.arc_scaffolds.base import (
        ArcScaffold, ArcSolveResult, build_arc_messages, parse_grid,
    )

    class VotingArcScaffold(ArcScaffold):
        name = "arc_voting"

        def solve_task(self, *, train, test_inputs, client, config,
                       max_tokens, max_attempts):
            attempts, ptoks, ctoks = [], 0, 0
            for test_input in test_inputs:
                messages = build_arc_messages(train, test_input)
                cands = []
                for _ in range(max_attempts):
                    r = client.chat(messages, max_tokens=max_tokens, temperature=0.7)
                    ptoks += r.prompt_tokens
                    ctoks += r.completion_tokens
                    g = parse_grid(r.content)
                    if g is not None:
                        cands.append(g)
                attempts.append(cands)
            return ArcSolveResult(attempts=attempts, prompt_tokens=ptoks,
                                  completion_tokens=ctoks)
"""

from __future__ import annotations

from worldcalib.reasoning.arc_scaffolds.base import ArcScaffold


class PassthroughArcScaffold(ArcScaffold):
    """The stock single-shot solver as an optimizable scaffold."""

    name = "arc_passthrough"
    # solve_task() is inherited from ArcScaffold — the pure seed behavior.


def build_scaffold() -> PassthroughArcScaffold:
    """Factory hook used by the dynamic candidate loader."""
    return PassthroughArcScaffold()


SCAFFOLD_CLASS = PassthroughArcScaffold
