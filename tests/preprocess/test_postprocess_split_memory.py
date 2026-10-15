from types import SimpleNamespace
import weakref

import numpy as np
import pytest
import spikeinterface as si
from joblib import Parallel as JoblibParallel
from threadpoolctl import threadpool_info

import src.postprocess.pipeline as pipeline
import src.postprocess.unit_split as split


class RecordingReads:
    def __init__(self, traces):
        self.traces = traces
        self.reads = []
        self.buffers = []

    def get_total_samples(self):
        return len(self.traces)

    def get_traces(self, *, start_frame, end_frame, channel_ids, return_in_uV):
        assert return_in_uV
        assert not any(ref() is not None for ref in self.buffers), "Previous chunk retained"
        data = self.traces[start_frame:end_frame, channel_ids].copy()
        self.buffers.append(weakref.ref(data))
        self.reads.append((start_frame, end_frame))
        return data


@pytest.mark.parametrize("frames", [
    np.array([28, 0, 18, 28, 199]),
    np.arange(10, 180, 2),
])
def test_waveform_reads_are_bounded_and_keep_spike_order(frames):
    traces = np.arange(200 * 6, dtype="float32").reshape(200, 6)
    recording = RecordingReads(traces)
    actual, invalid = split._extract_waveforms(
        recording, frames, [5, 2], 3, 4, max_chunk_samples=13,
    )
    expected = np.zeros((len(frames), 7, 2), dtype="float32")
    for i, frame in enumerate(frames):
        if frame >= 3 and frame + 4 <= len(traces):
            expected[i] = traces[frame - 3:frame + 4][:, [5, 2]]
    np.testing.assert_array_equal(actual, expected)
    assert invalid == sum((frames < 3) | (frames + 4 > len(traces)))
    assert all(end - start <= 13 for start, end in recording.reads)
    assert not any(ref() is not None for ref in recording.buffers)


def make_split_analyzer():
    rng = np.random.default_rng(24)
    unit_ids = [10, 20, 30]
    frames = {uid: np.arange(100 + k * 5000, 4100 + k * 5000, 20)
              for k, uid in enumerate(unit_ids)}
    sorting = si.NumpySorting.from_unit_dict(frames, 1000.0)
    traces = rng.normal(0, 0.005, (16000, 6)).astype("float32")
    wave = np.array([-0.2, -1, -0.4, 0.3, 0.1, 0], dtype="float32")
    templates = np.zeros((3, 6, 6), dtype="float32")
    pcs = {}
    for k, uid in enumerate(unit_ids):
        templates[k, :, k] = wave
        data = rng.normal(size=(200, 3, 6)).astype("float32")
        data[-30:] += 5
        pcs[uid] = data
        for i, frame in enumerate(frames[uid]):
            # Some PCA outliers have normal waveforms and can be rescued;
            # others have excessive amplitude and must remain outliers.
            gain = 10 if i >= 185 else 1
            traces[frame - 2:frame + 4, k] += gain * wave
    recording = si.NumpyRecording(traces, sampling_frequency=1000.0)
    recording.set_channel_gains(np.ones(6))
    recording.set_channel_offsets(np.zeros(6))
    extensions = {
        "principal_components": SimpleNamespace(get_projections_one_unit=lambda unit_id: pcs[unit_id]),
        "templates": SimpleNamespace(get_data=lambda **kwargs: templates),
        "waveforms": SimpleNamespace(params={"ms_before": 2, "ms_after": 4}),
    }
    return SimpleNamespace(sorting=sorting, recording=recording,
                           has_extension=lambda name: name in extensions,
                           get_extension=lambda name: extensions[name])


