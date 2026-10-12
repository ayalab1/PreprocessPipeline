# WILD-NP input integration

Date: 2026-10-11

## Goal and scope

Implement WILD-NP NP1.0 input, recursive recording discovery, usable-segment epochs,
chronological AP concatenation and independent per-probe Kilosort4 sorting in an
isolated workspace. Base: main at 7ef776a8a9f7d8ace48ecb4514f9018cf33119df.
Workspace: D:\PreprocessPipeline-integrating-wild-np; branch: codex/integrating-wild-np.
Selectively reuse the uncommitted NP implementation from
D:\PreprocessPipeline-integrating-terasort (5453afb03b78e4e22d96be7921cb73af0708162c).
Do not change that workspace, D:\WILD_NP, or recording inputs. Do not introduce
TeraSort as an NP dependency. Preserve other input formats and public APIs.

## Steps

1. Inspect source NP contracts and target recording metadata, configuration receipts,
   file lengths and logs; identify the minimal integration points on current main.
2. Port existing geometry, channel mapping, gain and common sorter connections;
   add explicit signed-count format and configuration-evidence handling.
3. Implement recursive discovery and eligibility, compatible epochs/merge provenance,
   identity/configuration consistency, and segment-boundary treatment.
4. Connect GUI, preflight and metadata outputs; document units, calibration and timing.
5. Review scoped changes and run at most one lightweight changed-file check if needed;
   record actual checks, limitations and remaining real-data validation.

## Validation boundary

Default validation is source/diff inspection. No new tests, full suites, environment
changes, full-data merge, filtering, sorting, waveform extraction or quality evaluation.
Read only the recording evidence needed to implement the stated format and contracts.
Implementation completion does not establish real-data numerical or GUI correctness.

## Progress

- Planning recorded before source edits.

## Completion

- Selectively ported NP1 site geometry, receipt channel mapping, original DAT
  indices, inactive-site reasons, per-probe reference/aggregation, nominal gain,
  XML/chanMap/CellExplorer coordinates, and GUI/worker scale propagation. Kept the
  existing common sorter/partition implementation; no TeraSort runner or dependency
  was imported. Explicit checkout-root resolution keeps defaults in this workspace.
- Added explicit signed-count metadata admission with no count/polarity transform;
  retained separate legacy encoding recognition. LFP rate uses the saved rational
  numerator/denominator, not rounded display text or the generic 1250 Hz default.
- Added recursive file-based discovery, empty-attempt exclusion with reasons,
  chronological usable-segment epochs, shared channel/configuration/rate checks,
  and confirmed-serial consistency. Incomplete segments require intact saved rows
  and clean continuity counters/status; they are not rejected solely for incomplete
  termination. Data-bearing ambiguous/error segments fail explicitly.
- Startup evidence uses each segment's writer declaration, level-3 applied receipt
  and its named NP1 request/identical original IMRO. ID/CRC are receipt-reported
  values; their JSON-to-firmware encoding is not recomputed. Evidence-file SHA256
  values are retained. No metadata or identity is borrowed from other segments.
  Startup parsing is limited to the observed NP1 external-reference schema.
- AP outputs retain original 768-column space and count units. Active-channel
  gain is required to be uniform for the existing scalar gain_to_uV contract.
  Hardware gain, nominal conversion and calibration uncertainty are distinct.
  ADC calibration remains unknown; nominal scaling is not calibrated voltage.
- Added zero-based half-open source/merged sample intervals to MergePoints and
  session epochs. Capture labels remain literal, including nSkip. Host observations
  and host-observed gaps are separate from AP session time. LFP time.dat is not
  used as AP timing or as an Intan counter; pc_time.dat is not required.
- Preprocessing filters/references independent segment/probe views. Raw KS4
  results retain their spike arrays; a 10 ms segment-edge mask is written alongside
  them, and postprocessing excludes those spikes before waveform features. KS4
  internal filtering/template fitting can still cross or be affected by boundaries;
  this guard is an explicit policy, not empirically validated edge-effect removal.
  Analog/digital decoding, artifact interpolation and sleep-state scoring are not
  enabled for this initial NP route.
- Original recording data, D:\WILD_NP, the main checkout's unrelated files, and
  the TeraSort workspace's uncommitted/untracked content were not modified.
  No commit, push, dependency installation or environment repair was performed.

## Checks actually performed

