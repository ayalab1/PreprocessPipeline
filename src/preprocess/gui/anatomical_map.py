from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np


class AnatomicalMapError(ValueError):
    """Raised when an anatomical map cannot be parsed or generated."""


@dataclass(frozen=True)
class AnatomicalChannel:
    channel: int
    x: float
    y: float


@dataclass(frozen=True)
class AnatomicalChannelGroup:
    group_id: int
    channels: tuple[AnatomicalChannel, ...]


def channel_groups_from_chanmap_data(
    data: dict[str, Any],
    *,
    anatomical_groups_0based: list[list[int]] | None = None,
) -> list[AnatomicalChannelGroup]:
    """Keep recorded channel order for CSV cells and use chanMap coordinates.

    WILD-NP groups follow physical probe IDs and include every recorded column.
    Inactive NP channels without a site retain their CSV row but are not drawn.
    Other recordings use XML groups or the existing kcoords grouping.
    """
    try:
        x = np.asarray(data["xcoords"], dtype=float).reshape(-1)
        y = np.asarray(data["ycoords"], dtype=float).reshape(-1)
        device_ch = np.asarray(
            data["chanMap0ind"] if "chanMap0ind" in data else np.asarray(data["chanMap"]) - 1,
            dtype=float,
        ).reshape(-1)
    except (KeyError, TypeError, ValueError) as exc:
        raise AnatomicalMapError(f"Invalid chanMap coordinates or channel IDs: {exc}") from exc
    if len(x) != len(y) or len(x) != len(device_ch):
        raise AnatomicalMapError("chanMap coordinates and channel IDs must have equal lengths.")
    if not np.all(np.isfinite(device_ch) & (device_ch >= 0) & (device_ch == np.floor(device_ch))):
        raise AnatomicalMapError("chanMap channel IDs must be nonnegative integers.")
    if len(np.unique(device_ch)) != len(device_ch):
        raise AnatomicalMapError("chanMap contains duplicate channel IDs.")
    if "chanMap" in data and not np.array_equal(np.asarray(data["chanMap"]).reshape(-1) - 1, device_ch):
        raise AnatomicalMapError("chanMap and chanMap0ind channel IDs disagree.")
    is_np = str(np.asarray(data.get("recording_format", "")).reshape(-1)[0]) == "wildx_np"
    missing_inactive: set[int] = set()
    if is_np:
        try:
            connected = np.asarray(data["connected"], dtype=float).reshape(-1) > 0
            probes = np.asarray(data["probe_ids"], dtype=float).reshape(-1)
        except (KeyError, TypeError, ValueError) as exc:
            raise AnatomicalMapError(f"Invalid NP chanMap probe IDs or connected mask: {exc}") from exc
        if len(connected) != len(device_ch) or len(probes) != len(device_ch):
            raise AnatomicalMapError("NP probe IDs, connected mask and channel IDs must have equal lengths.")
        if not np.all(np.isfinite(probes) & (probes == np.floor(probes))):
            raise AnatomicalMapError("NP physical probe IDs must be finite integers.")
        missing_inactive = set(int(ch) for ch in device_ch[~connected])
    lookup = {
        int(channel): AnatomicalChannel(int(channel) + 1, float(x[index]), float(y[index]))
        for index, channel in enumerate(device_ch)
    }
    if anatomical_groups_0based is None:
        if is_np:
            # Match the generated XML: one column per port, all recorded rows.
            ordered_groups = [
                (group_id, [int(ch) for ch in device_ch[probes == port]])
                for group_id, port in enumerate(sorted(set(probes.tolist())), start=1)
            ]
        else:
            kcoords = np.asarray(data.get("kcoords", np.ones_like(x))).reshape(-1)
            if len(kcoords) != len(device_ch):
                raise AnatomicalMapError("chanMap kcoords and channel IDs must have equal lengths.")
            ordered_groups = [
                (int(group_id), [int(ch) for ch in device_ch[kcoords == group_id]])
                for group_id in sorted(set(kcoords.tolist()))
            ]
    else:
        ordered_groups = list(enumerate(anatomical_groups_0based, start=1))
    seen: set[int] = set()
    groups: list[AnatomicalChannelGroup] = []
    for group_id, ids in ordered_groups:
        channels = []
        for channel in ids:
            if channel in seen:
                raise AnatomicalMapError(f"Anatomical groups contain duplicate channel {channel} (0-based).")
            if channel not in lookup:
                raise AnatomicalMapError(f"XML channel {channel} (0-based) is missing from chanMap.")
            point = lookup[channel]
            if (not np.isfinite(point.x) or not np.isfinite(point.y)) and channel not in missing_inactive:
                raise AnatomicalMapError(f"Channel {channel} (0-based) has no finite coordinates.")
            channels.append(point)
            seen.add(channel)
        groups.append(AnatomicalChannelGroup(group_id=group_id, channels=tuple(channels)))
    return groups


