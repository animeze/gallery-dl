# -*- coding: utf-8 -*- #noqa

# Copyright 2020-2026 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://olympustaff.com/"""

import re

from .common import ChapterExtractor, MangaExtractor
from .. import text

BASE_PATTERN = (r"((?:https?://)?(?:www\.)?"
                r"olympustaff\d?\.(?:com|net|info|top))")

TITLE_SUFFIX = " - مانجا مترجمة"


# -- parsing helpers (module level so they can be tested without network) --

def _meta(page, name):
    """Return the content of <meta property|name="NAME" content="...">"""
    n = re.escape(name)
    for pattern in (
        r'<meta[^>]+(?:property|name)=["\']' + n +
        r'["\'][^>]*?content=["\']([^"\']*)',
        r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*?'
        r'(?:property|name)=["\']' + n + r'["\']',
    ):
        match = re.search(pattern, page)
        if match:
            return text.unescape(match[1])
    return ""


def _label(page, label):
    """Return the text that follows an (Arabic) label such as 'النوع:'"""
    match = re.search(
        re.escape(label) + r'(?:[\s:]|<[^>]*>)*([^<\s][^<]*)', page)
    return text.unescape(match[1]).strip() if match else ""


def parse_images(page):
    """Return all chapter image URLs of a chapter page, in order"""
    urls = []
    for tag in re.findall(r"<img\b[^>]*>", page):
        for attr in ("data-src", "data-lazy-src", "src"):
            match = re.search(
                r'(?<![\w-])' + attr + r'\s*=\s*["\']([^"\']+)', tag)
            if match:
                url = match[1].strip()
                if "/uploads/" in url and url not in urls:
                    urls.append(url)
                break
    return urls


def parse_chapter_numbers(page, manga):
    """Return the chapter numbers linked on a series page (in page order)"""
    pattern = re.compile(
        r'href=["\'](?:https?://[^"\'/]+)?/series/' + re.escape(manga) +
        r'/(\d+(?:[.-]\d+)?)/?["\']')
    numbers = []
    for number in pattern.findall(page):
        if number not in numbers:
            numbers.append(number)
    return numbers


class OlympuStaffBase:
    """Base class for olympustaff extractors"""
    category = "olympustaff"
    root = "https://olympustaff.com"

    def manga_data(self, manga, page=None):
        if not page:
            page = self.request(f"{self.root}/series/{manga}").text

        title = _meta(page, "og:title").removesuffix(TITLE_SUFFIX).strip()
        description = _meta(page, "og:description")
        description = description.removeprefix(
            f"مانجا {title} مترجمة{title}").strip()

        genres = re.findall(
            r'href="[^"]*[?&](?:amp;)?genre=[^"]*"[^>]*>\s*([^<]+?)\s*<',
            page)
        score = re.search(r"(\d+(?:\.\d+)?)\s*/\s*5\b", page)

        return {
            "url"        : _meta(page, "og:url"),
            "manga"      : title,
            "score"      : text.parse_float(score[1]) if score else 0.0,
            "artist"     : _label(page, "الرسام"),
            "genre"      : list(dict.fromkeys(
                text.unescape(g) for g in genres)),
            "type"       : _label(page, "النوع"),
            "status"     : _label(page, "الحالة"),
            "description": description,
            "language"   : "Arabic",
            "lang"       : "ar",
        }

    def chapter_data(self, chapter):
        match = re.match(r"(\d+)(?:[.-](\w+))?", chapter)
        number, minor = match.groups() if match else (chapter, None)
        return {
            **self.cache(self.manga_data, self.manga),
            "chapter"      : text.parse_int(number),
            "chapter_minor": f".{minor}" if minor else "",
        }


class OlympuStaffChapterExtractor(OlympuStaffBase, ChapterExtractor):
    """Extractor for olympustaff manga chapters"""
    pattern = BASE_PATTERN + r"/series/([^/?#]+)/(\d+(?:[.-]\d+)?)"
    example = "https://olympustaff.com/series/MANGA/123"

    def __init__(self, match):
        root, self.manga, self.chapter = match.groups()
        self.root = text.ensure_http_scheme(root)
        ChapterExtractor.__init__(
            self, match, f"{self.root}/series/{self.manga}/{self.chapter}")

    def metadata(self, _):
        return self.chapter_data(self.chapter)

    def images(self, page):
        results = [(url, None) for url in parse_images(page)]
        if not results:
            self.log.warning(
                "%s/%s: No images found (paid chapter or layout change?)",
                self.manga, self.chapter)
        return results


class OlympuStaffMangaExtractor(OlympuStaffBase, MangaExtractor):
    """Extractor for olympustaff manga"""
    chapterclass = OlympuStaffChapterExtractor
    pattern = BASE_PATTERN + r"/series/([^/?#]+)/?(?:\?[^#]*)?$"
    example = "https://olympustaff.com/series/MANGA"

    def __init__(self, match):
        root, self.manga = match.groups()
        self.root = text.ensure_http_scheme(root)
        MangaExtractor.__init__(
            self, match, f"{self.root}/series/{self.manga}")

    def chapters(self, page):
        # warm the metadata cache with the first page
        self.cache(self.manga_data, self.manga, page)

        base = f"{self.root}/series/{self.manga}"
        results = {}
        pnum = 1
        while True:
            for number in parse_chapter_numbers(page, self.manga):
                if number not in results:
                    results[number] = (
                        f"{base}/{number}", self.chapter_data(number))

            # chapter list is paginated: ?page=2, ?page=3, ...
            pnum += 1
            if f"page={pnum}" not in page:
                break
            page = self.request(f"{base}?page={pnum}").text

        if not results:
            self.log.warning(
                "%s: No chapters found (site layout change?)", self.manga)
        return list(results.values())
