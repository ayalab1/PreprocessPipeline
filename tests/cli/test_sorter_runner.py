from __future__ import annotations

import os
from pathlib import Path

import src.preprocess.sorter_runner as sr
import pytest

from src.preprocess.channel_layout import NoActiveChannels


@pytest.fixture
def runtime_temp_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("PREPROCESS_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(sr.tempfile, "gettempdir", lambda: str(tmp_path))
    sr._default_runtime_root.cache_clear()
    yield tmp_path
    sr._default_runtime_root.cache_clear()


@pytest.mark.parametrize("windows_shim", [False, True])
def test_matlab_runtime_avoids_inaccessible_shared_directory(
    runtime_temp_dir, monkeypatch, windows_shim,
):
    shared_dir = runtime_temp_dir / "preprocess_pipeline"
    shared_dir.mkdir()
    original_mkdir = Path.mkdir

    def deny_shared_directory(path, *args, **kwargs):
        if path == shared_dir or shared_dir in path.parents:
            raise PermissionError("Shared runtime directory belongs to another user")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny_shared_directory)
    monkeypatch.setattr(sr, "_is_windows", lambda: windows_shim)
    # Restore environment mutations made by shim injection after the test.
    for name in ("PATH", "Path", "MATLABPATH"):
        monkeypatch.setenv(name, os.environ.get(name, ""))

    output = runtime_temp_dir / "session" / "Kilosort"
    log = sr._matlab_log_path(output)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("MATLAB test output\n", encoding="utf-8")
    shim = sr._inject_matlab_shim("matlab", log, matlab_max_workers=2)

    root = sr._runtime_root()
    assert root != shared_dir
    assert root.parent == runtime_temp_dir
    assert root in log.parents and root in shim.parents
    assert shim.is_file()
    assert (shim.parent / "startup.m").is_file()
    assert (shim.parent / "jobs").is_dir()
    assert sr._matlab_log_path(output) == log
    assert sr._persist_matlab_log(log, output).read_text(encoding="utf-8") == "MATLAB test output\n"
    assert list(shared_dir.iterdir()) == []
    if os.name != "nt":
        assert root.stat().st_mode & 0o777 == 0o700


def test_matlab_runtime_isolated_between_worker_processes(runtime_temp_dir, monkeypatch):
    output = runtime_temp_dir / "session" / "Kilosort"
    monkeypatch.setattr(sr.os, "getpid", lambda: 101)
    first_log = sr._matlab_log_path(output)
    first_log.parent.mkdir(parents=True, exist_ok=True)
    first_log.write_text("first worker", encoding="utf-8")
    assert sr._matlab_log_path(output) == first_log

    monkeypatch.setattr(sr.os, "getpid", lambda: 202)
    second_log = sr._matlab_log_path(output)
    second_log.parent.mkdir(parents=True, exist_ok=True)
    second_log.write_text("second worker", encoding="utf-8")
    assert second_log != first_log
    assert first_log.read_text(encoding="utf-8") == "first worker"
    assert sr._matlab_log_path(output) == second_log


def test_matlab_runtime_respects_explicit_override(runtime_temp_dir, monkeypatch):
    override = runtime_temp_dir / "configured-runtime"
    monkeypatch.setenv("PREPROCESS_RUNTIME_DIR", str(override))
    assert sr._runtime_root() == override.resolve()
    log = sr._matlab_log_path(runtime_temp_dir / "Kilosort")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("configured runtime", encoding="utf-8")
    assert log.parent == override / "matlab_shim"
    assert set(runtime_temp_dir.iterdir()) == {override}


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