- Initial Git state and applicable rules; targeted source and task-diff review.
- Read-only inspection of the target day's directory/file metadata, a complete
  segment's applied receipt, both interrupted segments' stream/status/startup
  evidence, an empty reconnect attempt, and host event records. No AP/LFP payload
  was read or processed. The 5 AP-file / 12 empty-attempt layout was inspected;
  the new reader was not run over the day as a validation job.
- Inspected installed SpikeInterface source for NumpySorting metadata copying,
  KS4 geometry input and current waveform-window contracts.
- One permitted lightweight check: in-memory syntax compilation of all 17 changed
  Python modules, including new wildx_np.py. PASS. Application modules were not
  imported and no bytecode files were written. No test suite or fixture was added.
- Diff review caught and repaired UTF-8 signature handling before that check.

## Remaining validation and limits

Implementation is complete within this task's scope. No full-data concatenation,
filtering, LFP export, Kilosort4 run, postprocessing, GUI interaction, regression
suite, performance benchmark or scientific quality evaluation was run. Runtime
integration and numerical behavior therefore remain unverified. Missing probe
identity, ADC calibration, AP/LFP/PC synchronization and sorter boundary effects
remain explicit uncertainties. The per-sample source/merged mapping supports a
future segment timing model without changing original recordings.

Usage and data contracts: docs/wild_np.md.


## Independent review (2026-10-11)

A separate read-only reviewer inspected the uncommitted integration and relevant
callers. Two actionable findings remain open; implementation source was not changed.

- P1: wildx_np_metadata.json is absent from the preprocess completion inventory,
  legacy/direct-run manifest requirements, and canonical-output backup list.
  Missing metadata is then treated as a non-NP recording, so copied/resumed outputs
  can pass completeness checks and silently skip the 10 ms segment-edge exclusion
  before waveform extraction. Preserve/require this sidecar as part of the NP data
  contract and reject incomplete NP outputs rather than dropping boundary handling.
- P1: session.extracellular.leastSignificantBit contains the AP conversion, whereas
  LFP conversion is stored only in lfpLeastSignificantBit. Existing CellExplorer
  LFP consumers still read leastSignificantBit. For AP gain 500 / LF gain 250,
  this reports nominal LF amplitudes at half scale and changes amplitude threshold
  semantics. The LFP unit contract and existing consumers need a coherent update.
- Unresolved contract question, not a confirmed defect: startup evidence requires
  verification level 3, while final receipts require applied state and valid channel
  structure. The inspected evidence does not establish that lower final-receipt
  levels imply an incorrect mapping; target receipts have level 3 and selection
  present. Clarify firmware verification semantics before changing this policy.

No additional tests, imports, checks, data processing or GUI operations were run.
The earlier 17-file syntax result was reused. These two fixes and real-data/runtime
validation remain outstanding. No commit or push was performed.

## Boundary policy revision (2026-10-11)

Goal: defer boundary-based exclusion to later analysis, as requested by the user.
Remove the provisional automatic 10 ms spike guard from the pipeline. Preserve
segment/source sample mappings and the existing NP preprocessing/gain behavior.

1. Remove sorter boundary-mask export and postprocess spike filtering, then delete
   the unused guard constant and helper functions.
2. Remove guard-only annotations and update the analyzer cache identity to reflect
   the unmasked spike input while retaining segment counts for preprocessing.
3. Update the data-contract documentation and review record; inspect this change's
   source/diff only. Do not add or run tests, sorting, or data-processing checks.

### Revision outcome

- Removed the automatic 10 ms spike exclusion, sorter mask export, unused helper
  functions and guard annotations. Postprocessing retains boundary spikes.
- Retained epoch boundaries and source/merged sample mappings for downstream
  analysis. Existing per-segment/probe preprocessing is unchanged. The analyzer
  identity retains segment counts and no longer includes the removed guard value,
  distinguishing the revised input policy from previously guarded analyzer caches.
- Updated docs/wild_np.md and output provenance descriptions. This revision
  supersedes the earlier 10 ms policy and its automatic-exclusion review finding.
  Required-output inventories were not changed; NP provenance persistence remains
  a separate follow-up.
- Reviewed the scoped diff/source and searched source/docs for removed guard
  references; none remain. No tests, new syntax check, real-data processing,
  sorting, GUI operations, commit or push were run. The earlier syntax PASS
  predates this revision and does not validate the revised runtime behavior.
- LFP conversion from recorded LF to 1250 Hz and the reviewed CellExplorer gain
  mismatch remain outstanding; this revision only changes automatic exclusion.

