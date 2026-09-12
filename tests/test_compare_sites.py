"""scripts/compare_sites.py — без мережі: транспорт і годинник підміняються.

Головне — червоні випадки. Порівняння, яке зеленіє на різних сайтах, гірше за відсутнє:
воно дає дозвіл переключити DNS.

    python -m unittest tests.test_compare_sites -v
"""

from __future__ import annotations

import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compare_sites as c  # noqa: E402

PROD = "https://table.central-aparts.store"
BOX = "https://box-table.central-aparts.store"

SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
    f'  <url><loc>{PROD}/</loc><xhtml:link rel="alternate" hreflang="en" href="{PROD}/en/"/></url>\n'
    f'  <url><loc>{PROD}/en/</loc></url>\n'
    f'  <url><loc>{PROD}/privacy</loc></url>\n'
    '</urlset>\n'
).encode()


def page(css_hash="ec27479cf3", img_hash="0123456789", text="Goren", eol="\n"):
    html = (f'<!doctype html>{eol}<html lang="he">{eol}<head>'
            f'<link rel="stylesheet" href="/assets/styles-next.{css_hash}.css">{eol}</head>{eol}'
            f'<body><h1>{text}</h1>{eol}'
            f'<img src="/assets/product/goren-hero-1600.{img_hash}.webp" alt="">{eol}</body></html>{eol}')
    return html.encode()


def site(**kw):
    """path -> тіло. Однаковий набір сторінок, параметри — для однієї зміни."""
    return {
        "/sitemap.xml": SITEMAP,
        "/robots.txt": b"User-agent: *\nAllow: /\n",
        "/": page(**kw),
        "/en/": page(**kw),
        "/privacy": b"<p>privacy</p>",
    }


class FakeTransport:
    """Кілька хостів, заготовлені відповіді, кожен запит записаний."""

    def __init__(self, sites):
        self.sites = sites          # base -> {path: bytes | Response | Exception}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        for base, pages in self.sites.items():
            if url.startswith(base):
                got = pages.get(url[len(base):])
                if isinstance(got, Exception):
                    raise got
                if isinstance(got, c.Response):
                    return got
                return c.Response(200, got) if got is not None else c.Response(404, b"")
        raise AssertionError(f"запит на невідомий хост: {url}")


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(s)
        self.now += s


def run(a_site, b_site, **kw):
    t = FakeTransport({PROD: a_site, BOX: b_site})
    fc = FakeClock()
    out = io.StringIO()
    code = c.run(PROD, kw.pop("side_b", BOX), transport=t, sleep=fc.sleep, clock=fc.clock, out=out, **kw)
    return code, out.getvalue(), t


class Verdicts(unittest.TestCase):
    def test_identical_sites_exit_0(self):
        code, out, t = run(site(), site())
        self.assertEqual(code, 0, out)
        self.assertIn("Код 0", out)
        self.assertEqual(out.count(f"{c.SAME:<11} /"), 5, out)   # 3 з sitemap + sitemap.xml + robots.txt

    def test_text_difference_after_normalisation_exits_1(self):
        code, out, _ = run(site(), site(text="Goren 2"))
        self.assertEqual(code, 1, out)
        self.assertIn(f"{c.DIFF:<11} /", out)
        self.assertIn("-<h1>Goren</h1>", out)       # фрагмент різниці, а не лише вердикт
        self.assertIn("+<h1>Goren 2</h1>", out)

    def test_page_only_on_one_side_exits_1(self):
        b = site()
        del b["/privacy"]
        code, out, _ = run(site(), b)
        self.assertEqual(code, 1, out)
        self.assertIn(f"{c.MISSING:<11} /privacy", out)
        self.assertIn("на B (статус 404)", out)

    def test_page_only_on_the_other_side_exits_1(self):
        a = site()
        a["/en/"] = c.Response(403, b"AccessDenied")      # так S3 за CloudFront відповідає на відсутній ключ
        code, out, _ = run(a, site())
        self.assertEqual(code, 1, out)
        self.assertIn("на A (статус 403)", out)

    def test_only_build_hash_differs_exits_0(self):
        code, out, _ = run(site(), site(css_hash="c1b62263e7", img_hash="abcdef0123"))
        self.assertEqual(code, 0, out)
        self.assertNotIn(f"{c.DIFF:<11} /", out)

    def test_hash_normalisation_is_not_a_blanket_wildcard(self):
        # інша назва файла з тим самим хешем — це різниця, не «хеш збірки»
        b = site()
        b["/"] = page().replace(b"styles-next.", b"styles-old.")
        code, out, _ = run(site(), b)
        self.assertEqual(code, 1, out)

    def test_broken_sitemap_exits_2(self):
        a = site()
        a["/sitemap.xml"] = b"<urlset><url><loc>https://x/</loc></url>"    # не закритий
        code, out, t = run(a, site())
        self.assertEqual(code, 2, out)
        self.assertIn("sitemap не розбирається як XML", out)
        self.assertEqual(t.calls, [PROD + "/sitemap.xml"])                  # далі не пішли

    def test_sitemap_without_locs_exits_2(self):
        a = site()
        a["/sitemap.xml"] = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>'
        code, out, _ = run(a, site())
        self.assertEqual(code, 2, out)

    def test_sitemap_missing_on_prod_exits_2(self):
        a = site()
        del a["/sitemap.xml"]
        code, out, _ = run(a, site())
        self.assertEqual(code, 2, out)
        self.assertIn("статус 404", out)

    def test_network_error_exits_2_not_0_or_1(self):
        b = site()
        b["/en/"] = OSError("connection refused")
        code, out, _ = run(site(), b)
        self.assertEqual(code, 2, out)
        self.assertIn(c.ERROR, out)

    def test_crlf_only_is_a_difference_by_default(self):
        code, out, _ = run(site(eol="\r\n"), site())
        self.assertEqual(code, 1, out)
        self.assertIn("лише кінці рядків", out)

    def test_ignore_eol_accepts_crlf_only(self):
        code, out, _ = run(site(eol="\r\n"), site(), ignore_eol=True)
        self.assertEqual(code, 0, out)

    def test_ignore_eol_does_not_hide_text_difference(self):
        code, out, _ = run(site(eol="\r\n"), site(text="Other"), ignore_eol=True)
        self.assertEqual(code, 1, out)


