"""Plot A vs C qualitative / composite scores and their gap across iterations.

The key question: calibration is append-only and grows every iter, so A sees an
ever-thicker world model while C always sees an empty one. If accumulated
calibration carries value, the A-minus-C advantage should GROW with iter. This
plots the two arms and the A-C gap with a linear trend line to test that.

Run:  python scripts/calib_value_test/plot_trend.py
Out:  scripts/calib_value_test/out/trend_A_vs_C.png
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"


def _qual(d: dict | None):
    if not d:
        return None
    ks = ("failure_movement", "trace_movement", "side_effects")
    if any(d.get(k) is None for k in ks):
        return None
    return sum(d[k] for k in ks)


def _linfit(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    return a, b


def main() -> None:
    rows = json.loads((OUT / "scores.json").read_text())
    iters, aq, cq, ac_q, ac_c = [], [], [], [], []
    for r in rows:
        A, C = r.get("A") or {}, r.get("C") or {}
        qa, qc = _qual(A), _qual(C)
        ca, cc = A.get("composite"), C.get("composite")
        if None in (qa, qc, ca, cc):
            continue
        iters.append(r["iter"])
        aq.append(qa)
        cq.append(qc)
        ac_q.append(qa - qc)
        ac_c.append(ca - cc)

    x = list(range(len(iters)))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)

    # --- panel 1: qualitative score, A vs C
    ax1.plot(x, aq, "-o", color="#1f77b4", label="A  (sees calibration < N, designed candidate)")
    ax1.plot(x, cq, "-s", color="#ff7f0e", label="C  (empty calibration, fixed candidate)")
    ax1.set_ylabel("qualitative score  (fail+trace+side, /60)")
    ax1.set_title("A vs C qualitative prediction quality across iterations")
    ax1.legend(loc="upper right", fontsize=9)
    ax1.grid(True, alpha=0.3)

    # --- panel 2: A - C gap, with trend line
    ax2.axhline(0, color="grey", lw=1)
    ax2.bar([xi - 0.18 for xi in x], ac_q, width=0.36, color="#1f77b4", alpha=0.6,
            label="A − C  qualitative gap")
    ax2.bar([xi + 0.18 for xi in x], ac_c, width=0.36, color="#2ca02c", alpha=0.5,
            label="A − C  composite gap")
    a, b = _linfit(x, ac_q)
    ax2.plot(x, [a + b * xi for xi in x], "--", color="#d62728", lw=2,
             label=f"qual-gap trend (slope {b:+.2f}/iter)")
    half = len(x) // 2
    ax2.hlines(st.mean(ac_q[:half]), -0.5, half - 0.5, color="#1f77b4", lw=2, linestyle=":")
    ax2.hlines(st.mean(ac_q[half:]), half - 0.5, len(x) - 0.5, color="#1f77b4", lw=2, linestyle=":")
    ax2.set_ylabel("A − C  (A's advantage)")
    ax2.set_title("A's advantage over zero-WMC shrinks as calibration grows "
                  f"(first-half {st.mean(ac_q[:half]):+.1f} → second-half {st.mean(ac_q[half:]):+.1f})")
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, alpha=0.3)

    ax2.set_xticks(x)
    ax2.set_xticklabels([str(i) for i in iters], fontsize=8)
    ax2.set_xlabel("iteration  (calibration grows left → right; C is always empty)")

    fig.tight_layout()
    out = OUT / "trend_A_vs_C.png"
    fig.savefig(out, dpi=130)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