def build_anatomical_map_rows(
    groups: list[AnatomicalChannelGroup],
    channel_regions: dict[int, str],
) -> list[list[str]]:
    known_channels = {channel.channel for group in groups for channel in group.channels}
    unknown = sorted(channel for channel, label in channel_regions.items() if label.strip() and channel not in known_channels)
    if unknown:
        raise AnatomicalMapError(f"Labels refer to channels outside the current XML groups: {unknown}")
    if not groups:
        return []
    max_rows = max((len(group.channels) for group in groups), default=0)
    rows: list[list[str]] = []
    for row_index in range(max_rows):
        row: list[str] = []
        for group in groups:
            if row_index < len(group.channels):
                label = channel_regions.get(group.channels[row_index].channel, "").strip()
                row.append(label)
            else:
                row.append("")
        rows.append(row)
    return rows


def build_anatomical_map_csv(
    groups: list[AnatomicalChannelGroup],
    channel_regions: dict[int, str],
) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in build_anatomical_map_rows(groups, channel_regions):
        writer.writerow(row)
    return buffer.getvalue()


def parse_anatomical_map_csv(
    text: str,
    groups: list[AnatomicalChannelGroup],
) -> dict[int, str]:
    try:
        rows = list(csv.reader(StringIO(text), strict=True))
    except csv.Error as exc:
        raise AnatomicalMapError(f"Invalid anatomical CSV: {exc}") from exc
    channel_regions: dict[int, str] = {}
    for row_index, row in enumerate(rows):
        for group_index, value in enumerate(row):
            label = value.strip()
            if group_index >= len(groups):
                if label:
                    raise AnatomicalMapError(f"CSV row {row_index + 1}, column {group_index + 1} exceeds the XML group count.")
                continue
            group = groups[group_index]
            if row_index >= len(group.channels):
                if label:
                    raise AnatomicalMapError(f"CSV row {row_index + 1}, column {group_index + 1} exceeds that XML group's channel count.")
                continue
            if label:
                channel_regions[group.channels[row_index].channel] = label
    return channel_regions


def load_anatomical_map_csv(
    path: str | Path,
    groups: list[AnatomicalChannelGroup],
) -> dict[int, str]:
    csv_path = Path(path)
    if not csv_path.exists():
        raise AnatomicalMapError(f"Anatomical map not found: {csv_path}")
    return parse_anatomical_map_csv(csv_path.read_text(encoding="utf-8"), groups)


_ATLAXIS_CHANNEL_HEADER = ("channel_id", "site_id", "shank", "region", "is_target")


def is_atlaxis_anatomical_csv(text: str) -> bool:
    """Recognize the header of an Atlaxis per-probe channel export."""
    try:
        header = next(csv.reader(StringIO(text.lstrip("\ufeff")), strict=True), [])
    except csv.Error as exc:
        raise AnatomicalMapError(f"Invalid anatomical CSV: {exc}") from exc
    return set(header) == set(_ATLAXIS_CHANNEL_HEADER)