class Safety(unittest.TestCase):
    def test_sitemap_with_api_or_admin_is_refused_before_any_page(self):
        for bad in ("/api/fx/lead", "/admin", "/ADMIN/leads", "/api"):
            a = site()
            a["/sitemap.xml"] = SITEMAP.replace(b"/privacy<", bad.encode() + b"<")
            code, out, t = run(a, site())
            self.assertEqual(code, 2, (bad, out))
            self.assertEqual(t.calls, [PROD + "/sitemap.xml"], bad)

    def test_side_with_path_is_refused(self):
        for bad in (PROD + "/api/fx", PROD + "/admin", "ftp://x", "table.central-aparts.store"):
            out = io.StringIO()
            code = c.run(bad, BOX, transport=FakeTransport({}), out=out)
            self.assertEqual(code, 2, (bad, out.getvalue()))

    def test_requests_are_paced(self):
        t = FakeTransport({PROD: site(), BOX: site()})
        fc = FakeClock()
        c.run(PROD, BOX, transport=t, sleep=fc.sleep, clock=fc.clock, out=io.StringIO())
        self.assertEqual(len(t.calls), 1 + 2 * 5)
        self.assertEqual(len(fc.slept), len(t.calls) - 1)
        self.assertTrue(all(s >= c.MIN_DELAY for s in fc.slept), fc.slept)

    def test_delay_below_minimum_is_refused(self):
        code = c.run(PROD, BOX, transport=FakeTransport({}), delay=0.1, out=io.StringIO())
        self.assertEqual(code, 2)

    def test_urllib_transport_sends_only_get_and_does_not_follow_redirects(self):
        seen = []

        def fake_open(self_, req, timeout=None):
            seen.append((req.get_method(), req.full_url, [type(h).__name__ for h in self_.handlers]))
            raise c.urllib.error.HTTPError(req.full_url, 404, "nf", {}, io.BytesIO(b"x"))

        with mock.patch.object(c.urllib.request.OpenerDirector, "open", fake_open):
            r = c.urllib_transport(PROD + "/")
        self.assertEqual(r, c.Response(404, b"x"))
        self.assertEqual(seen[0][0], "GET")
        self.assertIn("_NoRedirect", seen[0][2])