@pytest.mark.parametrize("threshold_mode", ["empirical", "adaptive_chi2"])
@pytest.mark.parametrize("waveform_gate", [False, True])
def test_batched_parallel_split_matches_serial(threshold_mode, waveform_gate, monkeypatch):
    analyzer = make_split_analyzer()
    kwargs = dict(threshold_mode=threshold_mode, contamination=0.15,
                  use_waveform_gate=waveform_gate, wf_threshold=0.8,
                  wf_template_max=41, wf_n_chans=2, min_spikes=3,
                  return_details=True, verbose=False)
    before_pools = {p["filepath"]: p["num_threads"] for p in threadpool_info() if p["user_api"] == "blas"}
    serial, serial_details = split.autosplit_outliers_pca(
        analyzer, n_jobs=1, waveform_batch_size=1024, **kwargs,
    )
    worker_counts = []
    blas_threads = []
    real_get = analyzer.get_extension("principal_components").get_projections_one_unit

    def get_projections(unit_id):
        blas_threads.extend(p["num_threads"] for p in threadpool_info() if p["user_api"] == "blas")
        return real_get(unit_id)

    def parallel(**options):
        worker_counts.append(options["n_jobs"])
        return JoblibParallel(**options)

    analyzer.get_extension("principal_components").get_projections_one_unit = get_projections
    monkeypatch.setattr(split, "Parallel", parallel)
    result, details = split.autosplit_outliers_pca(
        analyzer, n_jobs=128, max_workers=2, waveform_batch_size=7,
        waveform_chunk_samples=20, **kwargs,
    )
    np.testing.assert_array_equal(result.to_spike_vector(), serial.to_spike_vector())
    assert details == serial_details
    # Recorded from the pre-fix splitter on this deterministic fixture.
    expected_outliers = {
        ("empirical", False): [30, 30, 30],
        ("empirical", True): [6, 7, 10],
        ("adaptive_chi2", False): [31, 28, 27],
        ("adaptive_chi2", True): [5, 6, 8],
    }
    assert [details[uid]["n_outlier"] for uid in [10, 20, 30]] == expected_outliers[threshold_mode, waveform_gate]
    assert worker_counts == [2]
    assert blas_threads and all(n == 1 for n in blas_threads)
    assert {p["filepath"]: p["num_threads"] for p in threadpool_info() if p["user_api"] == "blas"} == before_pools
    assert any(d["n_outlier"] > 0 for d in details.values())


def _merged_analyzer(tmp_path):
    rng = np.random.default_rng(3)
    recording = si.NumpyRecording(rng.normal(size=(2000, 3)).astype("float32"), 1000)
    recording.set_channel_locations([[0, 0], [20, 0], [40, 0]])
    sorting = si.NumpySorting.from_unit_dict({0: np.arange(100, 900, 40),
                                           1: np.arange(1100, 1900, 40)}, 1000)
    analyzer = si.create_sorting_analyzer(sorting, recording, sparse=False,
                                         format="binary_folder", folder=tmp_path / "main")
    analyzer.compute({"random_spikes": {"method": "all"},
                      "waveforms": {"ms_before": 3, "ms_after": 4},
                      "templates": {},
                      "principal_components": {"n_components": 2, "mode": "by_channel_global"}},
                     n_jobs=1, progress_bar=False)
    return analyzer.merge_units([[0, 1]], censor_ms=0, format="binary_folder", folder=tmp_path / "merged")


def test_soft_merged_features_use_read_only_disk_buffers(tmp_path):
    analyzer = _merged_analyzer(tmp_path)
    before = {}
    refs = []
    for name in ("waveforms", "principal_components"):
        for key, data in analyzer.get_extension(name).data.items():
            if isinstance(data, np.ndarray):
                before[name, key] = np.array(data, copy=True)
                refs.append(weakref.ref(data))
    del data
    expected_bytes = sum(data.nbytes for data in before.values())
    assert pipeline._map_saved_split_arrays(analyzer) == expected_bytes
    assert all(ref() is None for ref in refs)
    for (name, key), expected in before.items():
        mapped = analyzer.get_extension(name).data[key]
        assert isinstance(mapped, np.memmap)
        assert not mapped.flags.writeable
        np.testing.assert_array_equal(mapped, expected)


def test_saved_feature_shape_mismatch_is_rejected(tmp_path):
    analyzer = _merged_analyzer(tmp_path)
    file = analyzer.folder / "extensions" / "waveforms" / "waveforms.npy"
    np.save(file, np.zeros(1, dtype="float32"))
    with pytest.raises(RuntimeError, match="Saved split feature does not match"):
        pipeline._map_saved_split_arrays(analyzer)


@pytest.mark.parametrize("parameter", ["max_workers", "waveform_batch_size", "waveform_chunk_samples"])
def test_nonpositive_memory_limits_are_rejected(parameter):
    with pytest.raises(ValueError, match=parameter):
        split.autosplit_outliers_pca(make_split_analyzer(), **{parameter: 0})
