from __future__ import annotations

import asyncio
import csv
from functools import partial
import gc
import gzip
from itertools import chain
import json
import logging
import multiprocessing as mp
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import range_streams
import requests
from aiostream.core import StreamEmpty
from range_streams import RangeStream
from range_streams.codecs import PngStream
from tqdm import tqdm

MYPY = False  # when using mypy will be overrided as True
if MYPY or not TYPE_CHECKING:  # pragma: no cover
    import httpx  # avoid importing to Sphinx type checker

from ..logs import _dir_path as logs_dir
from ..share.multiproc_utils import batch_multiprocess_with_return
from .ban_list import BANNED_URLS
from .logger import Log, Logger

__all__ = ["filter_tsv_rows"]


_DEFAULT_THUMB_WIDTH = 100
_MIN_WIDTH_HEIGHT = 1000
_MAX_WIDTH_HEIGHT = 0

LOG_FILTER = None
# LOG_FILTER = [Log.CheckPng, Log.AverageTime, Log.GarbageCollect, Log.PngDone]

log: Logger  # set as global variable in `filter_tsv_rows`


class TSV_FIELDS:
    LANG = 0
    PAGE_URL = 1
    IMAGE_URL = 2
    PAGE_TITLE = 3
    SECTION_TITLE = 4
    HIERARCHICAL_SECTION_TITLE = 5
    CAPTION_REFERENCE_DESCRIPTION = 6
    CAPTION_ATTRIBUTION_DESCRIPTION = 7
    CAPTION_ALT_TEXT_DESCRIPTION = 8
    MIME_TYPE = 9
    ORIGINAL_HEIGHT = 10
    ORIGINAL_WIDTH = 11
    IS_MAIN_IMAGE = 12
    ATTRIBUTION_PASSES_LANG_ID = 13
    PAGE_CHANGED_RECENTLY = 14
    CONTEXT_PAGE_DESCRIPTION = 15
    CONTEXT_SECTION_DESCRIPTION = 16


def get_png_thumbnail_url(png_url: str, width: int = _DEFAULT_THUMB_WIDTH, guess=True):
    f"""
    Given the full URL of a PNG of an image on Wikipedia Commons ``png_url``, extract
    its filename and use that to create a thumbnail URL with the given ``width``.

    Note: if the width of the PNG at the input URL is less than or equal to the
    requested thumbnail ``width``, the API will simply return the input URL
    (but without loading the input URL, it's not possible to know this in advance).

    Args:
      png_url : URL of a PNG under ``https://upload.wikimedia.org/wikipedia/commons/``
      width   : The desired output thumbnail's width (default:
                ``{_DEFAULT_THUMB_WIDTH=}``px)
      guess   : Whether to simply guess using the standard format (avoiding the
                need to wait for the API call).
    """
    filename = png_url[png_url.rfind("/") + 1 :]
    if guess:
        wpc_prefix = "https://upload.wikimedia.org/wikipedia/commons/"
        if png_url.startswith("http://"):
            png_url = png_url.replace("http://", "https://")
        if not png_url.startswith(wpc_prefix):
            # The input URL doesn't match expected format, so don't try to guess
            guess = False  # Resort to the API call in the next conditional block
        else:
            subdirs = png_url[len(wpc_prefix) : -len(filename)]
            thumb_url = f"{wpc_prefix}thumb/{subdirs}{filename}/{width}px-{filename}"
    if not guess:
        api_url = (
            "https://en.wikipedia.org/w/api.php?"
            "action=query&format=json"
            "&prop=imageinfo"
            f"&titles=File:{filename}"
            f"&iiurlwidth={width}"
            "&iiprop=url"
        )
        r = requests.get(api_url)
        j = json.loads(r.content)
        try:
            thumb_url = j["query"]["pages"]["-1"]["imageinfo"][0]["thumburl"]
        except:
            # Want to know which URLs don't conform if any
            raise ValueError(f"{api_url=} does not conform")
    return thumb_url


