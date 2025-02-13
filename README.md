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
- cuDF (GPU-accelerated replacement for pandas)

To install:

```sh
conda create -n wikitransp
conda activate wikitransp
conda install -c rapidsai -c nvidia -c numba -c conda-forge cudf=21.08 python=3.8 cudatoolkit=11.2
pip install .
```


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
- Note: log event timings have become unreliable after moving to async (to fix later!)

  ```
      HaltFinished ⠶ Successful completion in 29 minutes and 30.99 seconds.
      LogNotify ⠶ See /home/louis/dev/wikitransp/src/wikitransp/logs/wit_v1.train.all-1percent_sample_PNGs_with_alpha.log for full log.

      BonVoyage ⠶ Thank you for scraping with Wikitransp :^)-|-<
      ----------------------------------------------------------
      Init                     : n=1
      CheckPng                 : n=8181
      InternalLogException     : n=15
      PrePngStreamAsyncFetcher : n=1
      FetchIteration           : n=8
      PngStream                : n=7615, μ=605.6515, min=0.1247, max=1753.2464
      PngSuccess               : n=7615
      PngDone                  : n=7615
      GarbageCollect           : n=7615, μ=0.0128, min=0.0048, max=0.0347
      BanURL                   : n=52
      RoutineException         : n=8
      HaltFinished             : n=1
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
