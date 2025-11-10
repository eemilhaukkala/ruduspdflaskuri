# ... (kaikki aiempi koodi pysyy samana, korjataan vain historia-osa)

    # --- HISTORIA ---
    st.markdown("---")
    st.markdown("### Laskuhistoria")
    history = load_history()
    if not history.empty:
        # Muunna aika
        history["Aika"] = pd.to_datetime(history["Aika"], errors='coerce').dt.strftime("%d.%m.%Y %H:%M")
        history = history.sort_values("Aika", ascending=False).dropna(subset=["Aika"])

        for pdf in history["PDF_nimi"].unique():
            with st.expander(f"PDF: {pdf}"):
                group = history[history["PDF_nimi"] == pdf].copy()
                p = group.iloc[0]

                st.caption(f"{p['m3']} m³ | {p['Pumppausaika_h']} h | {p['Palveluaika_min']} min")

                # --- KORJAUS: Varmista, että Yhteensä_€_m3 on float ---
                group["Yhteensä_€_m3"] = pd.to_numeric(group["Yhteensä_€_m3"], errors='coerce').fillna(0)

                disp = group[["Betonilaatu", "Yhteensä_€_m3"]].copy()

                # Muotoile vain numeerinen sarake
                st.dataframe(
                    disp.style.format({
                        "Yhteensä_€_m3": "{:,.2f}"
                    }),
                    use_container_width=True
                )

                # Latausnapit
                cols = st.columns(3)
                for i, (_, r) in enumerate(group.iterrows()):
                    with cols[i % 3]:
                        if pd.notna(r["Laskenta_tiedosto"]) and os.path.exists(r["Laskenta_tiedosto"]):
                            with open(r["Laskenta_tiedosto"], "rb") as f:
                                st.download_button(
                                    label=r["Betonilaatu"][:25] + ("..." if len(r["Betonilaatu"]) > 25 else ""),
                                    data=f.read(),
                                    file_name=os.path.basename(r["Laskenta_tiedosto"]),
                                    mime="text/csv",
                                    key=f"dl_{r['Laskenta_ID']}_{i}"
                                )
                        else:
                            st.caption("Tiedosto puuttuu")

        # Koko historia
        st.download_button(
            label="Lataa koko historia CSV:nä",
            data=history.to_csv(index=False).encode(),
            file_name="rudus_laskuhistoria.csv",
            mime="text/csv"
        )
    else:
        st.info("Ei vielä laskuhistoriaa.")
