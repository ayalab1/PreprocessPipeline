import warnings
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat, savemat
from spikeinterface.core import NumpyRecording

from src.preprocess import sorter_runner as sr
from src.phy_metadata import write_phy_shank_metadata


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


@pytest.mark.parametrize("sorter", ["kilosort", "kilosort2_5", "kilosort4"])
def test_native_phy_shanks_follow_remapped_channel_order(tmp_path, monkeypatch, sorter):
    """Run the export hook after compact sorter IDs become original binary IDs."""
    chanmap = tmp_path / "chanMap.mat"
    savemat(chanmap, {
        "chanMap0ind": [6, 2, 7, 0, 4, 1, 5, 3],
        "kcoords": [2, 2, 2, 1, 1, 1, 1, 2],
        "probe_ids": [2, 1, 2, 1, 2, 1, 2, 1],
        "xcoords": [400, 200, 400, 0, 300, 0, 300, 200],
        "ycoords": np.arange(8) * 20,
    })
    config = tmp_path / "sorter.yaml"
    config.write_text("auto_geom_from_probe: false\n" if sorter == "kilosort4" else "{}\n")
    dat = tmp_path / "input.dat"
    dat.write_bytes(bytes(8 * 2 * 10))
    out = tmp_path / "out"

    def run_sorter(**kwargs):
        folder = kwargs["folder"] / "sorter_output"
        folder.mkdir(parents=True)
        # The map orders the selected recording as [6, 2, 0, 4]. Its export can
        # reorder/select channels independently of chanMap row order.
        assert kwargs["recording"].get_channel_ids().tolist() == [6, 2, 0, 4]
        np.save(folder / "channel_map.npy", [3, 0, 2, 1])
        np.save(folder / "channel_positions.npy", [[300, 0], [400, 0], [0, 0], [200, 0]])
        (folder / "params.py").write_text("pipeline_phy_export_basis = 'input_binary_v1'\n")
        if sorter == "kilosort4":
            np.save(folder / "channel_shanks.npy", [99, 99, 99, 99])

    monkeypatch.setattr(sr.ss, "run_sorter", run_sorter)
    monkeypatch.setattr(sr, "_resolve_matlab_cmd", lambda _: sys.executable)
    monkeypatch.setattr(sr, "_cleanup_sorter_runtime_processes", lambda *a, **k: None)
    sr.execute_sorting_job(
        sorter=sorter, dat_path=dat, xml_path=None, config_path=config,
        output_folder=out, chanmap_mat_path=chanmap,
        sampling_frequency=20000.0, num_channels=8,
        active_channels_0based=[0, 2, 4, 6], preprocess_for_sorting=False,
    )
    np.testing.assert_array_equal(np.load(out / "channel_map.npy"), [4, 6, 0, 2])
    np.testing.assert_array_equal(np.load(out / "channel_shanks.npy"), [2, 3, 0, 1])
    np.testing.assert_array_equal(np.load(out / "channel_probe.npy"), [1, 1, 0, 0])
    np.testing.assert_array_equal(np.load(out / "channel_positions.npy"), [[300, 0], [400, 0], [0, 0], [200, 0]])
    assert dat.read_bytes() == bytes(8 * 2 * 10)


@pytest.mark.parametrize("metadata", [None, {"chanMap0ind": [0, 1]}])
def test_native_phy_missing_shanks_preserves_existing_metadata(tmp_path, metadata):
    folder = tmp_path / "sorter_output"
    folder.mkdir()
    np.save(folder / "channel_map.npy", [1, 0])
    np.save(folder / "channel_shanks.npy", [7, 8])
    chanmap = None
    if metadata is not None:
        chanmap = tmp_path / "chanMap.mat"
        savemat(chanmap, metadata)
    sr._write_phy_shanks_from_chanmap(tmp_path, chanmap, 2)
    np.testing.assert_array_equal(np.load(folder / "channel_shanks.npy"), [7, 8])
    assert not (folder / "channel_probe.npy").exists()


@pytest.mark.parametrize("shanks, exported", [([1, np.nan], [0, 1]), ([1, 1], [0, 2])])
def test_invalid_shank_metadata_does_not_overwrite_existing_files(tmp_path, shanks, exported):
    np.save(tmp_path / "channel_shanks.npy", [7, 8])
    np.save(tmp_path / "channel_probe.npy", [0, 0])
    with pytest.raises(ValueError):
        write_phy_shank_metadata(
            tmp_path, source_channel_ids=[0, 1], shank_ids=shanks,
            probe_ids=[1, 1], exported_channel_ids=exported,
        )
    np.testing.assert_array_equal(np.load(tmp_path / "channel_shanks.npy"), [7, 8])
    np.testing.assert_array_equal(np.load(tmp_path / "channel_probe.npy"), [0, 0])
