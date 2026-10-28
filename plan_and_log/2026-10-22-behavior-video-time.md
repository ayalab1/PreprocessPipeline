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


## 2026-10-27: Synchronization by default

Goal: make camera-event synchronization the default Behavior workflow, as requested
following the Plum day8 linearTrackBehavior failure. Preserve an explicitly chosen
video-only workflow and report the actual timing source in exported metadata.

Source state: PreprocessPipeline main at
`b3f3403aaf1d86b8ba3fd01a3de50472d67e52a4`. The two affected Python files were clean;
existing unrelated README, parameter-documentation and other changes are retained.

Plan before source edits:
1. Record the observed GUI/default and output-metadata gaps in the shared ledger.
2. Keep Auto detect as the initial timing source and preserve the user's current
   timing selection when loading behavior; remove the forced video-time reset.
3. Record synchronized_to_ephys for both event-based and explicit video outputs,
   and update the Behavior workflow and parameter documentation.
4. Review the scoped diff and run one lightweight Python source syntax check;
   finish this record and the shared feature row. No new tests or full runs.

Observed input evidence (read-only): Plum/plum_day8_20260930 behavior timestamps
span 0-914.55 s, while the session's linear-track epoch spans
11921.7472-12923.8464 s. The behavior provenance records camera_sync_selection=video,
timebase=concatenated_video and synchronized_to_ephys=false. The empty interval
selection explains linearTrackBehavior line 159. Existing recordings and exported
MAT files are outside this default-setting change and will not be rewritten.

Completion:
- Auto detect is first in the initial and refreshed timing menus. Loading behavior
  no longer overrides the selection; explicit video or recorded-input choices remain.
- Successful event-based processing records synchronized_to_ephys=true; explicit
  video processing records false. This is provenance, not a new synchronization
  algorithm or independent physical-accuracy qualification. Existing input matching,
  MergePoints offsets and missing/ambiguous-input failures are unchanged.
- Updated the README and parameter documentation; recorded the feature in the
  shared NeuroAnalysis ledger and overview. Existing unrelated edits were preserved.
- Reviewed the source/documentation diff. One lightweight check compiled both changed
  Python sources in memory with Python's compile() and passed; no imports or bytecode
  files were produced. Registry fields, overview row and source references were
  reviewed as text for consistency. No new tests, GUI execution, test suite,
  real-data behavior export, commit or push was performed.
- Remaining: restart the GUI to load this code and use Auto detect or the appropriate
  recorded camera input when explicitly regenerating Plum day8 behavior. The
  existing unsynchronized MAT has not been relabeled, overwritten or corrected.

Final source SHA-256 (uncommitted working files over the baseline above):
- `src/preprocess/behavior.py`: `43b1dd59c6214502f2b526c01e3aa7a94bb89e96ef744581bc2e09aac777c048`
- `src/preprocess/gui/app.py`: `e3cf6d002bd02e1fa80edde4c3ab356703bfab4c14930cab19db59d36b3409dc`

Publication follow-up (2026-10-27):
- User explicitly authorized merging and pushing this correction. Fetched origin;
  local main and origin/main were both b3f3403 with zero divergence.
- Publish only the two Behavior Python changes, the Behavior portions of README
  and parameter documentation, and this log. Unrelated local source/documentation,
  data and shared-ledger work remain outside this PreprocessPipeline commit.
- Reuse the completed source/diff review and syntax check. No additional local
  tests or scientific processing are needed for publication. Pull-request checks
  and the merge outcome are recorded on the associated GitHub PR.
