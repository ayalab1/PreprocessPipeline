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
import src.preprocess as preprocess
from src.phy_metadata import read_phy_params, resolve_phy_dat_path
from src.preprocess.gui import run_pipeline as pipeline_cli
from src.preprocess.gui.config_model import PipelineGuiSettings
from src.preprocess.gui.run_pipeline import ERROR_PREFIX, RESULT_PREFIX, main
from src.preprocess.io import build_acquisition_catalog, discover_subsessions
from src.preprocess.sorter_runner import build_sorter_partitions, write_sorter_partition_manifest


@pytest.mark.parametrize("copy_binary", [False, True])
@pytest.mark.parametrize("with_geometry", [False, True])
def test_postprocess_phy_shanks_with_reordered_channels(tmp_path, monkeypatch, copy_binary, with_geometry):
    import spikeinterface as si
    from scipy.io import savemat
    from src.preprocess.recording import attach_probe_from_chanmap
    import src.postprocess.pipeline as post_pipeline

    traces = np.random.default_rng(0).integers(-100, 100, (1000, 8), dtype=np.int16)
    dat = tmp_path / "input.dat"
    traces.tofile(dat)
    recording = si.NumpyRecording(traces, sampling_frequency=20000)
    if with_geometry:
        chanmap = tmp_path / "chanMap.mat"
        savemat(chanmap, {
            "chanMap0ind": np.arange(8), "kcoords": [1, 1, 2, 2, 1, 1, 2, 2],
            "probe_ids": [1, 1, 1, 1, 2, 2, 2, 2],
            "xcoords": [0, 0, 200, 200, 400, 400, 600, 600],
            "ycoords": [0, 20, 0, 20, 0, 20, 0, 20],
        })
        recording = attach_probe_from_chanmap(recording, chanmap)
    else:
        recording.set_channel_locations(np.column_stack((np.arange(8) * 200, np.zeros(8))))
    selected = [4, 6, 0, 2]
    recording = recording.select_channels(selected)
    sorting = si.NumpySorting.from_unit_dict({0: np.array([200, 400, 600])}, sampling_frequency=20000)
    analyzer = si.create_sorting_analyzer(sorting, recording, format="memory", sparse=False)
    analyzer.compute("random_spikes", method="all")
    analyzer.compute("waveforms", n_jobs=1)
    analyzer.compute("templates")
    exporter = post_pipeline.export_to_phy

    def export(**kwargs):
        kwargs.update(compute_pc_features=False, compute_amplitudes=False)
        return exporter(**kwargs)

    monkeypatch.setattr(post_pipeline, "export_to_phy", export)
    monkeypatch.setattr(post_pipeline, "write_centered_native_templates", lambda *args: None)
    folder = tmp_path / "phy"
    folder.mkdir()
    post_pipeline._export_phy_to_output_folder(
        sorting_analyzer=analyzer, output_folder=folder, analyzer_cache_root=None,
        dat_path=dat, hp_filtered=False, raw_num_channels=8, copy_binary=copy_binary,
        use_relative_path=False, job_kwargs={"n_jobs": 1}, binary_dtype="int16",
    )
    np.testing.assert_array_equal(np.load(folder / "channel_map_si.npy"), selected)
    np.testing.assert_array_equal(np.load(folder / "channel_map.npy"), np.arange(4) if copy_binary else selected)
    if with_geometry:
        np.testing.assert_array_equal(np.load(folder / "channel_shanks.npy"), [2, 3, 0, 1])
        np.testing.assert_array_equal(np.load(folder / "channel_probe.npy"), [1, 1, 0, 0])
    else:
        assert not (folder / "channel_shanks.npy").exists()
        assert not (folder / "channel_probe.npy").exists()
    assert dat.read_bytes() == traces.tobytes()


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
def test_pipeline_cli_preserves_channel_identity_through_phy_and_cell_explorer(tmp_path, monkeypatch, capsys):
    import spikeinterface as si
    import src.postprocess.pipeline as post_pipeline

    settings, config_path, traces = _session_config(tmp_path)
    # Anatomical groups do not imply separate probes in the GUI defaults.
    settings.preprocess.probe_assignments = [
        {"type": "linear", "groups": [0], "x_offset": 0},
        {"type": "linear", "groups": [1], "x_offset": 200},
    ]
    settings.save(config_path)
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
    result_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith(RESULT_PREFIX))
    result = json.loads(result_line[len(RESULT_PREFIX):])
    assert result["mode"] == "all"
    assert Path(result["preprocess_result"]["dat_path"]) == output / "session.dat"
    assert result["postprocess_results"]["count"] == 1
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
    assert session["extracellular"]["sr"] == 20000
    assert np.dtype(session["extracellular"]["precision"]) == np.dtype("int16")
    assert session["extracellular"]["nSamples"] == len(traces)
    assert session["general"]["duration"] == len(traces) / 20000
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
        np.testing.assert_array_equal(np.load(phy / "channel_shanks.npy"), [0, 0, 0, 1, 1])
        np.testing.assert_array_equal(np.load(phy / "channel_probe.npy"), [0, 0, 0, 1, 1])
        np.testing.assert_array_equal(
            np.load(phy / "channel_positions.npy"), np.column_stack((coords["x"][good], coords["y"][good]))
        )
        assert params["n_channels_dat"] == (5 if copy_binary else 8)
        assert params["sample_rate"] == session["extracellular"]["sr"]
        assert np.dtype(params["dtype"]) == np.dtype(session["extracellular"]["precision"])
        phy_dat = resolve_phy_dat_path(phy)
        assert phy_dat == ((phy / "recording.dat").resolve() if copy_binary else dat.resolve())
        binary = np.fromfile(phy_dat, dtype=params["dtype"]).reshape(-1, params["n_channels_dat"])
        assert len(binary) == session["extracellular"]["nSamples"]
        np.testing.assert_array_equal(binary[:, np.load(phy / "channel_map.npy")], expected[:, good])

    # Resume through the postprocess CLI: keep original IDs within probe 2,
    # rather than interpreting its compact selection as new binary columns.
    partitions = build_sorter_partitions(
        mode="probe", chanmap_mat_path=output / "chanMap.mat", num_channels=8,
        excluded_channels_0based=[1, 4, 7],
    )
    assert [partition.name for partition in partitions] == ["probe1", "probe2"]
    assert partitions[1].channels_0based == [5, 6]
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


