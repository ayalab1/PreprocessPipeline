"""WILD-NP applied configuration, original-column geometry and saved AP epochs."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import base64
import csv
from datetime import datetime
import os
import re
import json
from pathlib import Path

import numpy as np

from .neuropixels_geometry import NP1_GEOMETRY_NAME, np1_site_geometry


RECEIPT_FORMAT = "WILDX NP applied probe receipt"
NP1_PART = "PRB_1_4_0480_1"
CHANNELS_PER_PROBE = 384
GAIN_VALUES = (50., 125., 250., 500., 1000., 1500., 2000., 3000.)
SIGNED_CODES = "signed nominal ADC counts stored in little-endian int16; no gain calibration or microvolt conversion"
LEGACY_CODES = "unsigned 10-bit ADC codes stored in little-endian int16; no calibration applied"


@dataclass(frozen=True)
class WildxNpRecording:
    directory: Path
    ap_path: Path
    lfp_path: Path | None
    sampling_frequency: float
    lfp_sampling_frequency: float
    num_channels: int
    sample_count: int
    lfp_sample_count: int
    probes: tuple[dict, ...]
    metadata: dict[str, str]
    capture_status: dict[str, str] = field(default_factory=dict)
    recording_settings: dict = field(default_factory=dict)

    @property
    def capture_directory(self) -> Path:
        return self.directory.parent if self.directory.name.startswith("segment_") else self.directory

    @property
    def epoch_name(self) -> str:
        return (f"{self.capture_directory.name}/{self.directory.name}"
                if self.capture_directory != self.directory else self.directory.name)


def _read_key_values(path: Path) -> dict[str, str]:
    return dict(line.strip().split("=", 1) for line in path.read_text(
        encoding="utf-8-sig").splitlines() if "=" in line and not line.lstrip().startswith("#"))


def _positive_number(metadata: dict[str, str], key: str, *, integer: bool = False):
    value = float(metadata[key])
    if not np.isfinite(value) or value <= 0 or (integer and value != int(value)):
        raise ValueError(f"WILDX NP {key} must be a positive {'integer' if integer else 'number'}")
    return int(value) if integer else value


def find_wildx_np_recording_directories(basepath: Path) -> list[Path]:
    """Recursively find stream markers, including failed attempts without AP.

    Capture names are labels, not a format test; NP_SESSION and WILDX_SESSION
    are both accepted. Directory links are not followed.
    """
    result = []
    for root, directories, files in os.walk(Path(basepath), followlinks=False):
        directories.sort()
        if (set(files) & {"neuropixels_ap.dat", "neuropixels_probes.txt", "neuropixels_capture_status.txt"}
                or any(re.fullmatch(r"neuropixels_probe\d+_metadata\.json", name) for name in files)):
            result.append(Path(root))
    return sorted(result)


def has_wildx_np_marker(basepath: Path) -> bool:
    return bool(find_wildx_np_recording_directories(basepath))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _evidence(path: Path) -> dict:
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _local_file(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or Path(name).name != name:
        raise ValueError(f"Expected a segment-local evidence filename: {name!r}")
    return directory / name


def _startup_probes(directory: Path, ports: list[int]) -> list[dict]:
    """Read this segment's device-confirmed request, never another segment's identity.

    The recording writer's per-probe manifest binds the request to a matching
    firmware ID/CRC/verification before capture release. These are receipt-reported
    hashes, not hashes recomputed from the JSON or IMRO file. File SHA256 values
    below preserve the exact evidence used by this reader.
    """
    receipt_path = directory / "requested-configuration-applied-receipts.txt"
    lines = receipt_path.read_text(encoding="utf-8-sig").splitlines()
    receipts = {}
    for line in lines:
        match = re.fullmatch(r"P(\d+): applied; ID=([0-9a-fA-F]{64}); CRC32=([0-9a-fA-F]{8}); verification=(\d+)", line.strip())
        if match:
            port = int(match[1])
            if port in receipts:
                raise ValueError(f"Duplicate startup receipt for port {port}: {directory}")
            receipts[port] = (match[2].lower(), match[3].lower(), int(match[4]))
    if set(receipts) != set(ports):
        raise ValueError(f"Startup applied receipts do not cover saved physical ports: {directory}")
    probes = []
    for port in ports:
        manifest_path = directory / f"probe_{port}.json"
        manifest = _json(manifest_path)
        config_id, crc, verification = receipts[port]
        if (manifest.get("schema_version") != 1 or manifest.get("probe") != port
                or manifest.get("active") is not True
                or manifest.get("configuration_state") != "device_confirmed_requested"
                or manifest.get("device_receipt_file") != receipt_path.name
                or verification != 3):
            raise ValueError(f"Missing device-confirmed startup configuration: {manifest_path}")
        request_path = _local_file(directory, manifest["requested_configuration_file"])
        request = _json(request_path)
        if (request.get("SchemaVersion") != 1 or request.get("Numbering") != "zero-based"
                or request.get("Profile") != "Np1" or request.get("Connector") != port
                or request.get("MappingId") != "imec-np1-phaseiii-v2-zero-based-v1"):
            raise ValueError(f"Unsupported NP1 startup configuration: {request_path}")
        imro_path = _local_file(directory, manifest["imro_file"])
        if (manifest.get("imro_state") != "device_confirmed_requested"
                or manifest.get("imro_origin") != "exact_imported_imro"
                or base64.b64decode(request["OriginalImro"], validate=True) != imro_path.read_bytes()):
            raise ValueError(f"IMRO is not bound to the confirmed startup request: {imro_path}")
        channels = []
        for row in request["Channels"]:
            # Other reference encodings need their writer contract before support.
            if row["Reference"] != "External" or row["Shank"] != 0:
                raise ValueError(f"Unsupported NP1 startup reference/shank: {request_path}")
            channels.append({"output_channel": row["Channel"], "site": row["Site"],
                             "connected": row["Site"] is not None,
                             "standby": row["Standby"], "high_pass": row["HighPass"],
                             "reference": 0, "ap_gain_index": GAIN_VALUES.index(row["ApGain"]),
                             "lfp_gain_index": GAIN_VALUES.index(row["LfpGain"])})
        probes.append({"physical_port": port,
                       "identity": {"model": None, "part": None, "serial_hex": None,
                                    "source": "unavailable in startup configuration evidence"},
                       "geometry_profile": "Neuropixels 1.0",
                       "configuration": {"state": "applied", "channels": channels,
                                         "configuration_id_sha256": config_id,
                                         "selection_crc32": "0x" + crc,
                                         "verification_level": verification},
                       "configuration_evidence": "startup device-confirmed request; firmware base readback / shank ACK",
                       "evidence_files": [_evidence(path) for path in
                                          (receipt_path, manifest_path, request_path, imro_path)]})
    return probes


def _validate_probe(probe: dict, directory: Path) -> None:
    configuration = probe["configuration"]
    if configuration.get("state") != "applied":
        raise ValueError(f"No applied NP configuration: {directory}")
    channels = configuration["channels"]
    ids = [row["output_channel"] for row in channels]
    if (any(type(ch) is not int for ch in ids) or sorted(ids) != list(range(CHANNELS_PER_PROBE))):
        raise ValueError(f"Each NP1 hardware output channel must appear once: {directory}")
    for row in channels:
        site = row["site"]
        if site is not None and (type(site) is not int or not 0 <= site < 960
                                 or site % CHANNELS_PER_PROBE != row["output_channel"]):
            raise ValueError(f"Invalid NP1 site/output-channel mapping: {directory}: {row}")
        if any(type(row[key]) is not bool for key in ("connected", "standby", "high_pass")):
            raise ValueError(f"Invalid NP channel flags: {directory}")
        if row["connected"] and not row["standby"] and site is None:
            raise ValueError(f"Connected NP channel has no site: {directory}")
        if any(type(row[key]) is not int or not 0 <= row[key] < len(GAIN_VALUES)
               for key in ("ap_gain_index", "lfp_gain_index")):
            raise ValueError(f"Invalid NP1 hardware gain index: {directory}")
    configuration["channels"] = sorted(channels, key=lambda row: row["output_channel"])
    port = probe["physical_port"]
    if type(port) is not int or port <= 0:
        raise ValueError(f"Invalid physical NP port: {directory}")


def read_wildx_np_recording(directory: Path) -> WildxNpRecording | None:
    """Read saved AP counts. Empty attempts are not sorting epochs.

    A data-bearing segment with ambiguous structure or continuity fails closed;
    complete=False alone does not reject a structurally intact saved prefix.
    """
    directory = Path(directory)
    ap_path = directory / "neuropixels_ap.dat"
    if not ap_path.exists() or ap_path.stat().st_size == 0:
        return None
    metadata_path = directory / "neuropixels_probes.txt"
    metadata = _read_key_values(metadata_path)
    if (metadata.get("dat_layout") != "merged"
            or metadata.get("merged_channel_order") != "ascending physical probe; 384 contiguous channels per probe"
            or metadata.get("physical_ports_known") != "True"):
        raise ValueError(f"Unsupported WILD-NP saved channel layout: {metadata_path}")
    codes = metadata.get("codes")
    if codes == SIGNED_CODES:
        if (metadata.get("sample_transform_version") != "1"
                or metadata.get("sample_transform") != "512 - raw10"
                or metadata.get("sample_range") != "-511..512"):
            raise ValueError(f"Inconsistent signed NP count transform: {metadata_path}")
    elif codes != LEGACY_CODES:
        raise ValueError(f"Unsupported WILD-NP voltage storage: {metadata_path}")
    if metadata.get("complete") not in {"True", "False"}:
        raise ValueError(f"Unknown capture completion state: {metadata_path}")
    n_channels = _positive_number(metadata, "dat_channel_count", integer=True)
    n_probes = _positive_number(metadata, "probe_count", integer=True)
    mask = int(metadata["probe_mask"])
    if mask <= 0 or mask > 15:
        raise ValueError(f"Unsupported physical probe mask: {metadata_path}")
    ports = [port for port in range(1, 5) if mask & (1 << (port - 1))]
    if len(ports) != n_probes or n_channels != n_probes * CHANNELS_PER_PROBE:
        raise ValueError(f"NP probe mask/count and DAT width disagree: {directory}")
    probes = []
    receipt_paths = sorted(directory.glob("neuropixels_probe*_metadata.json"))
    if receipt_paths:
        for path in receipt_paths:
            probe = _json(path)
            if probe.get("format") != RECEIPT_FORMAT or probe.get("format_version") != 1:
                raise ValueError(f"Unsupported applied NP receipt: {path}")
            identity = probe["identity"]
            if identity.get("model") != "Neuropixels 1.0" or identity.get("part") != NP1_PART:
                raise ValueError(f"Unsupported NP geometry: {path}")
            probe["configuration_evidence"] = "post-stop applied firmware receipt"
            probe["evidence_files"] = [_evidence(path)]
            probes.append(probe)
    else:
        probes = _startup_probes(directory, ports)
    for probe in probes:
        _validate_probe(probe, directory)
    probes.sort(key=lambda probe: probe["physical_port"])
    if [p["physical_port"] for p in probes] != ports:
        raise ValueError(f"Applied NP configuration does not cover saved physical ports: {directory}")
    status_path = directory / "neuropixels_capture_status.txt"
    status = _read_key_values(status_path)
    for key, expected in (("output_dat_layout", "merged"), ("output_dat_channel_count", str(n_channels)),
                          ("probe_mask", str(mask)), ("output_ap_sample_rate_hz", metadata["output_ap_sample_rate_hz"])):
        if status.get(key) != expected:
            raise ValueError(f"Capture and stream contracts disagree: {directory}: {key}")
    if status.get("complete") != metadata["complete"]:
        raise ValueError(f"Capture and stream completion states disagree: {directory}")
    for key in ("frame_errors", "counter_errors", "usb_sequence_gaps", "firmware_recording_fault"):
        if status.get(key) != "0":
            raise ValueError(f"NP saved continuity is unverified: {directory}: {key}={status.get(key)}")
    for port in ports:
        for metric in ("frame_errors", "counter_errors", "relocks"):
            key = f"probe{port}.{metric}"
            if metadata.get(key) != "0":
                raise ValueError(f"NP segment has unlocated continuity errors: {directory}: {key}={metadata.get(key)}")
    fs = _positive_number(metadata, "output_ap_sample_rate_hz")
    if "output_lfp_rate_numerator" in metadata:
        lfp_fs = (_positive_number(metadata, "output_lfp_rate_numerator", integer=True)
                  / _positive_number(metadata, "output_lfp_rate_denominator", integer=True))
        if not np.isclose(lfp_fs, _positive_number(metadata, "output_lfp_sample_rate_hz"), rtol=0, atol=1e-6):
            raise ValueError(f"LFP rational and display rates disagree: {directory}")
    else:
        lfp_fs = _positive_number(metadata, "output_lfp_sample_rate_hz")
    samples = _positive_number(metadata, "merged_ap_output_rows", integer=True)
    lfp_samples = int(metadata["merged_lfp_output_rows"])
    if lfp_samples < 0:
        raise ValueError(f"Negative LFP row count: {directory}")
    lfp_path = directory / "neuropixels_lfp.dat"
    for path, count in ((ap_path, samples), (lfp_path, lfp_samples)):
        if path.exists() and path.stat().st_size != count * n_channels * 2:
            raise ValueError(f"NP file length differs from complete saved rows: {path}")
    settings_path = directory / "recording_settings.json"
    settings = _json(settings_path) if settings_path.exists() else {}
    return WildxNpRecording(directory, ap_path, lfp_path if lfp_path.exists() else None,
                            fs, lfp_fs, n_channels, samples, lfp_samples, tuple(probes), metadata,
                            status, settings)


def recording_order_key(recording: WildxNpRecording) -> tuple:
    start = recording.recording_settings.get("recording_start_time_utc_host")
    if start:
        return (0, datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp(), str(recording.directory))
    return (1, str(recording.capture_directory), str(recording.directory))


def discover_wildx_np_recordings(basepath: Path, ignore_folders=()) -> tuple[list[WildxNpRecording], list[dict]]:
    recordings, excluded = [], []
    for directory in find_wildx_np_recording_directories(basepath):
        reason = None
        ap_path = directory / "neuropixels_ap.dat"
        if any(token.lower() in str(directory).lower() for token in ignore_folders):
            reason = "ignored_folder"
        elif not ap_path.exists():
            reason = "missing_ap_file"
        elif ap_path.stat().st_size == 0:
            reason = "empty_ap_file"
        if reason:
            status_path = directory / "neuropixels_capture_status.txt"
            excluded.append({"directory": str(directory), "reason": reason,
                             "capture_status": _read_key_values(status_path) if status_path.exists() else {}})
            continue
        if (directory / "amplifier.dat").exists() or (directory / "continuous.dat").exists():
            raise ValueError(f"Ambiguous acquisition formats in {directory}")
        recordings.append(read_wildx_np_recording(directory))
    return sorted(recordings, key=recording_order_key), excluded


def recorded_probe_assignments(recording: WildxNpRecording) -> list[dict]:
    """One GUI/XML group per saved physical probe, spaced by 2000 micrometres."""
    ports = sorted(probe["physical_port"] for probe in recording.probes)
    return [{"type": NP1_GEOMETRY_NAME, "groups": [index], "x_offset": index * 2000}
            for index, _port in enumerate(ports)]


def channel_map_data(
    recording: WildxNpRecording, reject_channels: list[int] = (),
    *, probe_assignments: list[dict] | None = None,
) -> dict:
    """Join (physical port, hardware output channel) to sites and saved columns."""
    assignments = recorded_probe_assignments(recording)
    if probe_assignments:
        from .io import _normalize_chanmap_layout

        groups = []
        offsets_by_group = {}
        for assignment in probe_assignments:
            if _normalize_chanmap_layout(assignment.get("type")) != NP1_GEOMETRY_NAME:
                raise ValueError("This recording uses Neuropixels 1.0; select that geometry for every probe")
            offset = float(assignment.get("x_offset", 0))
            if not np.isfinite(offset):
                raise ValueError("NP probe x offsets must be finite micrometre values")
            assigned_groups = [int(group) for group in assignment.get("groups", [])]
            groups.extend(assigned_groups)
            offsets_by_group.update({group: offset for group in assigned_groups})
        if sorted(groups) != list(range(len(assignments))):
            raise ValueError("NP channel groups must cover each recorded probe exactly once")
        for group, assignment in enumerate(assignments):
            assignment["x_offset"] = offsets_by_group[group]
    ports = sorted(probe["physical_port"] for probe in recording.probes)
    offsets_by_port = {port: assignments[group]["x_offset"] for group, port in enumerate(ports)}
    geometry = np1_site_geometry()
    n = recording.num_channels
    ids = np.arange(n, dtype=np.int64)
    x = np.full(n, np.nan)
    y = np.full(n, np.nan)
    sites = np.full(n, -1, dtype=np.int64)
    connected = np.zeros(n, dtype=bool)
    probe_ids = np.empty(n, dtype=np.int64)
    hardware_ids = np.empty(n, dtype=np.int64)
    reasons = np.empty(n, dtype=object)
    rejected = set(int(ch) for ch in reject_channels)
    if any(ch < 0 or ch >= n for ch in rejected):
        raise ValueError("Rejected WILDX NP channel is outside the saved binary width")
    for probe_index, probe in enumerate(recording.probes):
        for row in probe["configuration"]["channels"]:
            hardware = row["output_channel"]
            column = probe_index * CHANNELS_PER_PROBE + hardware
            site = row["site"]
            probe_ids[column] = probe["physical_port"]
            hardware_ids[column] = hardware
            if site is not None:
                sites[column] = site
                x[column] = geometry["xcoords"][site] + offsets_by_port[probe["physical_port"]]
                y[column] = geometry["ycoords"][site]
            reason = []
            if not row["connected"]:
                reason.append("disconnected")
            if row["standby"]:
                reason.append("standby")
            if site is None:
                reason.append("missing_site")
            elif geometry["is_reference"][site]:
                reason.append("reference_site")
            if column in rejected:
                reason.append("manual_reject")
            reasons[column] = ";".join(reason)
            connected[column] = not reason
    return {"chanMap": (ids + 1).reshape(-1, 1), "chanMap0ind": ids.reshape(-1, 1),
            "connected": connected.reshape(-1, 1), "xcoords": x.reshape(-1, 1),
            "ycoords": y.reshape(-1, 1), "kcoords": np.ones((n, 1), dtype=np.int64),
            "probe_ids": probe_ids.reshape(-1, 1), "site_ids": sites.reshape(-1, 1),
            "hardware_channel_ids": hardware_ids.reshape(-1, 1),
            "bad_channel_reason": reasons.reshape(-1, 1),
            "fs": float(recording.sampling_frequency), "recording_format": "wildx_np",
            "geometry_profile": NP1_GEOMETRY_NAME, "probe_assignments_json": json.dumps(assignments)}


def nominal_gain_to_uV(recording: WildxNpRecording, stream: str) -> float:
    """Uncalibrated NP1 ADC transfer, using the receipt's applied gain indices.

    Open Ephys Neuropixels1.cpp at the commit cited in the geometry catalog defines the gain
    table (lines 84-100) and 1.2 V / 1024 / gain conversion (lines 471-484).
    This supplies a nominal count scale, not per-channel calibration or a DC
    zero point. A single scalar output scale requires uniform applied gains.
    """
    if stream not in {"ap", "lfp"}:
        raise ValueError(f"Unknown NP stream: {stream}")
    gains = GAIN_VALUES
    key = "ap_gain_index" if stream == "ap" else "lfp_gain_index"
    indices = {row[key] for probe in recording.probes
               for row in probe["configuration"]["channels"]
               if row["connected"] and not row["standby"] and row["site"] not in {191, 575, 959}}
    if (len(indices) != 1 or any(type(index) is not int or not 0 <= index < len(gains)
                                 for index in indices)):
        raise ValueError(f"WILDX NP {stream} requires uniform valid gain indices for scalar output scaling")
    return 1.2e6 / 1024. / gains[next(iter(indices))]


def verified_probe_serial(probe: dict) -> str | None:
    identity = probe["identity"]
    serial = identity.get("serial_hex")
    if (identity.get("reason") == "ok" and isinstance(serial, str)
            and re.fullmatch(r"0x[0-9a-fA-F]{16}", serial) and int(serial, 16) != 0):
        return serial.lower()
    return None


def session_recordings(paths: list[Path]) -> list[WildxNpRecording]:
    """Validate one common saved-column contract before concatenating epochs."""
    recordings = [read_wildx_np_recording(Path(path).parent)
                  if Path(path).name == "neuropixels_ap.dat" else None for path in paths]
    if not any(recording is not None for recording in recordings):
        return []
    if any(recording is None for recording in recordings):
        raise ValueError("Mixing WILD-NP and other/empty acquisition inputs is unsupported")
    if [r.directory for r in recordings] != [r.directory for r in sorted(recordings, key=recording_order_key)]:
        raise ValueError("WILD-NP epochs must remain in recording order")
    first = recordings[0]
    def contract(recording):
        return (recording.sampling_frequency, recording.lfp_sampling_frequency, recording.num_channels,
                recording.metadata["codes"],
                [(p["physical_port"], p["configuration"]["configuration_id_sha256"].lower(),
                  p["configuration"]["selection_crc32"].lower(), p["configuration"]["channels"])
                 for p in recording.probes])
    expected = contract(first)
    serials = {}
    for recording in recordings:
        if contract(recording) != expected:
            raise ValueError(f"NP stream, gain/reference or site mapping differs between epochs: {recording.directory}")
        for probe in recording.probes:
            port = probe["physical_port"]
            serial = verified_probe_serial(probe)
            if serial:
                if port in serials and serials[port] != serial.lower():
                    raise ValueError(f"NP identity differs at physical port {port}: {recording.directory}")
                serials[port] = serial.lower()
    return recordings


def epoch_metadata(recordings: list[WildxNpRecording]) -> list[dict]:
    """MAT-compatible provenance using zero-based, half-open AP intervals."""
    rows, start = [], 0
    for recording in recordings:
        stop = start + recording.sample_count
        capture = recording.capture_directory
        # Preserve the actual capture label, including experiment-specific labels.
        match = re.match(r"(?:NP|WILDX)_SESSION_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_\d+_[^_]+(?:_(.*))?$", capture.name)
        label = (match[1] or "") if match else capture.name
        rows.append({"name": recording.epoch_name, "capture": str(capture),
                     "segment": str(recording.directory), "captureLabel": label,
                     "sourceFile": str(recording.ap_path), "sourceStartSample": 0,
                     "sourceStopSample": recording.sample_count,
                     "startSample": start, "stopSample": stop,
                     "startTime": start / recording.sampling_frequency,
                     "stopTime": stop / recording.sampling_frequency,
                     "complete": recording.metadata["complete"] == "True",
                     "interrupted": recording.metadata["complete"] != "True",
                     "failure": recording.capture_status.get("failure", "unknown"),
                     "configurationEvidence": "; ".join(p["configuration_evidence"] for p in recording.probes),
                     "probeIdentityVerified": all(verified_probe_serial(p) is not None for p in recording.probes)})
        start = stop
    return rows


def _host_timing(recording: WildxNpRecording) -> dict:
    path = recording.capture_directory / "session_events.csv"
    events = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            events = [row for row in csv.DictReader(handle)
                      if row.get("folder", "").replace("\\", "/").rsplit("/", 1)[-1] == recording.directory.name]
    first = next((row.get("current_first_or_last_host_receive_utc") for row in events
                  if row.get("event") == "first_host_receive"), None)
    last = next((row["current_first_or_last_host_receive_utc"] for row in reversed(events)
                 if row.get("current_first_or_last_host_receive_utc") not in {None, "", "unknown"}), None)
    return {"recording_start_utc_host": recording.recording_settings.get("recording_start_time_utc_host"),
            "first_host_receive_utc": first, "last_host_receive_utc": last,
            "events_file": str(path) if path.exists() else None, "events": events,
            "time_dat_file": str(recording.directory / "time.dat"),
            "time_dat_dtype": "<u4", "time_dat_rows": "LFP rows only",
            "time_dat_units": "local PC milliseconds of day",
            "time_metadata": {k: v for k, v in recording.metadata.items()
                              if k.startswith("time.dat.") or k.startswith("lfp_time_")},
            "ap_sample_time_model": None, "hardware_synchronization_verified": False}


def ensure_separate_output(output_dir: Path, source_basepath: Path) -> None:
    if Path(output_dir).resolve().is_relative_to(Path(source_basepath).resolve()):
        raise ValueError("WILD-NP outputs must be outside the selected raw recording directory")


def _recorded_lfp_metadata(recordings: list[WildxNpRecording], lfp_fs: float) -> dict:
    """Describe the derived LF binary, including the exact per-segment grid."""
    from fractions import Fraction

    def saved_rate(recording: WildxNpRecording) -> Fraction:
        metadata = recording.metadata
        if "output_lfp_rate_numerator" in metadata:
            return Fraction(int(metadata["output_lfp_rate_numerator"]),
                            int(metadata["output_lfp_rate_denominator"]))
        rate = recording.lfp_sampling_frequency
        if not float(rate).is_integer():
            raise ValueError("Non-integer NP LF input requires an exact numerator/denominator")
        return Fraction(int(rate), 1)

    first = recordings[0]
    source_rate = saved_rate(first)
    output_rate = float(lfp_fs)
    if not output_rate.is_integer() or output_rate <= 900 or float(source_rate) <= 900:
        raise ValueError("NP LFP output requires an integer rate and input/output rates above 900 Hz for the 450 Hz low-pass")
    if any(saved_rate(recording) != source_rate for recording in recordings):
        raise ValueError("NP segments have different exact LF sample rates")
    ratio = Fraction(int(output_rate), 1) / source_rate
    source_gain = nominal_gain_to_uV(first, "lfp")
    output_gain = nominal_gain_to_uV(first, "ap")
    source_counts = [recording.lfp_sample_count for recording in recordings]
    output_counts = [(count * ratio.numerator + ratio.denominator - 1) // ratio.denominator
                     for count in source_counts]
    source_edges = np.r_[0, np.cumsum(source_counts)]
    output_edges = np.r_[0, np.cumsum(output_counts)]
    return {
        "format": "WILDX NP derived LFP", "format_version": 1,
        "source": "recorded WILDX NP LF", "dtype": "<i2", "num_channels": first.num_channels,
        "sampling_frequency": output_rate, "source_sampling_frequency": float(source_rate),
        "source_rate_numerator": source_rate.numerator, "source_rate_denominator": source_rate.denominator,
        "resample_up": ratio.numerator, "resample_down": ratio.denominator,
        "lowpass": {"type": "Butterworth", "order": 5, "cutoff_hz": 450.,
                    "direction": "forward-backward", "intermediate_dtype": "float32"},
        "resample": {"method": "polyphase FIR", "window": ["kaiser", 5.],
                     "half_length": 10 * max(ratio.numerator, ratio.denominator),
                     "padtype": "reflect", "processing_overlap_ms": 100.},
        "gain_to_uV": output_gain, "source_gain_to_uV": source_gain,
        "count_scale_factor": source_gain / output_gain,
        "binary_units": "AP-equivalent counts", "source_binary_units": "ADC counts",
        "conversion_applied_to_binary": True, "microvolt_conversion_applied_to_binary": False,
        "integer_conversion": "round to nearest even; reject int16 overflow",
        "gain_calibration_applied": False, "adc_calibration_status": "unknown",
        "source_adc_zero_code": 0 if first.metadata["codes"] == SIGNED_CODES else None,
        "time_origin": "first saved LF row in each segment", "ap_alignment_verified": False,
        "source_files": [str(recording.lfp_path) if recording.lfp_path else None for recording in recordings],
        "epoch_names": [recording.epoch_name for recording in recordings],
        "source_sample_counts": source_counts, "sample_counts": output_counts,
        "source_sample_intervals": [[0, count] for count in source_counts],
        "source_concatenated_sample_intervals": np.column_stack((source_edges[:-1], source_edges[1:])).tolist(),
        "concatenated_sample_intervals": np.column_stack((output_edges[:-1], output_edges[1:])).tolist(),
        "sample_interval_convention": "zero-based half-open",
        "output_length_rule": "ceil(source_samples * up / down) independently per segment",
        "sample_index_mapping": "source_position = local_output_sample * down / up",
        "ap_time_axis_resampling_applied": False,
    }


def prepare_session_metadata(
    recordings: list[WildxNpRecording], *, output_dir: Path, basename: str,
    reject_channels: list[int], overwrite: bool,
    source_basepath: Path | None = None, ignore_folders=(), lfp_fs: float = 1250.,
    probe_assignments: list[dict] | None = None,
) -> tuple[Path, Path]:
    """Write local XML and chanMap from applied settings without source edits."""
    import xml.etree.ElementTree as ET
    from scipy.io import loadmat
    from .io import atomic_savemat, atomic_write_json, atomic_write_path, save_cell_explorer_chan_coords

    if not recordings:
        raise ValueError("No data-bearing WILD-NP epochs were selected")
    first = recordings[0]
    lfp_metadata = _recorded_lfp_metadata(recordings, lfp_fs)
    for source in ([source_basepath] if source_basepath is not None else [r.directory for r in recordings]):
        ensure_separate_output(output_dir, source)
    mapping = channel_map_data(first, reject_channels, probe_assignments=probe_assignments)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    chanmap_path = output_dir / "chanMap.mat"
    if chanmap_path.exists() and not overwrite:
        saved = loadmat(chanmap_path, simplify_cells=True)
        keys = ("chanMap0ind", "connected", "xcoords", "ycoords", "kcoords", "probe_ids", "site_ids", "hardware_channel_ids")
        if any(key not in saved or not np.array_equal(
                np.asarray(saved[key]).reshape(-1), np.asarray(mapping[key]).reshape(-1), equal_nan=True)
               for key in keys):
            raise ValueError(f"Existing WILDX NP chanMap disagrees with applied settings: {chanmap_path}")
    else:
        atomic_savemat(chanmap_path, mapping, required_key="chanMap")
    save_cell_explorer_chan_coords(
        chanmap_data=mapping, output_dir=output_dir, basename=basename,
        source="WILDX NP1 applied sites with configured probe x offsets", overwrite=overwrite)
    root = ET.Element("parameters")
    general = ET.SubElement(root, "generalInfo")
    ET.SubElement(general, "description").text = f"WILDX {NP1_GEOMETRY_NAME} recorded-site channel groups"
    acquisition = ET.SubElement(root, "acquisitionSystem")
    for key, value in (("nChannels", first.num_channels), ("samplingRate", first.sampling_frequency),
                       ("nBits", 16)):
        ET.SubElement(acquisition, key).text = str(value)
    field_potentials = ET.SubElement(root, "fieldPotentials")
    ET.SubElement(field_potentials, "lfpSamplingRate").text = str(lfp_metadata["sampling_frequency"])
    ports = np.asarray(mapping["probe_ids"]).reshape(-1)
    connected = np.asarray(mapping["connected"]).reshape(-1)
    for section in ("anatomicalDescription", "spikeDetection"):
        groups = ET.SubElement(ET.SubElement(root, section), "channelGroups")
        for port in sorted(set(ports.tolist())):
            channels = np.flatnonzero(ports == port)
            if section == "spikeDetection":
                channels = channels[connected[channels]]
            if channels.size == 0:
                continue
            group = ET.SubElement(groups, "group")
            channel_nodes = ET.SubElement(group, "channels")
            for column in channels:
                attributes = {"skip": "0" if connected[column] else "1"}
                ET.SubElement(channel_nodes, "channel", attributes).text = str(int(column))
    ET.indent(root)
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    xml_path = output_dir / f"{basename}.xml"
    if xml_path.exists() and not overwrite:
        if xml_path.read_bytes() != xml_bytes:
            raise ValueError(f"Existing WILDX NP XML disagrees with applied settings: {xml_path}")
    else:
        atomic_write_path(xml_path, lambda path: path.write_bytes(xml_bytes), validator=ET.parse)
    sources = []
    previous_host_end = None
    for recording, epoch in zip(recordings, epoch_metadata(recordings), strict=True):
        timing = _host_timing(recording)
        host_gap = None
        if previous_host_end and timing["first_host_receive_utc"]:
            try:
                host_gap = (datetime.fromisoformat(timing["first_host_receive_utc"].replace("Z", "+00:00"))
                            - datetime.fromisoformat(previous_host_end.replace("Z", "+00:00"))).total_seconds()
            except ValueError:
                pass
        previous_host_end = timing["last_host_receive_utc"]
        sources.append({"directory": str(recording.directory), "ap_file": str(recording.ap_path),
                        "lfp_file": str(recording.lfp_path) if recording.lfp_path else None,
                        "ap_samples": recording.sample_count, "lfp_samples": recording.lfp_sample_count,
                        "epoch": epoch, "host_timing": timing,
                        "host_observed_gap_before_seconds": host_gap,
                        "gap_is_hardware_sample_gap": False,
                        "stream_metadata": recording.metadata, "capture_status": recording.capture_status,
                        "probes": list(recording.probes)})
    excluded = []
    if source_basepath is not None:
        included = {r.directory for r in recordings}
        for directory in find_wildx_np_recording_directories(source_basepath):
            if directory in included:
                continue
            ap_path = directory / "neuropixels_ap.dat"
            reason = ("ignored_folder" if any(t.lower() in str(directory).lower() for t in ignore_folders)
                      else "missing_ap_file" if not ap_path.exists()
                      else "empty_ap_file" if ap_path.stat().st_size == 0 else "not_selected")
            status_path = directory / "neuropixels_capture_status.txt"
            excluded.append({"directory": str(directory), "reason": reason,
                             "capture_status": _read_key_values(status_path) if status_path.exists() else {}})
    signed = first.metadata["codes"] == SIGNED_CODES
    payload = {
        "format": "WILDX NP preprocessing input", "format_version": 3,
        "geometry_profile": NP1_GEOMETRY_NAME,
        "probe_assignments": json.loads(mapping["probe_assignments_json"]),
        "probe_coordinate_frame": "NP1 site coordinates plus configured probe x offsets in um",
        "source_type": "wildx_np", "output_ap_file": f"{basename}.dat", "dtype": "<i2", "storage_bits": 16, "adc_bits": 10,
        "num_channels": first.num_channels, "sorting_channel_count": int(connected.sum()),
        "sampling_frequency": first.sampling_frequency,
        "lfp_sampling_frequency": lfp_metadata["sampling_frequency"],
        "source_lfp_sampling_frequency": lfp_metadata["source_sampling_frequency"],
        "ap_gain_to_uV": nominal_gain_to_uV(first, "ap"),
        "lfp_gain_to_uV": lfp_metadata["gain_to_uV"],
        "source_lfp_gain_to_uV": lfp_metadata["source_gain_to_uV"],
        "lfp_output_contract": lfp_metadata,
        "hardware_gains": [{"physical_port": p["physical_port"],
                            "ap": sorted({GAIN_VALUES[r["ap_gain_index"]] for r in p["configuration"]["channels"]}),
                            "lfp": sorted({GAIN_VALUES[r["lfp_gain_index"]] for r in p["configuration"]["channels"]})}
                           for p in first.probes],
        "nominal_conversion_formula": "uV/count = 1.2e6 / 1024 / amplifier_gain",
        "binary_units": "ADC counts (filtered/referenced counts if preprocessing enabled)",
        "conversion_application": "AP gain metadata only; derived LF resampled and normalized to AP storage units",
        "saved_transform": "512 - raw10" if signed else "raw10",
        "reader_transform": "none", "adc_count_range": [-511, 512] if signed else [0, 1023],
        "adc_zero_code": 0 if signed else None, "gain_calibration_applied": False,
        "adc_calibration_status": "unknown from saved metadata", "amplitude_scale": "nominal, not probe-calibrated",
        "sample_interval_convention": "zero-based, half-open [start, stop)",
        "time_axis": "concatenated saved AP samples / AP sampling frequency; real gaps omitted",
        "pc_time_required": False, "ap_lfp_alignment_verified": False,
        "lfp_time_origin": "first saved LF row in each segment; source and resampled LF ranges in lfp_output_contract",
        "boundary_policy": {"preprocess_filter": "independent segment and probe views before concatenation",
                            "sorter_filter": "Kilosort4 may internally filter across concatenated boundaries",
                            "sorter_spikes": "raw Phy arrays retained without automatic boundary exclusion",
                            "postprocess": "retain boundary spikes; downstream analysis chooses exclusion intervals",
                            "limitation": "filtering and sorter edge effects are not quantified"},
        "inactive_columns_0based": np.flatnonzero(~connected).tolist(),
        "sources": sources, "excluded_segments": excluded}
    metadata_path = output_dir / "wildx_np_metadata.json"
    if metadata_path.exists() and not overwrite:
        if _json(metadata_path) != payload:
            raise ValueError(f"Existing NP provenance differs from selected inputs: {metadata_path}")
    else:
        atomic_write_json(metadata_path, payload)
    return xml_path, chanmap_path


def write_recorded_lfp(
    recordings: list[WildxNpRecording], *, output_path: Path, lfp_fs: float,
    overwrite: bool, job_kwargs: dict,
) -> Path:
    """Low-pass/resample saved LF independently per segment in AP storage units."""
    from scipy import signal
    import spikeinterface.preprocessing as spre
    from .io import atomic_write_json
    from .recording import (
        _PolyphaseLfpRecording, load_subsession_recordings,
        concatenate_recordings_si, write_concatenated_dat,
    )

    first = recordings[0]
    if any(recording.lfp_path is None or recording.lfp_sample_count < 2 for recording in recordings):
        raise ValueError("Each NP segment requires a recorded LF input with at least two samples")
    metadata = _recorded_lfp_metadata(recordings, lfp_fs)
    metadata_path = output_path.with_suffix(".lfp_metadata.json")
    expected_bytes = sum(metadata["sample_counts"]) * first.num_channels * 2
    if not overwrite:
        if metadata_path.exists() and _json(metadata_path) != metadata:
            raise ValueError(f"Existing LFP processing metadata differs; use a fresh output or overwrite: {metadata_path}")
        if output_path.exists():
            if not metadata_path.exists() or output_path.stat().st_size != expected_bytes:
                raise ValueError(f"Existing LFP lacks matching processing metadata or sample count: {output_path}")
            return output_path
    inputs = load_subsession_recordings(
        [recording.lfp_path for recording in recordings],
        sampling_frequency=metadata["source_sampling_frequency"],
        num_channels=first.num_channels, dtype="<i2",
        gain_to_uV=metadata["source_gain_to_uV"], offset_to_uV=0.)
    sos = signal.iirfilter(5, 450., btype="lowpass", ftype="butter",
                          fs=metadata["source_sampling_frequency"], output="sos")
    outputs = []
    for recording in inputs:
        filtered = spre.filter(recording, coeff=sos, filter_mode="sos",
                               direction="forward-backward", dtype="float32")
        outputs.append(_PolyphaseLfpRecording(
            filtered, sampling_frequency=metadata["sampling_frequency"],
            up=metadata["resample_up"], down=metadata["resample_down"],
            scale_factor=metadata["count_scale_factor"]))
    write_concatenated_dat(
        recording=concatenate_recordings_si(outputs), output_dat_path=output_path,
        dtype="int16", overwrite=overwrite, job_kwargs=job_kwargs)
    atomic_write_json(metadata_path, metadata)
    return output_path


def load_output_metadata(dat_path: Path | None, *, lfp_path: Path | None = None) -> dict | None:
    if dat_path is None:
        return None
    path = Path(dat_path).parent / "wildx_np_metadata.json"
    if not path.exists():
        return None
    metadata = _json(path)
    if metadata.get("format") != "WILDX NP preprocessing input" or metadata.get("format_version") != 3:
        raise ValueError(f"Unsupported NP output provenance: {path}")
    if Path(dat_path).name != metadata.get("output_ap_file"):
        return None
    count = sum(source["ap_samples"] for source in metadata["sources"])
    if Path(dat_path).stat().st_size != count * metadata["num_channels"] * 2:
        raise ValueError(f"NP output length differs from its sample mapping: {dat_path}")
    if lfp_path is not None:
        lfp_path = Path(lfp_path)
        contract = metadata["lfp_output_contract"]
        if (_json(lfp_path.with_suffix(".lfp_metadata.json")) != contract
                or lfp_path.stat().st_size != sum(contract["sample_counts"]) * metadata["num_channels"] * 2):
            raise ValueError(f"NP LFP differs from its processing metadata or sample mapping: {lfp_path}")
    return metadata
