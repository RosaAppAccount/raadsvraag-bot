# raadsvraag_scraper.py
import os
import time
import requests
import fitz  # PyMuPDF
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

TARGET_NAME = "Groningen, D. van"
BASE_URL = "https://rotterdamraad.bestuurlijkeinformatie.nl/Reports/Details/da9b533f-5f24-4f51-8567-19fe410f15d4"
DOWNLOAD_DIR = "downloaded_documents"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Set up browser
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 20)

print("🔍 Pagina openen...")
driver.get(BASE_URL)
time.sleep(5)

driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

items = driver.find_elements(By.CSS_SELECTOR, ".report-children a")
target_url = None
for item in items:
    if "Schriftelijke" in item.text and TARGET_NAME in item.text:
        target_url = item.get_attribute("href")
        break

if not target_url:
    driver.quit()
    raise Exception(f"❌ Geen schriftelijke vraag gevonden voor {TARGET_NAME}")

print("✅ Vraag gevonden. Naar detailpagina...")
driver.get(target_url)
time.sleep(5)

def download_doc_from_field(field_label):
    try:
        section = wait.until(EC.presence_of_element_located((By.XPATH, f"//div[h4[contains(text(), '{field_label}')]]")))
        links = section.find_elements(By.TAG_NAME, "a")
        downloaded_files = []
        for link in links:
            file_url = link.get_attribute("href")
            filename = os.path.join(DOWNLOAD_DIR, link.text.strip().replace("/", "_"))
            r = requests.get(file_url)
            with open(filename, 'wb') as f:
                f.write(r.content)
            downloaded_files.append(filename)
        return downloaded_files
    except Exception as e:
        print(f"⚠️ {field_label} niet gevonden of download mislukt: {e}")
        return []

hoofddocumenten = download_doc_from_field("Hoofddocument")
bijlagen = download_doc_from_field("Bijlagen")

driver.quit()

def summarize_pdf(pdf_path, max_chars=1000):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
        if len(text) > max_chars:
            break
    doc.close()
    return text[:max_chars].strip() + "..."

print("\n📄 SAMENVATTINGEN:")
for file in hoofddocumenten + bijlagen:
    print(f"\n--- {os.path.basename(file)} ---")
    print(summarize_pdf(file))
