from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Iterator

import httpx
from aiostream import stream

if TYPE_CHECKING:
    import tqdm
    from range_streams.codecs.png import PngStream

__all__ = ["fetch", "process", "async_fetch_urlset", "fetch_images"]


async def fetch(
    session: httpx.AsyncClient, url: str | httpx.URL, raise_for_status: bool = False
):
    response: httpx.Response = await session.get(str(url))  # type: ignore
    if raise_for_status:
        response.raise_for_status()
    return response


async def process_image(
    data: httpx.Response,
    images: list[str],
    pbar: tqdm.std.tqdm | None = None,
    verbose: bool = False,
):
    # Map the response back to the image it came from in the images list
    source_url = data.history[0].url if data.history else data.url
    image = next(im for im in images if source_url == im.get("url"))
    # breakpoint()
    downloaded_image = data.content
    if verbose:
        print({source_url: "foo"})
    image.update({"stream": downloaded_image})
    if pbar:
        pbar.update()


async def async_fetch_urlset(
    urls: list[str] | Iterator[str],
    images: list[str],
    pbar: tqdm.std.tqdm | None = None,
    verbose: bool = False,
    timeout_s: float = 10.0,
):
    timeout = httpx.Timeout(timeout=timeout_s)
    async with httpx.AsyncClient(timeout=timeout_cfg) as session:
        ws = stream.repeat(session)
        xs = stream.zip(ws, stream.iterate(urls))
        ys = stream.starmap(
            xs, fetch, ordered=False, task_limit=20
        )  # 30 is similar IDK
        process = partial(process_image, images=images, pbar=pbar, verbose=verbose)
        zs = stream.map(ys, process)
        return await zs


def fetch_images(
    urls: list[str] | Iterator[str],
    images: list[str],
    pbar: tqdm.std.tqdm | None = None,
    verbose: bool = False,
):
    return asyncio.run(async_fetch_urlset(urls, images, pbar, verbose))
