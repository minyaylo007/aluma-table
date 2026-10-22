#!/usr/bin/env python3
"""Збирає вітрину ALUMA: site/ + i18n/ + content.json + catalog/products.json -> dist/.

    python build.py                 preview (так сьогодні збирається прод)
    python build.py --production    відмовляє, якщо каталог порожній чи товар без розмірів/ціни

Що робить:
  1. сторінки з шаблонів site/pages/*.html у макеті site/_layout.html для кожної мови
     (he — корінь, en — /en/): головна, каталог, картка кожного товару /p/<slug>/, «як це працює»,
     «про майстерню», FAQ, приватність, умови, доступність, 404;
  2. {{t.key}} — рядки з i18n/<мова>.json, {{TOKEN}} — факти з content.json і блоки, що їх малює
     цей файл із каталогу (картки, конфігуратор, специфікації, силуети-заглушки) — жодне число чи
     речення не живе в HTML;
  3. публікує лише те, на що посилаються сторінки, і дає ассетам імена з хешем вмісту;
  4. LF і UTF-8 на будь-якій ОС (tests/test_build_eol.py).

Лише стандартна бібліотека.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).parent
SITE = ROOT / "site"
PAGES = SITE / "pages"
DIST = ROOT / "dist"
I18N = ROOT / "i18n"
CATALOG = pathlib.Path(os.environ.get("ALUMA_CATALOG") or (ROOT / "catalog" / "products.json"))
# Зразки тонів: шматок справжнього скану шпону (tools/oak_tones.py, «הדמיה») — або ФОТО зразка з фабрики.
# Фото кладемо сюди як <тон>.jpg (tools/oak_tones.py --factory фото.jpg <тон>): воно заміняє скан, і коли
# фото є для всіх тонів товару, підпис «הדמיה» біля зразків зникає. README.md поруч.
FINISH_SCANS = SITE / "assets" / "products" / "finishes"
FINISH_PHOTOS = FINISH_SCANS / "photo"
FINISH_PHOTO_MAX = 60 * 1024

PRODUCTION = "--production" in sys.argv
CONTENT = json.loads((ROOT / "content.json").read_text(encoding="utf-8"))
LOCALES = {"he": "", "en": "/en", "ru": "/ru"}          # мова -> префікс шляху; перша — x-default і корінь сайту
TEXT_EXT = (".html", ".css", ".js", ".webmanifest", ".xml", ".txt", ".svg", ".json")

# сторінки: (шаблон, шлях без префікса мови, ключ заголовка, ключ опису)
STATIC_PAGES = [
    ("home", "/", "home_title", "home_desc"),
    ("catalog", "/catalog/", "catalog_title", "catalog_desc"),
    ("how", "/how/", "how_title", "how_desc"),
    ("about", "/about/", "about_title", "about_desc"),
    ("faq", "/faq/", "faq_title", "faq_desc"),
    ("privacy", "/privacy", "privacy_title", "privacy_desc"),
    ("terms", "/terms", "terms_title", "terms_desc"),
    ("accessibility", "/accessibility", "a11y_title", "a11y_desc"),
    ("404", "/404", "nf_title", "nf_desc"),
    ("cart", "/cart/", "cart_title", "cart_desc"),
    ("checkout", "/checkout/", "checkout_title", "checkout_desc"),
]
# кошик і оформлення — кроки магазину (specs/003-shop-funnel): не для пошуковика і не в sitemap
NOINDEX = {"cart", "checkout"}


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def esc_bidi(s) -> str:
    """Текст тіла сторінки: каталог позначає розміри в he-описах U+2066 (LRI) … U+2069 (PDI) — стають <bdi dir="ltr">."""
    return esc(s).replace("\u2066", '<bdi dir="ltr">').replace("\u2069", "</bdi>")


def write_text_lf(f: pathlib.Path, text: str) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def read_text(f: pathlib.Path) -> str:
    return f.read_bytes().decode("utf-8").replace("\r\n", "\n")


def digest_bytes(data: bytes, suffix: str) -> str:
    if suffix.lower() in TEXT_EXT:            # джерело з CRLF (Windows checkout) хешується як LF
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()[:10]


CSS_COMMENT = re.compile(r"/\*[\s\S]*?\*/")


def strip_css_comments(css: str) -> str:
    """CSS без коментарів /* … */ і без порожніх рядків, що лишилися після них; решта байт у байт."""
    css = CSS_COMMENT.sub("", css)
    return "\n".join(line.rstrip() for line in css.split("\n") if line.strip())


def money(v: int, loc: str = "he") -> str:
    """Ціна: «₪4,490»; у ru — як пишуть російською, «4 490 ₪» з нерозривними пробілами (так само в aluma.js/shop.js)."""
    if loc == "ru":
        return f"{int(v):,}".replace(",", "\u00a0") + "\u00a0₪"
    return "₪" + f"{int(v):,}"


# --------------------------------------------------------------------------- дані


# Плейсхолдери legal.*.json, що беруться з /api/fx/config у браузері (aluma.js, [data-lv]). Абзац, де є хоч один
# із них, лежить прихованим, доки всі значення не прийдуть: «להשלמה» на сайті не буває. {company_name} — виняток:
# поки фірми немає, на його місці бренд, і абзац видно.
LEGAL_RUNTIME = ("company_name", "business_id", "address", "phone", "email", "a11y_name", "a11y_phone", "a11y_email",
                 "court_city")
LEGAL_LTR = ("business_id", "phone", "email", "a11y_phone", "a11y_email")


def legal_text(text: str, loc: str) -> str:
    """Рядок legal.*.json -> HTML: {brand}/{updated} — під час збірки, решта — спани для aluma.js."""
    brand = CONTENT.get("BRAND_HE" if loc == "he" else "BRAND_LAT") or CONTENT.get("BRAND_LAT", "ALUMA")
    out = esc(text).replace("{brand}", esc(brand)).replace("{updated}", esc(CONTENT.get("LEGAL_UPDATED", "")))

    def span(m):
        key = m.group(1)
        if key not in LEGAL_RUNTIME:
            raise SystemExit(f"legal.{loc}.json: unknown placeholder {{{key}}}")
        fallback = esc(brand) if key == "company_name" else ""
        inner = f'<span data-lv="{key}">{fallback}</span>'
        return f'<bdi dir="ltr">{inner}</bdi>' if key in LEGAL_LTR else inner
    return re.sub(r"\{([a-z0-9_]+)\}", span, out)


def legal_block(tag: str, text: str, loc: str) -> str:
    need = sorted(set(re.findall(r"\{([a-z0-9_]+)\}", text)) - {"brand", "updated", "company_name"})
    attrs = f' data-lneed="{" ".join(need)}" hidden' if need else ""
    return f"<{tag}{attrs}>{legal_text(text, loc)}</{tag}>"


def legal_page(doc: dict, loc: str) -> str:
    out = [f'<h1 class="h1">{legal_text(doc["title"], loc)}</h1>']
    if doc.get("updated") and CONTENT.get("LEGAL_UPDATED"):
        out.append(f'<p class="legal-updated">{legal_text(doc["updated"], loc)}</p>')
    for sec in doc.get("sections", []):
        ps = [legal_block("p", t, loc) for t in sec.get("p", [])]
        lis = [legal_block("li", t, loc) for t in sec.get("li", [])]
        empty = all(" hidden>" in b for b in ps + lis)       # розділ лише з незаданих даних — сховано цілком
        out.append(f'<section class="legal-sec" data-lsec{" hidden" if empty else ""}><h2>{legal_text(sec["h"], loc)}</h2>')
        out += ps
        if lis:
            out.append("<ul>" + "".join(lis) + "</ul>")
        out.append("</section>")
    return "\n".join(out)


def load_locales() -> dict:
    """i18n/<мова>.json + юридичні тексти сесії 3 (legal.<мова>.json): сторінки, банер, галочка реклами."""
    out = {}
    for loc in LOCALES:
        data = json.loads(read_text(I18N / f"{loc}.json"))
        legal_f = I18N / f"legal.{loc}.json"
        if legal_f.is_file():
            legal = json.loads(read_text(legal_f))
            for page in ("privacy", "terms", "accessibility"):
                if page in legal:
                    data[f"{page}_html"] = legal_page(legal[page], loc)
            ck, mk = legal.get("cookies") or {}, legal.get("marketing") or {}
            for key, val in (("cookie_notice", ck.get("text")), ("notice_ok", ck.get("accept")),
                             ("notice_no", ck.get("decline")), ("cookie_settings", ck.get("settings")),
                             ("f_marketing", mk.get("label")), ("f_marketing_hint", mk.get("hint")),
                             ("f_lead_notice", (legal.get("lead_notice") or {}).get("text"))):
                if val:
                    data[key] = legal_text(val, loc)
        out[loc] = {k: v for k, v in data.items() if not k.startswith("_")}
    return out


def load_catalog() -> list:
    if not CATALOG.is_file():
        raise SystemExit(f"catalog missing: {CATALOG} (сесія 2 кладе catalog/products.json)")
    data = json.loads(read_text(CATALOG))
    items = data["products"] if isinstance(data, dict) else data
    out, seen = [], set()
    for p in items:
        if p.get("hidden"):
            continue
        slug = str(p.get("slug") or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug) or slug in seen:
            raise SystemExit(f"catalog: bad or duplicate slug {slug!r}")
        seen.add(slug)
        sizes = [s for s in p.get("sizes") or [] if s.get("price_ils")]
        if not sizes and PRODUCTION:
            raise SystemExit(f"catalog: {slug} has no priced sizes")
        p["sizes"] = sizes
        p.setdefault("finishes", [])
        p.setdefault("bases", [])
        p.setdefault("images", [])
        p.setdefault("badges", [])
        if not p.get("price_from_ils") and sizes:
            p["price_from_ils"] = min(int(s["price_ils"]) for s in sizes)
        out.append(p)
    if not out:
        raise SystemExit("catalog: no visible products")
    return out


# Числа словами для рядків i18n («בחמישה גוונים», «in five finishes», «в пяти тонах»): іменники там чоловічого роду;
# у ru — прийменниковий відмінок (рядки ru.json пишуть лише «в {{FINISH_COUNT}} тонах»).
# Поза словником — цифри (у he з макафом: «וב־11 גוונים»).
NUM_WORDS = {"he": {2: "שניים", 3: "שלושה", 4: "ארבעה", 5: "חמישה", 6: "שישה", 7: "שבעה", 8: "שמונה", 9: "תשעה", 10: "עשרה"},
             "en": {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"},
             "ru": {2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти", 6: "шести", 7: "семи", 8: "восьми", 9: "девяти",
                    10: "десяти"}}


def num_word(n: int, loc: str) -> str:
    return NUM_WORDS.get(loc, {}).get(n) or (f"־{n}" if loc == "he" else str(n))


def catalog_facts(products: list, loc: str) -> dict:
    """Факти каталогу для тексту: строк виготовлення, кількість і назви тонувань — щоб i18n не тримав їх числами."""
    lts = [p.get("lead_time_weeks") or [10, 12] for p in products]
    finishes = {}
    for p in products:
        for f in p.get("finishes") or []:
            finishes.setdefault(f.get("id"), L(f.get("name"), loc))
    names = list(finishes.values())
    if loc != "he":
        names = [n[:1].lower() + n[1:] for n in names]
    # «א, ב וג» / «a, b and c» / «а, б и в»: у he сполучник «ו» пишеться разом зі словом
    conj = {"he": " ו", "ru": " и "}.get(loc, " and ")
    joined = ", ".join(names[:-1]) + conj + names[-1] if len(names) > 1 else "".join(names)
    word = num_word(len(names), loc)
    return {"LEAD_WEEKS": f"{min(lt[0] for lt in lts)}–{max(lt[-1] for lt in lts)}",
            "FINISH_COUNT": word, "FINISH_COUNT_CAP": word[:1].upper() + word[1:], "FINISH_NAMES": joined}


def L(obj, loc: str) -> str:
    """Поле {he, en, …} -> рядок мови; без перекладу — англійська (для he — іврит), далі будь-що; рядок — як є."""
    if isinstance(obj, dict):
        order = (loc, "he", "en") if loc == "he" else (loc, "en", "he")
        return str(next((obj[k] for k in order if obj.get(k)), ""))
    return str(obj or "")


# --------------------------------------------------------------------------- силуети-заглушки


def silhouette(p: dict, cls: str = "") -> str:
    """Лінійний силует виробу за його ж розмірами (1 одиниця = 1 см), поверх плитки кольору дуба.
    Заглушка, доки нема візуалізацій: жодної фотографії, лише креслення."""
    s = (p.get("sizes") or [{}])[0]
    length = float(s.get("length_cm") or 160)
    height = float(s.get("height_cm") or 75)
    cat = str(p.get("category") or "")
    slug = str(p.get("slug") or "")
    vw, vh = 300.0, 200.0
    scale = min(220 / max(length, 1), 120 / max(height, 1))
    w, h = length * scale, height * scale
    x0, base = (vw - w) / 2, 160.0
    top = base - h
    t = max(3.0, 4 * scale)
    parts = []
    round_ = "round" in slug or "round" in cat or str(s.get("label", "")).startswith("Ø")
    if cat in ("media_unit", "storage") or "tv" in slug or "unit" in slug:
        # підвісна тумба: корпус на стіні, тінь під ним, вертикальні фасади
        y = top - 10
        parts.append(f'<line class="sil-wall" x1="{x0 - 30:.1f}" y1="{y + h / 2:.1f}" x2="{x0 + w + 30:.1f}" y2="{y + h / 2:.1f}"/>')
        parts.append(f'<rect class="sil-body" x="{x0:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="1.5"/>')
        n = 3 if length < 170 else 4
        for i in range(1, n):
            xx = x0 + w * i / n
            parts.append(f'<line class="sil-line" x1="{xx:.1f}" y1="{y + 4:.1f}" x2="{xx:.1f}" y2="{y + h - 4:.1f}"/>')
        parts.append(f'<ellipse class="sil-shadow" cx="{vw / 2:.1f}" cy="{base + 6:.1f}" rx="{w / 2.2:.1f}" ry="4"/>')
    else:
        leg = max(3.0, 5 * scale)
        inset = w * (0.08 if round_ else 0.06)
        parts.append(f'<ellipse class="sil-shadow" cx="{vw / 2:.1f}" cy="{base + 2:.1f}" rx="{w / 2:.1f}" ry="5"/>')
        if round_:
            cx = vw / 2
            parts.append(f'<path class="sil-leg" d="M{cx - leg:.1f} {top + t:.1f}H{cx + leg:.1f}L{cx + leg * 1.6:.1f} {base:.1f}H{cx - leg * 1.6:.1f}Z"/>')
            parts.append(f'<rect class="sil-leg" x="{cx - w * 0.22:.1f}" y="{base - 3:.1f}" width="{w * 0.44:.1f}" height="3" rx="1.5"/>')
        else:
            for xx in (x0 + inset, x0 + w - inset - leg):
                parts.append(f'<rect class="sil-leg" x="{xx:.1f}" y="{top + t:.1f}" width="{leg:.1f}" height="{base - top - t:.1f}"/>')
            if cat == "console" or "console" in slug:
                parts.append(f'<rect class="sil-line-r" x="{x0 + inset:.1f}" y="{base - h * 0.28:.1f}" width="{w - 2 * inset:.1f}" height="{t * 0.8:.1f}"/>')
        parts.append(f'<rect class="sil-top" x="{x0:.1f}" y="{top:.1f}" width="{w:.1f}" height="{t:.1f}" rx="1.2"/>')
    return (f'<svg class="sil {cls}" viewBox="0 0 {vw:.0f} {vh:.0f}" aria-hidden="true" focusable="false">'
            + "".join(parts) + "</svg>")


# --------------------------------------------------------------------------- блоки з каталогу


def picture(img: dict, loc: str, *, eager: bool = False, sizes: str = "100vw", cls: str = "") -> str:
    src = str(img.get("src") or "")
    alt = esc(L(img.get("alt"), loc))
    attrs = f'src="{esc(src)}" alt="{alt}" decoding="async"'
    attrs += ' loading="eager" fetchpriority="high"' if eager else ' loading="lazy"'
    if img.get("width") and img.get("height"):
        attrs += f' width="{int(img["width"])}" height="{int(img["height"])}"'
    if img.get("srcset"):
        attrs += f' srcset="{esc(img["srcset"])}" sizes="{esc(sizes)}"'
    avset = avif_srcset(img, src)
    sources = f'<source type="image/avif" srcset="{esc(avset)}" sizes="{esc(sizes)}">' if avset else ""
    return f'<picture class="{cls}">{sources}<img {attrs}></picture>'


def avif_srcset(img: dict, src: str) -> str:
    """AVIF-набір для <source> або "" — тоді браузер бере WebP.

    Браузер з AVIF бере <source> першим, навіть коли AVIF важчий (22.10: tavor/home-1600.avif 75 КБ проти 65 КБ WebP).
    Тому набір іде, лише якщо він повний: ті самі ширини, що в WebP, і КОЖЕН AVIF є й легший за свого WebP-близнюка.
    Розміри файлів детерміновані — збірка лишається байт у байт на будь-якій ОС."""
    if not src.endswith(".webp"):
        return ""
    webset = img.get("srcset") or src
    avset = img.get("srcset_avif") or re.sub(r"\.webp(?=\s|,|$)", ".avif", webset)
    web = [e.split() for e in webset.split(",")]
    av = [e.split() for e in avset.split(",")]
    if len(web) != len(av):
        return ""
    for (w_url, *w_desc), (a_url, *a_desc) in zip(web, av):
        w_file, a_file = SITE / w_url.lstrip("/"), SITE / a_url.lstrip("/")
        if w_desc != a_desc or not a_url.endswith(".avif") or not w_file.is_file() or not a_file.is_file():
            return ""
        if a_file.stat().st_size >= w_file.stat().st_size:
            return ""
    return avset


def media(p: dict, loc: str, *, eager: bool = False, sizes: str = "100vw") -> str:
    """Перша візуалізація товару з позначкою «הדמיה» або плитка-силует."""
    imgs = [i for i in p.get("images") or [] if i.get("src")]
    if imgs:
        return (f'<div class="media media--img">{picture(imgs[0], loc, eager=eager, sizes=sizes)}'
                f'<span class="viz-tag">{{{{t.viz_tag}}}}</span></div>')
    return f'<div class="media media--tile">{silhouette(p)}</div>'


def finish_chip(f: dict) -> tuple:
    """(style для зразка, чи це фото з фабрики). Колір каталогу — підкладка, поки вантажиться картинка."""
    hexv = f.get("hex") if re.fullmatch(r"#[0-9a-fA-F]{3,8}", str(f.get("hex") or "")) else "#c8a27a"
    fid = str(f.get("id") or "")
    if not re.fullmatch(r"[a-z0-9-]+", fid):
        return f"--c:{hexv}", False
    photo = FINISH_PHOTOS / f"{fid}.jpg"
    if photo.is_file():
        if photo.stat().st_size > FINISH_PHOTO_MAX:
            raise SystemExit(f"photo/{photo.name}: більше {FINISH_PHOTO_MAX // 1024} КБ — "
                             "пропустіть через tools/oak_tones.py --factory")
        return f"--c:{hexv};--i:url(/assets/products/finishes/photo/{fid}.jpg)", True
    if (FINISH_SCANS / f"{fid}.webp").is_file():
        return f"--c:{hexv};--i:url(/assets/products/finishes/{fid}.webp)", False
    return f"--c:{hexv}", False


def finishes_viz(fins: list) -> bool:
    """Чи є серед зразків хоч один не-фото (тоді група підписана «הדמיה»)."""
    return any(not finish_chip(f)[1] for f in fins)


def card(p: dict, loc: str, prefix: str, eager: bool = False) -> str:
    """Картка товару: фото 4:5 (другий кадр — при наведенні), назва, ціна «מ־₪», кружки тонувань."""
    price = (f'<span class="card-price">{{{{t.from}}}}<bdi dir="ltr">{money(p["price_from_ils"], loc)}</bdi></span>'
             if p.get("price_from_ils") else "")
    sz = "(min-width: 1000px) 30vw, (min-width: 600px) 46vw, 92vw"
    imgs = [i for i in p.get("images") or [] if i.get("src")]
    if imgs:
        alt2 = (f'<span class="card-alt" aria-hidden="true">{picture(imgs[1], loc, sizes=sz)}</span>'
                if len(imgs) > 1 else "")
        pic = (f'<span class="media media--img card-media">{picture(imgs[0], loc, eager=eager, sizes=sz)}{alt2}'
               f'<span class="viz-tag">{{{{t.viz_tag}}}}</span></span>')
    else:
        pic = f'<span class="media media--tile card-media">{silhouette(p)}</span>'
    dots = "".join(f'<span class="card-dot" style="{esc(finish_chip(f)[0])}" title="{esc(L(f.get("name"), loc))}"></span>'
                   for f in (p.get("finishes") or [])[:6] if f.get("hex"))
    names = ", ".join(esc(L(f.get("name"), loc)) for f in (p.get("finishes") or [])[:6] if f.get("hex"))
    sw = (f'<span class="card-dots" role="img" aria-label="{{{{t.finishes_label}}}}: {names}">{dots}</span>' if dots else "")
    return (f'<li class="card"><a class="card-link" href="{prefix}/p/{p["slug"]}/" data-product="{esc(p["id"])}">'
            f'{pic}<span class="card-body"><span class="card-row"><span class="card-name">{esc(L(p.get("name"), loc))}</span>'
            f'{price}</span>{sw}</span></a></li>')


def badges(p: dict, loc: str) -> str:
    items = [b for b in p.get("badges") or [] if b.get("id") != "launch_series" and L(b.get("label"), loc)]
    if not items:
        return ""
    return '<ul class="badges" role="list">' + "".join(
        f'<li class="badge">{esc(L(b.get("label"), loc))}</li>' for b in items) + "</ul>"


def grid(products: list, loc: str, prefix: str, limit: int | None = None) -> str:
    items = products[:limit] if limit else products
    return '<ul class="cards" role="list">' + "".join(card(p, loc, prefix, eager=False) for p in items) + "</ul>"


def size_dims(s: dict) -> str:
    """Підпис плитки розміру; круглий стіл — як у кошику й рекламі: «Ø115», без висоти (аудит 22.10 (б) 5)."""
    lab = str(s.get("label") or "")
    if lab.startswith("Ø"):
        return lab
    parts = [s.get("length_cm"), s.get("width_cm"), s.get("height_cm")]
    parts = [str(x) for x in parts if x]
    return "×".join(parts)


def first_frame(p: dict) -> dict | None:
    """Перший кадр товару з src; без кадру — None."""
    return next((i for i in p.get("images") or [] if i.get("src")), None)


def smallest_src(img: dict) -> str:
    """Найменший кадр зі srcset (400w), без srcset — src: мініатюрі 44–96 px не треба home-1600 (аудит 22.10 (б) сев. 2)."""
    best = None
    for part in (img.get("srcset") or "").split(","):
        bits = part.split()
        if len(bits) == 2 and bits[1].endswith("w") and bits[1][:-1].isdigit():
            if best is None or int(bits[1][:-1]) < best[0]:
                best = (int(bits[1][:-1]), bits[0])
    return best[1] if best else img["src"]


def thumb_src(p: dict) -> str:
    """Мініатюра в кошику (shop.js): найменший кадр першого зображення; без кадру — порожньо."""
    img = first_frame(p)
    return smallest_src(img) if img else ""


def thumb(p: dict, loc: str) -> str:
    """Мініатюра обраного столу в липкій кнопці: найменший кадр героя; alt — «הדמיה: <назва>» (аудит 22.10, (а) 11)."""
    img = first_frame(p)
    if not img:
        return ""
    srcset = f' srcset="{esc(img["srcset"])}" sizes="44px"' if img.get("srcset") else ""
    tag = (f'<img class="sticky-thumb" src="{esc(smallest_src(img))}"{srcset} alt="{{{{t.viz_tag}}}}: {esc(L(p.get("name"), loc))}"'
           ' width="44" height="44" loading="lazy" decoding="async">')
    # той самий AVIF-набір, що в мініатюрі галереї: браузер бере вже закешований 400w AVIF, а не окремий WebP (Lighthouse 22.10, п. 3)
    avset = avif_srcset(img, str(img.get("src") or ""))
    if not avset:
        return tag
    return f'<picture class="sticky-pic"><source type="image/avif" srcset="{esc(avset)}" sizes="44px">{tag}</picture>'


def configurator(p: dict, loc: str) -> str:
    out = []
    sizes = p.get("sizes") or []
    if sizes:
        out.append('<fieldset class="opt" data-opt="size"><legend>{{t.pick_size}}</legend><div class="pills">')
        for i, s in enumerate(sizes):
            ext = (f'<span class="pill-sub"><bdi dir="ltr">→ {esc(s["extended_cm"])}</bdi></span>'
                   if s.get("extended_cm") else "")
            out.append(
                f'<label class="pill"><input type="radio" name="size" value="{esc(s.get("label"))}"'
                f' data-price="{int(s["price_ils"])}"{" checked" if i == 0 else ""}>'
                f'<span class="pill-main"><bdi dir="ltr">{esc(size_dims(s))}</bdi></span>{ext}'
                f'<span class="pill-price"><bdi dir="ltr">{money(s["price_ils"], loc)}</bdi></span>'
                # «הנבחר ביותר» — лише коли каталог сам позначив розмір; вигаданої популярності не показуємо
                + ('<span class="pill-pop">{{t.size_popular}}</span>' if s.get("popular") is True else "") + '</label>')
        out.append('</div><a class="opt-custom js-custom" href="#register">{{t.custom_size}}</a></fieldset>')
    fins = p.get("finishes") or []
    if fins:
        first = esc(L(fins[0].get("name"), loc))
        out.append('<fieldset class="opt" data-opt="finish"><legend>{{t.pick_finish}} <span class="opt-val" data-finish-name>'
                   + first + '</span></legend><div class="swatches">')
        for i, f in enumerate(fins):
            name = esc(L(f.get("name"), loc))
            out.append(f'<label class="swatch" title="{name}"><input type="radio" name="finish" value="{esc(f.get("id"))}"'
                       f' data-name="{name}"{" checked" if i == 0 else ""}><span class="swatch-dot" style="{esc(finish_chip(f)[0])}"></span>'
                       f'<span class="sr">{name}</span></label>')
        out.append("</div>" + ('<span class="swatch-viz">{{t.viz_tag}}</span>' if finishes_viz(fins) else "") + "</fieldset>")
    bases = p.get("bases") or []
    if bases:
        out.append('<fieldset class="opt" data-opt="base"><legend>{{t.pick_base}}</legend><div class="pills pills--text">')
        for i, b in enumerate(bases):
            out.append(f'<label class="pill"><input type="radio" name="base" value="{esc(b.get("id"))}"{" checked" if i == 0 else ""}>'
                       f'<span class="pill-main">{esc(L(b.get("name"), loc))}</span></label>')
        out.append("</div></fieldset>")
    return "".join(out)


def size_bars(products: list) -> str:
    """Смуги довжин першого товару з кількома розмірами — у масштабі, з його ж чисел."""
    p = next((q for q in products if len(q.get("sizes") or []) > 1), None)
    if not p:
        return ""
    sizes = [s for s in p["sizes"] if s.get("length_cm")]
    longest = max(float(s.get("extended_cm") or s["length_cm"]) for s in sizes)
    rows = []
    for s in sizes:
        w = float(s["length_cm"]) / longest * 100
        ext = float(s.get("extended_cm") or 0) / longest * 100
        extra = (f'<i class="gp-ext" style="width:{ext:.1f}%"></i>' if ext else "")
        rows.append(f'<span class="gp-row"><b><bdi dir="ltr">{esc(s["length_cm"])}</bdi></b><span class="gp-bar">{extra}'
                    f'<i class="gp-len" style="width:{w:.1f}%"></i></span>'
                    + (f'<small><bdi dir="ltr">→ {esc(s["extended_cm"])}</bdi></small>' if ext else "") + "</span>")
    return f'<div class="grain-panel" aria-hidden="true">{"".join(rows)}</div>'


def specs(p: dict, loc: str) -> str:
    rows = []
    sizes = p.get("sizes") or []
    if sizes:
        lens = ", ".join(esc(s.get("label")) for s in sizes)
        rows.append(("{{t.spec_sizes}}", f'<bdi dir="ltr">{lens}</bdi>&nbsp;{{{{t.cm}}}}'))
        s0 = sizes[0]
        if s0.get("width_cm"):
            ws = sorted({int(s["width_cm"]) for s in sizes if s.get("width_cm")})
            rows.append(("{{t.spec_width}}", f'<bdi dir="ltr">{" / ".join(map(str, ws))}</bdi>&nbsp;{{{{t.cm}}}}'))
        if s0.get("height_cm"):
            hs = sorted({int(s["height_cm"]) for s in sizes if s.get("height_cm")})
            rows.append(("{{t.spec_height}}", f'<bdi dir="ltr">{" / ".join(map(str, hs))}</bdi>&nbsp;{{{{t.cm}}}}'))
        ext = [s for s in sizes if s.get("extended_cm")]
        if ext:
            pairs = ", ".join(f'{esc(s["length_cm"])}→{esc(s["extended_cm"])}' for s in ext)
            rows.append(("{{t.spec_extended}}", f'<bdi dir="ltr">{pairs}</bdi>&nbsp;{{{{t.cm}}}}'))
    mat = L(p.get("material"), loc)
    if mat:
        rows.append(("{{t.spec_material}}", esc(mat)))
    if p.get("finishes"):
        rows.append(("{{t.spec_finishes}}", esc(", ".join(L(f.get("name"), loc) for f in p["finishes"]))))
    if p.get("bases"):
        rows.append(("{{t.spec_bases}}", esc(", ".join(L(b.get("name"), loc) for b in p["bases"]))))
    # строк першої серії — оцінка з каталогу (lead_time_weeks); точна дата — лише в підтвердженні замовлення
    rows.append(("{{t.spec_lead}}", "{{t.lead_series}}" if listed("SERIES_PRODUCTS", p) else "{{t.lead_exact}}"))
    rows.append(("{{t.spec_incl}}", "{{t.spec_incl_v}}"))
    rows.append(("{{t.spec_ship}}", "{{t.ship_pickup}} — {{PICKUP_PRICE}} · {{t.ship_door}} — {{DELIVERY_PRICE}}"))
    rows.append(("{{t.spec_warranty}}", "{{t.spec_warranty_v}}"))
    rows.append(("{{t.spec_assembly}}", "{{t.ship_assembly_long}}" if listed("ASSEMBLY_PRODUCTS", p) else "{{t.assembly_other}}"))
    return '<dl class="specs">' + "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in rows) + "</dl>"


# ---- «מה כלול במחיר»: лише факти з каталогу (матеріал, розміри, місця) і з i18n; жодних порівнянь з іншими
INC_ICONS = {  # 20×20, штрих currentColor, декоративні
    "table": '<path d="M2 7h16M4 7v9M16 7v9M4 11h12" />',
    "veneer": '<path d="M3 6h14M3 10h14M3 14h14" /><path d="M7 6c1 1.5 1 2.5 0 4M12 10c1 1.5 1 2.5 0 4" />',
    "edge": '<rect x="3" y="6" width="14" height="8" rx="1" /><path d="M3 9h14" />',
    "size": '<path d="M2 13l11-11 5 5-11 11z" /><path d="M6 9l2 2M9 6l2 2M12 3l2 2" />',
    "seats": '<circle cx="7" cy="7" r="2.5" /><circle cx="14" cy="8" r="2" /><path d="M2.5 17c.5-3 2.3-4.5 4.5-4.5s4 1.5 4.5 4.5M11.5 13.5c.7-.6 1.5-1 2.5-1 2 0 3.3 1.5 3.6 4" />',
    "incl": '<path d="M2 6h10v8H2zM12 9h3l3 3v2h-6" /><circle cx="5.5" cy="15" r="1.5" /><circle cx="14.5" cy="15" r="1.5" />',
    "warranty": '<path d="M10 2l6 2.5v5c0 4-2.6 7-6 8.5-3.4-1.5-6-4.5-6-8.5v-5z" /><path d="M7 10l2 2 4-4" />',
    "own": '<path d="M3 17V8l5-3v3l5-3v3l4-2v11z" /><path d="M7 17v-4h3v4" />',
}


def few(key: str, n: int, loc: str) -> str:
    """Ключ слова після числа: у ru 2–4 (крім 12–14) — форма «_few» («3 размера», «4 человека»), інакше — сам ключ."""
    return f"{key}_few" if loc == "ru" and n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else key


def seat_span(lo_hi: list) -> str:
    lo, hi = int(lo_hi[0]), int(lo_hi[-1])
    return str(lo) if lo == hi else f"{lo}–{hi}"


def included(p: dict, loc: str) -> str:
    # обідній стіл — першим рядком: ціна без стільців (ознака — категорія каталогу, не slug)
    rows = [("table", "{{t.inc_table_only}}")] if p.get("category") == "dining_table" else []
    rows.append(("veneer", "{{t.inc_veneer}}"))
    # кромка чи фасади — як написано в матеріалі каталогу (OFEK: фасади з масиву)
    rows.append(("edge", "{{t.inc_fronts}}" if "fronts" in L(p.get("material"), "en") else "{{t.inc_edges}}"))
    n = len(p.get("sizes") or [])
    rows.append(("size", f'<bdi dir="ltr">{n}</bdi> {{{{t.{few("inc_sizes", n, loc)}}}}}' if n > 1
                 else "{{t.inc_size_other}}"))
    seats = p.get("seats") or {}
    if seats.get("closed") and seats.get("extended"):
        word = few("unfold_seats", seats["closed"][-1], loc)
        rows.append(("seats", f'<bdi dir="ltr">{seat_span(seats["closed"])}</bdi> {{{{t.{word}}}}} · '
                              f'{{{{t.inc_seats_open}}}} <bdi dir="ltr">{seat_span(seats["extended"])}</bdi>'))
    rows += [("incl", "{{t.inc_vat}}"), ("warranty", "{{t.inc_warranty}}"), ("own", "{{t.inc_own}}")]
    lis = "".join(f'<li><svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" focusable="false">{INC_ICONS[k]}</svg>'
                  f"<span>{v}</span></li>" for k, v in rows)
    return f'<section class="pdp-inc" aria-labelledby="inc-h"><h2 class="pdp-inc-h" id="inc-h">{{{{t.inc_h}}}}</h2><ul role="list">{lis}</ul></section>'


def listed(key: str, p: dict) -> bool:
    """Товар у списку content.json через кому (SERIES_PRODUCTS, ASSEMBLY_PRODUCTS) — факт стосується лише його."""
    return p.get("slug") in [x.strip() for x in str(CONTENT.get(key) or "").split(",")]


def ship_terms(p: dict, loc: str) -> str:
    """Рядок під ціною: самовивіз, доставка до дверей, складання — числа лише з content.json (токени)."""
    items = ["{{t.ship_pickup}} — {{PICKUP_PRICE}}", "{{t.ship_door}} — {{DELIVERY_PRICE}}"]
    if listed("ASSEMBLY_PRODUCTS", p):
        items.append("{{t.ship_assembly}}")
    return '<ul class="pdp-terms" role="list">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>"


def ship_choice() -> str:
    """Вибір «самовивіз / до дверей» для кошика й кроку «משלוח»: shop.js читає name="ship", ціни — DATA.ship."""
    opts = [("door", "{{t.ship_door}} — {{DELIVERY_PRICE}}"), ("pickup", "{{t.ship_pickup}} — {{PICKUP_PRICE}}")]
    chips = "".join(f'<label class="chip"><input type="radio" name="ship" value="{v}"><span>{x}</span></label>' for v, x in opts)
    return (f'<fieldset class="f f-choice ship-choice" data-ship-choice><legend>{{{{t.ship_legend}}}}</legend>'
            f'<div class="chips">{chips}</div><p class="f-hint">{{{{t.ship_hint}}}}</p></fieldset>')


def inside(p: dict, loc: str) -> str:
    """«מה בפנים»: з чого зроблено (числа — content.json, специфікація 22.10) + інструкція збирання PDF своєю мовою.
    Лише для товарів INSIDE_PRODUCTS; PDF шукаємо site/assets/docs/<slug>-assembly-<мова>.pdf, нема своєї мови — en."""
    if not listed("INSIDE_PRODUCTS", p):
        return ""
    rows = ["top", "board", "edge", "legs", "mech", "finish", "origin"]
    lis = "".join(f"<li>{{{{t.inside_{k}}}}}</li>" for k in rows)
    pdf = next((f"/assets/docs/{p['slug']}-assembly-{lang}.pdf" for lang in (loc, "en")
                if (SITE / "assets" / "docs" / f"{p['slug']}-assembly-{lang}.pdf").is_file()), "")
    link = (f'<p><a class="pdp-pdf" href="{pdf}" target="_blank" rel="noopener" data-cta="assembly_pdf">'
            f'{{{{t.{"assembly_pdf" if pdf.endswith(f"-{loc}.pdf") else "assembly_pdf_en"}}}}}</a></p>') if pdf else ""
    return (f'<div class="pdp-inside"><h3 class="h3">{{{{t.inside_h}}}}</h3><ul class="pdp-inside-list" role="list">{lis}</ul>'
            f'<p class="muted small">{{{{t.inside_note}}}}</p>{link}</div>')


SIZE_HELP = {"dining_table": ("{{t.size_clear}}", "{{t.size_seat}}"), "coffee_table": ("{{t.size_clear_pass}}",)}


def size_help(p: dict, loc: str) -> str:
    """«איך לבחור מידה» — лише для столів; числа — токени CLEARANCE_CM (content.json) і SEAT_CM (план місць)."""
    lines = SIZE_HELP.get(p.get("category"))
    if not lines:
        return ""
    lis = "".join(f"<li>{x}</li>" for x in lines)
    return ('<section class="pdp-size" aria-labelledby="size-h"><h2 class="pdp-inc-h" id="size-h">{{t.size_h}}</h2>'
            f'<ul role="list">{lis}</ul>'
            '<p><a class="link-arrow js-wa" data-wa="size" href="#" hidden>{{t.size_help}}</a></p></section>')


# ---- план «סגור / פתוח»: вигляд згори з кріслами; числа — лише з каталогу
SEAT_CM = 55  # ширина місця за столом уздовж краю; число місць затиснуте в діапазон seats каталогу


def plan_seats(length: float, width: float, round_: bool, rng: list) -> int:
    if round_:
        n = int(math.pi * length // 75)
    else:
        n = 2 * int(length // SEAT_CM) + (2 if width >= 80 else 0)
    lo, hi = int(rng[0]), int(rng[-1])
    return max(lo, min(hi, n))


def plan_svg(length: float, width: float, span: float, seats: int, round_: bool, cls: str) -> str:
    pad, cw, cd, gap = 62.0, 44.0, 36.0, 8.0
    vw, vh = span + 2 * pad, width + 2 * pad
    x0, y0 = (vw - length) / 2, pad
    rx = width / 2 if round_ else 4
    parts = []
    chairs = []  # (cx, cy, кут)
    if round_ and length == width:
        r = length / 2 + gap + cd / 2
        for i in range(seats):
            a = 2 * math.pi * i / seats - math.pi / 2
            chairs.append((vw / 2 + r * math.cos(a), y0 + width / 2 + r * math.sin(a), math.degrees(a) + 90))
    else:
        ends = 2 if (seats % 2 == 0 and width >= 80) or round_ else 0
        side = (seats - ends) // 2
        for i in range(side):
            cx = x0 + length * (i + 0.5) / side
            chairs.append((cx, y0 - gap - cd / 2, 0))
            chairs.append((cx, y0 + width + gap + cd / 2, 180))
        if ends:
            chairs.append((x0 - gap - cd / 2, y0 + width / 2, 270))
            chairs.append((x0 + length + gap + cd / 2, y0 + width / 2, 90))
    for cx, cy, a in chairs:
        parts.append(f'<rect class="plan-chair" x="{cx - cw / 2:.1f}" y="{cy - cd / 2:.1f}" width="{cw:.0f}" height="{cd:.0f}"'
                     f' rx="7" transform="rotate({a:.0f} {cx:.1f} {cy:.1f})"/>')
    parts.append(f'<rect class="plan-top" x="{x0:.1f}" y="{y0:.1f}" width="{length:.0f}" height="{width:.0f}" rx="{rx:.1f}"/>')
    return (f'<svg class="plan-svg plan-svg--{cls}" viewBox="0 0 {vw:.0f} {vh:.0f}" aria-hidden="true" focusable="false">'
            + "".join(parts) + "</svg>")


def plan(p: dict, loc: str) -> str:
    seats = p.get("seats") or {}
    sizes = [s for s in p.get("sizes") or [] if s.get("extended_cm")]
    if not sizes or not seats.get("closed") or not seats.get("extended"):
        return ""
    span = max(float(s["extended_cm"]) for s in sizes)
    out = []
    for i, s in enumerate(sizes):
        lab = str(s.get("label") or "")
        round_ = lab.startswith("Ø")
        length = float(s.get("length_cm") or str(lab).lstrip("Ø") or 0)
        width = float(s.get("width_cm") or length)
        ext = float(s["extended_cm"])
        figs = []
        for state, ln, rng in (("closed", length, seats["closed"]), ("open", ext, seats["extended"])):
            n = plan_seats(ln, width, round_ and state == "closed", rng)
            dims = f"Ø{ln:.0f}" if round_ and state == "closed" else f"{ln:.0f}×{width:.0f}"
            figs.append(f'<figure class="plan-fig">{plan_svg(ln, width, span, n, round_, state)}'
                        f'<figcaption><b>{{{{t.unfold_{state}}}}}</b> · <bdi dir="ltr">{dims}</bdi>&nbsp;{{{{t.cm}}}}'
                        f' · {n} {{{{t.{few("unfold_seats", n, loc)}}}}}</figcaption></figure>')
        out.append(f'<div class="plan-size" data-plan-size="{esc(lab)}"{"" if i == 0 else " hidden"}>{"".join(figs)}</div>')
    return '<div class="plan" data-plan>' + "".join(out) + '<p class="muted small">{{t.unfold_plan_note}}</p></div>'


def light(p: dict, loc: str) -> str:
    """«בוקר / ערב»: пара кадрів light з однієї камери; без пари — порожньо."""
    pair = {i.get("light"): i for i in p.get("images") or [] if i.get("view") == "light" and i.get("src")}
    if not (pair.get("morning") and pair.get("evening")):
        return ""
    btns = "".join(f'<button class="light-btn" type="button" data-light="{k}" aria-pressed="{"true" if k == "morning" else "false"}">'
                   f'{{{{t.light_{k}}}}}</button>' for k in ("morning", "evening"))
    hide = ' aria-hidden="true"'
    layers = "".join(f'<div class="light-l" data-l="{k}"{hide if k == "evening" else ""}>'
                     f'{picture(pair[k], loc, sizes="(min-width: 960px) 66vw, 100vw")}</div>' for k in ("morning", "evening"))
    return (f'<section class="sec sec--paper light" id="light" aria-labelledby="light-h"><div class="wrap">'
            f'<div class="sec-head"><h2 class="h2" id="light-h">{{{{t.light_h2}}}}</h2><p class="sec-lede">{{{{t.light_lede}}}}</p></div>'
            f'<div class="light-switch" role="group" aria-label="{{{{t.light_h2}}}}">{btns}</div>'
            f'<figure class="media media--img light-media" data-light-fig data-on="morning">{layers}'
            f'<span class="viz-tag">{{{{t.viz_tag}}}}</span></figure></div></section>')



def chapters(p_how: str, p_light: str) -> str:
    """Навігація по главах картки: лише ті глави, що є на сторінці; активну позначає aluma.js (aria-current)."""
    items = [("spec", "spec_h2"), ("unfold", "ch_unfold") if p_how else None, ("light", "ch_light") if p_light else None,
             ("how", "how_eyebrow"), ("register", "ch_register")]
    links = "".join(f'<li><a href="#{i}">{{{{t.{k}}}}}</a></li>' for i, k in filter(None, items))
    return f'<nav class="chapters" aria-label="{{{{t.ch_label}}}}" data-chapters><ol role="list">{links}</ol></nav>'

def how(p: dict, loc: str) -> str:
    """Блок «איך נפתח השולחן»: кадри механізму (якщо є) + план. Без кадрів і без плану — порожньо."""
    imgs = p.get("images") or []
    mech = {i.get("state"): i for i in imgs if i.get("view") == "mechanism" and i.get("src")}
    opened = next((i for i in imgs if i.get("view") == "open" and i.get("src")), None)
    steps = ""
    if mech.get("closed") and mech.get("half"):
        frames = [("closed", mech["closed"]), ("half", mech["half"])] + ([("open", opened)] if opened else [])
        steps = '<ol class="how-steps" role="list" tabindex="0" aria-label="{{t.unfold_h2}}">' + "".join(
            f'<li><figure><div class="media media--img how-media">'
            f'{picture(im, loc, sizes="(min-width: 900px) 30vw, 80vw")}<span class="viz-tag">{{{{t.viz_tag}}}}</span></div>'
            f'<figcaption><span class="how-n">{k + 1}</span> {{{{t.unfold_{st}}}}}</figcaption></figure></li>'
            for k, (st, im) in enumerate(frames)) + "</ol>"
    pl = plan(p, loc)
    if not steps and not pl:
        return ""
    lede = '<p class="sec-lede">{{t.unfold_lede}}</p>' if steps else ""
    return (f'<section class="sec unfold" id="unfold" aria-labelledby="unfold-h"><div class="wrap">'
            f'<div class="sec-head"><h2 class="h2" id="unfold-h">{{{{t.unfold_h2}}}}</h2>{lede}</div>{steps}'
            + (f'<h3 class="h3 plan-h">{{{{t.unfold_plan_h3}}}}</h3>{pl}' if pl else "") + "</div></section>")


def gallery(p: dict, loc: str) -> str:
    # mechanism і light — окремі блоки вітрини (catalog/README.md), у галерею картки не йдуть
    imgs = [i for i in p.get("images") or [] if i.get("src") and i.get("view") not in ("mechanism", "light")]
    if not imgs:
        return f'<div class="gallery gallery--tile"><div class="media media--tile media--hero">{silhouette(p)}</div>' \
               f'<p class="gallery-note">{{{{t.viz_soon}}}}</p></div>'
    slides = "".join(
        f'<li class="g-slide" id="g-{p["slug"]}-{i}"><div class="media media--img">'
        f'{picture(im, loc, eager=(i == 0), sizes="(min-width: 960px) 58vw, 100vw")}'
        f'<span class="viz-tag">{{{{t.viz_tag}}}}</span></div></li>' for i, im in enumerate(imgs))
    dots = ""
    if len(imgs) > 1:
        dots = '<div class="g-thumbs" role="group" aria-label="{{t.gallery_nav}}">' + "".join(
            f'<a class="g-thumb" href="#g-{p["slug"]}-{i}" aria-label="{{{{t.gallery_item}}}} {i + 1}">'
            f'{picture(im, loc, sizes="88px")}</a>' for i, im in enumerate(imgs)) + "</div>"
    viewer = ""
    if p.get("model3d"):
        # шлях абсолютний: відносний з /en/p/<slug>/ вів у 404 (21.10); build.py публікує й хешує файл за цим посиланням
        vid = f'v3d-{p["slug"]}'
        states = ""
        if any(sz.get("extended_cm") for sz in p["sizes"]):
            states = ('<div class="v3d-states" role="group" aria-label="{{t.v3d_state}}">'
                      '<button class="v3d-st" type="button" data-state="closed" aria-pressed="true">{{t.v3d_closed}}</button>'
                      '<button class="v3d-st" type="button" data-state="open" aria-pressed="false">{{t.v3d_open}}</button></div>')
        # чип на самому кадрі (кут навпроти «הדמיה»), не блок на всю ширину: на телефоні назва й ціна — в першому екрані
        viewer = (f'<button class="g-3d js-3d" type="button" data-model="/{esc(p["model3d"])}" '
                  f'aria-controls="{vid}" aria-expanded="false">'
                  '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">'
                  '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9" fill="none" stroke="currentColor" '
                  'stroke-width="1.6" stroke-linejoin="round"/></svg>{{t.view_3d}}</button>'
                  f'<div class="viewer3d" id="{vid}" hidden><div class="v3d-stage"></div>'
                  '<p class="v3d-msg" role="status"></p><span class="viz-tag">{{t.viz_tag}}</span>'
                  f'<div class="v3d-bar">{states}<span class="v3d-hint">{{{{t.v3d_hint}}}}</span>'
                  '<button class="v3d-close" type="button">{{t.v3d_close}}</button></div></div>')
    return f'<div class="gallery"><ul class="g-track" role="list" tabindex="0" aria-label="{{{{t.gallery_label}}}}">{slides}</ul>{dots}{viewer}</div>'


def product_jsonld(p: dict, loc: str, url: str) -> str:
    imgs = [CONTENT["SITE_URL"] + i["src"] for i in p.get("images") or [] if i.get("src")]
    data = {"@context": "https://schema.org", "@type": "Product", "name": L(p.get("name"), loc),
            "description": L(p.get("tagline"), loc) or L(p.get("description"), loc), "url": url,
            "brand": {"@type": "Brand", "name": CONTENT["BRAND_LAT"]}, "material": L(p.get("material"), loc)}
    if imgs:
        data["image"] = imgs
    prices = [int(sz["price_ils"]) for sz in p["sizes"]]
    # пропозиція без рейтингів і відгуків; передзапуск = PreOrder, ціна — орієнтовна з каталогу
    data["offers"] = {"@type": "AggregateOffer", "priceCurrency": "ILS", "lowPrice": min(prices), "highPrice": max(prices),
                      "offerCount": len(prices), "availability": "https://schema.org/PreOrder"}
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def ld_script(data: dict) -> str:
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def organization_jsonld(loc: str, url: str) -> str:
    return ld_script({"@context": "https://schema.org", "@type": "Organization", "name": CONTENT["BRAND_LAT"],
                      "alternateName": CONTENT.get("BRAND_HE") or CONTENT["BRAND_LAT"], "url": url})


def faq_jsonld(items: list) -> str:
    # відповідь у schema.org — чистий текст, без розмітки сторінки
    plain = lambda h: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()  # noqa: E731
    return ld_script({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": plain(it["q"]), "acceptedAnswer": {"@type": "Answer", "text": plain(it["a"])}}
        for it in items]})


def product_data(products: list, loc: str) -> list:
    """Мінімум для форми, конфігуратора й 3D: id, назва, розміри з ціною й габаритами, тонування, опори."""
    return [{"id": p["id"], "slug": p["slug"], "name": L(p.get("name"), loc),
             "sizes": [{"label": str(s.get("label")), "price": int(s["price_ils"]),
                        # габарити — для 3D-перегляду (aluma3d.js бере ту саму сітку, що й рендери)
                        "dims": {k: s[k] for k in ("length_cm", "width_cm", "height_cm", "extended_cm") if s.get(k)}}
                       for s in p["sizes"]],
             "finishes": [{"id": f.get("id"), "name": L(f.get("name"), loc)} for f in p["finishes"]],
             "bases": [{"id": b.get("id"), "name": L(b.get("name"), loc)} for b in p["bases"]],
             "from": int(p.get("price_from_ils") or 0), "img": thumb_src(p)} for p in products]


# --------------------------------------------------------------------------- рендер


class Renderer:
    def __init__(self, strings: dict, loc: str):
        self.s, self.loc, self.missing = strings, loc, set()

    def __call__(self, text: str, tokens: dict) -> str:
        def sub_t(m):
            key = m.group(1)
            if key not in self.s:
                self.missing.add(f"{self.loc}:t.{key}")
                return ""
            v = self.s[key]
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)

        def sub(m):
            key = m.group(1)
            if key in tokens:
                return str(tokens[key])
            if key in CONTENT and not key.startswith("_"):
                return str(CONTENT[key])
            self.missing.add(f"{self.loc}:{key}")
            return ""

        for _ in range(4):                     # токени всередині рядків і рядки всередині блоків
            new = re.sub(r"\{\{t\.(\w+)\}\}", sub_t, text)
            new = re.sub(r"\{\{([A-Z][A-Z0-9_]*)\}\}", sub, new)
            if new == text:
                break
            text = new
        return text


def locale_dirs() -> list:
    return [DIST / prefix.lstrip("/") if prefix else DIST for prefix in LOCALES.values()]


def hreflang(path: str) -> str:
    """<link rel="alternate"> на кожну мову сторінки + x-default (перша мова LOCALES — корінь сайту)."""
    site = CONTENT["SITE_URL"]
    links = [(loc, site + prefix + path) for loc, prefix in LOCALES.items()]
    links.append(("x-default", links[0][1]))
    return "".join(f'<link rel="alternate" hreflang="{loc}" href="{href}">\n' for loc, href in links)


def lang_nav(loc: str, path: str, locales: dict) -> str:
    """Перемикач мов: кожна мова своєю назвою (i18n lang_name), поточна — текст, не посилання."""
    out = []
    for other, prefix in LOCALES.items():
        name = esc(locales[other]["lang_name"])
        if other == loc:
            out.append(f'<span class="lang-cur" lang="{other}" aria-current="true">{name}</span>')
        else:
            out.append(f'<a href="{(prefix + path) or "/"}" hreflang="{other}" lang="{other}">{name}</a>')
    return "".join(out)


def faq_html(items: list) -> str:
    out = []
    for it in items:
        out.append(f'<details class="qa"><summary>{it["q"]}</summary><div class="qa-a">{it["a"]}</div></details>')
    return '<div class="faq">' + "".join(out) + "</div>"


def main() -> None:
    blanks = [k for k, v in (CONTENT.get("OWNER_FACTS") or {}).items() if not str(v).strip()]
    if PRODUCTION and blanks:
        raise SystemExit(f"--production refused: owner facts missing in content.json: {', '.join(blanks)}")
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    locales = load_locales()
    products = load_catalog()
    layout = read_text(SITE / "_layout.html")
    templates = {f.stem: read_text(f) for f in sorted(PAGES.glob("*.html"))}
    tracking = (SITE / "assets" / "tracking.js").is_file()
    missing: set = set()
    pages_out = []                              # (мова, шлях) для sitemap

    for loc, prefix in LOCALES.items():
        s = locales[loc]
        render = Renderer(s, loc)
        base_tokens = {
            "LANG": loc, "DIR": s["dir"], "PREFIX": prefix,
            # піксель і Clarity не потрібні для першого кадру — вантажимо після load, коли потік вільний
            "TRACKING": ('<script>addEventListener("load",function(){(window.requestIdleCallback||setTimeout)(function(){'
                         'var s=document.createElement("script");s.src="/assets/tracking.js";document.head.appendChild(s)})})</script>'
                         if tracking else ""),
            "FAQ_ALL": faq_html(s.get("faq", [])), "FAQ_TOP": faq_html(s.get("faq", [])[:5]),
            "GRID_ALL": grid(products, loc, prefix), "GRID_HOME": grid(products, loc, prefix, int(CONTENT.get("HOME_PRODUCTS") or 5)),
            "PRODUCT_COUNT": str(len(products)), "SEAT_CM": str(SEAT_CM),
            **catalog_facts(products, loc),
            "SIZE_BARS": size_bars(products),
            # доставка й самовивіз — числа з content.json, у форматі ціни мови (₪350 / 350 ₪)
            "DELIVERY_PRICE": money(int(CONTENT["DELIVERY_ILS"]), loc), "PICKUP_PRICE": money(int(CONTENT["PICKUP_ILS"]), loc),
            "SHIP_CHOICE": ship_choice(),
            "CITY_OPTIONS": "".join(f'<option value="{esc(c["id"])}">{esc(c["name"])}</option>' for c in s.get("cities", [])),
            **{"PART_" + k[1:].upper(): v for k, v in templates.items() if k.startswith("_")},
            "FORM_PRODUCTS": "".join(f'<option value="{esc(p["id"])}">{esc(L(p.get("name"), loc))}</option>' for p in products),
            "DATA": json.dumps({"lang": loc, "prefix": prefix, "consent": CONTENT.get("CONSENT_VERSION", "v1"),
                                "s": s.get("js", {}), "products": product_data(products, loc),
                                "cities": s.get("cities", []),
                                "ship": {"pickup": int(CONTENT["PICKUP_ILS"]), "door": int(CONTENT["DELIVERY_ILS"])}},
                               ensure_ascii=False).replace("</", "<\\/"),
        }
        hero_p = next((p for p in products if p["slug"] == CONTENT.get("HERO_PRODUCT")), products[0])
        hero_imgs = [i for i in hero_p.get("images") or [] if i.get("src")]
        base_tokens["HERO_MEDIA"] = (
            f'<div class="hero-media">{picture(hero_imgs[0], loc, eager=True, sizes="100vw")}'
            f'<span class="viz-tag">{{{{t.viz_tag}}}}</span></div>' if hero_imgs
            else f'<div class="hero-media hero-media--tile">{silhouette(hero_p, "sil--hero")}</div>')
        band = next((i for i in hero_imgs if i.get("view") == "detail"), None)
        base_tokens["BAND_MEDIA"] = (
            f'<figure class="band">{picture(band, loc, sizes="100vw")}<span class="viz-tag">{{{{t.viz_tag}}}}</span>'
            f'<figcaption class="band-cap"><span class="wrap">{{{{t.band_cap}}}}</span></figcaption></figure>' if band else "")

        # «עץ אמיתי, בלי סיפורים»: крупний план фанери й крайки з каталогу (рендер — з «הדמיה»), тони — з каталогу
        tex = next((i for q in [hero_p] + products for i in q.get("images") or [] if i.get("view") == "texture" and i.get("src")), None)
        base_tokens["MAT_MEDIA"] = (
            f'<figure class="media media--img mat-media">{picture(tex, loc, sizes="(min-width: 900px) 50vw, 100vw")}'
            f'<span class="viz-tag">{{{{t.viz_tag}}}}</span></figure>' if tex else "")
        tones = []
        for f in (hero_p.get("finishes") or []):
            tones.append(f'<li><span class="swatch-dot" style="{esc(finish_chip(f)[0])}" aria-hidden="true"></span>{esc(L(f.get("name"), loc))}</li>')
        # «הדמיה» — під списком, а не пунктом: у списку лише тони (redesign.spec.js рахує li = тони каталогу)
        viz = ('<span class="swatch-viz mat-viz">{{t.viz_tag}}</span>'
               if tones and finishes_viz(hero_p.get("finishes") or []) else "")
        base_tokens["MAT_TONES"] = f'<ul class="mat-tones" role="list">{"".join(tones)}</ul>{viz}' if tones else ""

        def emit(rel: str, body: str, tokens: dict, title_key: str, desc_key: str, path: str):
            toks = {**base_tokens, **tokens}
            toks.setdefault("TITLE", "{{t." + title_key + "}}")
            toks.setdefault("DESC", "{{t." + desc_key + "}}")
            toks.setdefault("JSONLD", "")
            # загальні сторінки: превью головної своєю мовою (tools/make-og-products.js), інакше старе og.png
            home_og = f"/assets/og/home-{loc}.jpg"
            toks.setdefault("OG_IMAGE", home_og if (SITE / home_og.lstrip("/")).is_file() else "/assets/og.png")
            toks.setdefault("BODY_CLASS", "")
            toks.setdefault("ROBOTS", "")
            toks["CANONICAL"] = CONTENT["SITE_URL"] + prefix + path
            toks["HREFLANG"] = hreflang(path)
            toks["LANG_NAV"] = lang_nav(loc, path, locales)
            toks["MAIN"] = body
            text = render(layout, toks)
            write_text_lf(DIST / rel, text)

        for name, path, tk, dk in STATIC_PAGES:
            rel = (prefix.lstrip("/") + "/" if prefix else "") + (
                "index.html" if path == "/" else path.strip("/") + ("/index.html" if path.endswith("/") else ".html"))
            toks = {"BODY_CLASS": f"page-{name}"}
            if name in NOINDEX:
                toks["ROBOTS"] = '<meta name="robots" content="noindex">\n'
            if name == "about":
                # слот «תמונות מבית המלאכה יעלו בקרוב» — прихований, доки немає фото (content.json WORKSHOP_PHOTOS, аудит 22.10)
                toks["PHOTO_SLOT_HIDDEN"] = "" if CONTENT.get("WORKSHOP_PHOTOS") == "1" else " hidden"
            if name == "home":
                toks["JSONLD"] = organization_jsonld(loc, CONTENT["SITE_URL"] + prefix + "/")
            elif name == "faq" and s.get("faq"):
                toks["JSONLD"] = faq_jsonld(s["faq"])
            emit(rel, templates[name], toks, tk, dk, path)
            if path != "/404" and name not in NOINDEX:
                pages_out.append(prefix + path)

        for p in products:
            path = f"/p/{p['slug']}/"
            p_how, p_light = how(p, loc), light(p, loc)
            tokens = {
                "TITLE": esc(L(p.get("name"), loc)) + " — {{t.brand_name}}",
                "DESC": esc(L(p.get("tagline"), loc) or L(p.get("description"), loc) or s.get("catalog_desc", "")),
                "BODY_CLASS": "page-product",
                "P_ID": esc(p["id"]), "P_SLUG": p["slug"], "P_NAME": esc(L(p.get("name"), loc)),
                "P_TAGLINE": esc_bidi(L(p.get("tagline"), loc)), "P_DESC": esc_bidi(L(p.get("description"), loc)),
                "P_BADGES": badges(p, loc),
                "P_PRICE": money(p["sizes"][0]["price_ils"] if p["sizes"] else p.get("price_from_ils") or 0, loc),
                "P_PRICE_PLAIN": str(p["sizes"][0]["price_ils"] if p["sizes"] else p.get("price_from_ils") or 0),
                "P_GALLERY": gallery(p, loc), "P_THUMB": thumb(p, loc), "P_CONFIG": configurator(p, loc),
                "P_INC": included(p, loc), "P_TERMS": ship_terms(p, loc),
                "P_PRICE_NOTE": "{{t.series_price_n}}" if listed("SERIES_PRODUCTS", p) else "{{t.series_price}}", "P_SIZE_HELP": size_help(p, loc),
                "P_SPECS": specs(p, loc), "P_INSIDE": inside(p, loc), "P_VENEER": CONTENT["VENEER_MM"].replace(".", ",") if loc == "ru" else CONTENT["VENEER_MM"], "P_HOW": p_how, "P_LIGHT": p_light, "P_CHAPTERS": chapters(p_how, p_light), "JSONLD": f'<script type="application/ld+json">{product_jsonld(p, loc, CONTENT["SITE_URL"] + prefix + path)}</script>',
                "OG_IMAGE": f"/assets/og/{p['slug']}.jpg" if (SITE / "assets" / "og" / f"{p['slug']}.jpg").is_file() else "/assets/og.png",
                "P_MORE": grid([q for q in products if q is not p], loc, prefix, 3),
            }
            emit((prefix.lstrip("/") + "/" if prefix else "") + f"p/{p['slug']}/index.html",
                 templates["product"], tokens, "", "", path)
            pages_out.append(prefix + path)
        missing |= render.missing

    if missing:
        raise SystemExit(f"unknown tokens in templates: {sorted(missing)[:20]}")

    # ---- sitemap, robots, сторінки без розширення
    urls = "".join(f"<url><loc>{CONTENT['SITE_URL']}{u}</loc></url>" for u in pages_out)
    write_text_lf(DIST / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
                  f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    write_text_lf(DIST / "robots.txt", read_text(SITE / "robots.txt").replace("{{SITE_URL}}", CONTENT["SITE_URL"]))
    for d in locale_dirs():
        for name in ("privacy", "terms", "accessibility", "404"):
            src = d / f"{name}.html"
            if src.exists():
                shutil.copyfile(src, d / name)

    # ---- ассети: лише ті, на які посилаються, з хешем у імені
    REF = re.compile(r"/assets/[\w\-./]+?\.(?:avif|webp|png|jpg|jpeg|svg|woff2|css|js|glb|hdr|pdf)")
    referenced, seen = set(), set()
    frontier = [f for f in DIST.rglob("*") if f.is_file()]
    while frontier:
        f = frontier.pop()
        if f in seen:
            continue
        seen.add(f)
        for ref in REF.findall(read_text(f) if f.suffix.lower() in TEXT_EXT or f.suffix == "" else ""):
            if ref in referenced:
                continue
            referenced.add(ref)
            src = SITE / ref.lstrip("/")
            if not src.is_file():
                raise SystemExit(f"referenced asset missing from site/: {ref}")
            dst = DIST / ref.lstrip("/")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() in TEXT_EXT:
                write_text_lf(dst, read_text(src))
                if dst.suffix in (".css", ".js"):
                    frontier.append(dst)
            else:
                shutil.copyfile(src, dst)

    def text_files() -> list:
        return [f for f in DIST.rglob("*") if f.is_file() and (f.suffix.lower() in TEXT_EXT or f.suffix == "")]

    hashed = {}
    assets = sorted(f for f in (DIST / "assets").rglob("*") if f.is_file()) if (DIST / "assets").exists() else []
    # js, на який посилається інший js (aluma3d.js → vendor/three.min.js), хешується раніше за нього —
    # інакше хеш того, хто посилається, рахувався б до заміни посилання і не мінявся б разом із залежністю
    js = [f for f in assets if f.suffix == ".js"]
    url = {f: "/" + f.relative_to(DIST).as_posix() for f in js}
    body = {f: read_text(f) for f in js}
    js_order = []
    while js:
        f = next((f for f in js if not any(url[g] in body[f] for g in js if g is not f)), js[0])
        js_order.append(f)
        js.remove(f)
    order = ([f for f in assets if f.suffix not in (".css", ".js")] + [f for f in assets if f.suffix == ".css"]
             + js_order)
    for f in order:
        h = digest_bytes(f.read_bytes(), f.suffix)
        new = f.with_name(f"{f.stem}.{h}{f.suffix}")
        f.rename(new)
        old_url = "/" + f.relative_to(DIST).as_posix()
        new_url = "/" + new.relative_to(DIST).as_posix()
        hashed[old_url] = new_url
        pat = re.compile(re.escape(old_url) + r"(?![\w.\-/])")
        for t in text_files():
            body = read_text(t)
            if old_url in body:
                write_text_lf(t, pat.sub(new_url, body))

    # стилі вбудовані <style> у head: без блокуючого запиту перед першим кадром (~10 КБ gzip, Lighthouse «render-blocking»);
    # aluma.css — спільний, fonts-<мова>.css — обличчя лише своєї мови (he не качає кирилицю й повну латиницю)
    # коментарі /* … */ у вбудований стиль не їдуть: 12,9 КБ українських пояснень у кожній сторінці (замір 22.10);
    # у наших CSS нема «/*» усередині рядків url(…) чи content: "…" — це стереже tests/test_build_css_comments.py
    styles = {}
    for old_url in ["/assets/aluma.css"] + [f"/assets/fonts-{loc}.css" for loc in LOCALES]:
        css_url = hashed.get(old_url)
        if css_url:
            css = strip_css_comments(read_text(DIST / css_url.lstrip("/")))
            style = "<style>" + css.replace("</", "<\\/") + "</style>"
            styles[f'<link rel="stylesheet" href="{css_url}">'] = style
    if styles:
        for t in DIST.rglob("*.html"):
            body = read_text(t)
            new_body = body
            for link, style in styles.items():
                new_body = new_body.replace(link, style)
            if new_body != body:
                write_text_lf(t, new_body)
        for d in locale_dirs():                # копії без розширення (privacy, 404…) — з уже вбудованих
            for name in ("privacy", "terms", "accessibility", "404"):
                if (d / f"{name}.html").exists():
                    shutil.copyfile(d / f"{name}.html", d / name)

    (ROOT / ".build").mkdir(exist_ok=True)
    write_text_lf(ROOT / ".build" / "asset-map.json", json.dumps(hashed, indent=1, sort_keys=True))
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    n_files = sum(1 for f in DIST.rglob("*") if f.is_file())
    no_img = [p["slug"] for p in products if not any(i.get("src") for i in p.get("images") or [])]
    print(f"built {DIST} ({total / 1024:.0f} KB, {n_files} files, {len(hashed)} hashed assets, {len(products)} products)")
    if no_img:
        print(f"  products without visualisations (wood tile shown): {', '.join(no_img)}")
    print("  status: " + ("production build" if PRODUCTION else "preview build"))


if __name__ == "__main__":
    main()
