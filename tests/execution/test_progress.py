from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.execution import worker
from src.execution.models import AttemptSpec, BackendName, ResourceSpec, StageName
from src.preprocess.gui.config_model import PipelineGuiSettings


class ConfigCaptured(Exception):
    """Stop at the scientific stage boundary without launching a real job."""


@pytest.mark.parametrize("backend", [BackendName.LOCAL, BackendName.SLURM])
@pytest.mark.parametrize("stage", list(StageName))
@pytest.mark.parametrize("progress_enabled", [True, False])
def test_worker_preserves_stage_progress_setting(
    tmp_path: Path, monkeypatch, backend, stage, progress_enabled: bool
) -> None:
    settings = PipelineGuiSettings(basepath=str(tmp_path / "source"), local_root=str(tmp_path))
    preprocess_config = settings.to_preprocess_config()
    postprocess_config = settings.to_postprocess_config()
    for config in (preprocess_config, postprocess_config):
        assert config.job_kwargs["progress_bar"] is True
        if not progress_enabled:
            config.job_kwargs["progress_bar"] = False
    monkeypatch.setattr(settings, "to_preprocess_config", lambda: preprocess_config)
    monkeypatch.setattr(settings, "to_postprocess_config", lambda: postprocess_config)
    monkeypatch.setattr(worker, "_settings_for_run", lambda _store: settings)
    store = SimpleNamespace(
        load_run=lambda: {"enabled_stages": [item.value for item in StageName]},
        attempt_dir=lambda *_args: tmp_path / "attempt",
    )
    spec = AttemptSpec(
        run_id="run-progress", stage=stage, attempt=1, backend=backend,
        resources=ResourceSpec(2, 1024, 10, gpu_count=int(stage == StageName.SORTING)),
        analysis_sha256="test",
    )
    captured: dict = {}

    def capture_config(config, *_args, **_kwargs):
        captured.update(config.job_kwargs)
        raise ConfigCaptured

    if stage == StageName.PREPROCESS:
        monkeypatch.setattr(
            "src.execution.session.prepare_preprocess_output_contract",
            lambda *_args, **_kwargs: tmp_path / "contract.json",
        )
        monkeypatch.setattr(
            "src.preprocess.runtime_prep.prepare_preprocess_settings", lambda _settings: {}
        )
        monkeypatch.setattr("src.preprocess.run_preprocess_session", capture_config)
    elif stage == StageName.SORTING:
        monkeypatch.setattr(
            worker, "_load_upstream_result",
            lambda *_args: {"outputs": {"preprocess_result": {}}},
        )
        monkeypatch.setattr(
            worker, "_preprocess_result_from_dict",
            lambda _data: SimpleNamespace(
                n_channels=2, local_output_dir=tmp_path, bad_channels_0based=[],
            ),
        )
        monkeypatch.setattr(
            "src.execution.gpu_selection.activate_least_used_gpu",
            lambda **_kwargs: {"selected_gpu": {"uuid": "mock-gpu"}},
        )
        monkeypatch.setattr(
            "src.execution.gpu_selection.GpuUsageMonitor",
            lambda **_kwargs: SimpleNamespace(start=lambda: None, stop=lambda **_kw: None),
        )
        monkeypatch.setattr("src.preprocess.sorting_stage.run_sorting_stage", capture_config)
    else:
        monkeypatch.setattr("src.postprocess.run_postprocess_session", capture_config)

    with pytest.raises(ConfigCaptured):
        worker.run_stage(store, spec)

    assert captured["progress_bar"] is progress_enabled
    assert captured["n_jobs"] == spec.resources.cpus
    if stage != StageName.POSTPROCESS:
        assert captured["max_threads_per_worker"] == 1
        assert captured["chunk_duration"] == "1s"
        assert captured["pool_engine"] == "process"


@pytest.mark.parametrize("n_jobs", [1, 2])
def test_binary_writer_reports_progress_to_redirected_stderr(
    tmp_path: Path, capfd, n_jobs: int
) -> None:
    from spikeinterface.core import NumpyRecording
    from src.preprocess.recording import write_concatenated_dat

    traces = np.arange(8000, dtype=np.int16).reshape(4000, 2)
    recording = NumpyRecording(traces, sampling_frequency=1000)
    settings = PipelineGuiSettings(basepath=str(tmp_path), local_root=str(tmp_path))
    job_kwargs = settings.to_preprocess_config().job_kwargs
    job_kwargs["n_jobs"] = n_jobs
    output = tmp_path / "recording.dat"

    write_concatenated_dat(recording, output, "int16", False, job_kwargs)

    log = capfd.readouterr()
    assert "write_binary_recording" in log.err
    assert "100%" in log.err
    np.testing.assert_array_equal(np.fromfile(output, dtype=np.int16).reshape(-1, 2), traces)
    assert not list(tmp_path.glob("*.partial-*"))
