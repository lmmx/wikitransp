__all__ = ["DATA_URL_DIR", "SAMPLE_DATA_URL", "FULL_DATA_URLS"]

DATA_DIR_URL = "https://storage.googleapis.com/gresearch/wit/"
_DATA_URL_PREFIX = f"{DATA_DIR_URL}wit_v1.train.all-"

SAMPLE_DATA_URL = f"{_DATA_URL_PREFIX}1percent_sample.tsv.gz"
"""
The URL provided for a 1% sample of the WIT (Wikipedia
Image-Text) dataset from Google Research.
"""


FULL_DATA_URLS = [f"{_DATA_URL_PREFIX}0000{i}-of-00010.tsv.gz" for i in range(10)]
"""
The 10 URLs provided for the full sample of the WIT (Wikipedia
Image-Text) dataset from Google Research.
"""