def parse_atlaxis_anatomical_csv(
    text: str,
    group: AnatomicalChannelGroup,
    chanmap_data: dict[str, Any],
) -> dict[int, str]:
    """Map an Atlaxis NP1 export onto one recorded probe after routing checks.

    Atlaxis channel_id is a probe-local hardware output, not a DAT column.
    site_id uses s0_front_NNNN. is_target describes an anatomical target and
    does not select which channels to import. Unidentified inactive channels
    keep their CellExplorer row but receive no inferred region.
    """
    recording_format = str(np.asarray(chanmap_data.get("recording_format", "")).reshape(-1)[0])
    if recording_format != "wildx_np":
        raise AnatomicalMapError("Atlaxis channel CSV import requires a recorded WILD-NP chanMap.")
    try:
        arrays = {
            name: np.asarray(chanmap_data[name], dtype=float).reshape(-1)
            for name in ("chanMap0ind", "hardware_channel_ids", "site_ids", "probe_ids", "connected")
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise AnatomicalMapError(f"Missing or invalid NP routing metadata: {exc}") from exc
    count = len(arrays["chanMap0ind"])
    if any(len(values) != count for values in arrays.values()):
        raise AnatomicalMapError("NP routing metadata arrays must have equal lengths.")
    for name, values in arrays.items():
        if not np.all(np.isfinite(values) & (values == np.floor(values))):
            raise AnatomicalMapError(f"NP {name} must contain finite integers.")
    device_channels = arrays["chanMap0ind"].astype(int)
    if np.any(device_channels < 0) or len(np.unique(device_channels)) != count:
        raise AnatomicalMapError("NP recorded channel IDs must be unique nonnegative integers.")
    index_by_channel = {int(channel) + 1: index for index, channel in enumerate(device_channels)}
    try:
        indices = [index_by_channel[channel.channel] for channel in group.channels]
    except KeyError as exc:
        raise AnatomicalMapError(f"Selected probe channel is missing from chanMap: {exc}") from exc
    if not indices or len(set(arrays["probe_ids"][indices].tolist())) != 1:
        raise AnatomicalMapError("Select exactly one recorded physical probe for an Atlaxis CSV.")
    hardware = arrays["hardware_channel_ids"][indices].astype(int)
    sites = arrays["site_ids"][indices].astype(int)
    connected = arrays["connected"][indices].astype(int)
    if (np.any((hardware < 0) | (hardware >= 384))
            or len(np.unique(hardware)) != len(hardware)):
        raise AnatomicalMapError("The selected NP1 probe must have unique hardware channel IDs from 0 to 383.")
    if np.any((sites < -1) | (sites >= 960)) or np.any((sites < 0) & (connected != 0)):
        raise AnatomicalMapError("The selected NP1 probe has invalid or unidentified active sites.")
    recorded = {
        int(channel_id): (channel.channel, int(site))
        for channel_id, channel, site in zip(hardware, group.channels, sites)
    }
    try:
        rows = list(csv.reader(StringIO(text.lstrip("\ufeff")), strict=True))
    except csv.Error as exc:
        raise AnatomicalMapError(f"Invalid Atlaxis CSV: {exc}") from exc
    if not rows or len(rows[0]) != len(_ATLAXIS_CHANNEL_HEADER) or set(rows[0]) != set(_ATLAXIS_CHANNEL_HEADER):
        raise AnatomicalMapError("Expected Atlaxis CSV columns: channel_id,site_id,shank,region,is_target.")
    header = rows[0]
    seen: set[int] = set()
    regions: dict[int, str] = {}
    for row_number, values in enumerate(rows[1:], start=2):
        if len(values) != len(header):
            raise AnatomicalMapError(f"Atlaxis CSV row {row_number} has the wrong number of columns.")
        row = dict(zip(header, values))
        try:
            channel_id = int(row["channel_id"])
            shank = int(row["shank"])
        except ValueError as exc:
            raise AnatomicalMapError(f"Atlaxis CSV row {row_number} has an invalid channel ID or shank.") from exc
        match = re.fullmatch(r"s(\d+)_front_(\d+)", row["site_id"].strip())
        if match is None or shank != 0 or int(match.group(1)) != shank:
            raise AnatomicalMapError(f"Atlaxis CSV row {row_number} does not identify a single-shank NP1 site.")
        csv_site = int(match.group(2))
        if not 0 <= csv_site < 960:
            raise AnatomicalMapError(f"Atlaxis CSV row {row_number} has an NP1 site outside 0 to 959.")
        if channel_id in seen or channel_id not in recorded:
            raise AnatomicalMapError(f"Atlaxis CSV row {row_number} has a duplicate or unrecorded hardware channel {channel_id}.")
        seen.add(channel_id)
        recorded_channel, recorded_site = recorded[channel_id]
        if recorded_site < 0:
            continue
        if csv_site != recorded_site:
            raise AnatomicalMapError(
                f"Atlaxis routing differs for hardware channel {channel_id}: "
                f"CSV site {csv_site}, recorded site {recorded_site}. Use the export for this recording's routing."
            )
        label = row["region"].strip()
        if label:
            regions[recorded_channel] = label
    missing = sorted(set(recorded) - seen)
    if missing:
        raise AnatomicalMapError(f"Atlaxis CSV is missing hardware channels for the selected probe: {missing}")
    return regions


def save_anatomical_map_csv(
    path: str | Path,
    groups: list[AnatomicalChannelGroup],
    channel_regions: dict[int, str],
) -> Path:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(build_anatomical_map_csv(groups, channel_regions), encoding="utf-8")
    return csv_path
