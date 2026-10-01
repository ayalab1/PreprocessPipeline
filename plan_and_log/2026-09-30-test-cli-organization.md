# Test and CLI test organization

## Goal and scope

Organize tests and document targeted execution without changing runtime
source code, scripts, dependencies or scientific behavior. Preserve meaningful
regression conditions, and add CLI coverage within the user's follow-up scope.
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
