from pathlib import Path as _Path

from . import __path__ as _dir_nspath  # type: ignore

__all__ = ["_dir_path", "logs_dir"]

logs_dir = _dir_path = _Path(list(_dir_nspath)[0])