## Recorded LF output revision (2026-10-11)

Goal: derive the configured LFP output (1250 Hz by default) from recorded LF,
with consistent nominal units in existing CellExplorer readers and durable
metadata on restart. Preserve raw inputs, AP processing, segment boundaries,
and the requested absence of automatic boundary exclusion.

1. Low-pass each saved LF segment at 450 Hz in floating point and resample using
   the exact saved rate ratio (20000/12 to 1250 Hz is 3/4), with bounded chunk
   overlap and a consistent phase grid.
2. Store derived LF in AP count units so the standard session leastSignificantBit
   gives the correct nominal microvolts; record source/output scales and ranges.
3. Set XML/session output rates consistently and require matching processing
   metadata before reusing an existing LFP binary.
4. Include NP/LFP metadata in completion inventories and preserve recording kind
   and nominal scale through direct-run manifests and resume.
5. Update the contract documentation and inspect the scoped source/diff. Do not
   add/run tests, process data, launch sorting, or perform broader validation.
### Recorded LF revision outcome

- Implemented independent per-segment 450 Hz, fifth-order forward/backward
  Butterworth filtering in float32, followed by rational polyphase resampling.
  Exact 20000/12 Hz input gives up/down = 3/4 at the configured 1250 Hz output.
  A small streaming recording adapter keeps a fixed phase grid and bounded
  overlap; this avoids the installed SpikeInterface resampler's non-integer-rate
  FFT path. Final segment lengths use ceil(N * up / down).
- Derived LF is normalized to AP storage units before a single nearest-even
  int16 quantization. For the supplied AP/LF gains, the count multiplier is 2
  and the common nominal output scale is 2.34375 uV/count. Nonfinite/overflowing
  results raise errors. Source LF remains 4.6875 uV/count and is not rewritten.
- XML, session LFP rate, standard/explicit LFP leastSignificantBit and preflight
  descriptions now agree with the configured output. NP provenance format 3
  and the LFP sidecar record the processing recipe, source/output units, exact
  ratio and independent native/output half-open sample intervals. Existing LF
  reuse requires identical metadata and exact byte length.
- Registered NP/LFP sidecars as required outputs, with metadata fingerprints and
  derived-LF frame counts. Manifests now retain recording kind and nominal scale.
  Direct/legacy adoption and previous persistent-stage reuse validate NP/LF
  provenance; older or incomplete NP outputs cannot bypass the new contract.
- Updated docs/wild_np.md. Reviewed the scoped source/diff, including the follow-up
  correction to previous-stage reuse. No tests, syntax/import checks, GUI runs,
  data processing, sorting, benchmarks, commit or push were performed. The prior
  17-file syntax result predates these changes and is not current validation.
- Remaining: runtime/numerical validation of the new LF path, AP/LF time alignment,
  and scientific signal-quality checks. Boundary exclusion remains deferred to
  downstream analysis. The earlier unconfirmed final-receipt verification-level
  policy question remains unchanged; no unsupported receipt-policy change was made.
## Neuropixels geometry selector and Basepath GUI revision (2026-10-11)

Goal: replace the old channel-order NeuroPixel template with the recorded-site
NP1 geometry discussed in the TeraSort integration, make Basepath loading visible
and actionable, and allow WILD-NP use without a manually supplied XML.

1. Extract the existing, source-pinned NP1 physical-site catalog into a reusable
   geometry module. Replace the old NeuroPixel option with Neuropixels 1.0;
   require the saved column-to-site mapping rather than guessing sites from order.
2. Populate the GUI geometry/probe groups from WILD-NP metadata when Basepath is
   loaded, retain original binary IDs, and separate probes only in the preview.
3. Surface discovery/configuration errors in the visible panel and log, clear
   stale session metadata on a new Basepath selection, and align GUI chanMap
   generation/run preparation with the same recorded-site path used by workers.
4. Explain automatic XML creation and the supported NP options in the UI/docs.
5. Review only the scoped source/diff. Do not add/run tests or GUI/data-processing
   checks; the earlier one-check task budget has already been used. Do not edit
   the main or TeraSort worktrees or raw recordings.

### Geometry and GUI outcome

- Extracted the existing pinned NP1 site coordinates into neuropixels_geometry.py
  and replaced the old NeuroPixel selector/template with Neuropixels 1.0. The
  public np1_site_geometry symbol remains available through wildx_np.py.
  Preview, preflight, generation and pipeline preparation validate the selected
  model and recorded probe groups against the same column-to-site mapping.
