"""Railway src-layout runtime fallback smoke coverage."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import venv


ROOT = Path(__file__).resolve().parents[1]


def _venv_python(venv_path: Path) -> Path:
    return venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def test_runtime_pythonpath_imports_src_layout_outside_repository(tmp_path: Path) -> None:
    """The final-runtime fallback imports from ``/app/src`` without installation."""

    venv_path = tmp_path / "runtime"
    venv.EnvBuilder(with_pip=False).create(venv_path)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")

    result = subprocess.run(
        [
            str(_venv_python(venv_path)),
            "-c",
            "import kam_market_ai; import kam_market_ai.paper_trading.operator_app; print('RUNTIME_IMPORT_OK')",
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "RUNTIME_IMPORT_OK"
