"""Як сайт бачать Facebook, Google і телефон: кожна сторінка кожної мови (build.LOCALES) у зібраному dist/.

Одна збірка в тимчасовій копії дерева (як test_build_site), dist/ проєкту не чіпаємо. На кожній сторінці:
title і description, canonical, hreflang усіх мов + x-default, og:* (картинка в dist, не менша за 1200×630),
twitter:card, JSON-LD парситься (Product з ціною в ILS, Organization на головних, FAQPage на FAQ),
lang і dir на <html>, жодного битого внутрішнього href/src, alt у кожного img, sitemap.xml з усіма
сторінками й robots.txt, жодного «להשלמה» чи незаповненого маркера.

KNOWN — дірки зони вітрини (сесія 1), про які вона знає (~/maestro/tasks/aluma-noch-4-priemka.md).
Поки дірка є — тест пропускається з причиною; щойно виправлено — проходить сам, правити тест не треба.
Нова дірка, якої немає в KNOWN, — червоне.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import struct
import tempfile
import unittest
from html.parser import HTMLParser

from tests.locales import DIRS, DIST_PREFIX, LOCALES, lang_of
from tests.test_build_eol import make_tree, run_build

PROJECT = pathlib.Path(__file__).resolve().parent.parent
SITE = json.loads((PROJECT / "content.json").read_text(encoding="utf-8"))["SITE_URL"].rstrip("/")
OG_MIN = (1200, 630)
OG_LOCALE = {loc: json.loads((PROJECT / "i18n" / f"{loc}.json").read_text(encoding="utf-8"))["locale"] for loc in LOCALES}

KNOWN: dict[str, str] = {}


class Page(HTMLParser):
    """Теги з атрибутами, <title> і тексти JSON-LD однієї сторінки."""

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict]] = []
        self.title = ""
        self.ld: list[str] = []
        self._in = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        self.tags.append((tag, a))
        if tag == "title":
            self._in = "title"
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in = "ld"
            self.ld.append("")

    def handle_endtag(self, tag):
        if tag in ("title", "script"):
            self._in = None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "ld":
            self.ld[-1] += data

    def meta(self, key: str) -> str:
        for tag, a in self.tags:
            if tag == "meta" and key in (a.get("name"), a.get("property")):
                return a.get("content", "")
        return ""

    def links(self, rel: str) -> list[dict]:
        return [a for tag, a in self.tags if tag == "link" and a.get("rel") == rel]

    def ld_items(self) -> list[dict]:
        out = []
        for raw in self.ld:
            data = json.loads(raw)                      # падає тут — JSON-LD не парситься
            for item in data if isinstance(data, list) else data.get("@graph", [data]):
                out.append(item)
        return out


def png_size(path: pathlib.Path):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def jpeg_size(path: pathlib.Path):
    data = path.read_bytes()
    i = 2
    while i < len(data) - 9 and data[:2] == b"\xff\xd8":
        if data[i] != 0xFF:
            return None
        marker, length = data[i + 1], struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


class PagesQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-quality-pages-"))
        tree = cls.tmp / "t"
        tree.mkdir()
        make_tree(tree, crlf_sources=False)
        cls.dist = run_build(tree, as_windows=False)
        cls.pages = {f.relative_to(cls.dist).as_posix(): f.read_text(encoding="utf-8")
                     for f in sorted(cls.dist.rglob("*.html"))}
        cls.parsed = {rel: Page(html) for rel, html in cls.pages.items()}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # --- помічники ---------------------------------------------------------------------------------

    def exists(self, url_path: str) -> bool:
        clean = url_path.split("#")[0].split("?")[0]
        if not clean:
            return True
        cands = [clean + "index.html"] if clean.endswith("/") else [clean, clean + ".html", clean + "/index.html"]
        return any((self.dist / c.lstrip("/")).is_file() for c in cands)

    def known(self, key: str, problems: list[str]):
        """Порожньо — добре; дірка з KNOWN — пропуск із причиною; інакше — червоне зі списком."""
        if not problems:
            return
        if key in KNOWN:
            self.skipTest(f"відомо ({len(problems)}): {KNOWN[key]}")
        self.fail(f"{len(problems)} проблем:\n  " + "\n  ".join(problems[:40]))

    def content_pages(self):
        return {rel: p for rel, p in self.parsed.items() if rel.rsplit("/", 1)[-1] != "404.html"}

    # --- перевірки ---------------------------------------------------------------------------------

    def test_build_has_every_language(self):
        for loc in LOCALES:
            self.assertGreater(len([r for r in self.pages if lang_of(r) == loc]), 10, loc)

    def test_html_lang_and_dir(self):
        bad = []
        for rel, p in self.parsed.items():
            a = next(a for tag, a in p.tags if tag == "html")
            want = (lang_of(rel), DIRS[lang_of(rel)])
            if (a.get("lang"), a.get("dir")) != want:
                bad.append(f"{rel}: lang={a.get('lang')} dir={a.get('dir')}, треба {want}")
        self.known("lang", bad)

    def test_title_and_description(self):
        bad = []
        for rel, p in self.parsed.items():
            if not p.title.strip():
                bad.append(f"{rel}: порожній <title>")
            if len(p.meta("description").strip()) < 15:
                bad.append(f"{rel}: description порожній або коротший за 15 знаків")
        self.known("title", bad)

    def test_canonical_and_hreflang(self):
        bad = []
        for rel, p in self.content_pages().items():
            canon = [a.get("href", "") for a in p.links("canonical")]
            if len(canon) != 1 or not canon[0].startswith(SITE + "/"):
                bad.append(f"{rel}: canonical {canon}")
            elif not self.exists(canon[0][len(SITE):]):
                bad.append(f"{rel}: canonical веде на неіснуючу {canon[0]}")
            alts = {a.get("hreflang"): a.get("href", "") for a in p.links("alternate") if a.get("hreflang")}
            for lang in [*LOCALES, "x-default"]:
                if lang not in alts:
                    bad.append(f"{rel}: немає hreflang={lang}")
                elif not self.exists(alts[lang][len(SITE):]):
                    bad.append(f"{rel}: hreflang={lang} веде на неіснуючу {alts[lang]}")
        self.known("hreflang", bad)

    def test_open_graph_for_facebook(self):
        bad = []
        for rel, p in self.parsed.items():
            for key in ("og:title", "og:description", "og:image", "og:locale", "og:url", "og:type"):
                if not p.meta(key).strip():
                    bad.append(f"{rel}: немає {key}")
            want = OG_LOCALE[lang_of(rel)]
            if p.meta("og:locale") and p.meta("og:locale") != want:
                bad.append(f"{rel}: og:locale={p.meta('og:locale')}, треба {want}")
            img = p.meta("og:image")
            if img:
                if not img.startswith(SITE + "/"):
                    bad.append(f"{rel}: og:image не абсолютна адреса сайту — {img}")
                    continue
                f = self.dist / img[len(SITE) + 1:]
                if not f.is_file():
                    bad.append(f"{rel}: og:image немає в dist — {img}")
                    continue
                size = png_size(f) or jpeg_size(f)
                if size is None:
                    bad.append(f"{rel}: og:image не PNG/JPEG (Facebook надійно читає лише їх) — {f.name}")
                elif size[0] < OG_MIN[0] or size[1] < OG_MIN[1]:
                    bad.append(f"{rel}: og:image {size[0]}×{size[1]}, треба ≥ {OG_MIN[0]}×{OG_MIN[1]}")
        self.known("og", bad)

    def test_twitter_card(self):
        self.known("twitter:card", [rel for rel, p in self.parsed.items() if not p.meta("twitter:card")])

    def test_json_ld_parses_and_products_are_in_ils(self):
        bad = []
        for rel, p in self.parsed.items():
            try:
                items = p.ld_items()
            except ValueError as e:
                bad.append(f"{rel}: JSON-LD не парситься — {e}")
                continue
            for it in items:
                if it.get("@type") != "Product":
                    continue
                offers = it.get("offers") or {}
                offers = offers if isinstance(offers, list) else [offers]
                if not offers:
                    bad.append(f"{rel}: Product без offers")
                for o in offers:
                    if o.get("priceCurrency") != "ILS":
                        bad.append(f"{rel}: priceCurrency={o.get('priceCurrency')}")
                    if not (o.get("price") or o.get("lowPrice")):
                        bad.append(f"{rel}: offers без ціни")
                for key in ("aggregateRating", "review"):
                    if key in it:
                        bad.append(f"{rel}: {key} — відгуків у нас немає")
        self.known("ld", bad)

    def test_every_product_card_has_product_ld(self):
        cards = [rel for rel in self.parsed if re.match(r"(en/)?p/[^/]+/index\.html$", rel)]
        self.assertGreaterEqual(len(cards), 2)
        self.known("product", [rel for rel in cards
                               if "Product" not in {i.get("@type") for i in self.parsed[rel].ld_items()}])

    def test_home_pages_have_organization_ld(self):
        self.known("organization", [rel for rel in [pre + "index.html" for pre in DIST_PREFIX.values()]
                                    if "Organization" not in {i.get("@type") for i in self.parsed[rel].ld_items()}])

    def test_faq_pages_have_faqpage_ld(self):
        faq = [rel for rel in self.parsed if rel == DIST_PREFIX[lang_of(rel)] + "faq/index.html"]
        self.known("faqpage", [rel for rel in faq
                               if "FAQPage" not in {i.get("@type") for i in self.parsed[rel].ld_items()}])

    def test_no_broken_internal_links_or_sources(self):
        problems: dict[str, list[str]] = {}
        for rel, p in self.parsed.items():
            for tag, a in p.tags:
                for attr in ("href", "src", "srcset"):
                    raw = a.get(attr, "")
                    urls = [u.strip().split(" ")[0] for u in raw.split(",")] if attr == "srcset" else [raw]
                    for url in urls:
                        if url.startswith(SITE):
                            url = url[len(SITE):] or "/"
                        if not url.startswith("/") or url.startswith("//"):
                            continue
                        if tag == "link" and a.get("rel") in ("canonical", "alternate"):
                            continue                    # перевіряє test_canonical_and_hreflang
                        if not self.exists(url):
                            problems.setdefault(f"broken:{url.split('#')[0]}", []).append(f"{rel}: <{tag} {attr}={url}>")
        unknown = [line for key, lines in problems.items() if key not in KNOWN for line in lines]
        if unknown:
            self.fail(f"{len(unknown)} битих внутрішніх посилань/src:\n  " + "\n  ".join(unknown[:40]))
        for key in problems:
            self.known(key, problems[key])

    def test_every_img_has_alt(self):
        bad = [f"{rel}: <img src={a.get('src')}> без alt" for rel, p in self.parsed.items()
               for tag, a in p.tags if tag == "img" and "alt" not in a]
        self.known("alt", bad)

    def test_sitemap_lists_every_page_and_robots_points_to_it(self):
        sitemap = (self.dist / "sitemap.xml").read_text(encoding="utf-8")
        locs = set(re.findall(r"<loc>([^<]+)</loc>", sitemap))
        bad = []
        for rel in self.content_pages():
            if 'name="robots" content="noindex"' in self.pages[rel]:
                continue                    # кошик і оформлення (specs/003) — свідомо поза sitemap
            path = rel[:-len("index.html")] if rel.endswith("index.html") else rel[:-len(".html")]
            if f"{SITE}/{path}" not in locs:
                bad.append(f"sitemap.xml: немає {SITE}/{path}")
        for loc in locs:
            if not loc.startswith(SITE + "/") or not self.exists(loc[len(SITE):]):
                bad.append(f"sitemap.xml: {loc} — такої сторінки немає")
        robots = (self.dist / "robots.txt").read_text(encoding="utf-8")
        if f"Sitemap: {SITE}/sitemap.xml" not in robots:
            bad.append("robots.txt: немає рядка Sitemap")
        if re.search(r"^Disallow:\s*/\s*$", robots, re.M):
            bad.append("robots.txt: Disallow: / закриває весь сайт")
        self.known("sitemap", bad)

    def test_no_unfilled_markers(self):
        bad = []
        for rel, html in self.pages.items():
            text = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<[^>]+>", " ", html, flags=re.S)
            for marker in ("להשלמה", "{{", "}}", "TODO", "TBD", "lorem ipsum", "[[", "XXX"):
                if marker.lower() in text.lower():
                    bad.append(f"{rel}: «{marker}» у тексті сторінки")
        self.known("markers", bad)


if __name__ == "__main__":
    unittest.main()
