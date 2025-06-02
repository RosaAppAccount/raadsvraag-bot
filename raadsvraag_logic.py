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
    Geeft een selenium.webdriver.Chrome-object terug in headless modus.
    Lokale setup (Chrome + ChromeDriver) wordt automatisch geregeld via webdriver_manager.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")            # Geen echt venster openen
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    # Als je straks op Streamlit Cloud deployt, zit er meestal /usr/bin/chromium-browser:
    # options.binary_location = "/usr/bin/chromium-browser"
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )


def get_raadsleden_labels():
    """
    Haalt met Selenium alle linkteksten op onder '.report-children a' waarin ‘Schriftelijke vraag’ voorkomt,
    en knipt telkens het stuk ná “Schriftelijke vraag” eruit. Geeft een gesorteerde lijst terug.
    Bijvoorbeeld: “Schriftelijke vraag de Waard, J.M.D. – Voorzieningen jeugd”
    wordt in de return-lijst opgenomen als “de Waard, J.M.D. – Voorzieningen jeugd”.
    """
    driver = _get_selenium_driver()
    driver.get(START_URL)
    # Even kort wachten zodat JavaScript (indien aanwezig) tijd heeft om de links in te laden:
    time.sleep(4)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)

    # Alle <a> in het blok met CSS-class .report-children ophalen
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
    1. Met Selenium zoekt deze functie exact naar de <a>-link waarvan de tekst gelijk is aan
       “Schriftelijke vraag {raadslid_label}”.
    2. Haalt de bijbehorende detailpagina op via requests.
    3. Downloadt alle PDF’s uit secties “Hoofddocument” en “Bijlagen” naar DOWNLOAD_DIR.
    4. Leest elke PDF met PyMuPDF en geeft de eerste ~1000 tekens als samenvatting terug.

    Retourneert een dict met:
      {"summaries": [ {"filename": "...", "summary": "..."}, … ] }

    Werkt vanaf een lokaliteit met Chrome/ChromeDriver. Als je straks naar Streamlit Cloud gaat,
    kun je in _get_selenium_driver() alleen de optie `options.binary_location = "/usr/bin/chromium-browser"` 
    toevoegen (zie commentaar daarin).
    """
    # ── Stap A: vind met Selenium de detail-URL ────────────────────────────────────
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
                target_link = href  # volledige URL, want link.get_attribute('href') is al een absolute of relatieve URL
            break

    driver.quit()

    if not target_link:
        raise Exception(f"Geen schriftelijke vraag gevonden voor: {raadslid_label}")

    # ── Stap B: detailpagina ophalen met requests ─────────────────────────────────
    detail_resp = requests.get(target_link)
    if detail_resp.status_code != 200:
        raise Exception(f"Kon detailpagina niet laden (status {detail_resp.status_code}).")
    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

    # Hulpfunctie: download alle PDF’s uit een sectie met de gegeven label (bijv. “Hoofddocument” of “Bijlagen”)
    def _download_docs_in_section(label: str) -> list[str]:
        found_files = []
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
                        with open(lokaal_pad, "wb") as f:
                            f.write(r.content)
                        found_files.append(lokaal_pad)
                    except Exception:
                        # Als downloaden mislukt, slaan we dat bestand over
                        continue

        return found_files

    # Download zowel “Hoofddocument” als “Bijlagen”
    hoofddocs = _download_docs_in_section("Hoofddocument")
    bijlagen  = _download_docs_in_section("Bijlagen")
    alle_pdfs = hoofddocs + bijlagen

    # Hulpfunctie: maak van een PDF een tekstsamenvatting van ~1000 tekens
    def _summarize_pdf(pdf_pad: str, max_chars: int = 1000) -> str:
        try:
            doc = fitz.open(pdf_pad)
            text = ""
            for page in doc:
                text += page.get_text()
                if len(text) >= max_chars:
                    break
            doc.close()
            return text.strip()[:max_chars] + "..." if len(text) > max_chars else text.strip()
        except Exception as e:
            return f"(Kon niet samenvatten: {e})"

    # Bouw de uiteindelijke lijst met dicts: [{"filename": "...", "summary": "..."}, …]
    summaries = []
    for pad in alle_pdfs:
        fname = os.path.basename(pad)
        smry = _summarize_pdf(pad)
        summaries.append({"filename": fname, "summary": smry})

    return {"summaries": summaries}


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

    # Als voorbeeld (kopieer er zelf eentje uit de lijst hierboven):
    # result = find_latest_question_and_summarize("de Waard, J.M.D. – Voorzieningen jeugd")
    # print(result)
    pass
