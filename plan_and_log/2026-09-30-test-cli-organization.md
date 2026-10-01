# Test and CLI test organization

## Goal and scope

Organize existing tests and document targeted execution without changing runtime
source code, scripts, dependencies, scientific behavior, or test assertions.
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
- No new tests, fixtures, markers, runners, or CI workflows are in scope.
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
