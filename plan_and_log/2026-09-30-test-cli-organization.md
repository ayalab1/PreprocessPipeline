# Test and CLI test organization

## Goal and scope

Organize tests and document targeted execution. The initial phases leave runtime
source unchanged; the user's later bug-fix request authorizes the specific source
changes recorded below. Preserve scripts, dependencies, scientific behavior and
meaningful regression conditions; add CLI coverage within the user's follow-up scope.
Create a pull request containing only this task's changes; preserve existing
untracked notebooks, diagnostics, and the headstage investigation record.

## Implementation steps

1. Separate existing sorter CLI tests from sorter partition tests.
2. Group GUI, environment setup, and MATLAB tests by their execution requirements.
3. Limit default pytest discovery to project tests and document group selection,
   CLI coverage, optional help checks, and temporary-directory handling.
4. Align stale test assumptions with current implementation, preserve meaningful
   assertions, and avoid excessive conditions or expensive routine execution.
   Execute only CLI/setup and lightweight input-validation tests as selected
   by the user; inspect remaining relevant contracts without running them.
5. Commit, push, and create a pull request with the actual validation limits.

## Decisions and validation

- CLI parser/dispatch tests remain distinct from subprocess import tests and
  real-data end-to-end execution.
- Updated the existing test allowlist in `.gitignore` for relocated files only;
  other locally ignored tests keep their existing ignore behavior.
- Initial organization added no new tests, fixtures, runners or CI workflows.
- The user expanded scope to update stale tests and keep verification practical,
  then clarified that useful cases must remain. Removed one duplicate custom
  destination/resume test from GUI settings; the output-transfer test retains
  the same basename, selected output path and external workspace assertions.
- Scoped execution: CLI/setup, Intan validation, disk space and input identity:
  **51 passed in 4.25 s**, using the existing Windows `preprocess` environment,
  disabled pytest cache and a unique OS temporary directory removed afterward.
- Kept POSIX permission coverage, but limited that check to POSIX platforms.
- Fixed the output-transfer test's hand-built JSON fixture (invalid for Windows
  paths) and check the decoded output path. This GUI test is not executed here.
- Static limitation: runtime JSON relocation currently replaces the unescaped
  filesystem path in serialized JSON. Windows JSON paths contain escaped
  backslashes, so this useful relocation regression can still fail on Windows.
  Runtime source remains unchanged; fixing relocation is separate work.
- Scoped diff reviewed: runtime source, scripts, dependencies and scientific
  parameters are unchanged. Only tests, test discovery/ignore rules and related
  documentation are included on `codex/organize-tests-cli`.
- Full suite, GUI, process lifecycle, MATLAB, POSIX and real-data execution were
  not run. The Windows JSON relocation issue remains for separate source work;
  the pull request must state this limitation and remain a draft.

## Follow-up: CLI channel consistency

The user explicitly requested new useful CLI tests, especially channel/bad-channel
consistency through preprocessing, postprocessing, Phy and CellExplorer. Runtime
source remains out of scope. Keep the cases small and avoid a combinatorial matrix.

1. Exercise the pipeline CLI with a small synthetic binary and independent manual,
   XML-skip and spike-group exclusions, retaining original binary columns.
2. Use real postprocess channel resolution and Phy export for raw-reference and
   copied-binary outputs; check persisted CellExplorer input metadata and geometry.
3. Check postprocess-only partition selection and meaningful CLI error/no-work
   behavior without launching GPU sorting, GUI or MATLAB.
4. Run only the CLI group once, correct test defects if necessary, review the diff
   and update the existing draft PR. Report actual source defects separately.

MATLAB CellExplorer execution and scientific curation remain outside validation;
the channel test will bypass curation while exercising the real channel and
export code.

