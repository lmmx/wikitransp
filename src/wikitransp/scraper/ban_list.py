__all__ = ["BANNED_URLS"]

_URL_PREFIX = "https://upload.wikimedia.org/wikipedia/commons/"

BANNED_URLS = [
    f"{_URL_PREFIX}{url_part}"
    for url_part in (
        "5/50/50_Afghanis_of_Afghanistan_in_2002_Reverse.png",  # 404
        "4/4d/Nordamerikanische_Kulturareale_en.png",  # 404
        "e/ea/Park_Jihoon_GQ.png",  # 404
        "2/21/Breakers_Website_New_Logo_%281%29.png",  # 404
        "d/d2/StaatslijnC.png",  # 404
        "2/28/Logo_de_la_F%C3%A9d%C3%A9ration_de_Parkour.png",  # 404
    )
]
