from __future__ import annotations

from sys import stderr

from .check_png import filter_tsv_rows
from .decompress_utils import decompress_gz_files
from .download_utils import download_data_url, download_dataset

__all__ = ["scrape_images"]


def scrape_images(
    sample: bool = False,
    resume_at: str | None = None,
    resume_after: str | None = None,
    decompress_tsv: bool = False,
) -> None:
    """
    Build a local dataset by scanning the WIT datatset (or a small sample of it)
    for suitable PNGs. Note: only pass one of ``resume_at`` or ``resume_after``.

    Args:
      sample         : Whether to only scrape the 1% sample dataset
      resume_at      : The image URL to resume at (if scraping was interrupted).
      resume_at      : The image URL to resume after (if scraping was interrupted).
      decompress_tsv : Whether to decompress gzipped TSVs before filtering (not
                       necessary, and will increase dataset file size on disk).
    """
    try:
        dataset_files = download_dataset(sample=sample)
        if decompress_tsv:
            decompressed_files = decompress_gz_files(paths=dataset_files)
        filtered_tsv = filter_tsv_rows(
            input_tsv_files=decompressed_files if decompress_tsv else dataset_files,
            resume_at=resume_at,
        )
    except KeyboardInterrupt:
        raise SystemExit(1)
    return
