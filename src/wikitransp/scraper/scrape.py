import zlib

from range_streams import RangeStream
from range_streams.codecs import PngStream

from ..data import FULL_DATA_URLS, SAMPLE_DATA_URL

__all__ = ["scrape_images"]


def check_png_has_alpha(url: str) -> bool:
    try:
        p = PngStream(url=url)
        return p.alpha_as_direct
    except Exception:
        return False


def download_sample():
    s = RangeStream(url=SAMPLE_DATA_URL)
    s.add(s.total_range)
    b = s.active_range_response.read()
    d = zlib.decompress(b)
    return d


def scrape_images(sample: bool = True) -> None:
    """
    Build a local dataset by scanning the WIT datatset (or a small sample of it)
    for suitable PNGs.

    Args:
      sample : Whether to only scrape the 1% sample dataset
    """
    data_urls = [SAMPLE_DATA_URL] if sample else FULL_DATA_URLS