class FolderSide(unittest.TestCase):
    """Сторона B — тека dist/, як її віддасть nginx з try_files $uri $uri/ $uri/index.html."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        for path, body in site(css_hash="c1b62263e7").items():
            rel = path.lstrip("/")
            f = self.root / (rel + "index.html" if rel.endswith("/") or rel == "" else rel)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(body)

    def tearDown(self):
        self.tmp.cleanup()

    def test_prod_vs_folder_exits_0(self):
        code, out, t = run(site(), {}, side_b=str(self.root))
        self.assertEqual(code, 0, out)
        self.assertTrue(all(u.startswith(PROD) for u in t.calls))   # тека — без мережі

    def test_prod_vs_folder_missing_file_exits_1(self):
        (self.root / "privacy").unlink()
        code, out, _ = run(site(), {}, side_b=str(self.root))
        self.assertEqual(code, 1, out)
        self.assertIn("на B (статус 404)", out)

    def test_try_files_order(self):
        d = c.DirSide(self.root)
        self.assertEqual(d.get("/").status, 200)                    # index.html
        self.assertEqual(d.get("/en/").body, page(css_hash="c1b62263e7"))
        self.assertEqual(d.get("/en").status, 200)                  # $uri/index.html
        self.assertEqual(d.get("/privacy").body, b"<p>privacy</p>")
        self.assertEqual(d.get("/privacy/").status, 404)            # файл, а не тека
        self.assertEqual(d.get("/nope").status, 404)

    def test_no_escape_from_folder(self):
        secret = self.root.parent / f"{self.root.name}-secret.txt"
        secret.write_text("s")
        try:
            d = c.DirSide(self.root)
            self.assertEqual(d.get(f"/../{secret.name}").status, 404)
            self.assertEqual(d.get(f"/%2e%2e/{secret.name}").status, 404)
        finally:
            secret.unlink()

    def test_not_a_folder_exits_2(self):
        code, out, _ = run(site(), {}, side_b=str(self.root / "nope"))
        self.assertEqual(code, 2, out)


class Assets(unittest.TestCase):
    CSS_A = b'@font-face{src:url(/assets/fonts/x.1111111111.woff2)}\r\nbody{}'
    CSS_B = b'@font-face{src:url(/assets/fonts/x.2222222222.woff2)}\nbody{}'

    def sites(self, img_b=b"IMG", font_b=b"FONT"):
        a = site(css_hash="aaaaaaaaaa", img_hash="1234512345")
        a["/assets/styles-next.aaaaaaaaaa.css"] = self.CSS_A
        a["/assets/product/goren-hero-1600.1234512345.webp"] = b"IMG"
        a["/assets/fonts/x.1111111111.woff2"] = b"FONT"
        b = site(css_hash="bbbbbbbbbb", img_hash="6789067890")
        b["/assets/styles-next.bbbbbbbbbb.css"] = self.CSS_B
        b["/assets/product/goren-hero-1600.6789067890.webp"] = img_b
        b["/assets/fonts/x.2222222222.woff2"] = font_b
        return a, b

    def test_same_assets_behind_different_hashes_exit_0_with_ignore_eol(self):
        a, b = self.sites()
        a.update(site(css_hash="aaaaaaaaaa", img_hash="1234512345", eol="\r\n"))   # прод зібраний на Windows
        code, out, t = run(a, b, assets=True, ignore_eol=True)
        self.assertEqual(code, 0, out)
        self.assertIn(PROD + "/assets/fonts/x.1111111111.woff2", t.calls)   # шрифт знайдено через CSS

    def test_different_image_bytes_exit_1(self):
        a, b = self.sites(img_b=b"IMG-2")
        code, out, _ = run(a, b, assets=True, ignore_eol=True)
        self.assertEqual(code, 1, out)
        self.assertIn("байти різні", out)

    def test_different_font_found_through_css_exit_1(self):
        a, b = self.sites(font_b=b"FONT-2")
        code, out, _ = run(a, b, assets=True, ignore_eol=True)
        self.assertEqual(code, 1, out)
        self.assertIn("/assets/fonts/x.<hash>.woff2", out)

    def test_without_assets_flag_assets_are_not_fetched(self):
        a, b = self.sites(img_b=b"IMG-2")
        code, out, t = run(a, b, ignore_eol=True)
        self.assertEqual(code, 0, out)
        self.assertFalse([u for u in t.calls if "/assets/" in u])


class Sitemap(unittest.TestCase):
    def test_paths_from_locs_only_not_hreflang_links(self):
        self.assertEqual(c.parse_sitemap(SITEMAP), ["/", "/en/", "/privacy"])

    def test_sitemap_of_the_real_template(self):
        text = (ROOT / "site" / "sitemap.xml").read_text(encoding="utf-8").replace("{{SITE_URL}}", PROD)
        paths = c.parse_sitemap(text.encode())
        self.assertIn("/", paths)
        self.assertIn("/en/privacy", paths)
        self.assertFalse([p for p in paths if c.FORBIDDEN.match(p)])

    def test_relative_loc_is_broken(self):
        with self.assertRaises(c.SitemapError):
            c.parse_sitemap(b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>/x</loc></url></urlset>')

    def test_sitemap_index_is_not_a_urlset(self):
        with self.assertRaises(c.SitemapError):
            c.parse_sitemap(b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                            b'<sitemap><loc>https://x/s.xml</loc></sitemap></sitemapindex>')

    def test_local_sitemap_file(self):
        with tempfile.NamedTemporaryFile(suffix=".xml") as f:
            f.write(SITEMAP)
            f.flush()
            code, out, t = run(site(), site(), sitemap=f.name)
        self.assertEqual(code, 0, out)
        # /sitemap.xml із prod усе одно порівнюється, але як сторінка, а не джерело списку
        self.assertEqual(t.calls.count(PROD + "/sitemap.xml"), 1)


if __name__ == "__main__":
    unittest.main()
