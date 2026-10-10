from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import spikeinterface as si
from scipy.io import savemat
from spikeinterface.core import NumpyRecording, NumpySorting

from src.preprocess.channel_layout import load_channel_layout
from src.preprocess.recording import (
    _LocalMedianReference3D,
    _local_reference_channels_without_neighbors,
    analysis_channel_locations,
    attach_probe_from_chanmap,
)
from src.postprocess.pipeline import (
    _AnalyzerWithProjectedUnitLocations,
    _compute_final_features,
    _compute_merge_groups,
    _physical_3d_sparsity,
    _physical_3d_unit_locations,
    _phy_display_positions,
)


def _write_3d_map(path: Path, zcoords: list[float]) -> None:
    savemat(path, {
        "chanMap0ind": [0, 1, 2],
        "chanMap": [1, 2, 3],
        "xcoords": [0, 0, 20],
        "ycoords": [0, 0, 20],
        "zcoords": zcoords,
        "kcoords": [1, 1, 1],
    })


def test_3d_map_keeps_physical_contact_locations(tmp_path: Path) -> None:
    path = tmp_path / "chanMap3d.mat"
    _write_3d_map(path, [0, 10, 0])
    recording = NumpyRecording(np.zeros((20, 3), dtype=np.int16), 20000.0)

    attached = attach_probe_from_chanmap(recording, path)

    assert attached.get_probe().ndim == 3
    np.testing.assert_array_equal(attached.get_channel_locations(axes="xyz"), [[0, 0, 0], [0, 0, 10], [20, 20, 0]])
    np.testing.assert_array_equal(attached.get_property("zcoords"), [0, 10, 0])


def test_physical_3d_distance_controls_local_reference(tmp_path: Path) -> None:
    path = tmp_path / "chanMap3d.mat"
    savemat(path, {
        "chanMap0ind": [0, 1, 2], "chanMap": [1, 2, 3],
        "xcoords": [0, 50, 100], "ycoords": [0, 0, 0],
        "zcoords": [0, 50, 0], "kcoords": [1, 1, 1],
    })
    traces = np.tile(np.array([[10, 2, 0]], dtype=np.float32), (20, 1))
    attached = attach_probe_from_chanmap(NumpyRecording(traces, 20000.0), path)
    locations = analysis_channel_locations(attached)
    assert _local_reference_channels_without_neighbors(
        channel_ids=[0, 1, 2], locations=locations, local_radius_um=(0, 80)
    ) == []
    referenced = _LocalMedianReference3D(attached, (0, 80)).get_traces()
    np.testing.assert_array_equal(referenced[:, 0], np.full(20, 9, dtype=np.float32))


def test_3d_contacts_do_not_collapse_to_same_analysis_position(tmp_path: Path) -> None:
    path = tmp_path / "chanMap3d.mat"
    savemat(path, {
        "chanMap0ind": [0, 1], "chanMap": [1, 2],
        "xcoords": [0, 100], "ycoords": [0, 0],
        "zcoords": [100, 0], "kcoords": [1, 1],
    })
    attached = attach_probe_from_chanmap(NumpyRecording(np.zeros((20, 2), dtype=np.int16), 20000.0), path)
    locations = analysis_channel_locations(attached)
    assert np.linalg.norm(locations[0] - locations[1]) == pytest.approx(141.421356)
    assert _local_reference_channels_without_neighbors(
        channel_ids=[0, 1], locations=locations, local_radius_um=(0, 80)
    ) == [0, 1]
    np.testing.assert_array_equal(_phy_display_positions(attached, [0, 1]), [[100, 0], [100, 0]])


