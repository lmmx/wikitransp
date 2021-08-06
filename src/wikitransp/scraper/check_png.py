from __future__ import annotations

import csv
import gc
import gzip
import json
import time
from io import TextIOWrapper
from pathlib import Path
import logging

import range_streams
import requests
from range_streams import RangeStream
from range_streams.codecs import PngStream
from tqdm import tqdm

from .ban_list import BANNED_URLS
from .logger import Log, Logger
from ..logs import _dir_path as logs_dir

__all__ = ["filter_tsv_rows"]


# def png_has_alpha(url: str) -> bool:
#    p = PngStream(url=url)
#    return p.alpha_as_direct

_DEFAULT_THUMB_WIDTH = 200
_MIN_WIDTH_HEIGHT = 1000
_MAX_WIDTH_HEIGHT = 0

VERBOSE = True
ERR_VERBOSE = True
QUIET = False
LOG_FILTER = None
# LOG_FILTER = [Log.CheckPng, Log.AverageTime, Log.GarbageCollect, Log.PngDone]


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
            print(api_url)  # Want to know which URLs don't conform if any
            raise
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
    thumbnail_width=_DEFAULT_THUMB_WIDTH,
    min_size=_MIN_WIDTH_HEIGHT,
    max_size=_MAX_WIDTH_HEIGHT,
) -> Path:
    f"""
    Check the PNGs in the WIT dataset (made up of TSV files) by
    using :class:`~range_streams.codecs.png.PngStream` and its helper method
    :meth:`~range_streams.codecs.png.PngStream.alpha_as_direct`. Either
    compressed or decompressed are acceptable (recommended to leave compressed).

    To reduce the dataset size (or as a quality filter), filter out images of width
    and/or height below ``min_size`` or above ``max_size``.

    Args:
      input_tsv_files : The TSV file path(s). Gzip-compressed files are acceptable.
      resume_at       : The image URL (in the dataset) to resume at (default: ``None``)
      thumbnail_width : The width of the thumbnail to generate when verifying an
                        image with RGBA channels actually contains alpha transparency.
      min_size        : The minimum width and height of image to filter for. Default:
                        ``{_MIN_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
      max_size        : The maximum width and height of image to filter for. Default:
                        ``{_MAX_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
    """
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
    n_tsv = f"{(n := len(input_tsv_files))} TSV file{'s' if n > 1 else ''}"
    log = Logger(
        verbose=VERBOSE, error_verbose=ERR_VERBOSE, which=LOG_FILTER,
        add_silently=QUIET, path=log_path, name=__name__,
    )
    logging.helper = log
    # Make and immediately dispose of an empty RangeStream to get a persistent client
    # without having to import httpx at all (which avoids Sphinx type import hassle)
    client = RangeStream(range_streams._EXAMPLE_URL).client
    try:
        with open(out_path, "w") as tsv_out:
            tsvwriter = csv.writer(tsv_out, delimiter="\t")
            for tsv_path in tqdm(input_tsv_files, desc=f"Processing {n_tsv}"):
                handle_tsv_file(
                    tsv_path=tsv_path,
                    tsvwriter=tsvwriter,
                    client=client,
                    resume_at=resume_at,
                    thumbnail_width=thumbnail_width,
                    min_size=min_size,
                    max_size=max_size,
                )
    except KeyboardInterrupt:
        log.summarise()
        raise
    else:
        log.summarise()
    return out_path