def confirm_idat_alpha(stream: PngStream, nonzero: bool = True) -> bool:
    """
    Download the image data for a PNG image -- i.e. its IDAT chunk(s) -- and determine
    whether or not there is any non-maximum alpha value therein. This is to distinguish
    an image with an alpha channel (RGBA), but with all ``255`` values in that channel,
    from an image with an alpha channel and actual transparent or semitransparent
    pixels. It is recommended to pass in a thumbnail if possible to speed up this step.

    If the image uses an indexed palette and tRNS chunk rather than IDAT chunk RGBA
    values, this can't be checked, so assume it has transparency.

    Presumes :meth:`~range_streams.codecs.png.PngStream.alpha_as_direct` has already
    been called, to check the PNG has the possibility of an alpha channel before
    this function 'confirms' the channel is effectively used (rather than being entirely
    ``255``, fully opaque and non-transparent) by checking the IDAT chunks themselves.

    For simplicity, do not bother handling indexed PNGs (whose channel count will be 1),
    only those with 4 channels in the IDAT data will be used (so indexed PNGs with
    transparency will not be accepted, and return ``False`` from this method).

    Args:
      stream  : The :class:`~range_streams.codecs.png.PngStream` whose IDAT chunk(s)
                will be checked for the image data's alpha channel, or lack thereof.
      nonzero : If ``True`` (the default), checks specifically for semitransparency.
                If ``False``, checks for any transparency (i.e. any non-opacity).
    """
    rgba_check = stream.data.IHDR.channel_count == 4
    return rgba_check and stream.any_semitransparent_idat(nonzero=nonzero)


def filter_tsv_rows(
    input_tsv_files: list[Path],
    resume_at: str | None = None,
    resume_after: str | None = None,
    thumbnail_width=_DEFAULT_THUMB_WIDTH,
    min_size=_MIN_WIDTH_HEIGHT,
    max_size=_MAX_WIDTH_HEIGHT,
    fetch_async: bool = True,
) -> Path:
    f"""
    Check the PNGs in the WIT dataset (made up of TSV files) by
    using :class:`~range_streams.codecs.png.PngStream` and its helper method
    :meth:`~range_streams.codecs.png.PngStream.alpha_as_direct`. Either
    compressed or decompressed are acceptable (recommended to leave compressed).

    To reduce the dataset size (or as a quality filter), filter out images of width
    and/or height below ``min_size`` or above ``max_size``.

    Note: only pass one of ``resume_at`` or ``resume_after``.

    Args:
      input_tsv_files : The TSV file path(s). Gzip-compressed files are acceptable.
      resume_at       : Image URL (in the dataset) to resume at (default: ``None``)
      resume_after    : Image URL (in the dataset) to resume after (default: ``None``)
      thumbnail_width : The width of the thumbnail to generate when verifying an
                        image with RGBA channels actually contains alpha transparency.
      min_size        : The minimum width and height of image to filter for. Default:
                        ``{_MIN_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
      max_size        : The maximum width and height of image to filter for. Default:
                        ``{_MAX_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
      fetch_async     : Whether to use asynchronous partial requests to fetch PNGs.
    """
    if (resume_at is not None) and (resume_after is not None):
        raise ValueError(f"Got passed values for both {resume_at=} and {resume_after=}")
    skip_resume_url = resume_after is not None
    resume_at_url = resume_after if skip_resume_url else resume_at
    tsv_out_mode = "w" if resume_at_url is None else "a"
    if len(input_tsv_files) == 0:
        raise ValueError("No TSV files to filter")
    first_tsv = input_tsv_files[0]
    if first_tsv.suffix == ".gz":
        # Strip the suffix of a gzipped file
        first_tsv = first_tsv.parent / first_tsv.stem
    if len(input_tsv_files) == 1:
        # The sample file
        out_filename = f"{first_tsv.stem}_PNGs_with_alpha.tsv"
    else:
        # All files
        out_filename = f"{first_tsv.stem.split('-')[0]}_PNGs_with_alpha.tsv"
    out_path = first_tsv.parent / out_filename
    log_path = logs_dir / f"{out_path.stem}.log"
    total_tsvs = len(input_tsv_files)
    n_tsv = f"{total_tsvs} TSV file{'s' if total_tsvs > 1 else ''}"
    global log  # global singleton
    log = Logger(
        which=LOG_FILTER,
        path=log_path,
        name=__name__,
    )
    # logging.helper = log # global now
    # Make and immediately dispose of an empty RangeStream to get a persistent client
    # without having to import httpx at all (which avoids Sphinx type import hassle)
    client = httpx.AsyncClient() if fetch_async else httpx.Client()
    try:
        with open(out_path, tsv_out_mode) as tsv_out:
            tsvwriter = csv.writer(tsv_out, delimiter="\t")
            tsv_filter_funcs = [
                partial(
                    handle_tsv_file,
                    tsv_path=tsv_path,
                    thumbnail_width=thumbnail_width,
                    min_size=min_size,
                    max_size=max_size,
                )
                for tsv_path in input_tsv_files
            ]
            # The URL collection functions have been gathered, now run them on all cores
            url_lists = [*chain.from_iterable(
                batch_multiprocess_with_return(tsv_filter_funcs, show_progress=True)
            )]
            breakpoint()
            # Now the URLs have been collected, fetch in a single async multiprocess run
    except KeyboardInterrupt:
        log.halt()
        raise
    else:
        log.complete()
    return out_path


