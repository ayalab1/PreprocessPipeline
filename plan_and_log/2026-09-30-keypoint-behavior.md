# Keypoint behavior CSV support

## Goal and scope

Read Keypoint `keypoints.csv` through the existing Behavior discovery, point
selection, preview, and export flow. Preserve DLC APIs and existing calibration,
likelihood filtering, interpolation, and camera TTL matching. Do not modify session
data or run the full preprocessing pipeline.

## Implementation steps

1. Inspect the supplied RM018 CSV headers and current discovery/loader contracts.
2. Prefer recognized tracking outputs over adjacent Keypoint evidence H5 files.
3. Load Keypoint's three-row CSV header explicitly, preserving missing rows and
   source frame indices, and expose bodypart names without the scorer prefix.
4. Update Behavior UI wording and document supported inputs; review the scoped diff
   and perform one lightweight read-only loader check on the supplied CSV.

## Findings and decisions

- The supplied CSV has `scorer/bodyparts/coords` headers, 11 bodyparts, and missing
  coordinates in the initial frames. Its manifest reports 153391 frames at 40 Hz.
- Current generic H5 discovery selects `bbox-source.h5` before `keypoints.csv`.
- Preserve filtered DLC precedence, then named DLC outputs, then Keypoint's final
  CSV, then the existing generic H5/CSV discovery. Do not select Keypoint raw or
  processing H5 artifacts when the final CSV is available.
- The sandbox cannot see the mapped R drive; read-only access outside the sandbox
  successfully located the supplied session.

## Validation and remaining work

- Implemented discovery and explicit CSV loading without renaming public DLC APIs.
  Keypoint scorer prefixes are omitted from selectable bodypart names; exported
  processing source metadata identifies Keypoint (and both sources for mixed input).
- Updated Behavior UI discovery/selection messages and README input instructions.
- Reviewed the source diff. One read-only discovery/loader check on the supplied
  RM018 CSV passed: final CSV selected despite adjacent H5 artifacts; 153391 rows,
  11 bodyparts, original frame indices 0 through 153390, initial missing coordinates
  retained, and `Spine_mid` resolved by name.
- The first check stopped on its path assertion because R resolves to a UNC path;
  normalized the expected path and reran the same check once successfully.
- No tests, fixtures, dependencies, or session outputs were added or modified. No
  full pipeline, behavior MAT export, camera TTL validation, live GUI execution,
  broad suite, or separate DLC runtime check was run. Those remain unverified.

## Follow-up: preview dependencies and ADC camera synchronization

The user reported preview and digital-sync warnings and confirmed that camera sync
is recorded on ADC. The running GUI uses the Conda `preprocess` environment, which
has neither OpenCV nor imageio/imageio-ffmpeg. Automatic approval rejected installing
the already-declared imageio packages without explicit user authorization.

The supplied recording's digital TTL arrays are empty. Its existing preprocessing
parameters have `analog_inputs: false`, and its manifest has no analog event outputs.

### Steps

1. Diagnose the actual GUI environment and recording/event metadata.
2. Add an explicit camera ADC channel setting and read the existing exported
   `pulses.events.mat` format using that channel; retain digital synchronization by
   default and preserve epoch-local versus merged timestamp handling.
3. Explain missing ADC exports in the error and document the required input.
4. Review the follow-up diff and run one lightweight syntax check. Request explicit
   authorization for the blocked environment repair after preparing the changes.

No raw ADC extraction or full reprocessing is included; actual ADC sync remains
dependent on an exported pulse file and the user's camera channel selection.

### Follow-up status

- Added `camera_adc_channel` as an optional keyword to Behavior processing and sync
  inspection, with a saved GUI setting (0 retains digital input; positive values
  select the 1-based exported `pulses.analogChannel`). Preview, cleanup, export, and
  discovery sync inspection all pass this setting.
- Reads pulse onsets for the explicitly selected channel from local or merged
  `.pulses.events.mat`, preserving the existing local/global offset contract.
- Added actionable errors for missing ADC exports and documented the prerequisite.
- Reviewed the scoped diff and ran one changed-file syntax check on behavior.py,
  gui/app.py, and gui/config_model.py; it passed. No runtime ADC sync or GUI check
  was run because the session has no exported analog pulse file and the channel
  number is still unknown.
- Video dependency installation remains blocked by automatic approval review;
  no packages were installed. Await explicit approval to install imageio and
  imageio-ffmpeg into the identified Conda preprocess environment. No raw data,
  derived session outputs, or existing GUI processes were modified.

### Authorized video environment repair