def handle_tsv_file(
    tsv_path: Path,
    tsvwriter,
    client,
    resume_at: str | None,
    thumbnail_width: int,
    min_size: int,
    max_size: int,
):
    """
    Open and process the TSV file (in this function just handle its compression).

    Args:
      tsv_path        : path to the TSV file (gzipped or uncompressed)
      tsvwriter       : csv.writer object to write the TSV output file (shared across
                        all TSV input files)
      client          : The client all the HTTP requests will share (faster to do so)
      resume_at       : The image URL (in the dataset) to resume at (default: ``None``)
      thumbnail_width : The width of the thumbnail to generate when verifying an
                        image with RGBA channels actually contains alpha transparency.
      min_size        : The minimum width and height of image to filter for. Default:
                        ``{_MIN_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
      max_size        : The maximum width and height of image to filter for. Default:
                        ``{_MAX_WIDTH_HEIGHT=}``px. Ignored if ``0`` or below.
    """
    is_gz = tsv_path.suffix == ".gz"
    opener = gzip.open if is_gz else open
    mode = "rt" if is_gz else "r"
    with opener(tsv_path, mode) as tsv_in:
        handle_tsv_data(
            fh=tsv_in,
            tsvwriter=tsvwriter,
            client=client,
            resume_at=resume_at,
            thumbnail_width=thumbnail_width,
            min_size=min_size,
            max_size=max_size,
        )


def handle_tsv_data(
    fh: TextIOWrapper,
    tsvwriter,
    client,
    resume_at: str | None,
    thumbnail_width: int,
    min_size: int,
    max_size: int,
):
    """
    Handle an opened TSV file (regardless of compression) of the dataset.

    Args:
      fh              : A file handle opened in a suitable mode for reading text from
                        either a plain text or gzipped text file (a
                        :class:`io.TextIOWrapper`).
      tsvwriter       : csv.writer object to write the TSV output file (shared across
                        all TSV input files)
      client          : The client all the HTTP requests will share (faster to do so)
      resume_at       : The image URL (in the dataset) to resume at (default: ``None``)
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
    log = logging.helper
    for row in tsvreader:
        if row[TSV_FIELDS.MIME_TYPE] != "image/png":
            continue
        png_url = row[TSV_FIELDS.IMAGE_URL]
        if resume_at is not None:
            if png_url == resume_at:
                # Matched: set it to None so no more are skipped
                resume_at = None
                log.add(
                    Log.MatchResume, f"Resuming at match: {png_url}", level=logging.INFO
                )
            else:
                # Awaiting the matching URL, keep skipping rows
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
        #log.add(Log.CheckPng, msg, toggle_silencer=True, prefix="\n", suffix=" ")
        log.add(Log.CheckPng, msg, level=logging.INFO)#, prefix="\n", suffix=" ")
        try:
            png_is_small = png_width <= thumbnail_width
            if png_is_small:
                # Can happen if min_size < thumbnail_width
                thumb_url = png_url
            else:
                thumb_url = get_png_thumbnail_url(
                    png_url=png_url, width=thumbnail_width, guess=True
                )
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
            try:
                p.close()
            except Exception:
                pass
            log.add(Log.RoutineException, e)
            msg = f"Possibly add to banned URLs: {png_url}"
            log.add(Log.BanURLException, msg)
            continue
        # Reference for the GC timer
        log.add(Log.PngDone, prefix=":-) ")
        del p
        gc.collect()
        log.add(Log.GarbageCollect, since=Log.PngDone)
        td = log.get_duration_between_prior_events(
            which0=Log.CheckPng, which1=Log.GarbageCollect
        )
        # if log.has_event(which=Log.AverageTime):
        #    all_td = log.get_durations(which=Log.AverageTime)
        # else:
        #    all_td = []
        # all_td.append(td)
        # mean_td = sum(all_td) / len(all_td)
        mean_td = log.get_mean_duration(which=Log.AverageTime, extra=[td])
        log.add(
            Log.AverageTime,
            since=Log.CheckPng,
            prefix=f"{mean_td:.4f} ---> ",
            #toggle_silencer=True,
            #suffix="",
        )


def make_png_stream(row: list[str], url: str, client) -> PngStream:
    log = logging.helper
    log.add(Log.PrePngStream)
    p = PngStream(
        url=url,
        client=client,
        enumerate_chunks=False,
    )
    log.add(Log.PngStream, since=Log.PrePngStream)
    return p
