"""Physical Neuropixels site geometry, independent of saved channel order."""
from __future__ import annotations

import numpy as np


NP1_GEOMETRY_NAME = "Neuropixels 1.0"


def np1_site_geometry() -> dict[str, np.ndarray]:
    """NP1 physical site IDs and micrometre coordinates, independent of banks.

    Coordinates follow Open Ephys Geometry::NP1, commit
    8c2d85a2ace63fd873b1f74fb7516a660b30562d, Geometry.cpp lines 170-213.
    The three reference sites are retained in the catalog but are not contacts
    for ordinary neural sorting. The coordinate origin matches that source.
    """
    sites = np.arange(960, dtype=np.int64)
    return {
        "site_ids": sites,
        "xcoords": np.asarray([27., 59., 11., 43.])[sites % 4],
        "ycoords": (sites // 2).astype(float) * 20.,
        "shank_ids": np.zeros(sites.size, dtype=np.int64),
        "is_reference": np.isin(sites, [191, 575, 959]),
    }
