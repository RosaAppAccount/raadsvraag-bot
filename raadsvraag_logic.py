import os
import requests
import fitz  # PyMuPDF
from bs4 import BeautifulSoup

# 📌 URLs en mappen
BASE_URL = "https://rotterdamraad.bestuurlijkeinformatie.nl"
START_URL = f"{BASE_URL}/Reports/Details/da9b533f-5f24-4f51-8567-19fe410f15d4"
DOWNLOAD_DIR = "downloaded_documents"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def normalize(text):
    """Hulpmethode om hoofdletters, leestekens te verwijderen voor robuuste vergelijking"""
    return (
        text.lower()
        .replace(",", "")
        .replace(".", "")
        .replace("’", "")
        .replace("‘", "")
        .replace("`", "")
        .strip()
    )

def find_latest_question_and_summarize(raadslid_naam):
    # 🌍 Stap 1: HTML ophalen
    response = requests.get(START_URL)
    if response.status_code != 200:
        raise Exception(f"Kan de hoofdpagina niet laden: status {response.status_code}")
    
    soup = BeautifulSoup(response.text, "html.parser")
    report_links = soup.select(".report-children a")

    normalized_query = normalize(raadslid_naam)
    zoekdelen = normalized_query.split()

    target_link = None

    for link in report_links:
        link_text = link.get_text(strip=True)
        norm_link_text = normalize(link_text)

        print(f"🧪 {link_text}")  # Log voor debugging

        if "schriftelijke" in norm_link_text:
            if all(deel in norm_link_text for deel in zoekdelen):
                print(f"✅ MATCH: {link_text}")
                target_link = BASE_URL + link["href"]
                break

    if not target_link:
        raise Exception(f"Geen schriftelijke vraag gevonden voor: {raadslid_naam}")

    # 🌍 Stap 2: Details pagina ophalen
    detail_resp = requests.get(target_link)
    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")

    def get_documents_by_section(label):
        docs = []
        sections = detail_soup.find_all("div", class_="report-section")
        for section in sections:
            header = section.find("h4")
            if header and label.lower() in header.get_text().lower():
                for a in section.find_all("a", href=True):
                    doc_url = BASE_URL + a["href"]
                    filename = os.path.join(DOWNLOAD_DIR, a.get_text().strip().replace("/", "_"))
                    file_resp = requests.get(doc_url)
                    with open(filename, "wb") as f:
                        f.write(file_resp.content)
                    docs.append(filename)
        return docs

    # 📥 Stap 3: Download hoofddocument + bijlagen
    hoofddoc = get_documents_by_section("Hoofddocument")
    bijlagen = get_documents_by_section("Bijlagen")

    # 📄 Stap 4: PDF samenvatting
    def summarize_pdf(pdf_path, max_chars=1000):
        try:
            doc = fitz.open(pdf_path)
            text = ""
            for page in doc:
                text += page.get_text()
                if len(text) > max_chars:
                    break
            doc.close()
            return text.strip()[:max_chars] + "..."
        except Exception as e:
            return f"(Fout bij samenvatten: {e})"

    summaries = []
    for path in hoofddoc + bijlagen:
        summaries.append({
            "filename": os.path.basename(path),
            "summary": summarize_pdf(path)
        })

    return {"summaries": summaries}