- Basepath Browse and manual entry now reload metadata. The panel shows detected
  probe ports, saved/active channel counts and usable segments. Metadata errors
  are visible in the panel/log rather than silently leaving an empty preview.
  Reload clears stale XML/map-derived state while preserving manual rejections.
- NP geometry groups are populated from recording metadata; their group IDs and
  zero x offsets are fixed. Probe spacing is added only to the preview. Output
  XML/chanMap are generated automatically, and generic XML map generation cannot
  replace the recorded NP mapping before a run. Unsupported NP options are
  initially turned off; Kilosort4/probe partitioning are selected.
- Updated docs/wild_np.md with restart, Basepath, geometry, output and LFP steps.
  Scoped source/diff review included the reload signal guard and direct-slot
  error handling. No tests, syntax/import checks, interactive GUI run, recording
  processing, sorting, commit or push were performed. The reported GUI symptom
  was not reproduced interactively; its original failure message is unknown.
  Runtime behavior remains unverified. No main/donor/raw-data files were changed.

## Editable NP probe x offsets (2026-10-11)

Goal: honor the requested editable NP probe placement, with default x translations
of 0, 2000, 4000, ... micrometres in physical-port order. This supersedes the earlier
zero-offset/preview-only spacing policy while retaining recorded site/channel IDs.

1. Enable NP x-offset controls and initialize one assignment per recorded probe
   with 2000 um spacing; preserve explicitly loaded or edited NP assignments.
2. Apply the configured translation to each probe's site x coordinates in the
   shared chanMap path and retain the assignments in output provenance.
3. Remove the additional preview-only translation so GUI, chanMap and session
   coordinates agree. Keep sorting partitioned by physical probe.
4. Update the existing documentation and review the scoped diff only. No new
   tests, syntax/import checks, GUI/data execution, commit or push.

### Offset outcome

- NP x-offset fields are editable. Default translations are 0, 2000, 4000, ... um
  in physical-port order, with a zero default for a single probe.
- The shared channel-map builder validates finite offsets, applies each offset to
  its probe's recorded site coordinates, and stores canonical assignments in
  chanMap and NP provenance. Channel IDs, within-probe geometry and per-probe
  sorting remain intact. CellExplorer/session coordinate descriptions identify
  the configured translation.
- Removed extra preview-only spacing. GUI preview and saved coordinates now use
  the same values. Saved explicit assignments are restored without resetting
  their offsets when NP controls initialize; loading a config refreshes controls.
- Updated docs/wild_np.md and reviewed only the changed source/diff. No tests,
  syntax/import checks, GUI execution, data processing, commit or push were run.
  Interactive editing and save/load behavior remain unverified at runtime.

## Readable channel-map preview (2026-10-11)

Goal: make the dense NP channel map usable across the available canvas width,
while preserving configured offsets and the stored coordinates/channel identities.

1. Show NP probes in separate detail panels by default, with expanded horizontal
   scale and a common depth axis; retain a selectable layout view with equal x/y
   scale for viewing configured placement.
2. Add visible view/reset controls and interaction guidance. Keep wheel/box zoom,
   support panning in the active panel, and report hovered channel/site coordinates.
3. Keep all changes inside the preview widget plus the existing usage documentation;
   do not alter channel-map generation, data, sorting or geometry settings.
4. Review the scoped source/diff only; do not run GUI, tests, imports or data jobs.

Scope update from the user's follow-up: apply the readable default view and left
settings-panel fix to every probe type. The common splitter will start with a
620 px settings panel (minimum 520 px, non-collapsible), and geometry fields will
reserve enough width instead of yielding almost all space to channel groups.

### Preview and common layout outcome

- Reworked the channel-map canvas for all probe types. Probe detail is the default:
  separate probe panels fill the width, keep a shared depth scale and explicitly
  identify the expanded horizontal scale. Layout (equal scale) remains available
  to inspect configured placement. Coordinate arrays and generation are unchanged.
- Added visible view/reset controls and interaction guidance. Wheel depth zoom,
  box zoom, right-button pan and reset operate on the active panel; shared depth
  updates across probe panels. Hover reports original zero-based channel IDs,
  recorded site IDs when available, configured coordinates and active/bad status.
  Preserved the existing minimum wheel-zoom range guard and layout label behavior.
