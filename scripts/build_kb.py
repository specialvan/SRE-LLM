"""One-shot builder for the knowledge-base assets.

Run :
    python -m scripts.build_kb
"""

from __future__ import annotations

from scripts import build_mechanism_diagrams, build_benefit_gifs


def main() -> None:
    print("[1/2] building mechanism diagrams ...")
    build_mechanism_diagrams.main()
    print("[2/2] building benefit GIFs ...")
    build_benefit_gifs.main()
    print("done. open docs/knowledge-base.html in a browser.")


if __name__ == "__main__":
    main()
