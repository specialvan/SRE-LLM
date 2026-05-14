"""Static documentation UI asset checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_knowledge_pages_reference_modern_assets():
    assert 'href="assets/knowledge-modern.css"' in _read("docs/knowledge_base.html")
    assert 'src="assets/knowledge-modern.js"' in _read("docs/knowledge_base.html")

    for page in (
        "docs/V2_Knowledge/knowledge-base.html",
        "docs/V3_Knowledge/knowledge-base.html",
    ):
        html = _read(page)
        assert 'href="../assets/knowledge-modern.css"' in html
        assert 'src="../assets/knowledge-modern.js"' in html


def test_modern_docs_assets_are_accessible_and_no_build():
    css = _read("docs/assets/knowledge-modern.css")
    js = _read("docs/assets/knowledge-modern.js")

    assert "prefers-reduced-motion" in css
    assert "IntersectionObserver" in js
    assert "querySelector" in js
    assert "React" not in js
    assert "Vue" not in js
    assert not (ROOT / "package.json").exists()