@pytest.mark.parametrize("xcoords", ([0, 50, 100], [0, 0, 100]))
def test_radius_sparsity_uses_physical_3d_distance(tmp_path: Path, xcoords: list[int]) -> None:
    path = tmp_path / "chanMap3d.mat"
    savemat(path, {
        "chanMap0ind": [0, 1, 2], "chanMap": [1, 2, 3],
        "xcoords": xcoords, "ycoords": [0, 0, 0],
        "zcoords": [0, 50, 0], "kcoords": [1, 1, 1],
    })
    traces = np.random.default_rng(0).normal(0, 1, (4000, 3)).astype(np.float32)
    spikes = np.array([400, 900, 1400, 1900, 2400, 2900, 3400])
    traces[spikes, 0] -= 20
    attached = attach_probe_from_chanmap(NumpyRecording(traces, 20000.0), path)
    sorting = NumpySorting.from_unit_dict({1: spikes}, 20000.0)
    config = SimpleNamespace(
        analyzer_sparse=True, sparsity_method="radius", sparsity_radius_um=80,
        job_kwargs={"n_jobs": 1, "progress_bar": False},
    )
    sparsity = _physical_3d_sparsity(config, sorting, attached)
    np.testing.assert_array_equal(sparsity.mask, [[True, True, False]])


def test_best_channels_sparsity_with_shared_xy_contacts(tmp_path: Path) -> None:
    path = tmp_path / "chanMap3d.mat"
    savemat(path, {
        "chanMap0ind": [0, 1, 2], "chanMap": [1, 2, 3],
        "xcoords": [0, 0, 100], "ycoords": [0, 0, 0],
        "zcoords": [0, 25, 0], "kcoords": [1, 1, 1],
    })
    traces = np.random.default_rng(2).normal(0, 0.1, (4000, 3)).astype(np.float32)
    spikes = np.array([400, 900, 1400, 1900, 2400, 2900, 3400])
    traces[spikes, 0] -= 20
    traces[spikes, 1] -= 12
    traces[spikes, 2] += 30  # The default peak_sign="neg" excludes this larger positive peak.
    recording = attach_probe_from_chanmap(NumpyRecording(traces, 20000.0), path)
    sorting = NumpySorting.from_unit_dict({1: spikes}, 20000.0)
    config = SimpleNamespace(
        analyzer_sparse=True, sparsity_method="best_channels", sparsity_num_channels=2,
        job_kwargs={"n_jobs": 1, "progress_bar": False},
    )

    sparsity = _physical_3d_sparsity(config, sorting, recording)
    np.testing.assert_array_equal(sparsity.mask, [[True, True, False]])
    analyzer = si.create_sorting_analyzer(sorting, recording, format="memory", sparsity=sparsity)
    np.testing.assert_array_equal(analyzer.sparsity.mask, [[True, True, False]])
    np.testing.assert_array_equal(recording.get_channel_locations(axes="xyz"), [[0, 0, 0], [0, 0, 25], [100, 0, 0]])


def test_merge_candidates_use_3d_distance_with_shared_xy_contacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.postprocess.pipeline as post_pipeline

    path = tmp_path / "chanMap3d.mat"
    _write_3d_map(path, [0, 250, 50])
    traces = np.random.default_rng(3).normal(0, 0.01, (4000, 3)).astype(np.float32)
    spikes = [np.array([400, 900, 1400]), np.array([500, 1000, 1500]), np.array([600, 1100, 1600])]
    for channel, times in enumerate(spikes):
        traces[times, channel] -= 20
    recording = attach_probe_from_chanmap(NumpyRecording(traces, 20000.0), path)
    sorting = NumpySorting.from_unit_dict({1: spikes[0], 2: spikes[1], 3: spikes[2]}, 20000.0)
    analyzer = si.create_sorting_analyzer(sorting, recording, format="memory", sparse=False)
    analyzer.compute("random_spikes", method="all")
    analyzer.compute("waveforms", n_jobs=1)
    analyzer.compute("templates")

    locations = _physical_3d_unit_locations(analyzer, recording)
    projected = _AnalyzerWithProjectedUnitLocations(analyzer, locations)
    xy_pairs = post_pipeline.scur.compute_merge_unit_groups(
        projected, steps=["unit_locations"], resolve_graph=False, force_copy=False,
    )
    assert {tuple(pair) for pair in xy_pairs} == {(1, 2), (1, 3), (2, 3)}
    post_pipeline.scur.compute_merge_unit_groups(
        projected, preset="similarity_correlograms", resolve_graph=False,
        steps_params={"num_spikes": {"min_spikes": 1}}, force_copy=False,
        n_jobs=1, progress_bar=False,
    )

    def all_candidate_pairs(analyzer_arg, **kwargs):
        assert isinstance(analyzer_arg, _AnalyzerWithProjectedUnitLocations)
        assert kwargs["resolve_graph"] is False
        return [(1, 2), (1, 3), (2, 3)]

    monkeypatch.setattr(post_pipeline.scur, "compute_merge_unit_groups", all_candidate_pairs)
    config = SimpleNamespace(
        merge_min_spikes=1, merge_corr_diff_thresh=0.25,
        merge_template_diff_thresh=0.25, job_kwargs={},
    )
    assert _compute_merge_groups(config, analyzer, recording) == [[1, 3]]


