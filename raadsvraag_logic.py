import os
import time
import requests
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────────────────────────────────────────────────────
# Configuratie
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "https://rotterdamraad.bestuurlijkeinformatie.nl"
START_PATH = "/Reports/Details/da9b533f-5f24-4f51-8567-19fe410f15d4"
START_URL = BASE_URL + START_PATH

# Map voor tijdelijke opslag van gedownloade PDF’s
DOWNLOAD_DIR = "downloaded_documents"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _get_selenium_driver():
    """
    Geeft een headless Chrome-webdriver terug. Op Streamlit Cloud wijst de binary_location
    naar de geïnstalleerde headless chromium ("/usr/bin/chromium-browser"). Lokaal wordt
    via webdriver_manager automatisch ChromeDriver opgehaald.
    """
    options = webdriver.ChromeOptions()
    # Op Streamlit Cloud is headless chromium beschikbaar op dit pad:
    options.binary_location = "/usr/bin/chromium-browser"
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )


def get_raadsleden_labels():
    """
    Haalt met Selenium alle linkteksten op onder '.report-children a' waarin 'Schriftelijke vraag'
    voorkomt, en knipt het deel ná 'Schriftelijke vraag' eruit. Retourneert een gesorteerde lijst
    zoals ['de Waard, J.M.D. – Voorzieningen jeugd', 'Groningen, D. van – Energietransitie', …].
    """
    driver = _get_selenium_driver()
    driver.get(START_URL)
    # Kort pauzeren zodat eventuele JavaScript de linklijst kan inladen
    time.sleep(4)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    items = driver.find_elements(By.CSS_SELECTOR, ".report-children a")
    labels = set()

    for link in items:
        tekst = link.text.strip()
        if "Schriftelijke vraag" in tekst:
            na = tekst.split("Schriftelijke vraag", 1)[1].strip()
            if na:
                labels.add(na)

    driver.quit()
    return sorted(labels)


def find_latest_question_and_summarize(raadslid_label: str):
    """
    1) Gebruikt Selenium om exact de <a>-link te vinden met tekst 'Schriftelijke vraag {raadslid_label}'.
    2) Haalt de detailpagina op via requests.
    3) Downloadt alle PDF’s uit secties 'Hoofddocument' en 'Bijlagen' naar DOWNLOAD_DIR.
    4) Leest elke PDF met PyMuPDF en genereert een korte samenvatting (~1000 tekens).
    Retourneert een dict:
        {"summaries": [ {"filename": "...", "summary": "..."}, … ] }
    """

    # ── Stap A: vind de detail-URL met Selenium ─────────────────────────────────
    driver = _get_selenium_driver()
    driver.get(START_URL)
    time.sleep(4)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    items = driver.find_elements(By.CSS_SELECTOR, ".report-children a")
    target_link = None
    gezochte_tekst = f"Schriftelijke vraag {raadslid_label}"

    for link in items:
        if link.text.strip() == gezochte_tekst:
            href = link.get_attribute("href").strip()
            if href:
                target_link = href
            break

    driver.quit()

    if not target_link:
        raise Exception(f"Geen schriftelijke vraag gevonden voor: {raadslid_label}")

    # ── Stap B: detailpagina ophalen met requests ────────────────────────────────
    detail_resp = requests.get(target_link)
    if detail_resp.status_code != 200:
        raise Exception(f"Kon detailpagina niet laden (status {detail_resp.status_code}).")
    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

    def _download_docs_in_section(label: str) -> list[str]:
        """
        Zoekt in detail_soup naar <div class="report-section"> waarin de <h4> de opgegeven 'label'
        (bijv. 'Hoofddocument' of 'Bijlagen') bevat, en downloadt alle <a href="…">-links in die sectie.
        Retourneert een lijst met lokale bestandsnamen.
        """
        bestanden = []
        secties = detail_soup.find_all("div", class_="report-section")

        for sectie in secties:
            header = sectie.find("h4")
            if header and label.lower() in header.get_text(strip=True).lower():
                for a_tag in sectie.find_all("a", href=True):
                    doc_url = BASE_URL + a_tag["href"]
                    naam = a_tag.get_text(strip=True).replace("/", "_").replace("\\", "_")
                    lokaal_pad = os.path.join(DOWNLOAD_DIR, naam)

                    try:
                        r = requests.get(doc_url)
                        r.raise_for_status()
                        with open(lokaal_pad, "wb") as f_out:
                            f_out.write(r.content)
                        bestanden.append(lokaal_pad)
                    except Exception:
                        continue

        return bestanden

    # Download 'Hoofddocument' en 'Bijlagen'
    hoofddocs = _download_docs_in_section("Hoofddocument")
    bijlagen = _download_docs_in_section("Bijlagen")
    alle_pdfs = hoofddocs + bijlagen

    def _summarize_pdf(pdf_pad: str, max_chars: int = 1000) -> str:
        """
        Opent de PDF met PyMuPDF, leest pagina voor pagina tekst uit tot max_chars bereikt is,
        en geeft de tekst (plus '…' indien afgekapt) terug.
        """
        try:
            doc = fitz.open(pdf_pad)
            tekst = ""
            for pagina in doc:
                tekst += pagina.get_text()
                if len(tekst) >= max_chars:
                    break
            doc.close()
            return (tekst.strip()[:max_chars] + "...") if len(tekst) > max_chars else tekst.strip()
        except Exception as e:
            return f"(Kon niet samenvatten: {e})"

    samenvattingen = []
    for pad in alle_pdfs:
        fname = os.path.basename(pad)
        smry = _summarize_pdf(pad)
        samenvattingen.append({"filename": fname, "summary": smry})

    return {"summaries": samenvattingen}


# ─────────────────────────────────────────────────────────────────────────────
# Optioneel: lokaal testen van deze module
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Beschikbare raadsledenlabels met 'Schriftelijke vraag':")
    try:
        labels = get_raadsleden_labels()
        for lbl in labels:
            print(" •", lbl)
    except Exception as e:
        print("Fout bij ophalen labels:", e)

    # Als voorbeeld kun je hier een label uit de lijst invullen:
    # result = find_latest_question_and_summarize("Groningen, D. van – Energietransitie")
    # print(result)
    pass
