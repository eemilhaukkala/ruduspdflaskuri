import re
import pandas as pd
import streamlit as st
import math
import os
import hashlib
from datetime import datetime
from pypdf import PdfReader
from io import BytesIO
import base64

# --- ASETTELU ---
st.set_page_config(page_title="Rudus PDF -laskuri", page_icon="brick", layout="wide")
st.title("brick Rudus PDF -laskuri v47 — PDF näkyvissä sovelluksessa")

st.sidebar.write("Python-versio: 3.9+")

# --- KANSIOT ---
CALCS_DIR = "laskelmat"
HISTORY_FILE = os.path.join(CALCS_DIR, "laskuhistoria.csv")
os.makedirs(CALCS_DIR, exist_ok=True)

# --- TURVALLINEN NIMI ---
def safe_filename(text, max_len=80):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '_', str(text))
    text = re.sub(r'[\s._]+', '_', text).strip('_')
    if len(text) > max_len:
        text = text[:max_len]
    return text + ".csv"

# --- UNIikki ID ---
def calc_id(pdf_name, m3, h, min_):
    key = f"{pdf_name}|{m3}|{h}|{min_}"
    return hashlib.md5(key.encode()).hexdigest()[:10]

# --- HISTORIA ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            df = pd.read_csv(HISTORY_FILE)
            if "Yhteensä_€_m3" in df.columns:
                df["Yhteensä_€_m3"] = pd.to_numeric(df["Yhteensä_€_m3"], errors='coerce').fillna(0)
            return df
        except:
            pass
    return pd.DataFrame(columns=[
        "Aika", "PDF_nimi", "m3", "Pumppausaika_h", "Palveluaika_min",
        "Betonilaatu", "Yhteensä_€_m3", "Laskenta_ID", "Laskenta_tiedosto"
    ])

def save_history(df):
    try:
        df.to_csv(HISTORY_FILE, index=False)
    except Exception as e:
        st.error(f"Historiavirhe: {e}")

# --- TYÖMAAN TIEDOT ---
st.sidebar.header("Työmaan tiedot")
m3 = st.sidebar.number_input("Pumpattava määrä (m³)", min_value=0.1, step=0.5, value=12.0)
pumppausaika = st.sidebar.number_input("Pumppausaika (h)", min_value=0.0, step=0.5, value=2.0)
palveluaika = st.sidebar.number_input("Palveluaika (min)", min_value=0, step=5, value=120)

# --- LASKENTAFUNKTIO ---
def laske_taulukko(m3, pumppausaika, palveluaika, H):
    betonilaadut = {k: v for k, v in H.items() if "betoni" in k.lower() or re.search(r"C\d{2}/\d{2}", k)}
    if not betonilaadut:
        raise ValueError("Ei betonilaatuja.")
    
    pump_h_per_m3 = (H.get("Pumppaus €/h", 0) * pumppausaika) / m3 if m3 > 0 else 0
    charged_min = max(0, palveluaika - 25)
    num_inc = math.ceil(charged_min / 5)
    palvelu_per_m3 = (num_inc * H.get("Palveluaika €/5min", 0)) / m3 if m3 > 0 else 0
    kuljetus_per_m3 = H.get("Kuljetus €/m³", 0)

    rows = []
    for laatu, bh in betonilaadut.items():
        yhteensä = (
            bh
            + H.get("Ympäristölisä €/m³", 0)
            + kuljetus_per_m3
            + H.get("Pumppaus €/m³", 0)
            + pump_h_per_m3
            + palvelu_per_m3
        )
        rows.append({
            "Betonilaatu": laatu.split("#")[0].strip() if "#" in laatu else laatu,
            "Betonin hinta €/m³": bh,
            "Ympäristölisä €/m³": H.get("Ympäristölisä €/m³", 0),
            "Kuljetus €/m³": kuljetus_per_m3,
            "Pumppaus €/m³ (kiinteä)": H.get("Pumppaus €/m³", 0),
            "Pumppaus €/h → €/m³": round(pump_h_per_m3, 2),
            "Palveluaika €/m³": round(palvelu_per_m3, 2),
            "Yhteensä €/m³": round(yhteensä, 2),
        })
    return pd.DataFrame(rows).set_index("Betonilaatu")

