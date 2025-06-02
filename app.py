# app.py

import streamlit as st
from raadsvraag_logic import get_raadsleden_labels, find_latest_question_and_summarize

# ─────────────────────────────────────────────────────────────────────────────
# Pagina‐configuratie
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Raadsvraag Bot",
    page_icon="📄",
    layout="centered"
)

st.title("📄 Raadsvraag Bot")
st.markdown(
    "Zoek de **laatste schriftelijke vraag** van een Rotterdams raadslid "
    "en genereer een korte samenvatting van het hoofddocument + bijlagen."
)
st.write("")  # lege regel voor spacing

# ─────────────────────────────────────────────────────────────────────────────
# Stap 1: Dropdown vullen met alle beschikbare labels (“Schriftelijke vraag …”)
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Lijst met raadslid-labels ophalen…"):
    try:
        raadsleden_labels = get_raadsleden_labels()
    except Exception as e:
        st.error(f"Kon de lijst met labels niet ophalen: {e}")
        st.stop()

if len(raadsleden_labels) == 0:
    st.error("Er zijn geen raadsleden met “Schriftelijke vraag” gevonden op de startpagina.")
    st.stop()

# Toon een selectbox waar de gebruiker precies één van de gevonden items kiest:
keuze_label = st.selectbox(
    "Kies een raadslid + onderwerp:",
    raadsleden_labels,
    index=0,
    help="Selecteer hier één van de beschikbare labels (bijv. 'de Waard, J.M.D. – Voorzieningen jeugd')."
)

st.write("")  # lege regel voor spacing

# ─────────────────────────────────────────────────────────────────────────────
# Stap 2: Als op de knop wordt geklikt, de gekozen label doorgeven en samenvatting tonen
# ─────────────────────────────────────────────────────────────────────────────

if st.button("🔍 Haal laatste raadsvraag op"):
    with st.spinner("Bezig met ophalen, downloaden en samenvatten…"):
        try:
            # We geven exact het dropdown‐item door:
            result = find_latest_question_and_summarize(keuze_label)
        except Exception as e:
            # Als er iets misgaat (bijv. detailpagina niet gevonden), tonen we de foutmelding
            st.error(f"Er ging iets mis: {e}")
        else:
            samenvattingen = result.get("summaries", [])

            if len(samenvattingen) == 0:
                st.warning("Er zijn geen documenten (hoofddocument of bijlagen) gevonden voor deze vraag.")
            else:
                st.success(f"✅ Samenvattingen voor “{keuze_label}”")
                for sam in samenvattingen:
                    st.subheader(sam["filename"])
                    st.text_area(
                        label="Samenvatting",
                        value=sam["summary"],
                        height=200,
                        key=sam["filename"]
                    )
