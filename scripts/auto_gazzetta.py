"""
Auto-Gazzetta – trykker «Generer dagens utgave» på vegne av admin.

Kjører den samme koden som knappen i la_gazzetta.html, i en ekte nettleser
med norsk tidssone. Ingen endringer i Gazzetta-sidene er nødvendig.

Bruk:  python scripts/auto_gazzetta.py champ|selekt|osat
Miljø: FORCE=1          -> generer selv om dagens utgave allerede finnes
       SISTE_DATO=ÅÅÅÅ-MM-DD -> ingen utgaver etter denne datoen (Oslo-tid)
       GAZ_URL=...      -> overstyr URL (kun til testing)
"""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

KONKURRANSER = {
    "champ":  {"navn": "Championship", "url": "https://jorsna.github.io/vcso-serien/la_gazzetta.html", "rolle": "gaz-champ-role"},
    "selekt": {"navn": "Selekt Cup",   "url": "https://jorsna.github.io/selekt-cup/la_gazzetta.html",  "rolle": "gaz-role"},
    "osat":   {"navn": "OSAT League",  "url": "https://jorsna.github.io/OSAT-League/la_gazzetta.html", "rolle": "gaz-osat-role"},
}
STARTTEKST = "Ingen utgave generert i dag"
MAKS_GENERERING_MS = 300_000  # 5 min: data + AI + korrektur


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in KONKURRANSER:
        print("Bruk: auto_gazzetta.py champ|selekt|osat")
        return 2
    k = KONKURRANSER[sys.argv[1]]
    url = os.environ.get("GAZ_URL") or k["url"]
    force = os.environ.get("FORCE") == "1"

    idag = datetime.now(ZoneInfo("Europe/Oslo")).date().isoformat()
    siste = os.environ.get("SISTE_DATO")
    if siste and idag > siste:
        print(f"[{k['navn']}] {idag} er etter SISTE_DATO {siste} – hopper over.")
        return 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(timezone_id="Europe/Oslo", locale="nb-NO")
        ctx.add_init_script(f"localStorage.setItem('{k['rolle']}', 'admin');")
        page = ctx.new_page()
        page.on("console", lambda m: print(f"  [console] {m.text}"[:300]))

        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        # Vent til siden har sjekket siste utgave
        page.wait_for_function(
            "(t) => { const s = document.getElementById('admin-status'); return s && s.textContent.trim() !== t; }",
            arg=STARTTEKST, timeout=30_000,
        )
        status = page.inner_text("#admin-status").strip()
        forventet = page.evaluate("norskDato(igar())")
        print(f"[{k['navn']}] Status før: {status}")

        if not force and f"Siste utgave: {forventet}" in status:
            print(f"[{k['navn']}] Dagens utgave finnes allerede – ingen ny generering.")
            browser.close()
            return 0

        page.click("#gen-btn", force=True)
        page.wait_for_function(
            "() => { const t = document.getElementById('admin-status').textContent; return t.startsWith('Publisert!') || t.startsWith('Feil:'); }",
            timeout=MAKS_GENERERING_MS,
        )
        status = page.inner_text("#admin-status").strip()
        print(f"[{k['navn']}] Status etter: {status}")
        browser.close()
        return 0 if status.startswith("Publisert!") else 1


if __name__ == "__main__":
    sys.exit(main())
