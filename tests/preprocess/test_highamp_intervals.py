from __future__ import annotations

import numpy as np
import pytest
from scipy.io import loadmat, savemat
from spikeinterface.core import NumpyRecording

from src.preprocess.artifact_removal import remove_artifacts
from src.preprocess.gui.config_model import PipelineGuiSettings
from src.preprocess.gui.app import MainWindow
from src.preprocess.interval_artifacts import merge_trigger_windows
from src.preprocess.pipeline import _load_highamp_intervals_by_group
import src.preprocess.pipeline as preprocess_pipeline


def test_overlapping_windows_merge_into_one_full_interval() -> None:
    # At 1 kHz, each trigger has a one-sample window on either side.
    # The windows around 20 and 22 overlap, while the window at 30 stays separate.
    intervals = merge_trigger_windows(
        [20, 22, 30], sampling_frequency=1000.0,
        num_samples=100, ms_before=1.0, ms_after=1.0,
    )
    np.testing.assert_array_equal(intervals, [[19, 24], [29, 32]])


def test_merged_interval_interpolates_once_across_artifact_and_chunks() -> None:
    clean = np.arange(100, dtype=np.int16)
    traces = np.column_stack((clean, clean)).astype(np.int16)
    traces[19:24, 0] = 1000
    recording = NumpyRecording(traces, 1000.0)
    recording.set_property("group", [0, 1])
    intervals = merge_trigger_windows(
        [20, 22], sampling_frequency=1000.0,
        num_samples=100, ms_before=1.0, ms_after=1.0,
    )

    cleaned, details = remove_artifacts(
        recording, {0: intervals}, by_group=True, mode="linear", use_intervals=True
    )

    np.testing.assert_array_equal(cleaned.get_traces(start_frame=17, end_frame=26)[:, 0], clean[17:26])
    np.testing.assert_array_equal(cleaned.get_traces(start_frame=20, end_frame=22)[:, 0], clean[20:22])
    np.testing.assert_array_equal(cleaned.get_traces(start_frame=18, end_frame=25)[:, 1], traces[18:25, 1])
    assert details[0]["n_triggers"] == 1


@pytest.mark.parametrize("mode", ["linear", "cubic", "0"])
def test_merged_interval_supports_each_gui_replacement_mode(mode: str) -> None:
    clean = np.arange(30, dtype=np.int16)
    traces = clean.copy()
    traces[9:14] = 1000
    recording = NumpyRecording(traces[:, None], 1000.0)

    cleaned, _ = remove_artifacts(
        recording, {0: np.array([[9, 14]])},
        by_group=False, mode=mode, use_intervals=True,
    )

    actual = cleaned.get_traces(start_frame=8, end_frame=15)[:, 0]
    expected = clean[8:15].copy()
    if mode == "0":
        expected[1:6] = 0
    np.testing.assert_array_equal(actual, expected)


def test_saved_merged_intervals_reuse_original_boundaries(tmp_path) -> None:
    path = tmp_path / "artifactHigh.events.mat"
    savemat(path, {"artifactHigh": {
        "timestamps": np.array([[0.019, 0.024], [0.030, 0.035]]),
        "group_id": np.array([[0], [1]]),
        "merged_intervals": 1,
    }})

    loaded = _load_highamp_intervals_by_group(
        path, sampling_frequency=1000.0, group_mode="shank"
    )
    np.testing.assert_array_equal(loaded[0], [[19, 24]])
    np.testing.assert_array_equal(loaded[1], [[30, 35]])


def test_interval_merge_option_round_trips_to_preprocess_config(tmp_path) -> None:
    settings = PipelineGuiSettings(basepath=str(tmp_path / "session"))
    settings.preprocess.highamp_merge_intervals = True
    loaded = PipelineGuiSettings.from_json(settings.to_json())

    assert loaded.to_preprocess_config().highamp_merge_intervals is True


def test_interval_merge_checkbox_round_trips_from_gui(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.highamp_merge_intervals.setChecked(True)
        settings = window._collect_settings()
        settings.basepath = str(tmp_path / "session")
        loaded = PipelineGuiSettings.from_json(settings.to_json())
        window._apply_settings(loaded)

        assert window.highamp_merge_intervals.isChecked()
        assert loaded.to_preprocess_config().highamp_merge_intervals is True
    finally:
        window.close()
        application.processEvents()


def test_pipeline_saves_merged_intervals_and_reuses_them(tmp_path, monkeypatch) -> None:
    raw = tmp_path / "raw" / "session"
    epoch = raw / "epoch"
    epoch.mkdir(parents=True)
    traces = np.zeros((2048, 4), dtype=np.int16)
    traces[98:106, :] = 1000
    traces.tofile(epoch / "amplifier.dat")
    np.arange(len(traces), dtype=np.int32).tofile(epoch / "time.dat")
    xml = raw / "session.xml"
    xml.write_text(
        "<session><acquisitionSystem><nChannels>4</nChannels><sampleRate>20000</sampleRate>"
        "</acquisitionSystem><anatomicalDescription><channelGroups><group><channels>"
        "<channel>0</channel><channel>1</channel><channel>2</channel><channel>3</channel>"
        "</channels></group></channelGroups></anatomicalDescription></session>"
    )
    settings = PipelineGuiSettings(
        basepath=str(raw), local_root=str(tmp_path / "local"), xml_path=str(xml)
    )
    p = settings.preprocess
    p.run_sorter = False
    p.make_lfp = False
    p.state_score = False
    p.preprocess_worker_count = 1
    p.remove_highamp_artifacts = True
    p.artifact_highamp_group_mode = "all"
    p.highamp_merge_intervals = True
    p.highamp_ms_before = 0.1
    p.highamp_ms_after = 0.1
    p.overwrite = True
    monkeypatch.setattr(
        preprocess_pipeline, "preprocess_selected_channels_preserve_shape",
        lambda recording_raw, **kwargs: recording_raw,
    )
    monkeypatch.setattr(
        preprocess_pipeline, "detect_high_amplitude_artifacts",
        lambda recording, **kwargs: {0: [100, 103]},
    )

    config = settings.to_preprocess_config()
    preprocess_pipeline.run_preprocess_session(config)
    event_path = settings.local_output_dir / "session.artifactHigh.events.mat"
    event = loadmat(event_path, simplify_cells=True)["artifactHigh"]
    np.testing.assert_allclose(event["timestamps"], [98 / 20000, 106 / 20000])
    assert event["merged_intervals"] == 1
    cleaned = np.fromfile(settings.local_output_dir / "session.dat", dtype=np.int16).reshape(-1, 4)
    assert np.all(cleaned[98:106] == 0)

    config.overwrite = False
    monkeypatch.setattr(
        preprocess_pipeline, "save_mergepoints_events_mat", lambda path, *args, **kwargs: path
    )
    monkeypatch.setattr(
        preprocess_pipeline, "detect_high_amplitude_artifacts",
        lambda recording, **kwargs: (_ for _ in ()).throw(AssertionError("must reuse events")),
    )
    preprocess_pipeline.run_preprocess_session(config)
