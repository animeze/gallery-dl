# -*- coding: utf-8 -*- # noqa
"""Offline tests for gallery_dl.extractor.olympustaff (no network)"""

import re
import pytest
from gallery_dl.extractor import olympustaff as o


@pytest.mark.parametrize("url,slug,chapter", [
    ("https://olympustaff.com/series/monopolizing-fortunes/36",
     "monopolizing-fortunes", "36"),
    ("https://olympustaff.com/series/monopolizing-fortunes/36/",
     "monopolizing-fortunes", "36"),
    ("https://olympustaff.com/series/monopolizing-fortunes/37", "monopolizing-fortunes", "37"),
])
def test_chapter_pattern(url, slug, chapter):
    m = re.match(o.OlympuStaffChapterExtractor.pattern, url)
    assert m and m[2] == slug and m[3] == chapter


@pytest.mark.parametrize("url", [
    "https://olympustaff.com/series/monopolizing-fortunes",
    "https://olympustaff.com/series/monopolizing-fortunes/",
    "https://olympustaff.com/series/monopolizing-fortunes?page=2",
])
def test_manga_pattern_accepts_series_url(url):
    m = re.match(o.OlympuStaffMangaExtractor.pattern, url)
    assert m and m[2] == "monopolizing-fortunes"


def test_manga_pattern_rejects_chapter_urls():
    assert not re.match(o.OlympuStaffMangaExtractor.pattern,
                        "https://olympustaff.com/series/monopolizing-fortunes")


@pytest.mark.parametrize("raw,num,minor", [
    ("36", 36, ""),
    ("12.5", 12, ".5"),
    ("12-5", 12, ".5"),
])
def test_chapter_data(raw, num, minor):
    base = o.OlympuStaffBase()
    base.manga = "x"
    base.cache = lambda fn, *a: {}
    d = base.chapter_data(raw)
    assert d["chapter"] == num and d["chapter_minor"] == minor


def test_parse_images():
    html = (
        '<img src="https://cdn.olympustaff.com/images/TeamX.png">'
        '<img alt="image of episode" '
        'src="https://cdn.olympustaff.com/uploads/manga_1/36/a.webp">'
        '<img alt="image of episode" src="placeholder.gif" '
        'data-src="https://cdn.olympustaff.com/uploads/manga_1/36/b.webp">'
        '<img src="https://cdn.olympustaff.com/uploads/manga_1/36/a.webp">'
        '<img src="https://i.ibb.co/ad.png">'
    )
    assert o.parse_images(html) == [
        "https://cdn.olympustaff.com/uploads/manga_1/36/a.webp",
        "https://cdn.olympustaff.com/uploads/manga_1/36/b.webp",
    ]


def test_parse_chapter_numbers():
    html = (
        '<a href="https://olympustaff.com/series/x/3">3</a>'
        '<a href="/series/x/2">2</a>'
        '<a href="#">locked</a>'
        '<a href="https://olympustaff.com/series/x/2">dup</a>'
        '<a href="https://olympustaff.com/series/other/9">other</a>'
        '<a href="https://olympustaff.com/series/x/1.5">1.5</a>'
    )
    assert o.parse_chapter_numbers(html, "x") == ["3", "2", "1.5"]


def test_manga_data():
    html = (
        '<meta property="og:title" content="Some Title - مانجا مترجمة">'
        '<meta property="og:url" content="https://olympustaff.com/series/x">'
        '<meta property="og:description" '
        'content="مانجا Some Title مترجمةSome Title the plot">'
        '<span>النوع:</span> <a href="/series?type=a">مانهوا كورية</a>'
        '<span>الحالة:</span> <a href="/series?status=b">مستمرة</a>'
        '<span>الرسام:</span> <a href="#">Jo Ah-jin</a>'
        '<div>5/5</div>'
        '<a href="/series?genre=1">أكشن</a><a href="/series?genre=2">دراما</a>'
    )
    d = o.OlympuStaffBase().manga_data("x", html)
    assert d["manga"] == "Some Title"
    assert d["url"] == "https://olympustaff.com/series/x"
    assert d["type"] == "مانهوا كورية"
    assert d["status"] == "مستمرة"
    assert d["artist"] == "Jo Ah-jin"
    assert d["score"] == 5.0
    assert d["genre"] == ["أكشن", "دراما"]
    assert d["description"] == "the plot"
    assert d["lang"] == "ar"
