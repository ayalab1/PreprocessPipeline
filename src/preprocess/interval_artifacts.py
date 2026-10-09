"""Merge high-amplitude artifact windows and replace each complete interval."""
from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline
from spikeinterface.preprocessing.basepreprocessor import BasePreprocessor, BasePreprocessorSegment


def merge_trigger_windows(
    triggers: list[int] | np.ndarray,
    *,
    sampling_frequency: float,
    num_samples: int,
    ms_before: float,
    ms_after: float,
) -> np.ndarray:
    """Return merged [start, stop) sample intervals around trigger frames."""
    if ms_before < 0 or ms_after < 0:
        raise ValueError("Artifact windows must be nonnegative")
    frames = np.unique(np.asarray(triggers, dtype=np.int64).reshape(-1))
    if frames.size == 0:
        return np.empty((0, 2), dtype=np.int64)
    if np.any(frames < 0) or np.any(frames >= num_samples):
        raise ValueError("Artifact trigger is outside the recording")

    before = int(ms_before * sampling_frequency / 1000.0)
    after = int(ms_after * sampling_frequency / 1000.0)
    starts = np.maximum(0, frames - before)
    stops = np.minimum(num_samples, frames + after + 1)
    merged: list[list[int]] = []
    for start, stop in zip(starts, stops, strict=True):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], int(stop))
        else:
            merged.append([int(start), int(stop)])
    return np.asarray(merged, dtype=np.int64)


class RemoveArtifactIntervalsRecording(BasePreprocessor):
    """Lazy replacement of variable-length, nonoverlapping artifact intervals."""

    def __init__(self, recording, intervals: np.ndarray, mode: str = "linear") -> None:
        if recording.get_num_segments() != 1:
            raise ValueError("Artifact interval removal requires a single recording segment")
        if mode not in {"linear", "cubic", "0"}:
            raise ValueError(f"Unsupported artifact interval mode: {mode}")
        intervals = np.asarray(intervals, dtype=np.int64).reshape(-1, 2)
        if intervals.size and (
            np.any(intervals[:, 0] < 0)
            or np.any(intervals[:, 1] > recording.get_total_samples())
            or np.any(intervals[:, 0] >= intervals[:, 1])
            or np.any(intervals[1:, 0] <= intervals[:-1, 1])
        ):
            raise ValueError("Artifact intervals must be ordered, disjoint [start, stop) ranges")
        super().__init__(recording)
        self.add_recording_segment(
            _RemoveArtifactIntervalsSegment(recording._recording_segments[0], intervals, mode)
        )
        self._kwargs = {"recording": recording, "intervals": intervals.tolist(), "mode": mode}


class _RemoveArtifactIntervalsSegment(BasePreprocessorSegment):
    def __init__(self, parent_recording_segment, intervals: np.ndarray, mode: str) -> None:
        super().__init__(parent_recording_segment)
        self.intervals = intervals
        self.mode = mode

    def get_traces(self, start_frame, end_frame, channel_indices):
        parent = self.parent_recording_segment
        traces = parent.get_traces(start_frame, end_frame, channel_indices).copy()
        intervals = self.intervals
        first = np.searchsorted(intervals[:, 1], start_frame, side="right")
        for start, stop in intervals[first:]:
            if start >= end_frame:
                break
            fill_start = max(start, start_frame)
            fill_stop = min(stop, end_frame)
            target = slice(fill_start - start_frame, fill_stop - start_frame)
            if self.mode == "0":
                traces[target] = 0
                continue

            left = int(start) - 1
            right = int(stop)
            has_left = left >= 0
            has_right = right < parent.get_num_samples()
            if not has_left and not has_right:
                traces[target] = 0
                continue
            if not has_left or not has_right:
                anchor = right if has_right else left
                traces[target] = parent.get_traces(anchor, anchor + 1, channel_indices)[0]
                continue

            left_value = parent.get_traces(left, left + 1, channel_indices)[0].astype(np.float64)
            right_value = parent.get_traces(right, right + 1, channel_indices)[0].astype(np.float64)
            samples = np.arange(fill_start, fill_stop, dtype=np.float64)
            weight = ((samples - left) / (right - left)).reshape(-1, 1)
            values = left_value + weight * (right_value - left_value)
            if self.mode == "cubic" and left >= 1 and right + 1 < parent.get_num_samples():
                # Avoid using another artifact as a spline anchor. Fall back to linear
                # when the clean gap between adjacent intervals is too short.
                left_clean = not np.any((intervals[:, 0] <= left - 1) & (left - 1 < intervals[:, 1]))
                right_clean = not np.any((intervals[:, 0] <= right + 1) & (right + 1 < intervals[:, 1]))
                if left_clean and right_clean:
                    x = np.array([left - 1, left, right, right + 1])
                    y = np.vstack(
                        [
                            parent.get_traces(int(i), int(i) + 1, channel_indices)[0]
                            for i in x
                        ]
                    ).astype(np.float64)
                    values = CubicSpline(x, y, axis=0)(samples)
            traces[target] = values
        return traces
