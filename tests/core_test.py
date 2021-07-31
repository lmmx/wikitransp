from pytest import fixture, mark, raises

import wikitransp


@fixture(scope="session")
def foo():
    """
    Foo
    """
    return None


@mark.parametrize("expected", [None])
def test_nothing(foo, expected):
    assert foo is expected


@mark.parametrize(
    "expected",
    [
        "https://storage.googleapis.com/gresearch/wit/wit_v1.train.all-1percent_sample.tsv.gz"
    ],
)
def test_data_sample_url(expected):
    assert wikitransp.data.SAMPLE_DATA_URL == expected
