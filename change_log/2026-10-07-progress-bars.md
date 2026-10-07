# Persistent Run progress display

Persistent Local and Slurm workers no longer override `progress_bar=False` for
preprocess, sorting or postprocess. They retain the scientific configuration's
progress setting (enabled by default in the GUI), while still applying the
requested CPU count and existing thread limits. This restores SpikeInterface's
progress output for concatenated dat/LFP writing, sorter binary preparation,
analyzer computations and Phy export wherever those operations report progress.

The GUI's main Log converts carriage-return redraws into separate lines instead
of deleting their boundaries. Percentages, counts and ETA remain readable across
polls, even before an operation writes a terminating newline. Ordinary CRLF log
lines, warnings and the existing stage monitor remain supported. Native sorter
verbosity and the existing Kilosort log discovery are unchanged.

The regression checks cover default-enabled and explicitly disabled progress in
all three worker stages for Local/Slurm attempt specifications, actual tiny
binary writes with one/two workers, and offscreen GUI log polling. They do not
launch a GPU sorter, MATLAB or a Slurm job. These cases are included in the Linux
and Windows basic CI selection.

Local validation on Linux using SpikeInterface 0.103.2 passed all 101 cases in
the updated basic CI selection, including the 16 progress-related checks.
Windows CI and real-data/GPU/MATLAB/Slurm execution were not run locally.

Workers that are already running keep their loaded configuration; restarting
the GUI alone cannot enable progress in those workers. New workers use the
corrected settings, and a newly started GUI uses the corrected log rendering.