async def finish_async(client):
    await client.aclose()


def handle_tsv_file(
    tsv_path: Path,
    thumbnail_width: int,
    min_size: int,
    max_size: int,
) -> list[str]:
    """
    Open and process the TSV file (in this function just handle its compression).

    Args:
      tsv_path        : path to the TSV file (gzipped or uncompressed)
      thumbnail_width : The width of the thumbnail to generate when verifying an
                        image with RGBA channels actually contains alpha transparency.
      min_size        : The minimum width and height of image to filter for. Default:
                        ``{_MIN_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
      max_size        : The maximum width and height of image to filter for. Default:
                        ``{_MAX_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
    """
    with tsv_opener(tsv_path) as tsv_in:
        url_list = handle_tsv_data(
            fh=tsv_in,
            thumbnail_width=thumbnail_width,
            min_size=min_size,
            max_size=max_size,
        )
        return url_list


def tsv_opener(path: Path) -> TextIO:
    """
    Open a TSV (either text file or gzip-compressed text file).

    Args:
      path : The path to the TSV file.
    """
    if path.suffix == ".gz":
        fh = gzip.open(path, "rt")
    else:
        fh = open(path, "r")
    return fh


def handle_tsv_data(
    fh: TextIO,
    thumbnail_width: int,
    min_size: int,
    max_size: int,
):
    """
    Handle an opened TSV file (regardless of compression) of the dataset.

    Args:
      fh              : A file handle opened in a suitable mode for reading text from
                        either a plain text or gzipped text file.
      thumbnail_width : The width of the thumbnail to generate when verifying an
                        image with RGBA channels actually contains alpha transparency.
      width           : The desired output thumbnail's width (default:
                        ``{_DEFAULT_THUMB_WIDTH=}``px)
      min_size        : The minimum width and height of image to filter for. Default:
                        ``{_MIN_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
      max_size        : The maximum width and height of image to filter for. Default:
                        ``{_MAX_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
    """
    tsvreader = csv.reader(fh, delimiter="\t")
    count = 0
    urls_to_fetch: dict[str, str] = {}  # {thumb_url: png_url}
    max_urls_to_fetch = 0 # 0 is no limit (used for trial runs)
    for row_i, row in enumerate(tsvreader):
        if max_urls_to_fetch and count == max_urls_to_fetch:
            break
        if row_i == 0:
            assert row[0] == "language"  # TSV column label row
            continue
        if row[TSV_FIELDS.MIME_TYPE] != "image/png":
            continue
        png_url = row[TSV_FIELDS.IMAGE_URL]
        if png_url in urls_to_fetch.values():
            # Dataset contains duplicate URLs, match them before thumb URL generation
            continue
        if png_url in BANNED_URLS:
            continue
        png_width = int(row[TSV_FIELDS.ORIGINAL_WIDTH])
        png_height = int(row[TSV_FIELDS.ORIGINAL_HEIGHT])
        if min_size > 0 and min(png_width, png_height) < min_size:
            continue
        if max_size > 0 and max(png_width, png_height) > max_size:
            continue
        count += 1
        msg = f"({count}) @ {png_url}"
        log.add(Log.CheckPng, msg)
        try:
            png_is_small = png_width <= thumbnail_width
            if png_is_small:
                # Can happen if min_size < thumbnail_width
                thumb_url = png_url
            else:
                try:
                    thumb_url = get_png_thumbnail_url(
                        png_url=png_url, width=thumbnail_width, guess=True
                    )
                except Exception as excinfo:
                    log.error(err=excinfo)
                    continue
            urls_to_fetch.update({png_url: thumb_url})
        except Exception as e:
            log.fail(err=e)
            log.error(Log.RoutineException, err=e)
    url_list = list(urls_to_fetch)
    # Go no further now: come back to what follows when all files processed
    return url_list

