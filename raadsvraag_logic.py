import os
import requests
import fitz  # PyMuPDF
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────────────────────────────────────
# Configuratie
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://rotterdamraad.bestuurlijkeinformatie.nl"
START_PATH = "/Reports/Details/da9b533f-5f24-4f51-8567-19fe410f15d4"
START_URL = f"{BASE_URL}{START_PATH}"

# Map waar de gedownloade PDF’s tijdelijk in worden opgeslagen:
DOWNLOAD_DIR = "downloaded_documents"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Functie 1: Haal alle beschikbare raadsleden‐labels op uit de “Schriftelijke vraag”‐lijst
# ─────────────────────────────────────────────────────────────────────────────

def get_raadsleden_labels():
    """
    Haalt van de startpagina alle linkteksten op onder '.report-children a'
    waarvoor 'Schriftelijke vraag' in de tekst staat.
    Geeft een gesorteerde lijst terug met enkel het deel ná 'Schriftelijke vraag'.
    Bijvoorbeeld:
        'Schriftelijke vraag de Waard, J.M.D. – Thema A'
    wordt in de lijst opgenomen als: 'de Waard, J.M.D. – Thema A'

    Dit kun je vervolgens in je Streamlit-app als dropdown‐optie tonen.
    """
    resp = requests.get(START_URL)
    if resp.status_code != 200:
        raise Exception(f"Kan de startpagina niet laden (status {resp.status_code}).")

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(".report-children a")

    labels = set()
    for link in items:
        tekst = link.get_text(strip=True)
        # We willen alleen de regels waarin 'Schriftelijke vraag' voorkomt
        if "Schriftelijke vraag" in tekst:
            # Haal het stuk ná 'Schriftelijke vraag' er uit:
            # Bijvoorbeeld: "Schriftelijke vraag de Waard, J.M.D. – Voorzieningen jeugd"
            # wordt: "de Waard, J.M.D. – Voorzieningen jeugd"
            na_tekst = tekst.split("Schriftelijke vraag", 1)[1].strip()
            if na_tekst:
                labels.add(na_tekst)

    # Return een gesorteerde lijst, zodat de volgorde telkens hetzelfde is
    return sorted(labels)


# ─────────────────────────────────────────────────────────────────────────────
# Functie 2: Zoek de detailpagina bij een gekozen label, download de PDF’s en maak samenvatting
# ─────────────────────────────────────────────────────────────────────────────

