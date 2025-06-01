import streamlit as st
from raadsvraag_logic import find_latest_question_and_summarize

st.set_page_config(page_title="Raadsvraag Bot", page_icon="📄")

st.title("📄 Raadsvraag Bot")
st.markdown("Zoek de **laatste schriftelijke vraag** van een Rotterdamse raadslid en genereer een samenvatting van het hoofddocument + bijlagen.")

raadslid = st.text_input("👤 Vul de naam van het raadslid in (bijv. 'Groningen, D. van')")

if st.button("🔍 Haal laatste raadsvraag op"):
    if not raadslid.strip():
        st.warning("Voer eerst een naam in.")
    else:
        with st.spinner("Even bezig met zoeken, downloaden en samenvatten..."):
            try:
                result = find_latest_question_and_summarize(raadslid)
                st.success(f"✅ Laatste vraag gevonden voor {raadslid}")
                st.markdown(f"### 📑 Samenvattingen van documenten:")

                for summary in result['summaries']:
                    st.markdown(f"**📄 {summary['filename']}**")
                    st.text_area("📌 Samenvatting:", summary['summary'], height=200)

            except Exception as e:
                st.error(f"Er ging iets mis: {e}")