- Common startup splitter sizes are 620/880 px. The settings side cannot collapse
  or shrink below 520 px. Geometry selectors reserve 140 px, share row space more
  evenly with groups and show their full names on hover. This applies to NP and
  non-NP probes and all settings tabs.
- Updated docs/wild_np.md and completed the scoped source/diff review, including
  follow-up layout edits. No tests, syntax/import checks, interactive GUI launch,
  rendering, data processing, commit or push were run. Appearance and mouse/layout
  behavior remain unverified in a live GUI. Restart the worktree launcher to load
  these changes; the installed preprocess-gui entry point still targets main.


### Shared-layout and inactive-site preview revision (2026-10-11)

Goal: restore a single coordinate view so configured probe spacing is visible,
make wheel zoom anchor both axes at the cursor, and show NP inactive sites with
smaller zoom-aware markers. This supersedes the separate-panel default above;
the wider common settings panel remains.

1. Restore one equal-scale x/y axes for all probe types and retain configured
   offsets, hover readout, box zoom, pan and reset.
2. Use the existing NP1 physical-site catalog for a preview-only inactive
   background; join recorded site/channel IDs without inventing channel IDs.
3. Adapt the physical marker sizing and gray inactive-site presentation from
   Atlaxis probe_view.py at 395c5f7a124ecea02a1978939e4c60baa03f4f87.
   Scale the NP markers with zoom while keeping a small screen-size minimum.
4. Update usage documentation and inspect the scoped source/diff only. Do not
   run tests, imports, GUI, rendering, data processing or sorting.


### Shared-layout preview outcome

- Restored one equal-scale axes for every probe type; removed the separate-panel
  selector. Configured x offsets are displayed directly. The wider settings
  panel from the preceding revision is retained.
- Wheel zoom updates both x and y limits around the cursor, including fractional
  scroll steps. Box zoom, right-button pan, hover and reset remain available.
- NP1 previews include the full 960-site catalog per physical probe. Active
  recorded sites retain probe colors; excluded and unrecorded sites are gray.
  Hover preserves recorded channel IDs and explicitly identifies unrecorded
  sites without assigning them a channel.
- NP marker diameter follows coordinate scale (7 um active, 10 um inactive,
  display sizes only), with small 1.5/1.1 px minimums. A queued redraw updates
  markers after axes transforms settle. The design references Atlaxis ProbeView
  at commit 395c5f7a124ecea02a1978939e4c60baa03f4f87.
- Updated docs/wild_np.md and completed scoped source/diff inspection. No tests,
  syntax/import checks, interactive GUI, rendering, data jobs, commit or push
  were run. Live appearance and mouse behavior remain unverified. Restart the
  worktree launcher to load this revision.


### Full-width preview and chrome cleanup (2026-10-11)

Goal: fill the central viewer with a balanced grid, remove the upper controls
and lower explanatory/status text, and prevent the legend overlapping the title.

1. Keep one equal-scale coordinate system but adjust coordinate limits to the
   available axes area instead of shrinking the axes to a narrow strip.
2. Remove reset/help/status rows; retain double-click reset and site information
   as a hover tooltip. Keep load errors visible in the canvas and recording log.
3. Move the legend to the upper right, update the usage notes, and review only
   the changed source/diff. Do not run tests, imports, GUI or rendering.


### Full-width preview cleanup outcome

- The axes now fill the central canvas with equal x/y scale by adjusting data
  limits. View navigation uses non-fixed bounds so the plotting library can
  maintain the aspect ratio when the viewer is resized.
- Removed the reset button, top-left text, interaction help and bottom status
  rows. Double-click reset remains; channel/site details appear only in a hover
  tooltip. Recording errors still appear in the recording information/log.
- Kept the plot title and moved the legend explicitly to the upper right.
  Updated docs/wild_np.md and reviewed the scoped source changes and edit diff.
  No tests, syntax/import checks, GUI launch, rendering, data jobs, commit or push
  were run. Live appearance and interaction remain unverified.


### NP anatomical-map integration (2026-10-11)

Goal: support anatomical-map load/edit for the NP route without a manually
supplied XML, preserving the recorded-channel CSV contract.

1. Build NP anatomical groups from chanMap physical probe IDs and original
   recorded column order; retain inactive/missing-site rows in the CSV.
2. Permit missing coordinates only for inactive NP channels and omit those
   points from the graphical editor; keep active-channel coordinate validation.
3. Remove the NP XML prerequisite and bind loaded labels to the NP source
   context, retaining labels when the generated XML is created.
