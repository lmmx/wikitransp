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

## Wikidata query

[Wikidata has a query service](https://query.wikidata.org/) with examples like
[cats, with pictures](https://query.wikidata.org/#%23Cats%2C%20with%20pictures%0A%23defaultView%3AImageGrid%0ASELECT%20%3Fitem%20%3FitemLabel%20%3Fpic%0AWHERE%0A%7B%0A%3Fitem%20wdt%3AP31%20wd%3AQ146%20.%0A%3Fitem%20wdt%3AP18%20%3Fpic%0ASERVICE%20wikibase%3Alabel%20%7B%20bd%3AserviceParam%20wikibase%3Alanguage%20%22%5BAUTO_LANGUAGE%5D%2Cen%22%20%7D%0A%7D)

The first step to finding images I want is to go backwards and inspect the properties of an image
found already (from the Commons: Featured pictures link above)

- An example of such a picture is [Scheme of a submarine eruption](https://commons.wikimedia.org/wiki/Commons:Featured_pictures/Non-photographic_media/Computer-generated#/media/File:Submarine_Eruption-numbers.svg)
  - This is a SVG but every SVG has a PNG (e.g. here it's
    [this 1080x1080px PNG](https://upload.wikimedia.org/wikipedia/commons/thumb/9/93/Submarine_Eruption-numbers.svg/1080px-Submarine_Eruption-numbers.svg.png))
  - Clicking "More details" gives the [details page](https://commons.wikimedia.org/wiki/File:Submarine_Eruption-numbers.svg)
- The property for a Wikimedia Commons featured picture is [`Q63348049`](https://www.wikidata.org/wiki/Q63348049)

### Discarded options

Another possibility is to use the category [Transparent background](https://commons.wikimedia.org/wiki/Category:Transparent_background)
- You can filter these for [Featured pictures](https://commons.wikimedia.org/wiki/Category:Transparent_background#)
  but this doesn't give many (only 22 and they don't look very semitransparent, just "sticker-like",
  i.e. completely opaque or completely transparent)
