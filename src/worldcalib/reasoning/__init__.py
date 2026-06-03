"""ARC-AGI-2 single-shot reasoning backend.

This package wires the ARC-AGI-2 abstraction-and-reasoning benchmark into the
WorldCalib optimizer, mirroring the existing tau2 integration (self-distill
world-model calibration, no external critic). Unlike the agentic backends there
is no agent loop, no memory retrieval and no stateful environment: a *solver*
scaffold is given the train demonstration grid-pairs plus a test input grid and
must predict the output grid in a single served-model chat call (pass@2 scoring
by exact grid match), the way locomo calls the target model.

The module is kept deliberately free of heavy imports so it stays import-safe
when copied into a *partial* snapshot during proposer edits — only the
``arc_scaffolds`` subtree and the locomo base files are present there.
"""