The initial CLI run did not complete within the intended short-check window and
was stopped. Its exact interpreter, CLI selection and unique temporary-path
command were matched before stopping only the task-owned pytest PID; the shell
then removed its temporary directory. No passing result is claimed for that run.
Restrict Phy export to real binary/channel metadata without optional PCA,
amplitudes or display-template re-estimation. Scientific curation is also replaced
at its boundary. These feature computations are outside the channel test's claims.

The second attempt also did not finish and was stopped after matching the
task-owned interpreter, pytest command and unique temporary path. No new CLI
case has a confirmed runtime result. Do not attribute the delay to a specific
computation without evidence. No environment changes or further runs were made.

Separated the cross-stage case with a registered `integration` marker and moved
heavy postprocess imports inside it. Routine examples select `not integration`;
there is no global skip or xfail. Light error cases patch the package's lazy
dispatch at its dictionary boundary, avoiding an unnecessary scientific import.
Added five tests total, preserving the original two. Runtime source remains
unchanged. The new integration test's real data/channel code and the lighter CLI
cases require runtime verification in a responsive environment.

Scoped source/diff review confirms only tests, pytest/ignore selection rules and
related documentation changed. Follow-up checks cover the matching one-based
spike groups and Phy/CellExplorer channel coordinates too. The same draft PR #24
is updated; the older Windows JSON relocation limitation remains unchanged.

## Follow-up: CLI contracts and mixed acquisition inputs

The user requested implementation and verification of the proposed metadata,
mode-dispatch and result/error contracts, plus mixed Intan/Open Ephys/WILD inputs.
Treat "Inman" as Intan. Runtime source remains outside scope.

1. Extend the existing channel integration case with sampling rate, dtype,
   sample-count/duration and successful CLI result checks.
2. Add small mode-dispatch and malformed-config cases at the CLI boundary.
3. Add one three-format synthetic preprocessing case covering explicit epoch
   order, OE embedded ADC separation, WILD 1250 Hz analog normalization and
   unchanged source files; cover incompatible rates/channel counts separately.
4. Run only the requested CLI cases and relevant existing lightweight acquisition
   checks. Capture a stack trace if a run stalls, correct test defects within
   scope, and report source defects rather than relaxing meaningful assertions.
5. Review the task diff and update the existing draft PR with actual results.

### Results

- Added eight selected CLI cases (15 CLI cases total): three dispatch modes,
  malformed-config handling, three-format preprocessing, OE/WILD common-rate
  rejection, and ephys-width rejection. Extended the existing channel integration
  case with sampling rate, dtype, sample count/duration and success JSON checks.
- Normal mixed preprocessing uses the real OE reader, catalog, amplifier/analog
  writers, MergePoints and session metadata. It preserves the selected WILD/OE/
  Intan order, excludes the embedded OE ADC from ephys, normalizes analog to
  1250 Hz, pads absent ADC identities, zeroes bad ephys columns and leaves sources
  unchanged. TTL/camera synchronization and multi-day symlink staging are not
  covered; synthetic Intan ADC identities use the documented positional fallback.
- Corrected fixture mistakes: conventional OE date-directory naming, top-level
  GUI subsession-order settings, NumPy file writing at long Windows paths, and
  explicit two-probe assignment (XML anatomical groups default to one probe).
  These preserve the intended conditions and assertions, rather than hiding a
  runtime failure. One temporary-runner attempt had a missing parent directory
  and produced setup errors only; the parent is now created before pytest.
- Captured a stalled integration stack in Numba's cache-file creation during
  postprocess import. Stopped only the verified task-owned pytest PID. Redirecting
  NUMBA_CACHE_DIR to the unique OS temporary root allowed execution to finish;
  JIT remains enabled, environment settings are restored, and both Numba/pytest
  directories are removed after process exit. No dependencies or installed
  environment files were changed. This identifies the current stall location,
  not the precise filesystem reason or the untraced earlier stalled runs.
