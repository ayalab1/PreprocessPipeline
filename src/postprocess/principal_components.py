"""Bounded global PCA for the pipeline's pinned SpikeInterface 0.103.2.

Keep the standard extension name, parameters, models and projection layout so
SpikeInterface can load, merge and export the result normally. Only this
extension instance is changed; the SpikeInterface registry is untouched.
"""

import numpy as np
from sklearn.decomposition import IncrementalPCA
from spikeinterface.core.job_tools import fix_job_kwargs
from spikeinterface.postprocessing.principal_component import ComputePrincipalComponents
from threadpoolctl import threadpool_limits
from tqdm.auto import tqdm


class _BoundedGlobalPrincipalComponents(ComputePrincipalComponents):
    # Input-buffer budget, not a bound on the entire analyzer or SVD workspace.
    _batch_bytes = 64 * 1024**2

    def _run(self, verbose=False, **job_kwargs):
        jobs = fix_job_kwargs(job_kwargs)
        self.run_info["pipeline_pca_implementation"] = "bounded_global_v1"
        self.run_info["pipeline_pca_batch_bytes"] = self._batch_bytes
        print(f"[postprocess] global PCA input batches: at most {self._batch_bytes / 1024**2:g} MiB", flush=True)
        with threadpool_limits(limits=jobs["max_threads_per_worker"], user_api="blas"):
            super()._run(verbose=verbose, **jobs)

    def _channel_count(self, unit_id):
        sparsity = self.sorting_analyzer.sparsity
        if sparsity is None:
            return len(self.sorting_analyzer.channel_ids)
        return len(sparsity.unit_id_to_channel_indices[unit_id])

    def _fit_by_channel_global(self, progress_bar):
        model = IncrementalPCA(n_components=self.params["n_components"], whiten=self.params["whiten"])
        analyzer = self.sorting_analyzer
        waveforms = analyzer.get_extension("waveforms").data["waveforms"]
        spikes = analyzer.get_extension("random_spikes").get_random_spikes()
        n_samples = waveforms.shape[1]
        n_components = self.params["n_components"]
        # IPCA adds the old components and one mean-correction row to its SVD.
        lapack_rows = np.iinfo(np.int32).max // n_samples - n_components - 1
        max_rows = min(self._batch_bytes // (n_samples * waveforms.dtype.itemsize), lapack_rows)
        if max_rows < 2 * n_components:
            raise ValueError("PCA input budget is too small for the waveform length and component count")

        units = enumerate(analyzer.unit_ids)
        if progress_bar:
            units = tqdm(units, total=len(analyzer.unit_ids), desc="Fitting PCA")
        for unit_index, unit_id in units:
            indices = np.flatnonzero(spikes["unit_index"] == unit_index)
            n_channels = self._channel_count(unit_id)
            n_rows = len(indices) * n_channels
            if n_rows < n_components:
                continue
            n_batches = (n_rows + max_rows - 1) // max_rows
            # Balanced batches avoid dropping a final group smaller than n_components.
            for batch_index in range(n_batches):
                rows = np.arange(batch_index * n_rows // n_batches,
                                 (batch_index + 1) * n_rows // n_batches)
                # Same spike-major, channel-minor order as SI's transpose/reshape,
                # without copying an entire unit before slicing the batch.
                batch = waveforms[indices[rows // n_channels], :, rows % n_channels]
                model.partial_fit(batch)
                del batch
        return model

    def _transform_waveforms(self, spikes, waveforms, pca_model, progress_bar):
        projections = np.zeros((len(waveforms), self.params["n_components"], waveforms.shape[2]),
                               dtype="float32")
        units = enumerate(self.sorting_analyzer.unit_ids)
        if progress_bar:
            units = tqdm(units, total=len(self.sorting_analyzer.unit_ids), desc="Projecting waveforms")
        for unit_index, unit_id in units:
            indices = np.flatnonzero(spikes["unit_index"] == unit_index)
            n_channels = self._channel_count(unit_id)
            if n_channels == 0:
                continue
            batch_size = max(1, self._batch_bytes //
                             (waveforms.shape[1] * waveforms.dtype.itemsize))
            for channel in range(n_channels):
                for start in range(0, len(indices), batch_size):
                    selected = indices[start:start + batch_size]
                    batch = waveforms[selected, :, channel]
                    projections[selected, :, channel] = pca_model.transform(batch)
                    del batch
        return projections


def compute_principal_components(analyzer, *, n_components, mode, job_kwargs):
    """Compute PCA after waveform computation has invalidated any previous PCA."""
    if mode != "by_channel_global":
        return analyzer.compute("principal_components", n_components=n_components, mode=mode, **job_kwargs)
    if analyzer.has_extension("principal_components"):
        raise RuntimeError("Bounded PCA requires fresh waveform features with no existing PCA extension")
    for dependency in ComputePrincipalComponents.depend_on:
        if not analyzer.has_extension(dependency):
            raise RuntimeError(f"PCA requires the {dependency} extension")
    # Use the normal extension lifecycle without replacing SI's global registry.
    extension = _BoundedGlobalPrincipalComponents(analyzer)
    extension.set_params(n_components=n_components, mode=mode)
    extension.run(**job_kwargs)
    analyzer.extensions[extension.extension_name] = extension
    return extension
