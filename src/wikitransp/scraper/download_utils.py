from __future__ import annotations

from pathlib import Path
from sys import stderr

from range_streams import RangeStream
from tqdm import tqdm

from ..data import DATA_DIR_URL, FULL_DATA_URLS, SAMPLE_DATA_URL
from ..data.store import _dir_path as store_path

__all__ = ["download_dataset", "download_data_url"]


def download_dataset(sample: bool = False) -> list[Path]:
    data_urls = [SAMPLE_DATA_URL] if sample else FULL_DATA_URLS
    data_files = []
    for data_url in data_urls:
        data_file_path = download_data_url(data_url)
        data_files.append(data_file_path)
    return data_files


def download_data_url(data_url: str) -> Path:
    """
    Download (or finish downloading) the data file at ``data_url``, and return
    the :class:`~pathlib.Path` to it on disk.

    Args:
      data_url : The URL of the data file (a gzipped TSV) from the WIT dataset.
    """
    filename = data_url[len(DATA_DIR_URL) :]
    store_file = store_path / filename
    s = RangeStream(data_url)
    s.add(s.total_range)
    start_at = 0
    if store_file.exists():
        file_len = store_file.stat().st_size
        assert s.total_bytes is not None  # give mypy a clue
        if file_len < s.total_bytes:
            # Download rest of file
            remaining_range = (file_len, s.total_bytes)
            print(f"Incomplete {filename}, downloading {remaining_range=}", file=stderr)
            s.add(remaining_range)  # This re-assigns the active range response
            start_at += file_len
        elif file_len > s.total_bytes:
            # Delete the file and re-download entirely
            print(f"Bad {filename} found, re-downloading", file=stderr)
            store_file.unlink()
        else:
            # An existing file with the correct size doesn't need re-downloading
            return store_file
    response = s.active_range_response.request.response
    print(f"Storing {store_file}")
    with open(store_file, "ab") as f:
        with tqdm(
            total=s.total_bytes, unit_scale=True, unit_divisor=1024, unit="B"
        ) as progress:
            progress.update(start_at)
            num_bytes_downloaded = response.num_bytes_downloaded
            for chunk in response.iter_bytes():
                f.write(chunk)
                progress.update(response.num_bytes_downloaded - num_bytes_downloaded)
                num_bytes_downloaded = response.num_bytes_downloaded
    return store_file
