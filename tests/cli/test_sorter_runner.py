from __future__ import annotations

from pathlib import Path

import src.preprocess.sorter_runner as sr
import pytest

from src.preprocess.channel_layout import NoActiveChannels


def test_kilosort1_defaults_match_vendored_directory_case():
    root = Path(__file__).resolve().parents[2]
    expected = root / "sorter" / "KiloSort1"
    # Check the spelling explicitly: exists() alone accepts incorrect case
    # on Windows and would miss the Linux default-path failure.
    assert sr._default_kilosort1_path().as_posix() == expected.as_posix()
    args = sr.build_parser().parse_args([
        "--dat-path", "input.dat", "--output-folder", "out",
    ])
    assert args.kilosort1_path == "sorter/KiloSort1"
    assert expected.is_dir()


def test_run_sorter_cli_passes_active_and_excluded_channels(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_execute_sorting_job(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["output_folder"])

    monkeypatch.setattr(sr, "execute_sorting_job", _fake_execute_sorting_job)

    parser = sr.build_parser()
    args = parser.parse_args(
        [
            "--sorter",
            "kilosort4",
            "--dat-path",
            str(tmp_path / "input.dat"),
            "--xml-path",
            str(tmp_path / "input.xml"),
            "--output-folder",
            str(tmp_path / "out"),
            "--active-channels",
            "0, 2,3",
            "--exclude-channels",
            "7; 8",
        ]
    )
    sr.run_sorter_cli(args)

    assert captured["active_channels_0based"] == [0, 2, 3]
    assert captured["exclude_channels_0based"] == [7, 8]


def test_run_sorter_cli_defaults_channel_lists_to_none(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_execute_sorting_job(**kwargs):
        captured.update(kwargs)
        return Path(kwargs["output_folder"])

    monkeypatch.setattr(sr, "execute_sorting_job", _fake_execute_sorting_job)

    parser = sr.build_parser()
    args = parser.parse_args(
        [
            "--sorter",
            "kilosort4",
            "--dat-path",
            str(tmp_path / "input.dat"),
            "--xml-path",
            str(tmp_path / "input.xml"),
            "--output-folder",
            str(tmp_path / "out"),
        ]
    )
    sr.run_sorter_cli(args)

    assert captured["active_channels_0based"] is None
    assert captured["exclude_channels_0based"] is None


def test_sorter_cli_reports_all_excluded_channels_as_success(tmp_path, monkeypatch, capsys):
    def no_active_channels(**kwargs):
        raise NoActiveChannels("All recording channels are excluded")

    monkeypatch.setattr(sr, "execute_sorting_job", no_active_channels)
    args = sr.build_parser().parse_args([
        "--dat-path", str(tmp_path / "input.dat"),
        "--xml-path", str(tmp_path / "input.xml"),
        "--output-folder", str(tmp_path / "out"),
    ])
    sr.run_sorter_cli(args)
    assert "reason=no_active_channels" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_sorter_cli_requires_xml_before_sorter_execution(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(sr, "execute_sorting_job", lambda **kwargs: called.append(kwargs))
    args = sr.build_parser().parse_args([
        "--dat-path", str(tmp_path / "input.dat"),
        "--output-folder", str(tmp_path / "out"),
    ])
    with pytest.raises(ValueError, match="--xml-path is required"):
        sr.run_sorter_cli(args)
    assert called == []
