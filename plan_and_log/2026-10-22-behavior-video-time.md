# Behavior loading without electrophysiology

## Goal and scope

Load Behavior from a basepath using only videos and keypoint tracking. Skip
electrophysiology discovery and channel-map loading
while the Behavior tab is active. Keep existing synchronized Behavior processing
available and preserve unrelated local changes and source recordings. Export the
Behavior MAT file directly into the selected basepath, as subsequently requested.

## Implementation steps

1. Update main from origin while preserving the existing dirty checkout.
2. Separate Behavior basepath loading and refresh from ephys metadata and previews.
3. Add explicit video-frame timing and shallow video/tracking discovery for a day
   directory or a single recording; reuse calibration, cleanup and speed calculations.
   Keep the export destination separate from local synchronization metadata lookup.
4. Document the UI and timebase, review the scoped diff and run at most one
   lightweight changed-file check. Do not add tests or run broad validation.

## Decisions and progress

- Updated main from c17fbc6 to origin/main 2db1607 using fast-forward with autostash;
  Git reported that the existing tracked changes were restored successfully.
- Video time uses recorded frame indices and video FPS, with the existing explicit
  fallback FPS when video metadata is unavailable. It does not establish neural
  synchronization. Multiple videos use a documented concatenated video timeline;
  recording gaps are unknown and speed must not cross video boundaries.
- Added **Load behavior from basepath**, which selects video time and loads the
  selected folder or its immediate children. This mode prioritizes keypoints.csv
  and requires an adjacent video, skipping folders without videos and deeper
  outputs. Original synchronized discovery defaults remain unchanged.
- Placed the load button above the **Tracking script** group as requested.
  That group's optional external batch/script runs only when exporting Behavior;
  an existing keypoints.csv needs no tracking script.
- **Export Behavior** saves `<basename>.animal.behavior.mat` directly under
  basepath, with the existing overwrite control applied to that destination.
  A separate optional export directory in the processing function preserves local
  MergePoints/camera-event lookup for synchronized processing. Updated the GUI
  destination display, tooltip and README to agree with the requested destination.
- Behavior basepath reload, settings collection and preview now skip recording
  resolution, recording-format detection, XML/chanMap loading and ephys preflight. Existing
  exported camera-event timing remains selectable after loading.
- Video processing ignores MergePoints and session MAT metadata, retains source
  frame indices and missing coordinates, and records video paths, FPS sources,
  offsets and the unsynchronized timebase. Boundary speeds are NaN. Calibration,
  likelihood filtering, cleanup and within-video speed equations are reused.
- Updated the README. No dependencies, tests or unrelated source changes added;
  no source recordings or analysis outputs modified.
- Publication resumed on 2026-10-23 with authorization to create a PR and merge
  after checking the scoped diff and CI. Publish only the Behavior implementation,
  README and this log; preserve unrelated dirty files. Describe the general Behavior
  workflow without device-specific or recording-specific details.

## Verification and remaining work

- Reviewed the task-owned source/README diff and the final discovery/timing edits.
- One changed-file syntax check passed using the existing preprocess environment:
  `python -m py_compile src/preprocess/behavior.py src/preprocess/gui/app.py`.
- The later button layout and basepath export changes were reviewed in source/diff;
  no additional checks or live GUI/MAT export validation were run for those changes.
- Main and fetched origin/main were both 2db1607 (zero divergence) before publication.
- No live GUI, supplied-video processing, MAT export, scientific validation or
  test suite was run. Restart the GUI from this checkout and perform calibration
  before evaluating the real position/speed output. No implementation work remains.
- Publication review reuses these execution results; CI and merge results are
  recorded on the associated PR. No additional local validation was run.