@pytest.mark.parametrize("mode", ["preprocess", "postprocess", "noise_label"])
def test_pipeline_cli_dispatches_only_the_requested_stage(tmp_path, monkeypatch, capsys, mode):
    settings, config_path, _ = _session_config(tmp_path)
    calls = []

    def prepare(config):
        calls.append("prepare")
        return {}

    def run_preprocess(config):
        calls.append("preprocess")
        return SimpleNamespace(
            sorter_output_dir=None, local_output_dir=settings.local_output_dir,
            dat_path=settings.local_output_dir / "session.dat",
        )

    def run_postprocess(config):
        calls.append("postprocess")
        assert config.noise_label_only is (mode == "noise_label")
        return [SimpleNamespace(analyzer_cache_dir=settings.local_output_dir / "analyzer")]

    import src.preprocess.runtime_prep as runtime_prep

    monkeypatch.setattr(runtime_prep, "prepare_preprocess_settings", prepare)
    monkeypatch.setitem(preprocess.__dict__, "run_preprocess_session", run_preprocess)
    monkeypatch.setitem(postprocess.__dict__, "run_postprocess_session", run_postprocess)
    assert main(["--config", str(config_path), "--mode", mode]) == 0
    assert calls == (["prepare", "preprocess"] if mode == "preprocess" else ["postprocess"])
    result_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith(RESULT_PREFIX))
    result = json.loads(result_line[len(RESULT_PREFIX):])
    assert result["mode"] == mode
    assert ("preprocess_result" in result) is (mode == "preprocess")
    assert ("postprocess_results" in result) is (mode != "preprocess")
    if mode != "preprocess":
        assert result["postprocess_results"] == {
            "count": 1, "analyzer_cache_dirs": [str(settings.local_output_dir / "analyzer")],
        }
    assert not settings.local_output_dir.exists()


