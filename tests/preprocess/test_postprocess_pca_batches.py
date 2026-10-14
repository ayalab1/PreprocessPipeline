import numpy as np
import pytest
import spikeinterface as si
from spikeinterface.core import ChannelSparsity
from spikeinterface.core.sortinganalyzer import get_extension_class
from spikeinterface.postprocessing.principal_component import ComputePrincipalComponents

from src.postprocess.principal_components import (
    _BoundedGlobalPrincipalComponents,
    compute_principal_components,
)


def make_analyzer(tmp_path=None, *, sparse=True):
    rng = np.random.default_rng(46)
    recording = si.NumpyRecording(rng.normal(size=(5000, 4)).astype("float32"), 1000)
    recording.set_channel_locations([[0, 0], [20, 0], [40, 0], [60, 0]])
    sorting = si.NumpySorting.from_unit_dict({10: np.arange(100, 2200, 20),
                                            30: np.arange(2500, 4800, 23)}, 1000)
    sparsity = ChannelSparsity(np.array([[1, 1, 1, 0], [0, 1, 0, 1]], dtype=bool),
                              sorting.unit_ids, recording.channel_ids)
    kwargs = {} if tmp_path is None else dict(format="binary_folder", folder=tmp_path)
    analyzer = si.create_sorting_analyzer(sorting, recording, sparsity=sparsity if sparse else None,
                                         sparse=sparse, **kwargs)
    analyzer.compute({"random_spikes": {"method": "all"},
                      "waveforms": {"ms_before": 3, "ms_after": 4}},
                     n_jobs=1, progress_bar=False)
    return analyzer


def test_small_units_match_native_pca_exactly():
    analyzer = make_analyzer()
    native = ComputePrincipalComponents(analyzer)
    bounded = _BoundedGlobalPrincipalComponents(analyzer)
    for ext in (native, bounded):
        ext.set_params(n_components=3, mode="by_channel_global")
        ext.run(progress_bar=False)
    original, actual = native.get_pca_model(), bounded.get_pca_model()
    for name in ("components_", "singular_values_", "mean_", "var_", "explained_variance_"):
        np.testing.assert_array_equal(getattr(actual, name), getattr(original, name))
    np.testing.assert_array_equal(bounded.get_data(), native.get_data())


def test_large_units_fit_and_project_in_bounded_ordered_batches(monkeypatch):
    analyzer = make_analyzer()
    original = analyzer.get_extension("waveforms").data["waveforms"]
    spikes = analyzer.get_extension("random_spikes").get_random_spikes()
    budget = 1024
    fit_batches, transform_bytes, read_bytes = [], [], []
    from sklearn.decomposition import IncrementalPCA
    real_fit, real_transform = IncrementalPCA.partial_fit, IncrementalPCA.transform

    class BoundedReads:
        shape, dtype = original.shape, original.dtype

        def __len__(self):
            return len(original)

        def __getitem__(self, key):
            result = original[key]
            read_bytes.append(result.nbytes)
            assert result.nbytes <= budget, "Copied a whole unit before batching"
            return result

    def partial_fit(self, data, **kwargs):
        fit_batches.append(data.copy())
        assert data.nbytes <= budget
        return real_fit(self, data, **kwargs)

    def transform(self, data):
        transform_bytes.append(data.nbytes)
        assert data.nbytes <= budget
        return real_transform(self, data)

    monkeypatch.setattr(IncrementalPCA, "partial_fit", partial_fit)
    monkeypatch.setattr(IncrementalPCA, "transform", transform)
    analyzer.get_extension("waveforms").data["waveforms"] = BoundedReads()
    ext = _BoundedGlobalPrincipalComponents(analyzer)
    ext._batch_bytes = budget
    ext.set_params(n_components=3, mode="by_channel_global")
    ext.run(progress_bar=False)
    expected = []
    for index, uid in enumerate(analyzer.unit_ids):
        channels = len(analyzer.sparsity.unit_id_to_channel_indices[uid])
        unit_waveforms = original[spikes["unit_index"] == index, :, :channels]
        expected.append(unit_waveforms.transpose(0, 2, 1).reshape(-1, original.shape[1]))
    np.testing.assert_array_equal(np.concatenate(fit_batches), np.concatenate(expected))
    assert len(fit_batches) > len(analyzer.unit_ids)
    assert ext.get_pca_model().n_samples_seen_ == sum(len(data) for data in expected)
    assert read_bytes and transform_bytes
    assert np.isfinite(ext.get_data()).all()
    for index, uid in enumerate(analyzer.unit_ids):
        mask = spikes["unit_index"] == index
        channels = len(analyzer.sparsity.unit_id_to_channel_indices[uid])
        for channel in range(channels):
            expected_projection = real_transform(ext.get_pca_model(), original[mask, :, channel])
            np.testing.assert_allclose(ext.get_data()[mask, :, channel], expected_projection, atol=1e-6)
        assert np.all(ext.get_data()[mask, :, channels:] == 0)


def test_saved_pca_reloads_with_standard_spikeinterface_and_merges(tmp_path):
    analyzer = make_analyzer(tmp_path / "analyzer")
    ext = compute_principal_components(analyzer, n_components=3, mode="by_channel_global",
                                       job_kwargs={"progress_bar": False})
    assert get_extension_class("principal_components") is ComputePrincipalComponents
    reloaded = si.load_sorting_analyzer(tmp_path / "analyzer")
    loaded = reloaded.get_extension("principal_components")
    assert type(loaded) is ComputePrincipalComponents
    np.testing.assert_array_equal(loaded.get_data(), ext.get_data())
    assert loaded.run_info["pipeline_pca_implementation"] == "bounded_global_v1"
    assert loaded.run_info["pipeline_pca_batch_bytes"] == 64 * 1024**2
    merged = reloaded.merge_units([[10, 30]], censor_ms=0, sparsity_overlap=0)
    assert merged.has_extension("principal_components")
    assert len(merged.get_extension("principal_components").get_data()) == len(ext.get_data())


@pytest.mark.parametrize("mode", ["by_channel_local", "concatenated"])
def test_other_pca_modes_use_native_extension(mode):
    analyzer = make_analyzer(sparse=mode != "concatenated")
    ext = compute_principal_components(analyzer, n_components=3, mode=mode,
                                       job_kwargs={"n_jobs": 1, "progress_bar": False})
    assert type(ext) is ComputePrincipalComponents