- Scoped combined run: **19 passed, 1 failed in 18.18 s** (15 CLI cases plus five
  existing Intan/WILD/analog checks). The failure exposed the missing two-probe
  fixture setting. After correction, only that named test was rerun: **1 passed
  in 14.61 s**, including 12.74 s in its body. Thus all 20 distinct selected cases
  have passing results across the combined run and focused rerun, not a single
  all-pass group run. Mixed normal preprocessing took 0.53 s.
- No full suite, GUI, MATLAB, hardware acquisition, real-session processing,
  scientific curation, LFP validation or cluster execution was run. Runtime source
  is unchanged. The Windows JSON relocation limitation remains separate, so PR
  #24 stays draft; this follow-up resolves the newly added CLI validation gap.

## Follow-up: Windows relocation and reported concat stall

The user now requests handling the source issues and a Windows concatenated-dat
stall reported by another user. The input type, output storage and last log are
unknown, and the user's own environment does not reproduce it. The user notes
that OE normally puts ADC columns last; that tested layout works, so interleaved
OE layout concerns are deferred rather than changing its reader speculatively.

1. Fix escaped Windows JSON paths during staged output relocation by decoding
   and recursively rewriting string values, retaining atomic publication.
2. Add flushed, phase-specific diagnostic messages around concatenated binary
   writing, size validation and final publication, including requested worker/
   pool settings, binary dimensions and installed SpikeInterface version.
3. Preserve processing algorithms, worker defaults, dtype, channels and inputs;
   do not attribute the unreproduced stall to multiprocessing or change engines.
4. Run one existing named filesystem relocation regression, with offscreen Qt,
   disabled pytest cache and isolated temporary directories. Inspect writer changes
   without launching a broad pipeline or multiprocessing experiment.
5. Review the focused diff, record remaining uncertainties and update PR #24 to
   reflect the user-authorized source scope and actual validation.

### Results

- Changed only the generic JSON relocation branch in `src/preprocess/gui/app.py`
  to parse and recursively rewrite strings, including keys to retain existing
  POSIX replacement semantics. Serialization escapes destination paths correctly;
  publication stays atomic and unchanged JSON is not rewritten. The completed
  YAML record's special external-workspace rule is unchanged.
- Existing named filesystem regression passed on Windows: **1 passed in 2.85 s**,
  including 0.11 s in its body. It verifies the decoded sorter output path, YAML
  recovery path, custom-destination XML/RHD retention and local cleanup. Used
  offscreen Qt, disabled pytest cache and isolated Numba/pytest temporary folders
  cleaned after exit. No interactive GUI, full GUI group or broad suite was run.
- Added flushed diagnostic phases around `write_concatenated_dat`: writing,
  validating, publishing and complete, with failure-stage exception notes. The first message records paths,
  frames/channels/dtype, expected bytes, requested workers/pool and SI version.
  Writer behavior and processing settings are unchanged; source/diff inspection
  only for this diagnostic change, with no multiprocessing or data-scale run.
- Inspected the actual installed/pinned SI 0.103.2 writer and executor. It
  preallocates the binary before chunk processing and uses a process pool when
  the GUI requests it. Thus file size is not completion evidence. No available
  evidence attributes the other user's stall to file allocation, worker startup,
  computation, storage or final publication; there is no reproduced concat bug
  or confirmed resolution. No speculative engine/dependency change was made.
- OE reader source is unchanged following the user's standard trailing-ADC
  clarification. The tested trailing-ADC layout works; interleaved-ADC concerns
  remain unverified/deferred rather than being represented as a confirmed bug.
- Scoped source/diff review completed. Update the same PR #24 to include this
  newly authorized source scope, retain its draft state and distinguish the
  prior 20 passing CLI/acquisition cases from this one new regression run.

## Follow-up: output transfer progress

The user requests a visible start log and progress during the final transfer to
storage. Preserve staged copying, content verification, rollback, metadata
retention and cleanup order.

1. Add optional transfer logging with byte progress during copying and large-file
   verification, throttled to avoid flooding the GUI log.
