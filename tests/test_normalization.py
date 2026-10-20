import pytest

from leadfinder.business_id import is_valid_business_id, normalize_business_id
from leadfinder.normalization import (
    dedupe_domains,
    normalize_domain,
    registrable_root,
    same_registrable_domain,
)


@pytest.mark.parametrize("raw, expected", [
    ("https://www.Northstarshop.invalid/products?id=3", "northstarshop.invalid"),
    ("northstarshop.invalid/", "northstarshop.invalid"),
    ("http://NORTHSTARSHOP.INVALID:8080", "northstarshop.invalid"),
    ("  www.demo-outdoor.invalid  ", "demo-outdoor.invalid"),
    ("shop.northstarshop.invalid", "shop.northstarshop.invalid"),
])
def test_normalize_domain_variants(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "localhost", "not a domain", "https://", "bad_label.invalid"])
def test_normalize_domain_rejects_garbage(raw):
    assert normalize_domain(raw) is None


def test_registrable_root_handles_subdomains_and_multi_label_suffixes():
    assert registrable_root("kauppa.northstarshop.invalid") == "northstarshop.invalid"
    assert registrable_root("shop.example.co.uk") == "example.co.uk"
    # Two unrelated .co.uk sites must not share a root.
    assert not same_registrable_domain("a.co.uk", "b.co.uk")


def test_same_registrable_domain():
    assert same_registrable_domain("https://www.northstarshop.invalid", "kauppa.northstarshop.invalid")
    assert not same_registrable_domain("northstarshop.invalid", "demo-outdoor.invalid")
    assert not same_registrable_domain(None, "northstarshop.invalid")


def test_dedupe_domains_keeps_first_occurrence_in_order():
    urls = [
        "https://www.demo-outdoor.invalid/tents",
        "https://northstarshop.invalid/",
        "http://demo-outdoor.invalid/",
        "garbage",
        "NORTHSTARSHOP.INVALID/sale",
    ]
    assert dedupe_domains(urls) == ["demo-outdoor.invalid", "northstarshop.invalid"]


# --- Business ID (Y-tunnus) ------------------------------------------------

def test_business_id_checksum():
    assert is_valid_business_id("9900001-8")       # synthetic
    assert is_valid_business_id("9900005-0")       # synthetic, remainder 0 -> check digit 0
    assert not is_valid_business_id("9900001-1")   # wrong check digit
    assert not is_valid_business_id("0000000-0")   # passes checksum but never real
    assert not is_valid_business_id("123-4")
    assert not is_valid_business_id(None)


def test_business_id_normalization():
    assert normalize_business_id(" 9900001 - 8 ") == "9900001-8"
    assert normalize_business_id("99000018") == "9900001-8"
    assert is_valid_business_id("99000018")