4. Update usage documentation and review the scoped source/diff only. Do not
   run tests, imports, GUI, rendering or recording-data processing.


### NP anatomical-map outcome

- NP load/edit obtains anatomical groups directly from chanMap physical probe
  IDs, without requiring XML. CSV probe-column/channel-row order matches the
  generated anatomical XML and includes every saved recording column.
- Missing coordinates are accepted only for inactive NP channels. Those rows
  remain in CSV but are omitted from the editor's geometry; active-channel
  coordinates and the existing non-NP validation remain required.
- NP label context uses the source recording path instead of generated XML
  availability, preventing XML generation from clearing existing labels.
- Added usage guidance to docs/wild_np.md. Brain-region names still require
  anatomical evidence and manual assignment; nominal site coordinates do not
  determine brain regions. Existing CSV import requires the same site mapping.
- Completed scoped source/diff inspection. No tests, syntax/import checks, GUI,
  rendering, recording-data processing, commit or push were run. The user's
  exact error dialog and live NP editor behavior have not been reproduced.

## Atlaxis anatomical CSV import (2026-10-11)

Goal and scope: read Atlaxis channel export CSV in the Preprocess GUI and map its regions onto recorded WILD-NP channels. Keep the existing headerless CellExplorer anatomical_map.csv output unchanged. No Atlaxis source or raw recording changes.

1. Recognize the confirmed Atlaxis channel_id/site_id/shank/region/is_target format alongside the existing matrix CSV.
2. Validate hardware channel and NP1 site identities against the current chanMap before importing regions.
3. Ask for the destination probe when multiple probes are present, preserving labels on other probes.
4. Document the import/save workflow and review the scoped source diff; no GUI or data execution.
Import outcome:
- Added a dedicated Atlaxis NP1 channel CSV parser using the pinned exporter contract. Hardware channel IDs are probe-local; NP1 site identity, duplicate/missing rows and the recorded routing are checked before applying any region.
- The Load dialog recognizes this input and asks for the destination physical probe when needed. Labels on the other probe stay in memory; unidentified inactive rows remain blank. Existing CellExplorer matrix input and the headerless matrix saver retain their format and channel order.
- Import is reviewed/saved through the existing anatomical map editor. No Atlaxis source, recording files or generated outputs were changed.
- Reviewed the parser diff, changed GUI handler and documentation. No tests, imports, syntax checks, GUI execution or real CSV/data validation were run. No supplied CSV is available yet; end-to-end import remains unverified.

## RM034 day07 CLI execution (2026-10-11)

Goal and scope: run the implemented WILD-NP route on RM034_261005_day07 with Kilosort4, preserving source recordings and using the standard output layout under C:/Users/aalab/Documents/preprocess_tmp. The user explicitly requested this complete day and output destination.

1. Preserve the existing integration changes and use the preprocessing environment and repository KS4 settings.
2. Correct the generic disk estimate for KS4 exported channel subsets and sequential partition cleanup, retaining the existing headroom and other-sorter estimates.
3. Save the CLI configuration and launch preprocessing followed by per-probe KS4, with logs and exit status retained outside the source tree.
4. Inspect only the scoped changes and actual run completion/failure; record results and remaining limitations. No broad tests, extra data audits, commit or push.

The five nonempty epochs total approximately 697 GB of AP input. Empty reconnection attempts are handled by the existing NP adapter. Its current boundary and clock limitations remain unchanged.

A concrete CLI contract omission was found during preparation: the NP pipeline reads PreprocessConfig.probe_assignments, but the field and GUI-to-CLI handoff were absent. Added that existing setting to the dataclass and handoff so default and configured NP geometry can reach the existing code. No geometry or processing parameters changed.

The first actual CLI attempt (20261011_233838) failed before AP processing because runtime preparation stored R: paths while the pipeline canonicalized the same inputs to UNC paths. The LF rate was already 1250 Hz in both calls. A focused metadata replay with identical source paths succeeded; inspection confirmed the R:/UNC mismatch. Canonicalized the NP runtime source path before discovery. Preserved the failed attempt log/status and its generated provenance JSON; original recordings and analysis settings are unchanged.

### Day07 execution handoff