- The user explicitly authorized installing imageio and imageio-ffmpeg. Installed
  imageio 2.38.0 and imageio-ffmpeg 0.6.0 in the running GUI's Conda `preprocess`
  environment; no additional package upgrades were performed.
- One read-only call to `load_representative_frame` on the supplied RM018 MP4
  succeeded, returning a 1200 x 1200 x 3 uint8 frame. Live GUI preview was not tested.
- Camera ADC channel number remains pending; ADC pulse export and actual behavior
  synchronization remain unfinished. No GUI processes or session files were changed.

### ADC channel identification and existing sync check

- The user named ADC0/ADC1 as candidates and asked about existing sync-check code.
  `inspect_dlc_ttl_sync` in behavior.py is already called by GUI tracking discovery;
  `match_frames_to_ttl` checks pulse spacing and row-count mismatch. The related
  neurocode `process_and_sync_dlc.m` also contains a digital-only `sync_ttl` path.
- Read the recording's actual channel metadata: ADC1 through ADC8 correspond to
  continuous source columns 192 through 199 and native orders 0 through 7. Thus
  zero-based ADC0 is labelled ADC1 in this recording and maps to GUI channel 1.
- A bounded read of the first 10 seconds found 295 midpoint-threshold rising edges
  on ADC1, with median interval 0.025 s; ADC2 had one rising edge. This supports
  ADC1 as the camera-sync candidate, but does not establish full-session frame
  alignment. No full ADC extraction or session-wide synchronization check was run.
- Video dependencies are repaired and a frame read succeeded. Remaining prerequisite:
  export analog pulses with analog_inputs enabled, then use camera_adc_channel=1
  and run the existing sync check. The session still has no exported analog pulses.

## Requested execution: RM018 day33 analog inputs only

The user explicitly requested the Analog inputs step for the whole supplied day33
session. Use an isolated session-specific runner and local output directory
`D:/PreprocessPipeline/preprocess_tmp/RM018_day33_260611`; preserve the three existing
MergePoints epochs, all eight ADC identities, and native 20 kHz sampling. Do not run
ephys preprocessing, sorting, LFP, state scoring, or change source/session outputs.

### Steps

1. Check source stream metadata, sample counts, existing MergePoints, disk space,
   and whether task-owned outputs already exist.
2. Use the existing analog sidecar writer to extract and concatenate ADC channels.
3. Use existing analog pulse detection and plotting functions without changing
   thresholds, equations, channel identities, or sampling rate; save pulse events.
4. Run the existing Behavior sync inspection for camera ADC1 and record final
   execution results and output locations.

### Timing decision and corrected format finding

The existing generic analog export passes fixed 1250 Hz to its behavior builder
while Open Ephys analog sidecars retain native 20 kHz sampling. This standalone
execution passes the recording's actual native rate to the same builder, preserving
samples, scaling equations, and pulse detection settings. The generic exporter is
not changed. Contrary to the initial format concern, `atomic_savemat` already
supports MAT v7.3 and validates its structure without loading the full payload.
Generate the analog behavior MAT through that existing writer as well.

## Camera sync automatic detection: design discussion pending

The user requested considering Intan and Open Ephys behavior before implementing
automatic detection. No automatic detection source changes have been made.

- Existing digital Behavior readers select the channel with the most events,
  rather than validating each candidate against the video. Automatic selection
  should consider channel identity, timing, frame count, and epoch coverage.
- Intan digital words and Open Ephys TTL events require different input readers;
  existing acquisition metadata already preserves ADC and digital identities.
  Camera-specific candidate assessment can be shared after reading native times.
- The RM018 analog-only run wrote analogin.dat, its layout, pulse events, and a
  preview locally. Full analog behavior MAT export failed because h5py is missing;
  no h5py installation has been authorized or performed.
- Generic exported pulses contain no ADC1 pulses during CueChasing despite the
  bounded raw ADC1 read showing 40 Hz edges. Keep generic pulse detection unchanged;
  consider a separate camera edge detector and explicit provenance if approved.
- GUI existing-session resolution currently makes Behavior use the processed
  source session as its output path despite the displayed local working directory.
  This explains why locally generated pulse events are missed. No path fix has
  been made yet; preserve ephys resume semantics in any later correction.

Remaining work: agree on source readers, candidate acceptance and ambiguous-case
behavior before source edits; then address Behavior output lookup and finish the
requested analog MAT export if its required dependency is authorized. This update
used targeted source inspection only; no tests or execution were run.

## RM018 ADC1 threshold diagnosis and proposed minimal GUI impact