2. Connect the GUI log and repaint during synchronous transfer, and log failures.
3. Extend the existing relocation regression to exercise the progress callback
   alongside its existing metadata and cleanup assertions; run that named test
   only, using isolated OS temporary directories and disabled pytest cache.
4. Review the scoped diff, record the actual check and limitations, and update
   draft PR #24.

### Results

- Added an optional progress callback to storage transfer and connected it to
  the GUI log. The log identifies source/destination at start, aggregate copying
  bytes/percentage, content verification, publication, permissions and cleanup.
  Large-file copying and hashing report about once per second; phase boundaries
  report immediately. Copying 100% precedes verification and cleanup.
- With a callback, regular files copy in 8 MiB chunks and retain stat metadata;
  directory symlinks remain links and their target bytes are excluded from the
  progress total. Calls without a callback retain `shutil.copy2`. Staging,
  signature validation, rollback and local-deletion order are retained.
- GUI event processing updates the log during synchronous transfer while
  excluding user input. Failures are logged as well as shown in the existing
  error dialog. No new worker, cancellation mechanism or transfer algorithm
  outside this request was introduced.
- Extended the existing named relocation regression with a nested file over
  8 MiB, exact output-content checks, aggregate progress including metadata,
  start/completion messages and storage-verification-before-deletion ordering.
  **1 passed in 3.25 s**, including 0.20 s in the test body, on Windows with
  offscreen Qt. Pytest cache was disabled; isolated pytest/Numba temporary
  directories were removed and temporary environment settings restored.
- Reviewed the scoped source/test diff. Interactive GUI repaint, network or
  data-scale transfer, failure/corruption paths and the full test suite were not
  run for this follow-up. The external concatenated-dat stall remains
  unreproduced; this progress change is not a claimed resolution of its cause.

## Follow-up: bounded Windows CI

The user asks how to add CI after confirming that neither main nor PR #24 has
workflow definitions. Add a single GitHub Actions job for the already-selected
CLI and output-transfer regressions; leave runtime source and test inputs alone.

1. Add a Windows/Python 3.11 workflow triggered by pull requests, main pushes and
   manual dispatch. Use the declared project/dev dependencies and the existing
   Windows NumPy baseline, with pip download caching.
2. Select `tests/cli` (including the two bounded synthetic integration cases)
   plus the named output-transfer regression. Use offscreen Qt, isolated OS
   temporary pytest/Numba directories, disabled pytest cache and cleanup.
3. Document job scope and where to see results; inspect the workflow diff and
   update the existing PR. Do not add an OS/version matrix or broad test suite.
4. Push the workflow to trigger the PR run, collect its final result if available,
   and record CI failures or execution limitations accurately.

### Implementation checkpoint

- Added one Windows job, with a 15-minute overall limit and a five-minute test
  step. It installs `.[dev]` plus NumPy 1.26.4, caches pip downloads and selects
  the existing CLI group plus the named transfer regression (16 cases expected).
- The workflow uses read-only repository permission, ordinary `pull_request`
  execution and no persisted checkout credentials. Repeated updates to the same
  PR cancel obsolete runs. Manual dispatch becomes available on the default
  branch. No runtime source, fixtures, scientific settings or dependency
  manifests were changed.
- Reviewed the workflow YAML and PowerShell execution/cleanup sequence against
  GitHub's current action and event documentation. No local test run or local
  dependency installation was performed for this configuration change.
- CI execution is pending the first push of this checkpoint. The PR Checks tab
  records each run against its commit; report its observed result in the PR
  validation section rather than treating configuration inspection as CI success.

### First CI result and dependency correction

- GitHub Actions run 36812290670 at head `5c52f8b` executed all selected cases:
  **15 passed, 1 failed in 26.24 s**. The mixed Intan/OE/WILD case failed while
  constructing the OE reader: Neo 0.14.5 rejects `load_sync_channel`, which the
  pinned SpikeInterface 0.103.2 passes to `OpenEphysBinaryRawIO`.
