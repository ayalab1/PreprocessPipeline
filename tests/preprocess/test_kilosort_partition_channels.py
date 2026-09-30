import warnings
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat
from spikeinterface.core import NumpyRecording

from src.preprocess import sorter_runner as sr


@pytest.mark.parametrize("num_channels, active_count", [(8, 8), (32, 32), (64, 64), (64, 8)])
def test_kilosort1_default_generates_ops_without_whitening_warning(
    tmp_path: Path, num_channels: int, active_count: int,
) -> None:
    recording = NumpyRecording(np.zeros((10, num_channels), dtype=np.int16), 20000.0)
    if active_count < num_channels:
        recording = sr.select_recording_channels(
            recording, list(range(0, num_channels, num_channels // active_count)),
        )
    params = sr.ss.KilosortSorter.default_params()
    params.update(
        sr._normalize_kilosort_params(
            sr._load_params(sr._default_sorter_config_path("kilosort")),
            num_channels=num_channels,
            chanmap_mat_path=None,
            active_channel_count=active_count,
        )
    )
    params = sr.ss.KilosortSorter._check_params(recording, tmp_path, params)

    # Exercise the real wrapper code that emitted issue #20's warning and
    # serialize its settings, without launching MATLAB or requiring a GPU.
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        sr.ss.KilosortSorter._generate_ops_file(recording, params, tmp_path, tmp_path / "input.dat")

    ops = loadmat(tmp_path / "ops.mat", simplify_cells=True)["ops"]
    assert ops["whiteningRange"] == 32
    assert ops["Nchan"] == active_count


@pytest.mark.parametrize("preprocessed", [False, True])
def test_partition_does_not_exclude_original_binary_channels_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preprocessed: bool,
) -> None:
    config = tmp_path / "sorter.yaml"
    config.write_text("n_jobs: 1\nauto_geom_from_probe: false\n")
    dat = tmp_path / "input.dat"
    dat.write_bytes(bytes(128 * 2 * 10))
    active = list(range(0, 128, 4))
    full_recording, selected_recording = object(), object()
    monkeypatch.setattr(sr, "_get_kilosort4_allowed_param_keys", lambda: {"n_jobs"})
    monkeypatch.setattr(sr.se, "read_binary", lambda *a, **k: full_recording)

    def select(recording, channels):
        assert recording is full_recording
        assert channels == active
        return selected_recording

    monkeypatch.setattr(sr, "select_recording_channels", select)
    called = []

    def run_sorter(**kwargs):
        assert kwargs["recording"] is selected_recording
        # SpikeInterface exports a compact chanMap for this recording. Original
        # binary exclusions must not be applied to that compact channel space.
        assert not kwargs.get("bad_channels")
        called.append(True)
        return object()

    monkeypatch.setattr(sr.ss, "run_sorter", run_sorter)
    sr.execute_sorting_job(
        sorter="kilosort4", dat_path=dat, xml_path=None,
        config_path=config, output_folder=tmp_path / "out",
        sampling_frequency=20000.0, num_channels=128,
        active_channels_0based=active, input_is_preprocessed=preprocessed,
        preprocess_for_sorting=False,
    )
    assert called == [True]
