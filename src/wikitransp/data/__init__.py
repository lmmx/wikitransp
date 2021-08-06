from pathlib import Path as _Path

from . import __path__ as _dir_nspath  # type: ignore
from . import store
from .urls import DATA_DIR_URL, FULL_DATA_URLS, SAMPLE_DATA_URL

__all__ = ["DATA_DIR_URL", "SAMPLE_DATA_URL", "FULL_DATA_URLS", "_dir_path"]

_dir_path = _Path(list(_dir_nspath)[0])