def find_latest_question_and_summarize(raadslid_label: str):
    """
    Voor een gegeven label (zoals 'de Waard, J.M.D. – Voorzieningen jeugd') zoekt deze functie:
      1. In de '.report-children a'-links naar exact de tekst "Schriftelijke vraag {raadslid_label}"
      2. Navigeert naar de bijbehorende detailpagina
      3. Downloadt alle PDF’s uit de secties 'Hoofddocument' en 'Bijlagen'
      4. Gebruikt PyMuPDF om per PDF de eerste ~1000 tekens te extraheren als samenvatting

    Geeft een dict terug met de vorm:
        {
            "summaries": [
                {"filename": "XXX.pdf", "summary": "Eerste 1000 tekens…"},
                ...
            ]
        }

    Als er geen match is gevonden, wordt er een Exception opgeworpen.
    """

    # 1) Haal de startpagina opnieuw op
    resp = requests.get(START_URL)
    if resp.status_code != 200:
        raise Exception(f"Kan de startpagina niet laden (status {resp.status_code}).")

    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(".report-children a")

    # We willen zoeken naar exact de linktekst "Schriftelijke vraag {raadslid_label}"
    target_link = None
    gezochte_tekst = f"Schriftelijke vraag {raadslid_label}"

    for link in items:
        tekst = link.get_text(strip=True)
        if tekst == gezochte_tekst:
            # Vindt de juiste <a href="…"> die we willen volgen
            href = link.get("href", "").strip()
            if href:
                target_link = BASE_URL + href
            break

    if not target_link:
        raise Exception(f"Geen schriftelijke vraag gevonden voor: {raadslid_label}")

    # 2) Haal de detailpagina op
    detail_resp = requests.get(target_link)
    if detail_resp.status_code != 200:
        raise Exception(f"Kan detailpagina niet laden (status {detail_resp.status_code}).")

    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

    # Hulpfunctie om documenten te downloaden uit een sectie met bepaalde h4‐titel
    def download_docs_in_section(label: str):
        """
        Zoekt in detail_soup naar <div class="report-section"> waarin de <h4> de opgegeven 'label'
        bevat (bijv. 'Hoofddocument' of 'Bijlagen'), pakt alle <a href="…">-links in die sectie,
        en downloadt de bestanden naar DOWNLOAD_DIR. Geeft een lijst met lokale bestandsnamen terug.
        """
        gedownloade_bestanden = []
        secties = detail_soup.find_all("div", class_="report-section")

        for sectie in secties:
            header = sectie.find("h4")
            if header and label.lower() in header.get_text(strip=True).lower():
                # In deze sectie staan alle <a> die naar PDF’s verwijzen
                for a_tag in sectie.find_all("a", href=True):
                    bestand_url = BASE_URL + a_tag["href"]
                    # Bouw een veilige bestandsnaam op basis van de linktekst
                    naam = a_tag.get_text(strip=True).replace("/", "_").replace("\\", "_")
                    lokaal_pad = os.path.join(DOWNLOAD_DIR, naam)

                    # Download het bestand
                    try:
                        file_resp = requests.get(bestand_url)
                        file_resp.raise_for_status()
                        with open(lokaal_pad, "wb") as f:
                            f.write(file_resp.content)
                        gedownloade_bestanden.append(lokaal_pad)
                    except Exception:
                        # Bij een fout sla je dit bestand over, zonder heel de flow te breken
                        continue

        return gedownloade_bestanden

    # 3) Download “Hoofddocument” en “Bijlagen”
    hoofddoc_bestanden = download_docs_in_section("Hoofddocument")
    bijlagen_bestanden  = download_docs_in_section("Bijlagen")

    # 4) Maak per gedownload PDF-bestand een korte samenvatting
    def summarize_pdf(pdf_pad: str, max_chars=1000):
        """
        Opent het PDF-bestand via PyMuPDF (fitz), leest pagina voor pagina de tekst,
        stopt zodra er max_chars tekens zijn gelezen, en geeft deze tekst terug.
        """
        try:
            pdf = fitz.open(pdf_pad)
            tekst = ""
            for pagina in pdf:
                tekst += pagina.get_text()
                if len(tekst) >= max_chars:
                    break
            pdf.close()
            return tekst.strip()[:max_chars] + "..."
        except Exception as e:
            return f"(Kon niet samenvatten: {e})"

    samenvattingen = []
    alle_paden = hoofddoc_bestanden + bijlagen_bestanden
    for pad in alle_paden:
        bestandsnaam = os.path.basename(pad)
        samenvatting = summarize_pdf(pad)
        samenvattingen.append({
            "filename": bestandsnaam,
            "summary":  samenvatting
        })

    return {"summaries": samenvattingen}


# ─────────────────────────────────────────────────────────────────────────────
# Voorbeeld van lokaal testen (optioneel)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test: print eerst alle beschikbare labels
    print("Beschikbare raadsledenlabels met 'Schriftelijke vraag':")
    for label in get_raadsleden_labels():
        print(" •", label)
    print()

    # Sleep een moment zodat je de lijst kunt bekijken, of kies er zelf een
    # Daarna kun je een specifieke label invullen om die vraag op te halen
    # Bijvoorbeeld: 'de Waard, J.M.D. – Voorzieningen jeugd'
    # result = find_latest_question_and_summarize("de Waard, J.M.D. – Voorzieningen jeugd")
    # print(result)
    pass
