# Project tests

Run commands from the repository root using the existing `preprocess` environment
with pytest installed. Tests import the checkout's `src` package, so use
`python -m pytest`. No runtime source changes are needed to select a test group.

Default pytest discovery is limited to `tests/` by the root `pytest.ini`.
Vendored tests under `external/` and `sorter/` are outside the project suite.
MATLAB tests are run separately.

## Groups

| Path | Existing coverage | Execution requirements |
| --- | --- | --- |
| `tests/cli/` | Pipeline/sorter CLI arguments, bad-channel errors, no-work handling and cross-stage channel identity | Routine cases bypass sorting; the `integration` case uses real preprocessing and Phy binary/channel export |
| `tests/preprocess/` | Input validation, disk budgeting, multi-day preparation, sorter partitions/channel mapping, state-scoring memory | Pipeline Python dependencies; synthetic inputs and existing test doubles |
| `tests/execution/` | Local backend lifecycle/identity, session claims, GPU selection, worker allocator setup | Some tests start subprocesses; Windows/POSIX tests retain their existing skip conditions; GPU queries are mocked |
| `tests/gui/` | GUI settings, XML/probe selection, run setup, output transfer and recovery | PySide6 and the pipeline dependencies; use Qt's offscreen platform |
| `tests/setup/` | Conda/uv setup configuration, vendored dependency selection and environment safety | PyYAML and pytest; setup/install calls are mocked; one test starts a Python subprocess |
| `tests/stability/` | Channel MAD computation, filtering, plots and multi-day channel metadata | NumPy, SciPy, pandas, Matplotlib and pipeline dependencies |
| `tests/matlab/` | MergePoints folder naming/path resolution and waveform preservation | MATLAB and the bundled MATLAB/CellExplorer helpers |

These are existing regression tests. They do not establish real-data pipeline,
GPU sorter, Slurm cluster, or interactive GUI correctness.

Useful regression cases are retained even when they need an optional environment.
The POSIX permission-bit check is skipped on Windows because it does not test
Windows ACLs. Symlink tests require permission to create symlinks.

## Targeted Python execution

Choose a group, file, or named test deliberately. For example, the existing CLI
group is selected with `tests/cli`, and a single test with
`tests/cli/test_sorter_runner.py::test_run_sorter_cli_passes_active_and_excluded_channels`.
The GUI group is now selected with `tests/gui`, and environment setup with
`tests/setup`; sorter partition tests remain in `tests/preprocess`.

For a short routine check, select the existing CLI/setup tests and small input
validation tests together:

```text
python -m pytest tests/cli tests/setup tests/preprocess/test_intan_validation.py tests/preprocess/test_disk_space.py tests/execution/test_input_identity.py -m "not integration" -q -p no:cacheprovider --basetemp <unique-OS-temp-directory>
```

This selection does not launch a GUI, sorter, worker job, or Slurm job. The setup
tests include one short Python subprocess. Before the additional channel CLI
cases, the selection ran 51 cases in 4.25 seconds on the Windows `preprocess`
environment; the expanded selection has not been verified. GUI,
process lifecycle, scientific/plotting, and MATLAB groups remain separately
selectable. No new parameter combinations or exhaustive test matrix are added.

Keep pytest cache disabled and use a fresh temporary directory outside the
repository. Do not pass the temporary root itself as `--basetemp`.

PowerShell example (after activating `preprocess`):

```powershell
$testTemp = Join-Path ([System.IO.Path]::GetTempPath()) ("preprocess-tests-" + [guid]::NewGuid().ToString('N'))
try {
    python -m pytest tests/cli -m "not integration" -q -p no:cacheprovider --basetemp "$testTemp"
    $testExitCode = $LASTEXITCODE
} finally {
    # The unique path was created beneath the OS temporary directory above.
    if (Test-Path -LiteralPath $testTemp) {
        Remove-Item -LiteralPath $testTemp -Recurse -Force
    }
}
if ($testExitCode -ne 0) { throw "pytest failed with exit code $testExitCode" }
```

For GUI tests, set `$env:QT_QPA_PLATFORM = 'offscreen'` before the command.

POSIX example:

```bash
test_temp=$(mktemp -d "${TMPDIR:-/tmp}/preprocess-tests.XXXXXXXX")
python -m pytest tests/cli -m "not integration" -q -p no:cacheprovider --basetemp "$test_temp"
test_exit_code=$?
rm -rf -- "$test_temp"
(exit "$test_exit_code")
```

For GUI tests, prefix the Python command with `QT_QPA_PLATFORM=offscreen`.
Replace `tests/cli` with the selected group, file, or named test. Only select
`tests` for a full project run when that broader validation is intended.

## CLI coverage and optional launch checks

`tests/cli/test_sorter_runner.py` preserves the two existing tests:

- Explicit `--active-channels` and `--exclude-channels` values reach
  `execute_sorting_job` as zero-based integer lists.
- Omitting these options forwards `None` for both lists.

They call `build_parser()` and `run_sorter_cli()` directly and replace sorter
execution with a monkeypatch. They do not launch the module as a subprocess or
run a sorter. Subprocess import tests in `tests/execution/` and `tests/gui/`
test import behavior, rather than CLI parsing or full pipeline execution.

The added routine cases check a missing XML before sorting, an all-excluded
sorter no-work result, a pipeline bad-channel ID beyond the binary width, and an
invalid CLI mode in a real module subprocess before output creation.

Select the cross-stage channel check separately with
`python -m pytest tests/cli -m integration` and the same cache/temp arguments.
One eight-channel synthetic recording combines manual exclusion, XML skip and
omission from spike groups. The check follows these contracts:

- Preprocessing retains all binary columns and zeroes bad columns; postprocessing
  selects good channels by their original zero-based IDs.
- Raw-reference Phy output keeps the full binary width and original column IDs.
  Copied-binary Phy output uses compact indices, while `channel_map_si.npy`
  preserves the original IDs. Both mappings address the correct binary samples.
- The CellExplorer input `session.mat` uses one-based bad/electrode channels and
  the full binary width; `chanCoords` rows agree with the corresponding chanMap.
- Postprocess-only CLI execution respects a selected probe partition without
  treating original IDs as compact indices; source input samples remain intact.

This case uses real preprocessing, postprocess recording resolution, a small
analyzer and Phy export. It replaces scientific curation and disables exporter
PCA/amplitude computation and display-template re-estimation. MATLAB CellExplorer,
GUI interaction, GPU sorting and scientific feature validity are not verified.
Two CLI-group attempts did not complete within the intended short-check window
and were stopped without a result; new cases remain runtime-unverified. The
integration marker is registered but not excluded globally: choose the routine
or integration command deliberately.

When a launch/import check is needed, choose an entry point explicitly:

```powershell
python -m src.preprocess.sorter_runner --help
python -m src.execution.controller --help
python -m src.execution.worker --help
```

The installed console equivalents for the latter two are
`preprocess-run-controller --help` and `preprocess-stage-worker --help`.
Help checks confirm imports and parser startup only. They do not test controller
actions, worker execution, or sorting. The existing suite has no dedicated
controller/worker CLI argument tests; adding coverage is separate work.

Real execution uses data/output paths and can write results, submit jobs, retry
stages or cancel active work. Define the input, destination, command and expected
result separately before using those actions as an end-to-end test.

## MATLAB

From the repository root in MATLAB:

```matlab
results = runtests(fullfile('tests', 'matlab', 'test_mergepoints_foldernames.m'));
assertSuccess(results);
```

The existing test adds its bundled helper paths temporarily and restores the
MATLAB path at teardown. Its synthetic files live in a MATLAB temporary folder.
