import errno

import pytest

import src.postprocess.pipeline as pipeline


def test_rmtree_retries_directory_not_empty(tmp_path, monkeypatch):
    folder = tmp_path / "staging"
    folder.mkdir()
    (folder / "waveforms").mkdir()
    real_rmtree = pipeline.shutil.rmtree
    calls = []

    def initially_busy(path):
        calls.append(path)
        if len(calls) == 1:
            raise OSError(errno.ENOTEMPTY, "Directory not empty", path)
        real_rmtree(path)

    monkeypatch.setattr(pipeline.shutil, "rmtree", initially_busy)
    monkeypatch.setattr(pipeline.time, "sleep", lambda delay: None)

    pipeline._safe_rmtree(folder)

    assert len(calls) == 2
    assert not folder.exists()


def test_cleanup_failure_does_not_hide_original_error(tmp_path, monkeypatch):
    folder = tmp_path / "staging"
    folder.mkdir()

    def fail_run(config, *, sorting_phy_folder, attempt_state):
        attempt_state["staging_folder"] = folder
        raise ValueError("original failure")

    def fail_cleanup(path):
        raise OSError(errno.ENOTEMPTY, "Directory not empty", path)

    monkeypatch.setattr(pipeline, "_run_postprocess_single_session_impl", fail_run)
    monkeypatch.setattr(pipeline, "_safe_rmtree", fail_cleanup)

    with pytest.warns(RuntimeWarning, match="Could not remove failed postprocess attempt"):
        with pytest.raises(ValueError, match="original failure"):
            pipeline._run_postprocess_single_session(None, sorting_phy_folder=tmp_path)
