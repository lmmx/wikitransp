from __future__ import annotations

import gzip
import shutil
from pathlib import Path

from tqdm import tqdm

__all__ = ["decompress_gz_file"]


def decompress_gz_file(gz_path: Path) -> Path:
    """
    Decompress a gzip-compressed file to disk, naming it by just removing the ".gz"
    suffix. If the output path already exists, assume it was already decompressed,
    and do not touch it.

    Args:
      gz_path : The path to the gzip-compressed file
    """
    if gz_path.suffix != ".gz":
        raise ValueError(f"Expected file suffix to be '.gz', got '{gz_path.suffix}'")
    out_path = gz_path.parent / gz_path.stem
    if not out_path.exists():
        with gzip.open(gz_path, "r") as f_in, open(out_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    return out_path


def decompress_gz_files(paths: list[Path]) -> list[Path]:
    """
    Decompress a list of gzip-compressed files to disk, returning their decompressed
    file paths.

    Args:
      paths: List of paths to the gzip-compressed files.
    """
    decompressed_files = []
    n_tsv = f"{(n := len(paths))} gzipped file{'s' if n > 1 else ''}"
    for gz_path in tqdm(paths, desc=f"Decompressing {n_tsv}"):
        out_path = decompress_gz_file(gz_path=gz_path)
        decompressed_files.append(out_path)
    return decompressed_files
