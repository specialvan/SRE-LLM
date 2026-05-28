import types
from pathlib import Path

import pytest

from analysis import run_all


def test_run_all_records_import_failures_and_continues(tmp_path, monkeypatch):
    calls: list[str] = []

    def import_module(name: str):
        if name == "analysis.missing_study":
            raise ImportError("synthetic missing dependency")

        def main():
            calls.append(name)
            return {"banner": f"{name} ok"}

        return types.SimpleNamespace(main=main)

    monkeypatch.setattr(run_all.importlib, "import_module", import_module)

    with pytest.raises(SystemExit) as exc:
        run_all.main(
            studies=["analysis.ok_before", "analysis.missing_study", "analysis.ok_after"],
            artifacts_dir=tmp_path,
        )

    assert exc.value.code == 1
    assert calls == ["analysis.ok_before", "analysis.ok_after"]
    summary = (tmp_path / "SUMMARY.txt").read_text(encoding="utf-8")
    assert "analysis.ok_before ok" in summary
    assert "FAILED analysis.missing_study: ImportError: synthetic missing dependency" in summary
    assert "analysis.ok_after ok" in summary


def test_run_all_forwards_artifacts_dir_to_studies_that_accept_it(tmp_path, monkeypatch):
    calls: list[Path] = []

    def import_module(name: str):
        def main(*, artifacts_dir=None):
            artifacts = Path(artifacts_dir)
            calls.append(artifacts)
            (artifacts / "study-output.jsonl").write_text("{}\n", encoding="utf-8")
            return {"banner": f"{name} ok"}

        return types.SimpleNamespace(main=main)

    monkeypatch.setattr(run_all.importlib, "import_module", import_module)

    run_all.main(studies=["analysis.accepts_artifacts"], artifacts_dir=tmp_path)

    assert calls == [tmp_path]
    assert (tmp_path / "study-output.jsonl").exists()
    assert "analysis.accepts_artifacts ok" in (tmp_path / "SUMMARY.txt").read_text(
        encoding="utf-8"
    )


def test_run_all_does_not_pass_artifacts_dir_to_legacy_studies(tmp_path, monkeypatch):
    calls: list[str] = []

    def import_module(name: str):
        def main():
            calls.append(name)
            return {"banner": f"{name} ok"}

        return types.SimpleNamespace(main=main)

    monkeypatch.setattr(run_all.importlib, "import_module", import_module)

    run_all.main(studies=["analysis.legacy"], artifacts_dir=tmp_path)

    assert calls == ["analysis.legacy"]
    assert "analysis.legacy ok" in (tmp_path / "SUMMARY.txt").read_text(
        encoding="utf-8"
    )
