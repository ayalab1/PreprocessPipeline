from pathlib import Path

import numpy as np
import pytest
from scipy.io import savemat
from spikeinterface.core import NumpyRecording

from src.preprocess.channel_layout import load_channel_layout
from src.preprocess.recording import attach_probe_from_chanmap


def _write_3d_map(path: Path, zcoords: list[float]) -> None:
    savemat(path, {
        "chanMap0ind": [0, 1, 2],
        "chanMap": [1, 2, 3],
        "xcoords": [0, 0, 20],
        "ycoords": [0, 0, 20],
        "zcoords": zcoords,
        "kcoords": [1, 1, 1],
    })


def test_3d_map_attaches_distinct_projected_contacts_and_keeps_depth(tmp_path: Path) -> None:
    path = tmp_path / "chanMap3d.mat"
    _write_3d_map(path, [0, 10, 0])
    recording = NumpyRecording(np.zeros((20, 3), dtype=np.int16), 20000.0)

    attached = attach_probe_from_chanmap(recording, path)

    np.testing.assert_array_equal(attached.get_channel_locations(), [[0, 0], [10, 0], [20, 20]])
    np.testing.assert_array_equal(attached.get_property("zcoords"), [0, 10, 0])


def test_3d_map_rejects_missing_depth_entries(tmp_path: Path) -> None:
    path = tmp_path / "chanMap3d.mat"
    _write_3d_map(path, [0, 10])

    with pytest.raises(ValueError, match="zcoords length"):
        load_channel_layout(path, 3)
