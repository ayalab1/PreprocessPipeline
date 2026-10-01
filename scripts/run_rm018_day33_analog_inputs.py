"""Export only RM018 day33 analog inputs into the local Behavior working folder."""

from __future__ import annotations

from pathlib import Path
import argparse
import gc
import json
import os
import shutil
import sys

os.environ["MPLBACKEND"] = "Agg"
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np

from src.preprocess.behavior import _load_mergepoints, inspect_dlc_ttl_sync
from src.preprocess.events import (
    _build_analog_behavior_struct,
    _detect_analog_pulses,
    _save_analog_plot,
)
from src.preprocess.io import (
    atomic_savemat,
    atomic_write_json,
    build_acquisition_catalog,
    discover_subsessions,
    validate_mat_output,
    _openephys_adc_epochs,
)
from src.preprocess.recording import write_concatenated_dat_analogin


BASE = Path(r"\\cbsuruizfs1.biohpc.cornell.edu\storage\shared\data\AutoMaze\RM018\RM018_day33_260611")
OUTPUT = REPO_ROOT / "preprocess_tmp" / BASE.name


def repair_adc1_events(catalog, counts: list[int], names: list[str], intervals: np.ndarray, sr: float) -> None:
    """Repair camera ADC1 events without rewriting raw ADC or existing exports."""
    analog_path = OUTPUT / "analogin.dat"
    layout = json.loads(analog_path.with_name("analogin.dat.layout.json").read_text())
    if (
        layout["sample_counts"] != counts
        or layout["num_channels"] != 8
        or layout["dtype"] != "uint16"
        or layout["sampling_frequency"] != sr
        or layout["source_channel_indices"] != catalog.adc_channel_indices_by_subsession
        or layout["destination_channel_indices"] != catalog.adc_output_indices_by_subsession
        or analog_path.stat().st_size != sum(counts) * 8 * 2
    ):
        raise ValueError("Existing analog sidecar does not match this session's ADC geometry")
    epochs = _openephys_adc_epochs(catalog, counts)
    camera_epochs = [(s, e, [gains[0]]) for s, e, gains in epochs]
    repair_output = OUTPUT / "adc_signed_repair"
    repair_output.mkdir(parents=True, exist_ok=True)
    pulses_path = repair_output / f"{BASE.name}.pulses.events.mat"
    if pulses_path.exists():
        raise FileExistsError(f"Repair output already exists; inspect it before rerunning: {pulses_path}")
    data = np.memmap(analog_path, dtype=np.uint16, mode="r", shape=(sum(counts), 8))
    print("Repairing signed OE ADC1 with a camera-only midrange threshold if the legacy threshold is unreachable...", flush=True)
    pulses = _detect_analog_pulses(
        analog_data_u16=data[:, :1], channel_ids_1based=[1], sr=sr,
        merge_timestamps_sec=intervals, openephys_adc_epochs=camera_epochs,
        camera_adc_channel=1,
    )
    if pulses is None:
        raise ValueError("Signed ADC1 decoding produced no events; threshold diagnosis is still required")
    pulses["cameraSyncOnly"] = True
    atomic_savemat(pulses_path, {"pulses": pulses}, required_key="pulses")
    starts = np.asarray(pulses["timestamps"])[:, 0]
    epoch_counts = {
        name: int(np.count_nonzero((starts >= start) & (starts < stop)))
        for name, (start, stop) in zip(names, intervals, strict=True)
    }
    print(f"Repaired ADC1 event counts: {epoch_counts}", flush=True)
    try:
        warnings = inspect_dlc_ttl_sync(BASE, output_dir=repair_output, camera_adc_channel=1)
    except (ValueError, FileNotFoundError) as exc:
        warnings = [str(exc)]
    atomic_write_json(repair_output / "adc1_repair.json", {
        "source": str(BASE), "analog_sidecar": str(analog_path), "output": str(pulses_path),
        "camera_adc_channel": 1, "sampling_rate": sr, "epoch_event_counts": epoch_counts,
        "adc_decoding": "openephys_signed_int16",
        "threshold_equations": "legacy_with_selected_camera_midrange_when_unreachable",
        "camera_threshold": pulses.get("cameraThreshold"),
        "camera_threshold_method": pulses.get("cameraThresholdMethod"),
        "sync_warnings": warnings,
    })
    for warning in warnings:
        print(f"Sync warning: {warning}", flush=True)
    print(f"ADC1 EVENT REPAIR COMPLETE: {pulses_path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-events-only", action="store_true", help="Regenerate only camera ADC1 events from the existing local sidecar")
    args = parser.parse_args()
    names, intervals = _load_mergepoints(BASE, BASE.name, None)
    if names is None or intervals is None:
        raise FileNotFoundError("Existing MergePoints is required for this analog-only export")
    recordings = discover_subsessions(
        BASE, sort_files=True, alt_sort=None, ignore_folders=None,
        subsession_order=[
            str(BASE / name / "Record Node 101" / "experiment1" / "recording1")
            for name in names
        ],
    )
    catalog = build_acquisition_catalog(recordings, n_amplifier_channels=192, dtype="int16")
    if catalog.subsession_names != names or any(kind != "openephys" for kind in catalog.source_types):
        raise ValueError("Discovered recordings must match the existing Open Ephys MergePoints order")
    sr = float(catalog.sampling_frequency)
    counts = [int(count) for count in catalog.sample_counts]
    stops = np.cumsum(counts)
    expected_intervals = np.column_stack((np.r_[0, stops[:-1]], stops))
    if not np.array_equal(np.rint(intervals * sr).astype(np.int64), expected_intervals):
        raise ValueError("Existing MergePoints disagrees with native source sample counts")
    n_channels = int(catalog.board_adc_channels)
    channel_ids = [int(order) + 1 for order in catalog.board_adc_native_orders]
    if n_channels != 8 or channel_ids != list(range(1, 9)) or sr != 20000:
        raise ValueError(f"Unexpected RM018 ADC layout: {n_channels=}, {channel_ids=}, {sr=}")
    total_samples = sum(counts)
    if args.repair_events_only:
        repair_adc1_events(catalog, counts, names, intervals, sr)
        return
    adc_epochs = _openephys_adc_epochs(catalog, counts)
    # Reserve uncompressed native ADC data plus the scaled MAT and time vector.
    required_bytes = total_samples * (2 * n_channels + 8 * n_channels + 8) + 1024**3
    if shutil.disk_usage(REPO_ROOT).free < required_bytes:
        raise OSError(f"Insufficient local space: reserve {required_bytes} bytes for analog outputs")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    analog_path = OUTPUT / "analogin.dat"
    behavior_path = OUTPUT / f"{BASE.name}.analogInput.behavior.mat"
    pulses_path = OUTPUT / f"{BASE.name}.pulses.events.mat"
    report_path = OUTPUT / "analog_inputs_only.json"
    print(f"Source: {BASE}\nOutput: {OUTPUT}\nADC: {n_channels} channels at {sr:g} Hz", flush=True)
    for name, count in zip(names, counts, strict=True):
        print(f"  {name}: {count} samples", flush=True)
    print("Extracting native ADC sidecar in existing epoch order...", flush=True)
    write_concatenated_dat_analogin(
        dat_paths=catalog.analogin_source_paths,
        output_dat_path=analog_path,
        sampling_frequency=sr,
        num_channels=n_channels,
        overwrite=False,
        job_kwargs={},
        sample_counts=counts,
        source_sample_counts=catalog.analog_sample_counts_by_subsession,
        source_sampling_frequencies=catalog.analog_sampling_frequencies_by_subsession,
        source_num_channels=catalog.source_total_channels,
        source_channel_indices=catalog.adc_channel_indices_by_subsession,
        destination_channel_indices=catalog.adc_output_indices_by_subsession,
    )
    data = np.memmap(analog_path, dtype=np.uint16, mode="r", shape=(total_samples, n_channels))
    print(f"ADC extraction complete: {analog_path.stat().st_size} bytes", flush=True)
    print("Detecting analog pulses with existing equations and native timebase...", flush=True)
    if pulses_path.exists():
        pulses = validate_mat_output(pulses_path, "pulses")["pulses"]
        if pulses.get("adcDecoding") != "openephys_signed_int16" or pulses.get("cameraAdcChannel") != 1:
            raise ValueError("Existing pulses predate this correction; use --repair-events-only to preserve them")
    else:
        pulses = _detect_analog_pulses(
            analog_data_u16=data, channel_ids_1based=channel_ids,
            sr=sr, merge_timestamps_sec=intervals,
            openephys_adc_epochs=adc_epochs,
            camera_adc_channel=1,
        )
        if pulses is None:
            raise ValueError("No analog pulses detected; no empty pulse output will be published")
        atomic_savemat(pulses_path, {"pulses": pulses}, required_key="pulses")
    pulse_channels, pulse_counts = np.unique(np.asarray(pulses["analogChannel"]), return_counts=True)
    counts_by_channel = {str(int(ch)): int(count) for ch, count in zip(pulse_channels, pulse_counts, strict=True)}
    print(f"Pulse events saved: {counts_by_channel}", flush=True)
    del pulses
    gc.collect()
    print("Writing analog pulse preview with the noninteractive backend...", flush=True)
    _save_analog_plot(OUTPUT, data, channel_ids, sr, overwrite=False, openephys_adc_epochs=adc_epochs)
    print("Writing analog behavior MAT with native-rate timestamps...", flush=True)
    if behavior_path.exists():
        validate_mat_output(behavior_path, "analogInp", load_payload=False)
    else:
        behavior = _build_analog_behavior_struct(
            analog_data_u16=data, active_channels_1based=channel_ids, sampling_rate=sr,
            openephys_adc_epochs=adc_epochs,
        )
        atomic_savemat(behavior_path, {"analogInp": behavior}, required_key="analogInp")
        del behavior
        gc.collect()
    del data
    print("Checking exported camera ADC1 pulses against tracking CSV...", flush=True)
    sync_warnings = inspect_dlc_ttl_sync(BASE, output_dir=OUTPUT, camera_adc_channel=1)
    atomic_write_json(report_path, {
        "source": str(BASE), "output": str(OUTPUT), "sampling_rate": sr,
        "adc_channels_1based": channel_ids, "epoch_names": names,
        "epoch_samples": counts, "merge_intervals_seconds": intervals.tolist(),
        "pulse_counts_by_channel": counts_by_channel,
        "camera_adc_channel": 1, "sync_warnings": sync_warnings,
        "analog_behavior_sampling_rate": sr,
        "scope": "analog_inputs_only; no ephys preprocessing or sorting",
    })
    for warning in sync_warnings:
        print(f"Sync warning: {warning}", flush=True)
    print(f"ANALOG INPUT EXPORT COMPLETE: {report_path}", flush=True)


if __name__ == "__main__":
    main()