def deprecated_rest_of_async_fetch_func(tsvwriter, close_client: bool):
    """
    Args:
      tsvwriter       : csv.writer object to write the TSV output file (shared across
                        all TSV input files)
      close_client    : Whether to close the client after use.
    """
    ###########################################################################
    log.add(Log.PrePngStreamAsyncFetcher)  # Here this is once for all the URLs
    fetched = PngStream.make_async_fetcher(
        urls=url_list,
        callback=thumb_callback,
        client=client,
        raise_response=False,
        close_client=close_client,
    )
    fetch_iteration = 0
    while fetched.completed.isempty() or min(fetched.completed).end < fetched.n:
        iter_msg = f"{fetch_iteration}: ({fetched.total_complete} of {fetched.n})"
        log.add(Log.FetchIteration, msg=iter_msg)
        fetch_iteration += 1
        try:
            fetched.make_calls()
        except Exception as exc:
            # Regenerate the client to force close any connections left open?
            # log.error(Log.UnclosedStreamException)
            log.error(Log.RoutineException, err=exc)
            log.fail(err=exc)
        else:
            log.succeed()


async def thumb_callback(fetcher, stream, url):
    log.add(Log.PngStream, msg=url, since=Log.PrePngStreamAsyncFetcher)
    stream_response = stream._ranges[stream.total_range].request.response
    status_code = stream_response.status_code
    try:
        stream_response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if status_code == 404:
            # Note this is the thumbnail URL not the source URL in the dataset
            msg = f"Add to banned URLs (status code {status_code}): {url}"
            log.add(Log.BanURL, msg)
            fetcher.mark_url_complete(url)
            log.succeed()  # Recover from 404
        else:
            log.error(Log.URLException, msg)
            log.fail(err=exc)  # Don't accept non-404 error codes
    else:
        if stream.data.IHDR.channel_count != 4:
            # Don't want indexed so must have 4 channels
            pass  # just close
        # await stream.enumerate_chunks_async() # Put back in later
        log.succeed()  # No error is a success
    await stream.aclose()  # always close the stream
    log.add(Log.PngDone, prefix=":-) ")
    del stream
    gc.collect()
    log.add(Log.GarbageCollect, since=Log.PngDone)


def make_png_stream(row: list[str], url: str, client) -> PngStream:
    # log = logging.helper # global now
    p = PngStream(
        url=url,
        client=client,
        enumerate_chunks=False,
    )
    log.add(Log.PngStream, since=Log.PrePngStreamAsyncFetcher)
    return p


def deprecated():
    for x in []:
        try:
            p = make_png_stream(row=row, url=thumb_url, client=client)
            if p.data.IHDR.channel_count != 4:
                # Don't want indexed so must have 4 channels
                p.close()
                continue
            # p.populate_chunks(which=["IDAT"])  # This is still the slowest step
            p.populate_chunks()
            log.add(Log.PopulateChunks, since=Log.PngStream)
            direct_alpha = p.alpha_as_direct
            log.add(Log.DirectAlpha, since=Log.PopulateChunks)

            if direct_alpha:
                if confirm_idat_alpha(stream=p):
                    log.add(Log.ConfAlpha, since=Log.DirectAlpha)
                    tsvwriter.writerow(row)
                    log.add(Log.WriteRow, since=Log.ConfAlpha)
                else:
                    log.add(Log.ConfAlphaNeg, since=Log.DirectAlpha)
            else:
                log.add(Log.DirectAlphaNeg, since=Log.DirectAlpha)
            p.close()
        except Exception as e:
            log.fail(err=e)
            try:
                p.close()
            except Exception:
                pass
            log.error(Log.RoutineException, err=e)
            msg = f"Possibly add to banned URLs: {png_url}"
            log.error(Log.BanURLException, msg)
            continue
        # Reference for the GC timer
        log.add(Log.PngDone, prefix=":-) ")
        del p
        gc.collect()
        log.add(Log.GarbageCollect, since=Log.PngDone)
        td = log.get_duration_between_prior_events(
            which0=Log.CheckPng, which1=Log.GarbageCollect
        )
        assert td is not None  # give mypy a clue
        mean_td = log.get_mean_duration(which=Log.AverageTime, extra=[td])
        log.add(
            Log.AverageTime,
            since=Log.CheckPng,
            prefix=f"{mean_td:.4f} ---> ",
        )
        log.succeed()