# --- PDF-LATAUS ---
uploaded_pdf = st.file_uploader("Lataa Ruduksen tarjous (PDF)", type=["pdf"])

# --- PÄÄUI ---
if uploaded_pdf:
    pdf_name = uploaded_pdf.name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- LUE PDF KERRAN ---
    pdf_bytes = uploaded_pdf.read()
    pdf_stream = BytesIO(pdf_bytes)

    # --- PDF-ESIKATSELU SUORAAN SOVELUKSESSA ---
    st.markdown("### PDF-esikatselu")
    try:
        # Koodaa base64
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        # Upota iframe (pieni koko, skaalautuu)
        pdf_display = f'''
        <iframe 
            src="data:application/pdf;base64,{base64_pdf}" 
            width="100%" 
            height="600px" 
            style="border: none; border-radius: 8px;">
        </iframe>
        '''
        st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.warning("PDF-esikatselu ei onnistunut. Voit ladata tiedoston:")
        st.download_button("Lataa PDF", data=pdf_bytes, file_name=pdf_name, mime="application/pdf")

    # --- HINNAT ---
    hinnat = {}
    try:
        reader = PdfReader(pdf_stream)
        teksti = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                teksti += page_text + "\n"
        
        rivit = [r.strip() for r in teksti.splitlines() if r.strip()]
        betoni_section = False
        betoni_descs = []
        betoni_prices = []

        for i, rivi in enumerate(rivit):
            lower = rivi.lower()

            if "ympäristölisä" in lower:
                for j in range(i, min(i+5, len(rivit))):
                    if "2,20" in rivit[j] and "€/m³" in rivit[j]:
                        m = re.search(r"(\d+[.,]\d+)\s*€/m³", rivit[j])
                        if m:
                            hinnat["Ympäristölisä €/m³"] = float(m.group(1).replace(",", "."))
                            break

            if "palveluaikakorvaus" in lower or ("palveluaika" in lower and "€" in rivi):
                m = re.search(r"(\d+[.,]\d+)", rivi)
                if m:
                    hinnat["Palveluaika €/5min"] = float(m.group(1).replace(",", "."))

            if "nettohinnat betoneista" in lower:
                betoni_section = True
                continue
            if betoni_section and ("kuljetus" in lower or "ympäristölisä" in lower):
                betoni_section = False

            if betoni_section:
                if re.search(r"C\d{2}/\d{2}", rivi) and "betoni" in lower:
                    betoni_descs.append(rivi.strip())
                m = re.search(r"(\d+[.,]\d+)\s*€/m³", rivi)
                if m:
                    betoni_prices.append(float(m.group(1).replace(",", ".")))

            if "kuljetus" in lower or "> 5,0 m3" in rivi:
                for j in range(i, min(i+5, len(rivit))):
                    if "12,47" in rivit[j] and "€/m³" in rivit[j]:
                        m = re.search(r"(\d+[.,]\d+)\s*€/m³", rivit[j])
                        if m:
                            hinnat["Kuljetus €/m³"] = float(m.group(1).replace(",", "."))
                            break

            if "pumppaus" in lower and "€" in rivi:
                match_h = re.search(r"(\d+[.,]\d+)\s*€\s*/?\s*h", rivi)
                match_m3 = re.search(r"(\d+[.,]\d+)\s*€\s*/?\s*m", rivi)
                if match_h:
                    hinnat["Pumppaus €/h"] = float(match_h.group(1).replace(",", "."))
                if match_m3:
                    hinnat["Pumppaus €/m³"] = float(match_m3.group(1).replace(",", "."))

        if len(betoni_descs) == len(betoni_prices):
            for desc, price in zip(betoni_descs, betoni_prices):
                hinnat[desc] = price

    except Exception as e:
        st.error(f"PDF-lukuvirhe: {e}")
        hinnat = {}

    if not hinnat:
        st.error("Ei hintoja PDF:stä. Varmista, että se on Ruduksen tarjous.")
    else:
        st.markdown("### Poimitut hinnat")
        st.json(hinnat, expanded=False)

        try:
            df = laske_taulukko(m3, pumppausaika, palveluaika, hinnat)
            st.markdown("### Betonilaatujen hinnat (€/m³)")
            st.dataframe(df.style.format("{:,.2f}"), use_container_width=True)
            st.info(f"**{m3} m³** | **{pumppausaika} h** | **{palveluaika} min**")

            # --- TALLENNA ---
            history = load_history()
            calc_id_val = calc_id(pdf_name, m3, pumppausaika, palveluaika)
            safe_name = safe_filename(f"{pdf_name}_{m3}m3_{pumppausaika}h_{palveluaika}min_{calc_id_val}")
            calc_file = os.path.join(CALCS_DIR, safe_name)

            dup = history[
                (history["PDF_nimi"] == pdf_name) &
                (history["m3"] == m3) &
                (history["Pumppausaika_h"] == pumppausaika) &
                (history["Palveluaika_min"] == palveluaika)
            ]

            if dup.empty:
                df_with_params = df.copy().reset_index()
                df_with_params.insert(0, "m³", m3)
                df_with_params.insert(1, "Pumppausaika_h", pumppausaika)
                df_with_params.insert(2, "Palveluaika_min", palveluaika)
                df_with_params.to_csv(calc_file, index=False)

                new_rows = []
                for laatu, row in df.iterrows():
                    new_rows.append({
                        "Aika": timestamp,
                        "PDF_nimi": pdf_name,
                        "m3": m3,
                        "Pumppausaika_h": pumppausaika,
                        "Palveluaika_min": palveluaika,
                        "Betonilaatu": laatu,
                        "Yhteensä_€_m3": row["Yhteensä €/m³"],
                        "Laskenta_ID": calc_id_val,
                        "Laskenta_tiedosto": calc_file
                    })
                history = pd.concat([history, pd.DataFrame(new_rows)], ignore_index=True)
                save_history(history)
                st.success(f"Tallennettu: `{safe_name}`")

            st.download_button(
                label="Lataa tämä laskenta (kaikki laadut)",
                data=df.to_csv().encode(),
                file_name=f"{safe_filename(pdf_name, 50)}_laskenta.csv",
                mime="text/csv"
            )

        except Exception as e:
            st.error(f"Laskentavirhe: {e}")

    # --- HISTORIA ---
    st.markdown("---")
    st.markdown("### Laskuhistoria")
    history = load_history()
    if not history.empty:
        history["Aika"] = pd.to_datetime(history["Aika"], errors='coerce')
        history = history.dropna(subset=["Aika"]).sort_values("Aika", ascending=False)
        history["Aika"] = history["Aika"].dt.strftime("%d.%m.%Y %H:%M")

        for pdf in history["PDF_nimi"].unique():
            with st.expander(f"PDF: {pdf}"):
                group = history[history["PDF_nimi"] == pdf].copy()
                p = group.iloc[0]
                st.caption(f"{p['m3']} m³ | {p['Pumppausaika_h']} h | {p['Palveluaika_min']} min")

                disp = group[["Betonilaatu", "Yhteensä_€_m3"]].copy()
                st.dataframe(disp.style.format({"Yhteensä_€_m3": "{:,.2f}"}), use_container_width=True)

                calc_file = p["Laskenta_tiedosto"]
                if pd.notna(calc_file) and os.path.exists(calc_file):
                    with open(calc_file, "rb") as f:
                        st.download_button(
                            label="Lataa kaikki betonilaadut CSV:nä",
                            data=f.read(),
                            file_name=os.path.basename(calc_file),
                            mime="text/csv",
                            key=f"dl_{p['Laskenta_ID']}"
                        )
                else:
                    st.caption("Tiedosto puuttuu")

        st.download_button(
            label="Lataa koko historia CSV:nä",
            data=history.to_csv(index=False).encode(),
            file_name="rudus_laskuhistoria.csv",
            mime="text/csv"
        )
    else:
        st.info("Ei historiaa vielä.")

else:
    st.info("Lataa Ruduksen tarjous-PDF vasemmalta.")
