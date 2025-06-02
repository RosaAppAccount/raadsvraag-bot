# raadsvraag_logic.py

import os
import re
import requests
import fitz   # PyMuPDF
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# Configuratie
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL   = "https://rotterdamraad.bestuurlijkeinformatie.nl"
START_PATH = "/Reports/Details/da9b533f-5f24-4f51-8567-19fe410f15d4"
START_URL  = BASE_URL + START_PATH

DOWNLOAD_DIR = "downloaded_documents"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def get_raadsleden_labels() -> list[str]:
    """
    Haalt met requests + BeautifulSoup alle <a>-links op onder '.report-children a'
    waarvoor de linktekst 'Schriftelijke vraag' bevat. Knipt telkens het stuk ná
    'Schriftelijke vraag' eruit (inclusief onderwerp), en retourneert een gesorteerde
    lijst van strings zoals:
      ['de Waard, J.M.D. – Voorzieningen jeugd', 'Groningen, D. van – Energietransitie', …].
    """
    resp = requests.get(START_URL)
    if resp.status_code != 200:
        raise Exception(f"Kon startpagina niet laden (status {resp.status_code})")

    soup = BeautifulSoup(resp.text, "html.parser")

    # Vind alle <a> binnen het element met class "report-children"
    items = soup.select(".report-children a")
    labels = set()

    for a in items:
        tekst = a.get_text(strip=True)
        if "Schriftelijke vraag" in tekst:
            # Knip het stuk na "Schriftelijke vraag" weg
            na = tekst.split("Schriftelijke vraag", 1)[1].strip()
            if na:
                labels.add(na)

    return sorted(labels)


def find_latest_question_and_summarize(raadslid_label: str) -> dict:
    """
    1. In de HTML van START_URL zoekt deze functie exact naar een <a>-link met
       link.text == f"Schriftelijke vraag {raadslid_label}".
    2. Haalt de bijbehorende detail-URL op (href attribuut).
    3. Downloadt alle PDF’s uit de secties 'Hoofddocument' en 'Bijlagen' naar DOWNLOAD_DIR.
    4. Leest elke PDF met PyMuPDF en geeft per bestand de eerste ~1000 tekens terug.

    Retourneert een dict:
      {
        "summaries": [
          {"filename": "Hoofddocument.pdf", "summary": "…eerste 1000 tekens…"},
          {"filename": "Bijlage1.pdf",       "summary": "…eerste 1000 tekens…"},
          …
        ]
      }

    Als de link niet gevonden wordt, wordt er een Exception gegooid.
    """

    # ── A) Zoek in de startpagina naar de exacte link "Schriftelijke vraag {raadslid_label}"
    resp = requests.get(START_URL)
    if resp.status_code != 200:
        raise Exception(f"Kon startpagina niet laden (status {resp.status_code})")

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(".report-children a")

    target_link = None
    gezochte_tekst = f"Schriftelijke vraag {raadslid_label}"

    for a in items:
        if a.get_text(strip=True) == gezochte_tekst:
            href = a.get("href", "").strip()
            if href:
                # Bouw absolute URL (soms is href relatieve pad)
                if href.startswith("http"):
                    target_link = href
                else:
                    target_link = BASE_URL + href
            break

    if not target_link:
        raise Exception(f"Geen schriftelijke vraag gevonden voor: {raadslid_label}")

    # ── B) Haal detailpagina op en parse met BeautifulSoup
    detail_resp = requests.get(target_link)
    if detail_resp.status_code != 200:
        raise Exception(f"Kon detailpagina niet laden (status {detail_resp.status_code})")

    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

    def _download_docs_in_section(label: str) -> list[str]:
        """
        Zoekt in detail_soup naar <div class="report-section"> waarvan de <h4>
        de opgegeven 'label' (bijv. 'Hoofddocument' of 'Bijlagen') bevat. Downloadt
        alle <a href="…">-links in die sectie en schrijft ze naar DOWNLOAD_DIR.
        Retourneert de lijst met lokale bestandsnamen.
        """
        bestanden = []
        secties = detail_soup.find_all("div", class_="report-section")

        for sectie in secties:
            header = sectie.find("h4")
            if header and label.lower() in header.get_text(strip=True).lower():
                for a_tag in sectie.find_all("a", href=True):
                    # De <a> bevat meestal een relatieve URL naar PDF
                    rel_url = a_tag["href"]
                    if rel_url.startswith("http"):
                        doc_url = rel_url
                    else:
                        doc_url = BASE_URL + rel_url

                    # Bouw veilige bestandsnaam
                    naam = a_tag.get_text(strip=True).replace("/", "_").replace("\\", "_")
                    lokaal_pad = os.path.join(DOWNLOAD_DIR, naam)

                    try:
                        r = requests.get(doc_url)
                        r.raise_for_status()
                        with open(lokaal_pad, "wb") as f_out:
                            f_out.write(r.content)
                        bestanden.append(lokaal_pad)
                    except Exception:
                        # Bij downloadfout overslaan we dit bestand
                        continue

        return bestanden

    # Download alle documenten uit secties "Hoofddocument" en "Bijlagen"
    hoofddocs = _download_docs_in_section("Hoofddocument")
    bijlagen  = _download_docs_in_section("Bijlagen")
    alle_paden = hoofddocs + bijlagen

    def _summarize_pdf(pdf_path: str, max_chars: int = 1000) -> str:
        """
        Opent het PDF-bestand met PyMuPDF (fitz), leest pagina voor pagina tekst uit
        totdat max_chars is bereikt. Retourneert de eerste max_chars tekens (plus "...")
        of de volledige tekst als hij korter is dan max_chars.
        """
        try:
            doc = fitz.open(pdf_path)
            tekst = ""
            for pagina in doc:
                tekst += pagina.get_text()
                if len(tekst) >= max_chars:
                    break
            doc.close()
            return (tekst.strip()[:max_chars] + "...") if len(tekst) > max_chars else tekst.strip()
        except Exception as e:
            return f"(Kon niet samenvatten: {e})"

    # Bouw de uiteindelijke lijst met samenvattingen
    samenvattingen = []
    for pad in alle_paden:
        fname = os.path.basename(pad)
        smry  = _summarize_pdf(pad)
        samenvattingen.append({"filename": fname, "summary": smry})

    return {"summaries": samenvattingen}


# ─────────────────────────────────────────────────────────────────────────────
# Optioneel: lokaal testen van deze module
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Beschikbare labels met 'Schriftelijke vraag':")
    try:
        labels = get_raadsleden_labels()
        for lbl in labels:
            print(" •", lbl)
    except Exception as e:
        print("Fout bij ophalen labels:", e)

    # Voorbeeld (kopieer een label uit bovenstaande lijst):
    # result = find_latest_question_and_summarize("de Waard, J.M.D. – Voorzieningen jeugd")
    # print(result)
    pass