- Saved the standard session GUI/CLI JSON and an unchanged copy of the repository KS4 YAML under `C:/Users/aalab/Documents/preprocess_tmp/RM034_261005_day07/config/`.
- Source remains the complete RM034 day07 folder. Requested workflow is preprocessing followed by sequential KS4 probe partitions. Existing AP filtering/reference settings, 1250 Hz derived LF, and KS4 scientific parameters are unchanged; NP-unsupported analog/digital event export and state scoring are disabled.
- The KS4 disk estimate now follows selected channel widths and the wrapper's export/copy/delete flags across sequential partitions. The existing 20%/5 GiB headroom rule and other-sorter estimates remain. The actual run admitted 1218.01 GiB including headroom with 1446.33 GiB free.
- Fixed the missing probe-assignment config field/handoff and canonicalized NP runtime input paths to match the main pipeline. Reviewed the scoped edit diffs. No tests, broad checks, environment installation, commit or push were run. One focused metadata replay helped diagnose the actual startup failure; it did not read AP samples.
- Attempt `20261011_233838` stopped on mapped-drive versus UNC provenance; its generated provenance was preserved with its log. Attempt `20261011_234103` passed discovery/admission and reached DAT writing, then stopped during MKL initialization in worker processes. The writer removed its failed partial DAT.
- Attempt `20261011_234251` uses `conda run --no-capture-output -p C:/Users/aalab/miniforge3/envs/preprocess python -u -B -m src.preprocess.gui.run_pipeline --config <session>/config/pipeline_gui.json --mode preprocess`. It was still running after the startup wait and had reached DAT writing (453729893 frames, 768 channels, 696929115648 expected bytes, 24 workers). A threadpoolctl warning about multiple OpenMP runtimes remains in the log; successful completion has not been confirmed.
- Background launcher PID: 58372. This task's launcher writes the eventual exit code and completed/failed state to `<session>/cli_runs/20261011_234251/status.json`; console output is retained in the adjacent `pipeline.log`. It continues independently of this chat turn.
- Remaining: preprocessing and both KS4 partitions must complete. No completed sorting output, unit quality, or scientific timing accuracy is claimed. No postprocessing/CellExplorer export was requested or launched.

Handoff recorded at 2026-10-12T03:45:11.697438+00:00.


### Day07 recovery after LFP worker failure (2026-10-12)

Status inspection requested by the user found that AP DAT publication completed, followed by a stalled LFP write. The Windows worker failed while SpikeInterface tried to reconstruct the project-defined LF recording because the src package lacks __version__. The parent remained alive with stale running status.

1. Stop only this failed pipeline process tree and retain its logs and completed AP DAT.
2. Expose the project version required by SpikeInterface worker deserialization, matching the existing package version.
3. Resume with the same settings and overwrite disabled, reusing the completed DAT and rebuilding only the failed LF output before KS4.
4. Review the scoped change and inspect the actual resumed run; do not add tests or expand the data-validation scope.

Recovery outcome at approximately 08:10 EDT:
- AP DAT was published successfully after 2:52:03 of writer processing and has the expected 696929115648 bytes. The main job then stalled at LF worker reconstruction; it had not reached KS4.
- Stopped only the confirmed pipeline PID 96200. Its launcher recorded failure; prior logs remain. Removed only its unpublished 43558069248-byte LFP partial after the process exited, recording the removed path/size in the old attempt.
- Added src.__version__ = "0.1.0", matching pyproject.toml, for SpikeInterface worker reconstruction. Reviewed the focused source diff. No tests or additional numerical validation were run.
- Resumed the same CLI configuration with overwrite disabled in cli_runs/20261012_080840 (launcher PID 83316, Conda PID 99688). The AP DAT was reused; the capacity estimate now excludes that completed file.
- The actual resumed LFP writer passed the earlier failure point and reached 712/22687 chunks (about 3%), with the log updating immediately. Both KS4 partitions remain pending after LF completion; no completed sorting output is claimed. Status and console output remain in this attempt's status.json and pipeline.log.


### Day07 KS4 dependency recovery (2026-10-12)

The 08:08 attempt completed the LF output and session.mat, then exited at 08:13 EDT before KS4 processing because faiss was not installed. The repository KS4 setup.py explicitly requires faiss-cpu. This is a required execution dependency, not an optional verification dependency.

1. Inspect the binary-wheel dependency plan and preserve the installed NumPy/PyTorch stack.
2. Install only the missing KS4 runtime dependency and record the exact version.
3. Resume the unchanged CLI settings, reusing completed AP and LF files; inspect actual startup and report any remaining failure.

