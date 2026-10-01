from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
from scipy.io import loadmat
import pytest

import src.postprocess as postprocess
from src.phy_metadata import read_phy_params, resolve_phy_dat_path
from src.preprocess.gui.config_model import PipelineGuiSettings
from src.preprocess.gui.run_pipeline import ERROR_PREFIX, main
from src.preprocess.sorter_runner import build_sorter_partitions, write_sorter_partition_manifest


def _session_config(tmp_path: Path) -> tuple[PipelineGuiSettings, Path, np.ndarray]:
    raw = tmp_path / "raw" / "session"
    epoch = raw / "epoch"
    epoch.mkdir(parents=True)
    traces = np.random.default_rng(0).integers(1, 1000, (2048, 8), dtype=np.int16)
    traces += np.arange(8, dtype=np.int16) * 1000
    traces.tofile(epoch / "amplifier.dat")
    (np.arange(len(traces), dtype=np.int32)).tofile(epoch / "time.dat")
    xml = raw / "session.xml"
    xml.write_text(
        """<session>
<acquisitionSystem><nChannels>8</nChannels><sampleRate>20000</sampleRate></acquisitionSystem>
<anatomicalDescription><channelGroups>
<group><channels><channel>0</channel><channel skip="1">1</channel><channel>2</channel><channel>3</channel></channels></group>
<group><channels><channel>4</channel><channel>5</channel><channel>6</channel><channel>7</channel></channels></group>
</channelGroups></anatomicalDescription>
<spikeDetection><channelGroups>
<group><channels><channel>0</channel><channel>1</channel><channel>2</channel><channel>3</channel></channels></group>
<group><channels><channel>4</channel><channel>5</channel><channel>6</channel></channels></group>
</channelGroups></spikeDetection>
</session>""",
        encoding="utf-8",
    )
    settings = PipelineGuiSettings(
        basepath=str(raw), local_root=str(tmp_path / "local"), xml_path=str(xml)
    )
    settings.preprocess.reject_channels = [4]
    settings.preprocess.run_sorter = False
    settings.preprocess.do_preprocess = False
    settings.preprocess.make_lfp = False
    settings.preprocess.state_score = False
    settings.preprocess.preprocess_worker_count = 1
    settings.preprocess.overwrite = True
    config_path = tmp_path / "config.json"
    settings.save(config_path)
    return settings, config_path, traces


