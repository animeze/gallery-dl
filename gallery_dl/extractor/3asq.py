# -*- coding: utf-8 -*- #noqa

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://3asq.online/"""

import re

from .common import ChapterExtractor, MangaExtractor
from .. import text

BASE_PATTERN = (r"((?:https?://)?(?:www\.)?"
                r"3asq\.(?:online|org))")

# "888", "chapter-888", "888-5", "888.5", "888-end"
CHAPTER_PATTERN = r"((?:chapter-)?\d+(?:[.-][^/?#]+)?)"


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


def _section(page, label):
    """Return the HTML that follows a <h5>LABEL</h5> summary heading,
    up to the end of its enclosing item"""
    match = re.search(re.escape(label) + r"\s*</h\d>", page)
    if not match:
        return ""
    start = match.end()
    rest = page[start:]

    # the heading usually sits in its own <div class="summary-heading">
    # inside the item <div>, so two divs are open at this point
    depth = 2 if "summary-heading" in page[max(0, match.start() - 150):
                                           match.start()] else 1
    end = len(rest)
    for tag in re.finditer(r"<(/?)div\b", rest):
        depth += -1 if tag[1] else 1
        if depth <= 0:
            end = tag.start()
            break
    # never run into the next item
    nxt = re.search(r'<div[^>]*class="post-content_item', rest)
    if nxt:
        end = min(end, nxt.start())
    return rest[:end]


def _texts(chunk):
    """Return link texts of a section, or its plain text as fallback"""
    links = [text.unescape(t).strip()
             for t in re.findall(r"<a\b[^>]*>([^<]+)</a>", chunk)]
    links = [t for t in links if t]
    if links:
        return links
    plain = text.remove_html(chunk).strip()
    return [plain] if plain else []


def _description(page):
    """Return the series description (several Madara layouts)"""
    # 1) <div class="description-summary"> / <div class="summary__content">
    for pattern in (
        r'class="[^"]*description-summary[^"]*"[^>]*>(.*?)</div>',
        r'class="[^"]*summary__content[^"]*"[^>]*>(.*?)</div>',
    ):
        match = re.search(pattern, page, re.S)
        if match:
            desc = text.remove_html(text.unescape(match[1])).strip()
            if desc:
                return desc

    # 2) the <p> block(s) right before the "show more" link
    index = page.find("مشاهدة المزيد")
    if index > 0:
        paragraphs = re.findall(
            r"<p[^>]*>(.*?)</p>", page[max(0, index - 6000):index], re.S)
        if paragraphs:
            return text.remove_html(text.unescape(paragraphs[-1])).strip()
    return ""


def parse_images(page):
    """Return all chapter image URLs of a chapter page, in order"""
    urls = []
    for tag in re.findall(r"<img\b[^>]*>", page):
        url = ""
        for attr in ("data-src", "data-lazy-src", "src"):
            match = re.search(
                r"(?<![\w-])" + attr + r'\s*=\s*["\']([^"\']+)', tag)
            if match and not match[1].strip().startswith("data:"):
                url = text.unescape(match[1]).strip()
                break
        if not url:
            continue
        is_chapter_img = (
            "wp-manga-chapter-img" in tag or
            re.search(r'id=["\']image-\d+', tag) or
            "/WP-manga/data/" in url
        )
        if is_chapter_img and url not in urls:
            urls.append(url)
    return urls


