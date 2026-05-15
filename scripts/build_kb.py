"""One-shot builder for the knowledge-base assets.

Run :
    python -m scripts.build_kb
"""

from __future__ import annotations

from scripts import build_benefit_gifs, build_mechanism_diagrams, quality_gate_counts


def main() -> None:
    print("[1/3] updating quality gate counts ...")
    quality_gate_counts.update_quality_gate_docs()
    print("[2/3] building mechanism diagrams ...")
    build_mechanism_diagrams.main()
    print("[3/3] building benefit GIFs ...")
    build_benefit_gifs.main()
    print("done. open docs/knowledge-base.html in a browser.")


if __name__ == "__main__":
    main()
