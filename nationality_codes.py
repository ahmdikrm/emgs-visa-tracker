"""
Convert a nationality written in a spreadsheet (e.g. "CHINA", "SOUTH KOREA",
"UK") into the ISO 3166 two-letter code the EMGS form expects (e.g. "CN").

Uses the pycountry library for the standard names, plus a short list of
aliases for the informal spellings people actually type.
"""

import pycountry

# Informal or older names -> ISO alpha-2 code.
ALIASES = {
    "UK": "GB",
    "UNITED KINGDOM": "GB",
    "BRITAIN": "GB",
    "GREAT BRITAIN": "GB",
    "USA": "US",
    "US": "US",
    "UNITED STATES": "US",
    "AMERICA": "US",
    "UAE": "AE",
    "KOREA": "KR",
    "SOUTH KOREA": "KR",
    "NORTH KOREA": "KP",
    "RUSSIA": "RU",
    "IRAN": "IR",
    "SYRIA": "SY",
    "VIETNAM": "VN",
    "LAOS": "LA",
    "TAIWAN": "TW",
    "TURKEY": "TR",
    "TURKIYE": "TR",
    "BOLIVIA": "BO",
    "VENEZUELA": "VE",
    "TANZANIA": "TZ",
    "MOLDOVA": "MD",
    "PALESTINE": "PS",
    "BRUNEI": "BN",
    "CZECH REPUBLIC": "CZ",
    "CONGO": "CG",
    "DR CONGO": "CD",
    "IVORY COAST": "CI",
    "CAPE VERDE": "CV",
    "SWAZILAND": "SZ",
    "ESWATINI": "SZ",
    "MICRONESIA": "FM",
    "VATICAN CITY": "VA",
    "TIMOR-LESTE": "TL",
    "EAST TIMOR": "TL",
    "BURMA": "MM",
    "MYANMAR": "MM",
}


def to_country_code(nationality: str) -> str:
    """Return the ISO alpha-2 code for a nationality, or "" if unknown."""
    name = " ".join(nationality.split()).upper()
    if not name:
        return ""
    if name in ALIASES:
        return ALIASES[name]
    if len(name) == 2 and pycountry.countries.get(alpha_2=name):
        return name

    country = pycountry.countries.get(name=name.title())
    if country:
        return country.alpha_2

    try:
        matches = pycountry.countries.search_fuzzy(name)
    except LookupError:
        return ""
    # Only accept an unambiguous fuzzy match; a wrong country is worse than none.
    return matches[0].alpha_2 if len(matches) == 1 else ""