def parse_chapters(html):
    """Return [(url, label), ...] from the 'ajax/chapters/' response"""
    results = []
    for item in text.extract_iter(
            html, '<li class="wp-manga-chapter', "</li>"):
        match = re.search(
            r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', item, re.S)
        if not match:
            continue
        url = text.unescape(match[1]).strip()
        if url.startswith(("http", "/")):   # locked chapters use "#"
            results.append((url, text.remove_html(match[2])))
    return results


def parse_title(label, manga=""):
    """'Manga - 888 - Title' / '888 - Title' -> 'Title'"""
    label = label.strip()
    if manga:
        label = label.removeprefix(manga).lstrip(" -–").strip()
    return label.partition(" - ")[2].strip()


class _3asqBase():
    """Base class for 3asq extractors (WordPress 'Madara' theme)"""
    category = "3asq"
    root = "https://3asq.online"

    def manga_data(self, manga, page=None):
        if not page:
            page = self.request(f"{self.root}/manga/{manga}/").text

        score = re.search(
            r'id=["\']averagerate["\'][^>]*>\s*([\d.]+)', page)
        if not score:
            score = re.search(r"5\s*/\s*([\d.]+)\s*من مجموع", page)

        return {
            "url"        : _meta(page, "og:url"),
            "manga"      : _meta(page, "og:title").strip(),
            "score"      : text.parse_float(score[1]) if score else 0.0,
            "author"     : ", ".join(_texts(_section(page, "الكاتب"))),
            "artist"     : ", ".join(_texts(_section(page, "الرسام"))),
            "genre"      : _texts(_section(page, "التصنيفات")),
            "alt_names"  : [
                n.strip() for n in
                text.remove_html(_section(page, "أسماء أخرى")).split(",")
                if n.strip()],
            "type"       : text.remove_html(
                _section(page, "النوع")).strip(),
            "team"       : _texts(_section(page, "فرق الترجمة")),
            "release"    : text.parse_int(text.remove_html(
                _section(page, "سنة الإصدار"))),
            "status"     : text.remove_html(
                _section(page, "الحالة")).strip(),
            "description": _description(page),
            "language"   : "Arabic",
            "lang"       : "ar",
        }

    def chapter_data(self, chapter, title=""):
        chapter = chapter.removeprefix("chapter-")
        match = re.match(r"(\d+)(?:[.-](\d+))?", chapter)
        number, minor = match.groups() if match else (chapter, None)
        return {
            **self.cache(self.manga_data, self.manga),
            "chapter"      : text.parse_int(number),
            "chapter_minor": f".{minor}" if minor else "",
            "title"        : title,
        }


class _3asqChapterExtractor(_3asqBase, ChapterExtractor):
    """Extractor for 3asq manga chapters"""
    pattern = BASE_PATTERN + r"/manga/([^/?#]+)/" + CHAPTER_PATTERN
    example = "https://3asq.online/manga/MANGA/123/"

    def __init__(self, match):
        root, self.manga, self.chapter = match.groups()
        self.root = text.ensure_http_scheme(root)
        # '?style=list' makes Madara put all images on a single page
        ChapterExtractor.__init__(
            self, match,
            f"{self.root}/manga/{self.manga}/{self.chapter}/?style=list")

    def metadata(self, page):
        manga = self.cache(self.manga_data, self.manga)["manga"]
        title = parse_title(_meta(page, "og:title"), manga)
        return self.chapter_data(self.chapter, title)

    def images(self, page):
        results = [(url, None) for url in parse_images(page)]
        if not results:
            self.log.warning(
                "%s/%s: No images found (site layout change?)",
                self.manga, self.chapter)
        return results


class _3asqMangaExtractor(_3asqBase, MangaExtractor):
    """Extractor for 3asq manga"""
    chapterclass = _3asqChapterExtractor
    pattern = BASE_PATTERN + r"/manga/([^/?#]+)/?(?:\?[^#]*)?$"
    example = "https://3asq.online/manga/MANGA/"

    def __init__(self, match):
        root, self.manga = match.groups()
        self.root = text.ensure_http_scheme(root)
        MangaExtractor.__init__(
            self, match, f"{self.root}/manga/{self.manga}/")

    def chapters(self, page):
        # warm the metadata cache with the page we already have
        self.cache(self.manga_data, self.manga, page)

        base = f"{self.root}/manga/{self.manga}/"
        results = []
        for url, label in parse_chapters(self._chapters_html(page, base)):
            if url.startswith("/"):
                url = self.root + url
            chapter = url.rstrip("/").rpartition("/")[2]
            results.append((url, self.chapter_data(
                chapter, parse_title(label))))

        if not results:
            self.log.warning(
                "%s: No chapters found (site layout change?)", self.manga)
        return results

    def _chapters_html(self, page, base):
        """Fetch the chapter list (loaded by the site via AJAX)"""
        headers = {
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": self.root,
            "Referer": base,
        }
        html = self.request(
            base + "ajax/chapters/", method="POST", headers=headers).text
        if "wp-manga-chapter" in html:
            return html

        # fallback: newer Madara versions use admin-ajax.php
        match = (
            re.search(r'manga-chapters-holder[^>]*data-id=["\'](\d+)', page) or
            re.search(r'data-id=["\'](\d+)["\'][^>]*manga-chapters-holder',
                      page) or
            re.search(r'"manga_id"\s*:\s*"?(\d+)', page)
        )
        if match:
            return self.request(
                f"{self.root}/wp-admin/admin-ajax.php", method="POST",
                headers=headers,
                data={"action": "manga_get_chapters", "manga": match[1]},
            ).text
        return html