The user asked how to prevent the observed misses while minimizing GUI changes.
Read the existing local analog sidecar and reconstructed ADC1 level distributions
and threshold statistics across PRE/Cue/POST without altering any outputs.

- Cue ADC1: uint16 values 304..16736, median 16576; corrected range 0..16432.
- PRE/POST contain uint16 values up to 65520. Source inspection confirms the OE
  extractor reads int16 and casts to uint16 without an offset (-16 becomes 65520).
  Downstream pulse detection interprets these wrapped words as unsigned magnitude.
- Reconstructed shared threshold is 45210.5683 (4.5 times pooled standard deviation),
  above every Cue ADC1 value after baseline correction and global shift. Thus no
  Cue sample passes the binary threshold. Epoch boundaries used layout sample counts.
- All epoch effectiveness metrics exceed 0.9996; the channel rejection threshold
  0.3 does not explain this miss.
- Diagnostic first failed with Windows DLL exception in the directly launched
  Conda executable. Repeated once through conda run, using histogram moment sums;
  completed successfully. Temporary scripts were removed. No source edits or tests.

Proposed scope, still awaiting implementation agreement: preserve Intan unsigned
ADC semantics, decode OE signed ADC using acquisition metadata, then assess
camera pulse detection within its epoch rather than pooling session thresholds.
Keep continuous ADC data and generic event detection contracts; avoid adding GUI
controls for this repair. Confirm full Cue edge count and timing before claiming
complete recovery. Analog voltage scaling also needs acquisition-specific metadata;
legacy Intan scaling must not be applied indiscriminately to OE counts.

## Approved implementation on bugfix/openephys-adc-decoding

The user approved implementing the normal preprocessing correction and a separate
repair of this already processed session on a dedicated branch. Per-epoch camera
Low/High classification and new GUI controls are excluded. Existing dirty changes
remain in place; no commits or source data overwrites are authorized.

### Implementation steps

1. Preserve the existing sidecar bytes and decode signed OE versus unsigned Intan
   ADC using acquisition metadata; carry OE voltage gains to continuous exports.
2. Connect decoding to the existing preprocessing event export without changing
   pulse threshold constants or introducing per-epoch threshold classification.
3. Add an event-only repair mode for RM018 that reuses analogin.dat and writes to
   a separate local repair output; run ADC1 through the same corrected detector.
4. Inspect the scoped diff, perform at most one lightweight changed-file check,
   and report actual Cue pulse/frame alignment and any remaining detection failure.

OE Cue metadata reports bit_volts=0.0001525879 and units=V for ADC1/ADC2. Native
20 kHz timestamps must also be retained in OE continuous Analog exports. Intan
legacy scaling and sampling behavior remain unchanged in this correction.

### Material plan adjustment after the first repair attempt

Signed ADC1 decoding with the unchanged detector returned no events. The correction
therefore includes a narrowly scoped threshold change: only the explicitly selected
OE camera ADC can use global waveform midrange when the legacy threshold is at or
above its maximum. Existing effectiveness screening and all other channel threshold
rules are retained. This does not introduce per-epoch Low/High classification.
The existing Behavior ADC selector is forwarded into PreprocessConfig/event export;
no new GUI controls are added. The pulse output records the selected camera channel,
threshold, and method. Existing signed exports must also match the camera selection
before reuse. The first failed repair did not publish a pulse file.

### Completion and remaining boundaries

- Active branch: bugfix/openephys-adc-decoding. Earlier dirty worktree changes
  were retained; nothing was committed or pushed.
- Normal preprocessing receives the existing Behavior camera ADC selection and
  decodes OE ADC words as signed counts. OE continuous voltage uses recorded gains
  and the native ADC rate; Intan legacy scaling remains unchanged. No GUI controls
  were added. Old OE outputs without the decoding/camera metadata are not reused.
- The standalone ADC1 repair completed in adc_signed_repair. It retained native
  20 kHz timing and used a corrected-waveform threshold of 8216 counts. It found
  153392 Cue events, no PRE/POST events, versus 153391 tracking rows. Existing sync
  inspection reported a one-frame/0.025-second discrepancy. The saved pulse file
  retains all measured events; the extra event's position/origin is unresolved.
- Reviewed task-owned source diffs and runner changes. One lightweight AST syntax
  check passed on events.py, io.py, metafile.py, pipeline.py, gui/config_model.py,
  and the runner. No new tests or broad suites were added/run.
- The first production attempt (signed decoding, legacy threshold unchanged) found
  no events. The second, with the selected-camera-only midrange rule, completed.
