from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


def _run_without_display(script: str, output_dir: Path, *args: str):
    environment = os.environ.copy()
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    environment.update(
        MPLBACKEND="QtAgg",
        QT_QPA_PLATFORM="pipeline-test-unavailable-platform",
        MPLCONFIGDIR=str(output_dir / "mplconfig"),
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(output_dir), *args],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_event_plots_save_pngs_without_loading_pyplot_or_qt(tmp_path):
    observed = _run_without_display(
        """
import json, sys
from pathlib import Path
import numpy as np
from src.preprocess.events import _save_analog_plot, _save_digital_plot

output = Path(sys.argv[1])
samples = np.arange(1000, dtype=np.uint16).reshape(-1, 1)
_save_analog_plot(output / 'single', samples, [1], 1000., overwrite=False)
_save_analog_plot(output / 'multi', np.repeat(samples, 2, axis=1), [1, 2],
                  1000., overwrite=False)
periods = np.empty((1, 16), dtype=object)
for index in range(16):
    periods[0, index] = np.empty((0, 2))
periods[0, 0] = np.array([[0.1, 0.2], [0.3, 0.4]])
_save_digital_plot(output, {'intsPeriods': periods}, overwrite=False)
print(json.dumps({
    'pyplot_loaded': 'matplotlib.pyplot' in sys.modules,
    'qt_loaded': any(name.startswith(('PyQt', 'PySide')) for name in sys.modules),
}))
""",
        tmp_path,
    )
    assert observed == {"pyplot_loaded": False, "qt_loaded": False}
    for path in (
        tmp_path / "single/pulses/analogPulsesDetection.png",
        tmp_path / "multi/pulses/analogPulsesDetection.png",
        tmp_path / "Pulses/digitalIn.png",
    ):
        with Image.open(path) as picture:
            assert picture.format == "PNG"
            picture.verify()


@pytest.mark.parametrize("backend", ["local", "slurm"])
def test_stage_worker_overrides_inherited_qt_backend_before_plotting(tmp_path, backend):
    observed = _run_without_display(
        """
import json, os, sys
from pathlib import Path
from src.execution import worker
from src.execution.models import (
    AnalysisConfig, AttemptSpec, BackendName, ExecutionConfig,
    RequestedBackend, ResourceSpec, StageName,
)
from src.execution.store import RunStore

root = Path(sys.argv[1])
backend = BackendName(sys.argv[2])
analysis = AnalysisConfig.create({})
resource = ResourceSpec(1, 1024, 10)
store = RunStore(root / 'run')
store.initialize(
    run={'run_id': 'headless-test', 'enabled_stages': ['preprocess'],
         'requested_backend': backend.value, 'resolved_backend': backend.value},
    analysis=analysis,
    execution=ExecutionConfig(
        requested_backend=RequestedBackend(backend.value), resolved_backend=backend,
        workspace=str(root), resources={'preprocess': resource},
    ),
)
store.create_attempt(AttemptSpec(
    run_id='headless-test', stage=StageName.PREPROCESS, attempt=1,
    backend=backend, resources=resource, analysis_sha256=analysis.sha256,
))
worker._verify_analysis_artifacts = lambda *_args: None

def save_stage_plot(*_args):
    import matplotlib
    import matplotlib.pyplot as plt
    assert matplotlib.get_backend().lower() == 'agg'
    figure, axes = plt.subplots()
    axes.plot([0, 1], [1, 0])
    path = root / 'worker.png'
    figure.savefig(path)
    plt.close(figure)
    return {'validated_paths': [str(path)]}

worker.run_stage = save_stage_plot
exit_code = worker.execute(store.run_dir, StageName.PREPROCESS, 1)
result = store.read_attempt_fact(StageName.PREPROCESS, 1, 'result.json')
print(json.dumps({
    'exit_code': exit_code, 'status': result['status'],
    'backend': os.environ['MPLBACKEND'],
    'qt_loaded': any(name.startswith(('PyQt', 'PySide')) for name in sys.modules),
}))
""",
        tmp_path,
        backend,
    )
    assert observed == {
        "exit_code": 0, "status": "completed", "backend": "Agg", "qt_loaded": False,
    }
    with Image.open(tmp_path / "worker.png") as picture:
        assert picture.format == "PNG"
        picture.verify()
