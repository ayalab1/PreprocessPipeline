# WILD-NP NP1 input

This route reuses the existing NP1 geometry, original-column channel map and
common Kilosort4 runner. TeraSort is not required. It accepts a day directory,
a capture directory or an individual segment. Discovery follows recording
files and metadata recursively; capture names need not start with NP_SESSION.

## Use

Launch this checkout with the existing `preprocess` environment, from
`D:\PreprocessPipeline-integrating-wild-np`:

```powershell
conda activate preprocess
python -c "from src.preprocess.gui import main; raise SystemExit(main())"
```

Restart the GUI after updating this checkout, then:

1. Browse to the raw day, capture or segment as Basepath. For example, select
   `R:\shared\data\Neuropixels\NP1.0\RM034\RM034_261005_day07` itself.
2. Check the WILD-NP summary in **Session and channel map**. It shows the detected
   probes, saved/active channels, segments and the physical port for each group.
   Discovery or mapping errors appear in this panel and the log.
3. The geometry selector is populated with `Neuropixels 1.0` for each recorded
   probe. This replaces the old `NeuroPixel` channel-order template. The saved
   binary-column/hardware-channel/site mapping selects contacts from the shared
   960-site NP1 catalog; XML channel order alone cannot identify those sites.
   Other probe models are unsupported for these NP1 recordings and produce an
   error if selected. Channel groups come from the recording and are read-only.
4. Leave XML empty; it is generated together with chanMap in the output directory
   when running. **Generate chanMap** can also create these metadata files before
   a run. Select a separate Local working dir and use a fresh output directory
   with overwrite disabled.
5. Kilosort4 and independent probe partitions are selected automatically when the
   recording is loaded. Analog/digital export, state scoring and artifact
   interpolation are initially turned off because this NP route does not support
   them. For recorded LF export, enable LFP and use 1250 Hz.

Probe x offsets are editable in micrometres. For multiple probes the defaults
are 0, 2000, 4000, ... in physical-port order; a single probe defaults to zero.
Each offset translates that probe's NP1 site coordinates. The same coordinates
appear in the preview, chanMap and session exports, without an additional display
offset. Explicit assignments are retained when saving/loading GUI configuration.
The offsets are user-defined placement values, not measured inter-probe anatomy.
Recorded site/channel IDs and independent sorting per physical probe are unchanged.

The channel-map preview fills the central viewer with a shared grid and equal
x/y scale for all probe types. The coordinate ranges expand to the available
viewer area, preserving the configured probe spacing. The legend stays in the
upper right. Reset/help controls and permanent status text are omitted.
The mouse wheel zooms both axes around the cursor. Left-drag zooms a region,
right-drag pans, and a double-click restores the full range.