- Verified the actual installed local Neo 0.14.4 API and upstream 0.14.4/0.14.5
  reader signatures plus SI 0.103.2's argument mapping. Its declared minimum
  Neo version is 0.14.3; the Linux manifest already pins that version.
- This concrete CI failure extends the scope to the relevant dependency
  manifests: constrain project Neo to `>=0.14.3,<0.14.5` and explicitly pin
  Windows Conda Neo to the working local 0.14.4 baseline. Leave the Linux pin,
  reader source, test assertions/inputs and numerical settings unchanged.
- Review only the new manifest/documentation diff and rerun the same bounded CI
  job through the corrective push. No local environment repair or broader
  validation is needed.
- Corrective run 36812682765 at head `a77a0ec` succeeded: **16 passed in 27.05 s**,
  with Neo 0.14.4 installed. Channel/Phy took 18.42 s, mixed preprocessing 0.30 s
  and transfer 0.11 s. The job completed its cleanup/cache steps successfully.

### Scope clarification: basic checks for incoming PRs

The user wants CI to detect basic regressions when other contributors open PRs.
Extend the one Windows job with existing short setup, Intan input-validation,
disk-space and input-identity modules, plus the two existing move failure/content-
corruption regressions. Keep the CLI/channel/Phy/mixed-input cases and successful
transfer regression. All selected files are tracked, and tests use small inputs
or test doubles; no new tests or full-suite selection is needed.

1. Make the selected paths explicit in the workflow and rename the job to
   `Windows basic checks` to reflect its purpose.
2. Update the CI scope documentation and keep ordinary `pull_request` triggering
   with read-only permission for incoming contributions.
3. Push this selection, collect the bounded CI result, and record actual failures
   or limitations without expanding into scientific or real-data validation.

All selected modules and the vendored sorter setup metadata they inspect are
tracked. Reviewed the new selection/PowerShell array and documentation diff.
No local test run was added; the expanded selection will be validated by the
same single Windows CI job. The earlier corrected 16-case run is passing.

### Basic-check result

- GitHub Actions run 36813003995 at head `4d58301` completed successfully:
  **67 passed in 26.66 s**. It covers the selected CLI/channel/Phy/mixed inputs,
  setup configuration, Intan validation, disk budgets, input identity and three
  transfer success/failure/content-corruption cases. Channel/Phy took 17.76 s;
  mixed preprocessing took 0.33 s. Job setup, cleanup and cache steps succeeded.
- Kept one Windows/Python 3.11 job and the original 15-minute job/five-minute
  test limits. No new test cases, runtime source edits or local dependency
  installation were needed for the expanded basic checks.
- Source/diff review and scoped CI execution are complete. Record the result in
  PR #24; this final log-only update retains the verified test selection. Full
  suite, other OS/Python combinations, GPU sorting, interactive GUI, MATLAB,
  real-data processing and the external Windows concat stall remain unverified.

### Linux CI follow-up after PR #24 (2026-10-01)

The user merged PR #24 and clarified that Linux servers are the primary runtime.
Add Linux basic checks in a separate PR based on merged `main` (`b97a39f`), while
retaining Windows coverage. Both environment manifests use Python 3.11 and NumPy
1.26.4. Keep the same 67 existing regressions and CPU-only project/dev install;
no runtime source, scientific settings, dependency manifests or test edits.

1. Convert the Windows workflow to one shared basic-check workflow with Ubuntu
   24.04 and Windows jobs; keep the existing Windows check name and time limits.
2. Use an inline Python runner for the common test selection, subprocess exit
   status and cleanup of unique OS-temporary pytest/Numba directories.
3. Update the CI scope documentation, inspect the focused diff, and open the
   Linux follow-up PR.
4. Collect both scoped CI results and record actual failures or remaining limits.
   Hosted Ubuntu checks do not establish Slurm, CUDA or production-server behavior.
