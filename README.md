# wikimedia-transp

[![Documentation](https://readthedocs.org/projects/wikitransp/badge/?version=latest)](https://wikitransp.readthedocs.io/en/latest/)
[![CI Status](https://github.com/lmmx/wikitransp/actions/workflows/master.yml/badge.svg)](https://github.com/lmmx/wikitransp/actions/workflows/master.yml)
[![Coverage](https://codecov.io/gh/lmmx/wikitransp/branch/master/graph/badge.svg)](https://codecov.io/github/lmmx/wikitransp)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)


Dataset of transparent images from Wikimedia.

- e.g. [an image of some dice](https://www.wikidata.org/wiki/Q178051#/media/File:PNG_transparency_demonstration_1.png)

## Requirements

- Python 3.8+

## License

TODO: determine license based on licensing of images (I presume they will be CC, so CC0 if
possible).

- Note: this remains to be determined and the dataset will probably be split up accordingly

This library is MIT licensed (a permissive license).

## Usage (TBD)

Intended usage is to provide a simple interface to a scraped dataset of images from Wikimedia

- Scraping of the 1% sample can be carried out as:

  ```py
  from wikitransp.scraper import scrape_images
  scrape_images(sample=True)
  ```

  and the full dataset can be scraped instead by toggling the `sample` flag to `False`.

  Currently this only filters the dataset according to size and transparency (this step remains
  too slow to proceed further, and will be parallelised with async HTTP requests).

  This then saves the filtered TSV (in future will save the images themselves) to the default
  directory within the package (`src/wikitransp/data/store`) or an argument `save_dir` could
  be passed to `scrape_images()` [not implemented for now].

- If you cancel after a while (KeyboardInterrupt) or it finishes up, you'll get a nice summary,
  e.g. here's the summary after the above command `scrape_images(sample=True)`:

  ```
      BonVoyage ⠶ Thank you for scraping with Wikitransp :^)-|-<
      ----------------------------------------------------------
      Init             : n=1
      CheckPng         : n=8181
      PrePngStream     : n=8168
      PngStream        : n=8117, μ=0.3169, min=0.0533, max=3.8237
      PopulateChunks   : n=6084, μ=0.0704, min=0.0054, max=0.7792
      DirectAlpha      : n=6084, μ=0.0000, min=0.0000, max=0.0002
      ConfAlphaNeg     : n=4169, μ=0.0726, min=0.0122, max=0.3423
      PngDone          : n=6074
      GarbageCollect   : n=6074, μ=0.0113, min=0.0025, max=0.0328
      AverageTime      : n=6074, μ=0.4433, min=0.0998, max=4.1011
      ConfAlpha        : n=1905, μ=0.0682, min=0.0092, max=0.2414
      WriteRow         : n=1905, μ=0.0000, min=0.0000, max=0.0051
      RoutineException : n=74
      BanURLException  : n=74
      ----------------------------------------------------------
  ```

  `BanURLException` indicates a suggestion to add URLs to the banned URL list (usually due to 404,
  but check these manually).

- Data access will look something like this (I expect):

  ```py
  from wikitransp.dataset import all_images, large_images, medium_images, small_images
  ```

## Guide to filtering images

- I'm currently filtering the dataset for PNGs with semitransparency, rather than PNGs with transparency
  which would include 'stickers', with potentially only two levels of alpha, 0 or 255,
  (which would presumably be less effective to train on for alpha decompositing)
- The dataset source is [WIT](https://github.com/google-research-datasets/wit/), the Wikipedia
  Image-Text dataset from Google Research.
