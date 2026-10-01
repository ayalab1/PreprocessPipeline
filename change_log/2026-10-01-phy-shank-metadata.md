# Phy shank metadata

Future native Kilosort1, Kilosort2.5 and Kilosort4 outputs and postprocessed Phy
exports write `channel_shanks.npy` and `channel_probe.npy` when source geometry
defines shank IDs. Existing sessions are not migrated.

The native hook runs after compact sorter channels are remapped to original
binary columns. Postprocessing uses the recording's contact vector and the
exporter's original channel IDs, including when the exported binary is compact.
Both paths align metadata with the actual exported channel order.

Labels are zero-based. Shanks are numbered by sorted `(probe, shank)` pairs,
preventing repeated local shank IDs on separate probes from mixing channels in
Phy's waveform selection. Labels are relative to available source geometry and
need not match XML anatomical-group numbers. Missing metadata leaves existing
behavior intact; invalid IDs/coverage warn and do not replace existing labels.

The change does not alter sorter settings, binary samples, channel maps,
coordinates, spike assignments or scientific feature calculations. It uses the
Python export hooks rather than modifying vendored sorters.

Regression coverage includes all three native sorter paths with simulated
sorter output, reordered/noncontiguous channels, repeated shank IDs across
probes, missing/invalid metadata, and real SI exports with external and copied
binaries. The existing channel identity integration also checks the new files.
The native regression file is included in Linux/Windows basic CI checks.

Windows validation: **84 passed** in 32.36 seconds using the complete updated
basic-CI test selection, including the new export checks. The existing
`preprocess` environment supplied SI 0.103.2; pytest and the repository-supported
Neo 0.14.4 were supplied from an isolated temporary dependency directory without
changing the Conda environment. Expected synthetic-input/dummy-probe warnings
were reported. `git diff --check` passed.

No real GPU/MATLAB sorting or interactive Phy session was run, and HP19 day10
outputs were not modified.

CI follow-up: Windows passed all 84 cases, while Linux passed 83 and failed the
native Kilosort1 case because the existing default path used `Kilosort1` instead
of the checked-in `KiloSort1`. The API and CLI defaults now match the actual
directory. A spelling regression catches this even on case-insensitive Windows;
explicit user-supplied paths still take precedence. All 18 sorter/CLI checks
passed locally after the correction. The CI selection now includes 85 cases.
