import streamlit as st
from raadsvraag_logic import get_raadsleden_labels, find_latest_question_and_summarize

st.set_page_config(
    page_title="Raadsvraag Bot",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="auto",
)

st.title("📄 Raadsvraag Bot")
st.markdown(
    "Zoek de **laatste schriftelijke vraag** van een Rotterdams raadslid "
    "en genereer een samenvatting van het hoofddocument + bijlagen."
)

# ─────────────────────────────────────────────────────────────────────────────
# Stap 1: Haal alle labels op (de strings ná “Schriftelijke vraag …”)
# ─────────────────────────────────────────────────────────────────────────────

with st.spinner("Labels ophalen…"):
    try:
        raadsleden_labels = get_raadsleden_labels()
    except Exception as e:
        st.error(f"Kon de labels niet ophalen: {e}")
        st.stop()

if not raadsleden_labels:
    st.error("Er zijn geen raadsleden met 'Schriftelijke vraag' gevonden op de startpagina.")
    st.stop()

# Laat de gebruiker kiezen uit een dropdown
keuze_label = st.selectbox(
    "Kies een raadslid + onderwerp:",
    raadsleden_labels,
    index=0,
    help="Selecteer hier de exacte tekst zoals getoond op de site (bijv. 'de Waard, J.M.D. – Voorzieningen jeugd')."
)

st.write("")  # lege regel voor spacing

# ─────────────────────────────────────────────────────────────────────────────
# Stap 2: Als de knop wordt ingedrukt, zoek detail-URL, download PDF's en toon samenvattingen
# ─────────────────────────────────────────────────────────────────────────────

if st.button("🔍 Haal laatste raadsvraag op"):
    with st.spinner("Details ophalen, PDF’s downloaden en samenvatten…"):
        try:
            # Vind de detail-URL voor de gekozen label
            result = find_latest_question_and_summarize(keuze_label)
        except Exception as e:
            st.error(f"Er ging iets mis: {e}")
        else:
            samenvattingen = result.get("summaries", [])
            if not samenvattingen:
                st.warning("Er zijn geen documenten (hoofddocument of bijlagen) gevonden voor deze vraag.")
            else:
                st.success(f"✅ Samenvattingen voor: \"{keuze_label}\"")
                for sam in samenvattingen:
                    st.subheader(sam["filename"])
                    st.text_area(
                        label="Samenvatting",
                        value=sam["summary"],
                        height=200,
                        key=sam["filename"]
                    )