def test_pipeline_cli_reports_malformed_config_before_processing(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    config_path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(pipeline_cli, "run_pipeline", lambda *args: pytest.fail("Processing must not start"))
    assert main(["--config", str(config_path), "--mode", "all"]) == 1
    output = capsys.readouterr()
    error_line = next(line for line in output.out.splitlines() if line.startswith(ERROR_PREFIX))
    error = json.loads(error_line[len(ERROR_PREFIX):])
    assert error["type"] == "JSONDecodeError"
    assert error["message"]
    assert RESULT_PREFIX not in output.out
    assert config_path.read_text(encoding="utf-8") == "{invalid"
    assert list(tmp_path.iterdir()) == [config_path]


def _mixed_session_config(tmp_path):
    settings, config_path, intan_traces = _session_config(tmp_path)
    raw = settings.basepath_path
    intan_analog = np.arange(len(intan_traces), dtype=np.int16).reshape(-1, 1) + 5000
    intan_analog.tofile(raw / "epoch" / "analogin.dat")

    wild = raw / "wild"
    wild.mkdir()
    wild_traces = np.arange(1024 * 8, dtype=np.int16).reshape(-1, 8) + 10000
    wild_traces.tofile(wild / "amplifier.dat")
    wild_analog = np.arange(64 * 2, dtype=np.int16).reshape(-1, 2) + 3000
    wild_analog.tofile(wild / "analogin.dat")
    (wild / "wild_preprocess_run.json").write_text(json.dumps({"merge": {
        "fs": 20000, "n_channels": 8, "n_samples": len(wild_traces),
        "analog_channels": 2, "analog_samples": len(wild_analog),
    }}), encoding="utf-8")

    oe = raw / "2026-09-30_12-00-00" / "Record Node 101" / "experiment1" / "recording1"
    stream = "Acquisition_Board-100.acquisition_board"
    continuous = oe / "continuous" / stream
    continuous.mkdir(parents=True)
    oe_traces = np.arange(1536 * 8, dtype=np.int16).reshape(-1, 8) + 1000
    oe_analog = np.arange(len(oe_traces), dtype=np.int16).reshape(-1, 1) + 100
    (continuous / "continuous.dat").write_bytes(np.column_stack((oe_traces, oe_analog)).tobytes())
    np.save(continuous / "sample_numbers.npy", np.arange(len(oe_traces), dtype=np.int64))
    channels = [{
        "channel_name": f"CH{index + 1}", "identifier": "acq-board.rhythm.continuous.ephys",
        "units": "uV", "bit_volts": 0.195,
    } for index in range(8)]
    channels.append({
        "channel_name": "ADC1", "identifier": "acq-board.rhythm.continuous.adc",
        "units": "V", "bit_volts": 1.0,
    })
    (oe / "structure.oebin").write_text(json.dumps({"continuous": [{
        "folder_name": f"{stream}/", "sample_rate": 20000, "num_channels": 9,
        "recorded_processor": "Record Node", "recorded_processor_id": 101, "channels": channels,
    }], "events": []}), encoding="utf-8")

    settings.subsession_order = [
        "wild/amplifier.dat", oe.relative_to(raw).as_posix(), "epoch/amplifier.dat",
    ]
    settings.preprocess.digital_inputs = False
    settings.save(config_path)
    expected_traces = np.vstack((wild_traces, oe_traces, intan_traces))
    oe_padded = np.column_stack((oe_analog[::16], np.zeros((96, 1), dtype=np.int16)))
    intan_padded = np.column_stack((intan_analog[::16], np.zeros((128, 1), dtype=np.int16)))
    expected_analog = np.vstack((wild_analog, oe_padded, intan_padded)).astype(np.uint16)
    return settings, config_path, expected_traces, expected_analog


@pytest.mark.integration
def test_pipeline_cli_preprocesses_mixed_intan_oe_wild_in_selected_order(tmp_path, capsys):
    settings, config_path, expected, expected_analog = _mixed_session_config(tmp_path)
    raw = settings.basepath_path
    sources = {path: path.read_bytes() for path in raw.rglob("*") if path.is_file()}
    discovered = discover_subsessions(
        basepath=raw, sort_files=True, alt_sort=None, ignore_folders=[],
        subsession_order=settings.subsession_order,
    )
    catalog = build_acquisition_catalog(discovered, n_amplifier_channels=8, dtype="int16")
    assert catalog.source_types == ["wild", "openephys", "intan"]
    assert catalog.sample_counts == [1024, 1536, 2048]
    assert catalog.source_total_channels == [8, 9, 8]
    assert catalog.source_ephys_channels == [8, 8, 8]
    assert catalog.source_adc_channels == [2, 1, 1]

    assert main(["--config", str(config_path), "--mode", "preprocess"]) == 0
    result_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith(RESULT_PREFIX))
    result = json.loads(result_line[len(RESULT_PREFIX):])
    assert result["mode"] == "preprocess"
    assert "postprocess_results" not in result
    output = settings.local_output_dir
    expected[:, [1, 4, 7]] = 0
    np.testing.assert_array_equal(np.fromfile(output / "session.dat", dtype="int16").reshape(-1, 8), expected)
    np.testing.assert_array_equal(
        np.fromfile(output / "analogin.dat", dtype=np.uint16).reshape(-1, 2), expected_analog,
    )
    layout = json.loads((output / "analogin.dat.layout.json").read_text(encoding="utf-8"))
    assert layout["sampling_frequency"] == 1250
    assert layout["sample_counts"] == [64, 96, 128]
    merge = loadmat(output / "session.MergePoints.events.mat", simplify_cells=True)["MergePoints"]
    np.testing.assert_array_equal(merge["timestamps_samples"], [[0, 1024], [1024, 2560], [2560, 4608]])
    np.testing.assert_array_equal(merge["foldernames"], catalog.subsession_names)
    session = loadmat(output / "session.session.mat", simplify_cells=True)["session"]
    assert session["extracellular"]["nChannels"] == 8
    assert session["extracellular"]["sr"] == 20000
    assert session["extracellular"]["nSamples"] == len(expected)
    assert session["general"]["duration"] == len(expected) / 20000
    np.testing.assert_array_equal(session["channelTags"]["Bad"]["channels"], [2, 5, 8])
    assert all(path.read_bytes() == content for path, content in sources.items())