Dependency recovery outcome at approximately 09:31 EDT:
- The resumed LF writer completed, and session.mat was generated before the preceding attempt failed on the missing faiss import. AP/LF outputs remain reusable with overwrite disabled.
- Installed only faiss-cpu 1.15.1 from its Windows CPython 3.11 binary wheel using --no-deps. Its declared NumPy/packaging requirements were checked against the installed NumPy 1.26.4 and packaging 26.2. PyTorch 2.9.1+cu130 and the existing scientific stack were not upgraded. The installation plan is retained in the session config directory. This installation was required for the authorized KS4 execution.
- Restarted unchanged settings in cli_runs/20261012_092857 (launcher PID 53568, Conda PID 88572). Both completed binaries were reused, and the actual run reached probe1 (383 channels), resolved KS4 parameters and passed disk admission. Its output folder is Kilosort4_2026-10-12_092920_probe1.
- At the startup inspection the process was running with worker initialization warnings from threadpoolctl; no completed export chunks or GPU spike-detection/clustering progress had yet been reported. Probe2 remains pending. No completed sorting result is claimed.
- No source edits, tests, benchmarks or additional neural-data validation were made in this dependency-recovery step. Previous failed attempt folders and logs remain.

## Publication (2026-10-12)

The user explicitly requested commit, push and a PR for this branch. The publication includes the WILD-NP implementation, requested LF/GUI/anatomical-map revisions and the logged Day07 runtime fixes (KS4 disk admission and src package version for worker reconstruction).

- Reviewed task ownership, the newer runtime-fix diffs and the saved execution outcomes; earlier source/diff reviews cover the implementation and GUI revisions.
- Refreshed origin/main and checked for an existing open PR for this head; none was found. Target is main, head is codex/integrating-wild-np.
- The saved execution record confirms AP and LF publication and session.mat generation. Its latest KS4 entry records probe1 startup only; successful sorting, postprocessing, GUI behavior, Atlaxis CSV import and numerical/scientific correctness are not claimed.
- No new tests, syntax/import checks, benchmark, recording processing or execution-status inspection was performed for publication. The initial 17-module syntax check predates later revisions.
- Publish one coherent implementation commit with this log and documentation. Recording outputs, environments and external workspaces are excluded. PR description records the remaining validation and timing/calibration limitations.

### Input-scope clarification (2026-10-12)

The user requested an explicit distinction from ordinary Neuropixels support. The documentation and PR scope wording now identify this as the WILD-NP recorder's NP1 route, requiring its saved binary layout, stream metadata and configuration receipts. SpikeGLX/Open Ephys recordings are outside this route's scope; selecting NP1 geometry alone does not establish compatible input. Documentation-only follow-up, with scoped diff inspection and no tests or processing.

### CI regression repair (2026-10-12)

The user reported Linux and Windows failures in PR 38. Basic tests run 38286784304 failed the same two existing disk-admission tests on both OSes (112 passed, 2 failed per job).

1. Restore non-KS4 disk admission before MATLAB/dependency initialization, preserving the detailed KS4 allocation estimate.
2. Keep optional WILD-NP result metadata optional for existing callers, and evaluate partition-channel widths only for KS4 where they are used.
3. Review the scoped source diff, commit/push the fix to PR 38 and collect the automatically triggered CI result. Do not change tests/fixtures, install dependencies, run local suites or inspect the ongoing recording job.
CI source-fix outcome:
- Non-KS4 sorting again checks disk admission before resolving MATLAB or creating sorter logs. KS4 retains its configured exported-width/file-lifecycle estimate.
- WILD-NP detection uses optional result metadata, consistent with existing callers. Partition channel counts are evaluated only for KS4; generic sorters retain the previous estimate without requiring KS4-only partition fields.
- Reviewed the focused source diff. Existing tests and CI configuration are unchanged. No local tests/import checks or ongoing recording-job inspection were performed. The automatic CI result after pushing this fix is pending.

CI completion:
- Code fix 866804472d17654326c680f5802c94406a4b597f passed Basic tests run 38288850731 on both Linux and Windows. Each job reports 114 passed, 12 warnings, with no failures; the two reported disk-admission regressions are resolved in these existing checks.
- Final CI logs were read once per completed job. No test expectations, fixtures, CI configuration or scientific parameters were changed, and no local suites or recording jobs were run for this repair.
- This result covers the existing selected CI regressions, not real-data sorting quality, GUI/Atlaxis-import behavior or AP/LF synchronization. PR 38 retains those limitations. This completion record is a documentation-only follow-up to the tested code commit.