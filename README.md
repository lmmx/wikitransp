# wikimedia-transp

Dataset of transparent images from Wikimedia.

- E.g. [an image of some dice](https://www.wikidata.org/wiki/Q178051#/media/File:PNG_transparency_demonstration_1.png)

## Requirements

- Python 3
- Libraries: (None yet)

## License

TODO: determine license based on licensing of images (I presume they will be CC, so CC0 if
possible). Code cannot be licensed as CC0 so I presume GPLv3 would be the equivalent.

## Usage

Intended usage is to provide a simple interface to a scraped dataset of images from Wikimedia

- Scraping can be carried out as:
  
  ```py
  from wikitransp import scrape_images
  scrape_images()
  ```
  
  This would then save the images to the default directory within the package
  (`src/wikitransp/data/store`) or an argument `save_dir` could be passed to `scrape_images()`

- Data access
  
  ```py
  from wikitransp.dataset import all_images, large_images, medium_images, small_images
  ```

## Guide to finding images

The tutorial [Finding images](https://en.wikipedia.org/wiki/Wikipedia:Finding_images_tutorial)
details how to use search tools for Wikimedia

## Transparent image search results

- CC search (mentioned [here](https://commons.wikimedia.org/wiki/Commons:Simple_media_reuse_guide)) finds
  [quite a few HR semi-transparent images](https://search.creativecommons.org/search?q=transparent&extension=png&size=large)
  - Unclear at a glance how many would have a range of values rather than just blocks of same alpha
    value (which would presumably be less effective to train on for alpha decompositing)
- [Commons: Featured pictures » Non-photographic media » Computer-generated](https://commons.wikimedia.org/wiki/Commons:Featured_pictures/Non-photographic_media/Computer-generated)
  seems to match the genre of emojis
  - Perhaps some portion would be either 0 or 255 alpha-valued, but I would want to check (for the rest)
    that each image has at least one pixel with 0 < A < 255
    - Categories: `Astronomy, Biology, Drawing, Engineering, Geology, Heraldry, Insignia, Mathematics, Other`

## Wikidata query service

See [notes on using Wikidata query service](https://github.com/lmmx/devnotes/wiki/Using-Wikidata-Query-Service)

### Discarded options

<details><summary><em>More details</em></summary>
  
<p>

Another possibility is to use the category [Transparent background](https://commons.wikimedia.org/wiki/Category:Transparent_background)
- You can filter these for [Featured pictures](https://commons.wikimedia.org/wiki/Category:Transparent_background#)
  but this doesn't give many (only 22 and they don't look very semitransparent, just "sticker-like",
  i.e. completely opaque or completely transparent)

</p>
</details>