@pytest.mark.parametrize("source_type", ["openephys", "wild"])
def test_pipeline_cli_rejects_mixed_acquisition_rate_mismatch_before_binary_exports(
    tmp_path, monkeypatch, capsys, source_type,
):
    settings, config_path, _, _ = _mixed_session_config(tmp_path)
    raw = settings.basepath_path
    if source_type == "openephys":
        metadata_path = next(raw.rglob("structure.oebin"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["continuous"][0]["sample_rate"] = 30000
    else:
        metadata_path = raw / "wild" / "wild_preprocess_run.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["merge"]["fs"] = 10000
        metadata["merge"]["analog_samples"] = 128
        np.zeros((128, 2), dtype=np.int16).tofile(raw / "wild" / "analogin.dat")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    sources = {path: path.read_bytes() for path in raw.rglob("*") if path.is_file()}
    monkeypatch.setitem(postprocess.__dict__, "run_postprocess_session", lambda *args: pytest.fail("Postprocess must not start"))
    assert main(["--config", str(config_path), "--mode", "all"]) == 1
    error_line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith(ERROR_PREFIX))
    error = json.loads(error_line[len(ERROR_PREFIX):])
    assert error["type"] == "ValueError"
    assert ("sampling rate" if source_type == "openephys" else "sampling frequency") in error["message"]
    assert not (settings.local_output_dir / "session.dat").exists()
    assert not (settings.local_output_dir / "analogin.dat").exists()
    assert not (settings.local_output_dir / "session.MergePoints.events.mat").exists()
    assert all(path.read_bytes() == content for path, content in sources.items())


def test_mixed_acquisition_catalog_rejects_different_ephys_channel_counts(tmp_path):
    settings, _, _, _ = _mixed_session_config(tmp_path)
    raw = settings.basepath_path
    metadata_path = next(raw.rglob("structure.oebin"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    # A valid seven-ephys/two-ADC stream still has nine physical binary columns.
    channel = metadata["continuous"][0]["channels"][7]
    channel.update(channel_name="ADC2", identifier="acq-board.rhythm.continuous.adc", units="V")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    sources = {path: path.read_bytes() for path in raw.rglob("*") if path.is_file()}
    discovered = discover_subsessions(basepath=raw, sort_files=True, alt_sort=None, ignore_folders=[])
    with pytest.raises(ValueError, match="mismatched ephys channel counts"):
        build_acquisition_catalog(discovered, n_amplifier_channels=8, dtype="int16")
    assert all(path.read_bytes() == content for path, content in sources.items())