def test_final_3d_features_avoid_unsupported_localization() -> None:
    computed = []
    analyzer = SimpleNamespace(compute=lambda features, **kwargs: computed.append(features))

    _compute_final_features(
        analyzer, n_components=3, pc_mode="by_channel_global",
        job_kwargs={}, include_locations=False,
    )

    assert "spike_locations" not in computed[0]
    assert "unit_locations" not in computed[0]
    assert {"templates", "spike_amplitudes", "principal_components"} <= computed[0].keys()


def test_zero_depth_keeps_existing_2d_layout(tmp_path: Path) -> None:
    path = tmp_path / "chanMap2d.mat"
    savemat(path, {
        "chanMap0ind": [0, 1, 2], "chanMap": [1, 2, 3],
        "xcoords": [0, 10, 20], "ycoords": [0, 0, 20],
        "zcoords": [0, 0, 0], "kcoords": [1, 1, 1],
    })
    attached = attach_probe_from_chanmap(
        NumpyRecording(np.zeros((20, 3), dtype=np.int16), 20000.0), path
    )
    assert attached.get_probe().ndim == 2
    np.testing.assert_array_equal(analysis_channel_locations(attached), [[0, 0], [10, 0], [20, 20]])


def test_phy_export_projects_3d_only_in_display_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.postprocess.pipeline as post_pipeline

    path = tmp_path / "chanMap3d.mat"
    _write_3d_map(path, [0, 10, 0])
    traces = np.random.default_rng(1).normal(0, 1, (1000, 3)).astype(np.float32)
    dat_path = tmp_path / "recording.dat"
    traces.tofile(dat_path)
    recording = attach_probe_from_chanmap(NumpyRecording(traces, 20000.0), path)
    sorting = NumpySorting.from_unit_dict({1: np.array([200, 400, 600])}, 20000.0)
    analyzer = si.create_sorting_analyzer(sorting, recording, format="memory", sparse=False)
    analyzer.compute("random_spikes", method="all")
    analyzer.compute("waveforms", n_jobs=1)
    analyzer.compute("templates")

    exporter = post_pipeline.export_to_phy
    monkeypatch.setattr(post_pipeline, "export_to_phy", lambda **kwargs: exporter(
        **dict(kwargs, compute_pc_features=False, compute_amplitudes=False)
    ))
    monkeypatch.setattr(post_pipeline, "write_centered_native_templates", lambda *args: None)
    output_folder = tmp_path / "phy"
    output_folder.mkdir()
    post_pipeline._export_phy_to_output_folder(
        sorting_analyzer=analyzer, output_folder=output_folder, analyzer_cache_root=None,
        dat_path=dat_path, hp_filtered=False, raw_num_channels=3, copy_binary=False,
        use_relative_path=False, job_kwargs={"n_jobs": 1}, binary_dtype="float32",
    )
    np.testing.assert_array_equal(np.load(output_folder / "channel_positions.npy"), [[0, 0], [10, 0], [20, 20]])
    np.testing.assert_array_equal(recording.get_channel_locations(axes="xyz"), [[0, 0, 0], [0, 0, 10], [20, 20, 0]])


def test_3d_map_rejects_missing_depth_entries(tmp_path: Path) -> None:
    path = tmp_path / "chanMap3d.mat"
    _write_3d_map(path, [0, 10])

    with pytest.raises(ValueError, match="zcoords length"):
        load_channel_layout(path, 3)