- Full preprocessing, server execution, live GUI, and full continuous analog MAT
  export were not run. The earlier analog MAT export remains incomplete because
  this local environment lacks h5py; no dependency was installed for this change.
- Corrected camera events/report are local only; file-server publication and GUI
  display have not been performed. Existing raw data and prior exports are intact.

### Authorized publication

The user explicitly requested commit, push, and merge. Publish this topic through
bugfix/openephys-adc-decoding into the repository's default branch main. The fetched
origin/main matches the topic's starting commit, so no integration conflicts exist.
Include the related Keypoint loader, Behavior ADC plumbing, OE ADC correction,
session-specific repair runner, README, and this record. Exclude unrelated notebooks,
diagnostics, and the headstage topic record. Generated session artifacts stay local.
Reuse the recorded loader/frame checks, six-file syntax check, and actual ADC1
repair/sync result; no additional tests or broad validation were run for publication.
The one-frame discrepancy, missing local h5py for large continuous MAT export, and
unverified live GUI/server execution remain documented limitations. Publication
commit and merge identities are recorded in Git and the attached pull request.

### Merge held; server-side Behavior follow-up

The user explicitly requested holding the merge before any commit/push/merge was
executed, reported that the GUI still cannot find pulse events, and requested a
clearer camera sync selector. All topic files remain staged; no publication occurred.

1. Publish the measured camera ADC1 events to the selected file-server session,
   without overwriting an existing file or changing the source ADC. Mark the output
   camera-only so full Analog export cannot silently reuse it as an all-channel file.
2. Clarify the Behavior sync selection UI after the pending source-selection
   preference (automatic default versus explicit Digital/Analog) is resolved.
3. Reuse the measured 153392 versus 153391 result and preserve its warning. Perform
   one scoped changed-file check after the follow-up edits; keep merge on hold.

### Approved automatic source selection and neutral public naming

The user chose automatic camera sync as the default, with explicit selection only
when multiple candidates match. They also requested likelihood default 0 and neutral
Keypoint tracking labels because the source tool is not public. Remove its name from
new code/docs/log filenames before any commit or push.

1. Enumerate existing digital and ADC event channels and compare cadence/frame count
   with each recording's video/tracking; expose matching input names in the selector.
2. Carry automatic camera recovery into normal OE event export using native-rate
   pulse-spacing probes; keep the existing threshold recovery limited to confirmed
   camera candidates or an explicitly selected channel, without per-epoch level
   classification or changes to other Analog thresholds.
3. Update Behavior selection persistence, default likelihood, and public terminology.
4. Verify the supplied server session through automatic selection and one scoped
   changed-file check; keep merge held and preserve the one-frame warning.

Corrected camera-only events were newly published to the supplied file-server
session after confirming the target did not exist. No source ADC or previous output
was overwritten. Full Analog export now refuses to reuse a camera-only event file.
The user subsequently explicitly authorized file-server upload.

### Behavior export controls follow-up

The user requested a camera-input dropdown like tracking point, an overwrite
checkbox beside the bottom export action, and a clearer export button name.

1. Keep Auto as the default and list recorded inputs in the same dropdown widget
   as tracking point, immediately below tracking point.
2. Move overwrite into the bottom Export group and name the action Export Behavior;
   preserve the existing output directory and overwrite guard.
3. Finish the requested likelihood default of 0 in the processing entry point,
   review the scoped changes, and run one lightweight changed-file syntax check.

The one-frame warning represents 153392 measured pulses versus 153391 tracking
rows; index 153392 is the last pulse in one-based numbering. Truncation does not
establish that the extra pulse actually occurred at the end. Retain the measured
events and alignment behavior; keep merge held.

Completion: Camera sync input now uses the tracking-point dropdown style directly
below tracking point and lists all exported recorded inputs, while Auto still
requires a unique cadence/count match. Overwrite is in the bottom Export group;
the action is Export Behavior. Its output directory and overwrite guard are unchanged.
Likelihood defaults to 0 in both the GUI settings and the processing entry point.

The earlier production read of the supplied server session found Analog (ADC1) as
the single automatic match, with 153392 events versus 153391 tracking rows. The
one-frame warning remains. Reviewed the scoped UI/default diff; one AST syntax
check on gui/app.py and behavior.py passed. Live GUI interaction and full normal
preprocessing were not run. Other analog inputs and full analog MAT export retain
the previously recorded validation limits. Commit/push remain authorized; merge is
held. Unrelated notebooks, diagnostics, and headstage work are excluded.
