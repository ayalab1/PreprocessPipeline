"""Conservative admission checks for large pipeline outputs.

These estimates are additional allocations, not total session sizes. Existing
files already consume the free space reported by the destination filesystem.
"""
from __future__ import annotations

import errno
import math
from pathlib import Path
import shutil
from typing import Any, Mapping

import numpy as np

GIB = 1024**3
MIN_HEADROOM_BYTES = 5 * GIB


def require_disk_space(
    output_dir: Path, components: Mapping[str, int], *, stage: str,
) -> None:
    """Check the actual destination volume, including not-yet-created folders."""
    destination = Path(output_dir).expanduser().resolve()
    probe = destination
    while not probe.exists():
        probe = probe.parent
    if not probe.is_dir():
        raise NotADirectoryError(str(probe))
    planned = sum(int(size) for size in components.values())
    if any(int(size) < 0 for size in components.values()):
        raise ValueError("Disk-space estimates must be nonnegative")
    headroom = max(MIN_HEADROOM_BYTES, math.ceil(planned / 5)) if planned else 0
    required = planned + headroom
    free = shutil.disk_usage(probe).free
    details = ", ".join(
        f"{name}={size / GIB:.2f} GiB" for name, size in components.items() if size
    )
    message = (
        f"{stage} disk-space check for {destination}: "
        f"estimated additional space {required / GIB:.2f} GiB "
        f"(including {headroom / GIB:.2f} GiB headroom), "
        f"available {free / GIB:.2f} GiB. {details}"
    )
    if free < required:
        raise OSError(
            errno.ENOSPC,
            f"Insufficient disk space. {message}. "
            f"Free at least {(required - free) / GIB:.2f} GiB more or choose "
            "a working directory on a larger volume, then retry.",
            str(destination),
        )
    print(message, flush=True)


def sorting_space_components(binary_bytes: int) -> dict[str, int]:
    # Allow one exported recording plus one full whitened/preprocessed copy.
    # KiloSort1's RAM cache can reduce the latter, but must not be relied on.
    return {"sorter recording and temporary data": 2 * int(binary_bytes)}


def preprocess_space_components(
    config: Any, catalog: Any, *, output_dir: Path, basename: str,
    n_channels: int, sampling_frequency: float, analog_sampling_frequency: float,
    sorter: str | None,
) -> dict[str, int]:
    samples = sum(int(value) for value in catalog.sample_counts)
    itemsize = np.dtype(config.dtype).itemsize
    binary_bytes = samples * int(n_channels) * itemsize
    components: dict[str, int] = {}

    def pending(name: str, filename: str, size: int) -> None:
        # Overwrites use atomic same-directory temporary files. Do not credit
        # the old output's size: it remains allocated until publication.
        if config.overwrite or not (output_dir / filename).is_file():
            components[name] = int(size)

    pending("processed recording", f"{basename}.dat", binary_bytes)
    if config.save_raw:
        pending("raw recording", f"{basename}_raw.dat", binary_bytes)
    lfp_samples = math.ceil(samples * float(config.lfp_fs) / sampling_frequency)
    lfp_bytes = lfp_samples * int(n_channels) * itemsize
    if config.make_lfp:
        pending("LFP", f"{basename}.lfp", lfp_bytes)
    if config.state_score:
        # Budget double-precision LFP-derived arrays and MATLAB exports.
        pending("sleep scoring", f"{basename}.SleepState.states.mat", 4 * lfp_bytes)

    ttl = str(config.artifact_ttl_group_mode).lower() != "none"
    if config.export_intermediate_dat or config.analog_inputs or config.digital_inputs or ttl:
        # Conservative for mixed acquisitions and missing epochs that are
        # materialized as zeros. Use the output ADC width, not source size.
        analog_samples = max(
            math.ceil(samples * analog_sampling_frequency / sampling_frequency),
            sum(int(value or 0) for value in catalog.analog_sample_counts_by_subsession),
        )
        pending("analog sidecar", "analogin.dat", analog_samples * max(1, catalog.board_adc_channels) * 2)
        pending("digital sidecar", "digitalin.dat", samples * max(1, catalog.board_digital_word_channels) * 2)
    if config.export_intermediate_dat:
        for name, paths in (
            ("auxiliary", catalog.auxiliary_paths),
            ("supply", catalog.supply_paths),
            ("time", catalog.time_paths),
        ):
            pending(f"{name} sidecar", f"{name}.dat", sum(Path(p).stat().st_size for p in paths))
    if sorter:
        components.update(sorting_space_components(binary_bytes))
    return components
