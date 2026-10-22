#!/usr/bin/env python3
"""Вирізати мовні сабсети шрифтів, щоб іврит- і англійська сторінки не тягнули чужих облич.

Що качала he-картка (Playwright 390, 22.10): FrankRuhlLibre-latin 44 КБ заради «ALUMA» і цифр у заголовках
і PlexSans-400-cyrillic 15 КБ заради одного слова «Русский» у перемикачі мов. Звідси два файли:

* FrankRuhlLibre-latin-caps.woff2 — лише великі A–Z, цифри й пунктуація, без малих літер і діакритики.
  Підключається тільки на he (site/assets/fonts-he.css): на he Frank Ruhl малює лише « ,./0-9:?ALMU—₪»
  (заміряно по всіх сторінках sitemap). На /ru/ є малі латинські в заголовках, на /en/ — усі, там повний latin.
* PlexSans-400-cyrillic-lang.woff2 — лише літери назви мови i18n/ru.json → lang_name («Русский»),
  для he і en: слово малюється тим самим Plex Sans, що й раніше, вигляд не змінюється.
* PlexSansHebrew-{400,600,700}-latin-he.woff2 — латиниця Plex Sans Hebrew для he: A–Z, a–z і кілька знаків, яких нема
  в PlexSansHebrew-*-num (цифри й спільна пунктуація вже там, aluma.css). На he латиницею пишуться лише слова
  на кшталт «Meta Pixel», «WhatsApp», «English», «Ø» (банер згоди, перемикач мов, nojs, privacy) — 19–20 КБ
  повного latin заради них (замір 22.10). Діапазони не перетинаються з num, тож жоден знак не тягне двох файлів.
  700 на he сьогодні малює лише цифри (num), його latin-he вантажиться тільки якщо колись знадобиться.

unicode-range кожного обличчя у fonts-*.css дорівнює списку, з яким його вирізано (перевіряє
tests/test_build_site.py). Джерела — вже наявні OFL-файли в site/assets/fonts, нових шрифтів немає.

    python tools/subset_locale_fonts.py      # переписує всі мовні файли; потрібен fontTools (+ brotli) у venv
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FONTS = ROOT / "site" / "assets" / "fonts"
# Великі латинські, цифри, ASCII-пунктуація до «_», | і знаки, що стоять поряд у заголовках (« » · © × – — “ ” • … €).
# Без a–z і літер U+00C0–00FF. ₪ у латинському файлі немає — його, як і раніше, малює івритське обличчя.
CAPS_UNICODES = ("U+0020-005F, U+007C, U+00A0, U+00A9, U+00AB, U+00B7, U+00BB, U+00D7, U+2013-2014, U+2018-201E, "
                 "U+2022, U+2026, U+20AC")
# Латиниця Plex для he: A–Z, a–z, Ø (Ø115 на плитці), " & ' ‘ ’ “ ” „ … — що на he малює Plex поза num (замір усіх
# he-сторінок sitemap з JS і без, 390 px). Решта ASCII в i18n/he.json — розмітка й {плейсхолдери}, не текст; що жоден
# видимий знак he не лишився без обличчя, стереже tests/test_build_site.py. Цифри й спільна пунктуація — у num.
PLEX_HE_LATIN_UNICODES = "U+0022, U+0026-0027, U+0041-005A, U+0061-007A, U+00D8, U+2018-201E, U+2026"


def lang_unicodes() -> str:
    """Літери назви російської мови з i18n — одне джерело, перемикач малює саме їх."""
    name = json.loads((ROOT / "i18n" / "ru.json").read_text(encoding="utf-8"))["lang_name"]
    return ", ".join(f"U+{ord(c):04X}" for c in sorted(set(name)))


def jobs() -> list:
    return [("FrankRuhlLibre-latin.woff2", "FrankRuhlLibre-latin-caps.woff2", CAPS_UNICODES),
            ("PlexSans-400-cyrillic.woff2", "PlexSans-400-cyrillic-lang.woff2", lang_unicodes())] + [
            (f"PlexSansHebrew-{w}-latin.woff2", f"PlexSansHebrew-{w}-latin-he.woff2", PLEX_HE_LATIN_UNICODES)
            for w in (400, 600, 700)]


def main() -> None:
    for src_name, dst_name, unicodes in jobs():
        src, dst = FONTS / src_name, FONTS / dst_name
        if not src.exists():
            sys.exit(f"missing {src}")
        subprocess.run([sys.executable, "-m", "fontTools.subset", str(src),
                        "--unicodes=" + unicodes.replace(" ", ""), "--flavor=woff2", "--layout-features=*",
                        f"--output-file={dst}"], check=True)
        print(f"{dst.name}: {dst.stat().st_size} B  (from {src.name}: {src.stat().st_size} B)")


if __name__ == "__main__":
    main()