@pytest.mark.integration
def test_pipeline_cli_preserves_channel_identity_through_phy_and_cell_explorer(tmp_path, monkeypatch):
    import spikeinterface as si
    import src.postprocess.pipeline as post_pipeline

    settings, config_path, traces = _session_config(tmp_path)
    output = settings.local_output_dir
    observed_channels = []
    export_to_phy = post_pipeline.export_to_phy

    def export_channel_metadata(**kwargs):
        # PCA/amplitude features and display-template estimation are separate
        # scientific computations, unnecessary for this binary/ID contract.
        kwargs["compute_pc_features"] = False
        kwargs["compute_amplitudes"] = False
        return export_to_phy(**kwargs)

    monkeypatch.setattr(post_pipeline, "export_to_phy", export_channel_metadata)
    monkeypatch.setattr(post_pipeline, "write_centered_native_templates", lambda *args: None)

    def inspect_and_export(config):
        # Bypass scientific curation and GPU sorting, but use the actual binary
        # reader, channel resolver, analyzer and Phy exporter.
        recording = post_pipeline._resolve_recording_for_postprocess(config)
        observed_channels.append(recording.get_channel_ids().tolist())
        if len(observed_channels) == 1:
            assert config.reject_channels == [1, 4, 7]
            assert config.num_channels == 8
            sorting = si.NumpySorting.from_unit_dict(
                {0: np.array([200, 400, 600, 800, 1200, 1600])}, sampling_frequency=20000
            )
            analyzer = si.create_sorting_analyzer(
                sorting, recording, format="memory", sparse=False
            )
            analyzer.compute("random_spikes", method="all")
            analyzer.compute("waveforms", ms_before=1.0, ms_after=2.0, n_jobs=1)
            analyzer.compute("templates")
            for copy_binary in (False, True):
                phy = output / ("phy_copy" if copy_binary else "phy_raw")
                phy.mkdir()
                post_pipeline._export_phy_to_output_folder(
                    sorting_analyzer=analyzer, output_folder=phy, analyzer_cache_root=None,
                    dat_path=config.dat_path, hp_filtered=False, raw_num_channels=8,
                    copy_binary=copy_binary, use_relative_path=True,
                    job_kwargs={"n_jobs": 1, "progress_bar": False}, binary_dtype="int16",
                )
        return [SimpleNamespace(analyzer_cache_dir=None)]

    monkeypatch.setitem(postprocess.__dict__, "run_postprocess_session", inspect_and_export)
    assert main(["--config", str(config_path), "--mode", "all"]) == 0
    assert observed_channels == [[0, 2, 3, 5, 6]]

    expected = traces.copy()
    expected[:, [1, 4, 7]] = 0
    dat = output / "session.dat"
    np.testing.assert_array_equal(np.fromfile(dat, dtype="int16").reshape(-1, 8), expected)
    chanmap = loadmat(output / "chanMap.mat")
    np.testing.assert_array_equal(chanmap["chanMap0ind"].reshape(-1), np.arange(8))
    np.testing.assert_array_equal(chanmap["chanMap"].reshape(-1), np.arange(1, 9))
    np.testing.assert_array_equal(np.flatnonzero(~chanmap["connected"].reshape(-1).astype(bool)), [1, 4, 7])

    # CellExplorer reads full-width session metadata and 1-based channels.
    session = loadmat(output / "session.session.mat", simplify_cells=True)["session"]
    assert session["extracellular"]["nChannels"] == 8
    np.testing.assert_array_equal(session["channelTags"]["Bad"]["channels"], [2, 5, 8])
    groups = session["extracellular"]["electrodeGroups"]["channels"]
    np.testing.assert_array_equal(groups[0], [1, 2, 3, 4])
    np.testing.assert_array_equal(groups[1], [5, 6, 7, 8])
    spike_groups = session["extracellular"]["spikeGroups"]["channels"]
    np.testing.assert_array_equal(spike_groups[0], [1, 2, 3, 4])
    np.testing.assert_array_equal(spike_groups[1], [5, 6, 7])
    coords = loadmat(output / "session.chanCoords.channelInfo.mat", simplify_cells=True)["chanCoords"]
    np.testing.assert_array_equal(coords["x"], chanmap["xcoords"].reshape(-1))
    np.testing.assert_array_equal(coords["y"], chanmap["ycoords"].reshape(-1))

    good = np.array([0, 2, 3, 5, 6])
    for copy_binary in (False, True):
        phy = output / ("phy_copy" if copy_binary else "phy_raw")
        params = read_phy_params(phy)
        np.testing.assert_array_equal(np.load(phy / "channel_map_si.npy"), good)
        np.testing.assert_array_equal(np.load(phy / "channel_map.npy"), np.arange(5) if copy_binary else good)
        np.testing.assert_array_equal(
            np.load(phy / "channel_positions.npy"), np.column_stack((coords["x"][good], coords["y"][good]))
        )
        assert params["n_channels_dat"] == (5 if copy_binary else 8)
        phy_dat = resolve_phy_dat_path(phy)
        assert phy_dat == ((phy / "recording.dat").resolve() if copy_binary else dat.resolve())
        binary = np.fromfile(phy_dat, dtype=params["dtype"]).reshape(-1, params["n_channels_dat"])
        np.testing.assert_array_equal(binary[:, np.load(phy / "channel_map.npy")], expected[:, good])

    # Resume through the postprocess CLI: keep original IDs within probe 2,
    # rather than interpreting its compact selection as new binary columns.
    partitions = build_sorter_partitions(
        mode="probe", chanmap_mat_path=output / "chanMap.mat", num_channels=8,
        excluded_channels_0based=[1, 4, 7],
    )
    selected = output / "Kilosort4_probe2"
    selected.mkdir()
    partitions[1] = replace(partitions[1], output_folder=str(selected))
    write_sorter_partition_manifest(output_dir=output, mode="probe", sorter="kilosort4", partitions=partitions)
    settings.postprocess.sorting_phy_folder = str(selected)
    settings.postprocess.dat_path = str(dat)
    settings.save(config_path)
    assert main(["--config", str(config_path), "--mode", "postprocess"]) == 0
    assert observed_channels[-1] == [5, 6]
    np.testing.assert_array_equal(np.fromfile(settings.basepath_path / "epoch/amplifier.dat", dtype="int16").reshape(-1, 8), traces)


def test_pipeline_cli_rejects_out_of_range_bad_channel_without_postprocessing(tmp_path, monkeypatch, capsys):
    settings, config_path, traces = _session_config(tmp_path)
    settings.preprocess.reject_channels = [8]
    settings.save(config_path)
    called = []
    monkeypatch.setitem(postprocess.__dict__, "run_postprocess_session", lambda config: called.append(config))
    assert main(["--config", str(config_path), "--mode", "all"]) == 1
    error_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith(ERROR_PREFIX))
    error = json.loads(error_line[len(ERROR_PREFIX):])
    assert error["type"] == "ValueError"
    assert "Bad/reject channels absent from the input recording: [8]" in error["message"]
    assert called == []
    assert not (settings.local_output_dir / "session.dat").exists()
    np.testing.assert_array_equal(np.fromfile(settings.basepath_path / "epoch/amplifier.dat", dtype="int16").reshape(-1, 8), traces)


def test_pipeline_cli_module_rejects_invalid_mode_before_creating_output(tmp_path):
    config = tmp_path / "missing.json"
    result = subprocess.run(
        [sys.executable, "-m", "src.preprocess.gui.run_pipeline", "--config", str(config), "--mode", "invalid"],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert list(tmp_path.iterdir()) == []