For NP1, the preview includes all 960 physical sites per probe. Active sites use
the probe color; inactive sites, including unrecorded and excluded sites, are
gray. Zoom-aware markers follow coordinate spacing and remain small in the full
view. This display follows the approach in
[Atlaxis ProbeView](https://github.com/yoshihito-saito/Atlaxis/blob/395c5f7a124ecea02a1978939e4c60baa03f4f87/src/probe_planner/rendering/probe_view.py).
Marker dimensions are display settings, not electrode-size measurements.
A hover tooltip shows the original zero-based channel ID when recorded, site ID,
coordinates and status. Unrecorded sites show no recorded channel; their display
does not add channels to the saved map or change sorting.

The common settings panel starts at about 620 px wide and cannot shrink below
520 px. Geometry selectors reserve their own minimum width, with full model names
available on hover. These layout changes also apply to non-NP probes.

For anatomical labels, choose the recording Basepath and a separate local
output directory, then use **Edit anatomical map**. NP groups are obtained from
the recorded physical-probe map; a manual or pre-generated XML is not required.
Select contacts by their recorded site coordinates and assign the region names
established from anatomical evidence. Nominal probe geometry alone does not
identify a brain region. The editor shows zero-based recorded channel IDs.

The saved **anatomical_map.csv** keeps one column per physical probe and one row
per recorded channel in that probe's original order, matching the generated XML.
Inactive channels without coordinates remain as rows but are omitted from the
graphical editor, so later labels do not shift to another channel. Use **Load
anatomical map** to reuse a CSV made for the same recording/site mapping. Creating
the generated XML does not clear the current NP labels.

**Load anatomical map** also accepts the per-probe CSV exported by Atlaxis
(`channel_id,site_id,shank,region,is_target`, including `*.active_channels.csv`).
For two probes, choose the destination physical probe in the import dialog.
Probe-local hardware channel IDs and NP1 site IDs are checked against the
recorded chanMap before any labels are applied; a different IMRO routing is
rejected. The `is_target` flag does not filter regions. Inactive recorded columns
without a verified site remain blank. Import replaces labels only on the chosen
probe, so load each probe's export separately.

After import, use **Edit anatomical map** to review and save. The saved
**anatomical_map.csv** remains the existing headerless CellExplorer matrix:
columns follow the generated XML groups and rows follow each group's recorded
channel order. Atlaxis channel/site columns are input metadata and are not
written into this file. An imported region is anatomical evidence from the
Atlaxis project, not independent confirmation of the recorded contact position.
The supported export contract is
[Atlaxis prepare_channel_export](https://github.com/yoshihito-saito/Atlaxis/blob/395c5f7a124ecea02a1978939e4c60baa03f4f87/src/probe_planner/project/bundle.py).

Recorded LF is low-pass filtered per segment and resampled to the configured rate;
it is never generated from the AP file.

The existing Python API is also available:

```python
from pathlib import Path
from src.preprocess import PreprocessConfig, run_preprocess_session

config = PreprocessConfig(
    basepath=Path(r"R:\shared\data\Neuropixels\NP1.0\RM034\RM034_261005_day07"),
    localpath=Path(r"D:\PreprocessPipeline-integrating-wild-np\sorting_temp"),
    sorter="kilosort4",
    sorter_partition_mode="probe",
    make_lfp=True,
    lfp_fs=1250,
    analog_inputs=False,
    digital_inputs=False,
    state_score=False,
    overwrite=False,
)
# Explicitly run this only when ready for full preprocessing and sorting:
# result = run_preprocess_session(config)
```

## Counts, gains and channels

- Source AP and LF binaries are little-endian signed int16 containers. The signed
  format declares `saved_count = 512 - raw10`, 10 ADC bits and nominal limits
  -511 through 512. The reader does not subtract 512 or invert polarity.
  Legacy unsigned-code metadata is recognized separately; the two encodings
  cannot be mixed in one session. Saturation limits describe the ADC, not int16.
- Hardware gain indices come from each interval's applied configuration.
  `gain_to_uV = 1.2e6 / 1024 / amplifier_gain` defines the nominal scale.
  AP filters/reference operate on counts; AP binary writes do not apply this
  microvolt multiplier. The scalar-scale path requires uniform active-channel
  gains. AP gain 500 corresponds to 2.34375 uV/count; source LF gain 250 to
  4.6875 uV/count.
- Derived LF uses AP storage units: after filtering/resampling, multiply counts
  by `source_lf_gain_to_uV / ap_gain_to_uV` (2 here), round to the nearest integer
  and save int16. Nonfinite values or int16 overflow raise an error. Thus the
  existing CellExplorer `leastSignificantBit` converts both AP and derived LF
  to nominal microvolts correctly. Original LF files retain their own scale;
  source/output scales and the count multiplier are recorded in metadata.
- Gain calibration was not applied by this storage format. ADC calibration is
  unknown from saved metadata. Neither nominal scaling nor firmware readback
  establishes calibrated analog amplitudes.
- `chanMap0ind` always indexes the original binary columns. Physical port,
  hardware output channel, site and coordinates remain separate fields. The
  two-probe file retains all 768 columns; the supplied configuration has 766
  active sorting sites. Inactive columns are excluded from reference/sorting
  and may be zeroed in processed output by the existing `zero_bad` setting.

## Evidence and admission

Post-stop `neuropixels_probeN_metadata.json` receipts remain authoritative when
present. Without them, this segment must contain all of:

1. A per-probe writer manifest declaring `device_confirmed_requested` and naming
   the local request and device receipt.
2. An `applied` startup receipt with firmware configuration ID, CRC32 and
   verification level 3 for each saved physical port.
3. The named NP1 request and its byte-identical original IMRO.

This binding relies on the recording writer's confirmation before capture
release. Firmware ID/CRC values are recorded as reported, not claimed to have
been recomputed from JSON/IMRO; SHA256 hashes retain the actual evidence files.
A requested configuration or IMRO alone is insufficient. The current startup
adapter supports the observed NP1 external-reference configuration; other
startup reference encodings fail explicitly. It never borrows a receipt or a
serial number from a different interval. Unknown identity remains unknown.

A data-bearing incomplete interval is admitted when AP length matches complete
saved rows and the stream/capture metadata report zero frame/counter errors,
relocks, USB sequence gaps and firmware recording faults. This is structural
admission of the saved prefix, not verification of analog signal quality or
payload bit integrity. An ambiguous data-bearing interval raises an error;
it is not silently trimmed or skipped. Empty/missing AP attempts are excluded
and their paths, reasons and status logs are recorded in output metadata.

Before concatenation, rates, encoding, saved width, physical-port order,
applied ID/CRC, site mapping, gains and reference/high-pass settings must agree.
Confirmed serials must agree at each port; missing serials do not become known
through configuration equality.

## Epochs, timing and boundaries

Each usable continuous segment becomes an epoch, ordered by its host recording
start metadata (legacy captures without it use path order). `MergePoints` and
`session.epochs` keep the standard timestamps and add source provenance.
Intervals are zero-based and half-open `[start, stop)`. The capture label is
retained literally, including presleep, postsleep and experiment-specific
labels such as nSkip; no behavior label is inferred from an unknown name.

`wildx_np_metadata.json` records source capture/segment/AP file, source sample
range, merged sample range and seconds, completion/failure, configuration
proof, identity uncertainty, exclusions and host timing observations.
Session time is cumulative saved AP samples divided by AP rate. No padding
samples are inserted for real-world gaps. Host-observed gaps and original
session events are separate, explicitly non-hardware timing evidence.

`time.dat` contains one uint32 local-PC millisecond value per LFP row. It is not
an AP clock or an Intan counter and is never fed to either reader. `pc_time.dat`
is not required. Recorded LF is processed independently per segment using a
450 Hz, fifth-order Butterworth low-pass in both directions, then a polyphase
FIR resampler. The exact input rate 20000/12 Hz gives an up/down ratio of 3/4
for 1250 Hz output. Floating-point intermediates avoid repeated integer rounding;
only the final normalized output is quantized. Chunk overlap and source starts
aligned to the rational grid preserve resampling phase across write chunks.

The LFP sidecar and `wildx_np_metadata.json` retain native and output sample
counts, exact rate ratio, processing recipe, source/output gains and per-segment
half-open ranges. Each output segment contains `ceil(N_source * up / down)`
samples; its nominal duration can exceed the native duration by less than one
output sample. XML and `session.extracellular.srLfp` describe the output rate.
Resampling does not establish AP/LF synchronization: each segment retains its
own first saved LF row as its time origin. The AP mapping remains available for
future per-segment time models without reindexing spikes or altering originals.

Pipeline filtering and referencing use independent segment/probe views.
Kilosort4's internal processing can still filter across concatenation edges.
Sorting and postprocessing do not automatically exclude spikes near segment
boundaries or export a boundary spike mask. Source/merged sample intervals remain
available in the NP metadata, MergePoints and session epochs so downstream
analysis can choose its own exclusion intervals without reindexing the data.
Boundary effects are not quantified. Waveform extraction and later LFP analyses
may span concatenation edges unless the analysis explicitly uses these intervals.

NP provenance and the LFP sidecar are required completion outputs and are included
in resume inventories with content fingerprints. Direct-run manifests retain the
NP recording type and nominal AP scale. Reusing an existing LFP requires matching
processing metadata and the exact output frame count; old native-rate or differently
scaled outputs require a fresh output directory or an explicit overwrite.

## Validation boundary

This change implements the route. Full-data concatenation, filtering,
Kilosort4 execution, interactive GUI behavior and scientific quality assessment
require a separately authorized run. See the task's plan/log for checks actually
performed. Existing acquisition formats retain their established route.
