"""Export a standalone, assembled proposer Skill from package resources."""

import argparse
from pathlib import Path
from worldcalib.optimize_cli import BENCHMARKS
from worldcalib.prompts import load_proposer_skill


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", choices=[f"{b}_{v}" for b in BENCHMARKS
                                        for v in ("calib", "nowmc")])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = load_proposer_skill(args.skill).rstrip() + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
