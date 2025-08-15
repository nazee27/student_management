import io
import os
import json
import zipfile
from datetime import datetime
from typing import List

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

DATA_PATH = "students_sample.csv"
CONFIG_PATH = "config.json"
RECEIPTS_DIR = "receipts"

DEFAULT_CONFIG = {
    "app_title": "Sistem Yuran Asrama (Mengaji & Silat)",
    "branding_text": "SMK PONDOK UPEH",
    "receipt_prefix": "DN",
    "receipt_footer": "Resit ini dijana secara digital dan tidak memerlukan tandatangan.",
    "receipt_logo_path": "",
    "currency": "RM",
    "receipt_left_label_block": "Nama\nNo. KP\nTingkatan & Kelas\nJenis Yuran\nAmaun\nTarikh Bayaran\nNo. Resit",
    "receipt_right_label_block": "{NAMA}\n{NO_KP}\n{TINGKATAN} {KELAS}\n{FEE_TYPE}\n{CURRENCY}{AMOUNT:.2f}\n{DATE}\n{RECEIPT_NO}",
    "ui_labels": {"mengaji": "Yuran Mengaji", "silat": "Yuran Silat"}
}

REQUIRED_COLS = [
    "NAMA","NO_KP","TINGKATAN","KELAS",
    "MENGAJI_STATUS","MENGAJI_AMOUNT","MENGAJI_DATE",
    "SILAT_STATUS","SILAT_AMOUNT","SILAT_DATE"
]

# ----------------- helpers -----------------
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = ""
    df["MENGAJI_AMOUNT"] = pd.to_numeric(df["MENGAJI_AMOUNT"], errors="coerce").fillna(0.0)
    df["SILAT_AMOUNT"] = pd.to_numeric(df["SILAT_AMOUNT"], errors="coerce").fillna(0.0)
    return df[REQUIRED_COLS]

def load_students():
    if os.path.exists(DATA_PATH):
        df = pd.read_csv(DATA_PATH, dtype=str, keep_default_na=False)
        for col in ["MENGAJI_AMOUNT","SILAT_AMOUNT"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return ensure_columns(df)
    return ensure_columns(pd.DataFrame(columns=REQUIRED_COLS))

def save_students(df: pd.DataFrame):
    df.to_csv(DATA_PATH, index=False)

def next_receipt_no(prefix: str) -> str:
    # unique enough for our use
    return f"{prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

# -------------- receipt drawing --------------
def draw_receipt_page(c, cfg: dict, student: dict, fee_type: str, amount: float, paid_date: str, receipt_no: str):
    width, height = A4
    margin = 18*mm
    y = height - margin

    if cfg.get("receipt_logo_path"):
        try:
            logo = ImageReader(cfg["receipt_logo_path"])
            c.drawImage(logo, margin, y-20*mm, width=20*mm, height=20*mm, preserveAspectRatio=True, mask='auto')
            c.setFont("Helvetica-Bold", 16)
            c.drawString(margin+25*mm, y-10*mm, cfg.get("branding_text",""))
        except Exception:
            c.setFont("Helvetica-Bold", 16)
            c.drawString(margin, y-10*mm, cfg.get("branding_text",""))
    else:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, y-10*mm, cfg.get("branding_text",""))

    c.setFont("Helvetica", 11)
    c.drawRightString(width - margin, y-10*mm, "RESIT PEMBAYARAN YURAN")
    c.line(margin, y-12*mm, width - margin, y-12*mm)

    left_labels = cfg.get("receipt_left_label_block", DEFAULT_CONFIG["receipt_left_label_block"])
    right_labels = cfg.get("receipt_right_label_block", DEFAULT_CONFIG["receipt_right_label_block"])

    formatted_right = right_labels.format(
        NAMA=student["NAMA"],
        NO_KP=student["NO_KP"],
        TINGKATAN=student["TINGKATAN"],
        KELAS=student["KELAS"],
        FEE_TYPE=fee_type,
        AMOUNT=float(amount),
        DATE=paid_date if paid_date else datetime.now().strftime("%Y-%m-%d"),
        RECEIPT_NO=receipt_no,
        CURRENCY=cfg.get("currency","RM")
    )

    top = y - 25*mm
    row_h = 7*mm
    left_lines = left_labels.split("\n")
    right_lines = formatted_right.split("\n")
    for i in range(max(len(left_lines), len(right_lines))):
        y_line = top - i*row_h
        c.setFont("Helvetica", 11)
        c.drawString(margin, y_line, left_lines[i] if i < len(left_lines) else "")
        c.drawString(width/2, y_line, right_lines[i] if i < len(right_lines) else "")

    c.line(margin, 25*mm, width - margin, 25*mm)
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(margin, 20*mm, cfg.get("receipt_footer",""))

def generate_single_pdf_bytes(cfg: dict, student_row: pd.Series, fee_type_key: str) -> bytes:
    fee_map = {"MENGAJI": ("MENGAJI_AMOUNT","MENGAJI_DATE"),
               "SILAT": ("SILAT_AMOUNT","SILAT_DATE")}
    label_map = {"MENGAJI": cfg["ui_labels"]["mengaji"],
                 "SILAT": cfg["ui_labels"]["silat"]}

    amt_col, date_col = fee_map[fee_type_key]
    amount = float(student_row[amt_col])
    paid_date = str(student_row[date_col]) if str(student_row[date_col]) else datetime.now().strftime("%Y-%m-%d")
    receipt_no = next_receipt_no(cfg.get("receipt_prefix","DN"))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_receipt_page(c, cfg, student_row.to_dict(), label_map[fee_type_key], amount, paid_date, receipt_no)
    c.showPage()
    c.save()
    return buf.getvalue()

def generate_bulk_one_pdf(cfg: dict, students: pd.DataFrame, fee_type_key: str) -> bytes:
    fee_map = {"MENGAJI": ("MENGAJI_AMOUNT","MENGAJI_DATE"),
               "SILAT": ("SILAT_AMOUNT","SILAT_DATE")}
    label_map = {"MENGAJI": cfg["ui_labels"]["mengaji"],
                 "SILAT": cfg["ui_labels"]["silat"]}
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for _, row in students.iterrows():
        amt_col, date_col = fee_map[fee_type_key]
        amount = float(row[amt_col])
        paid_date = str(row[date_col]) if str(row[date_col]) else datetime.now().strftime("%Y-%m-%d")
        receipt_no = next_receipt_no(cfg.get("receipt_prefix","DN"))
        draw_receipt_page(c, cfg, row.to_dict(), label_map[fee_type_key], amount, paid_date, receipt_no)
        c.showPage()
    c.save()
    return buf.getvalue()

# ----------------- UI -----------------
st.set_page_config(page_title="Sistem Yuran", layout="wide")
cfg = load_config()
st.title(cfg.get("app_title", DEFAULT_CONFIG["app_title"]))

tab_import, tab_data, tab_receipt, tab_settings = st.tabs(["📥 Import/Export", "📋 Data Pelajar", "🧾 Resit & Cetak", "⚙️ Tetapan"])

with tab_import:
    st.subheader("Import/Export Data")
    colA, colB = st.columns(2)
    with colA:
        st.write("**Muat Naik CSV (gantikan data sedia ada)**")
        up = st.file_uploader("Pilih fail CSV", type=["csv"], key="upload_csv")
        if up is not None:
            df_new = pd.read_csv(up, dtype=str, keep_default_na=False)
            df_new = ensure_columns(df_new)
            save_students(df_new)
            st.success("Data dimuat naik & disimpan.")
    with colB:
        st.write("**Muat Turun Data Semasa (CSV)**")
        df_now = load_students()
        st.download_button(
            "Muat Turun CSV",
            data=df_now.to_csv(index=False).encode("utf-8"),
            file_name=f"students_export_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

with tab_data:
    st.subheader("Senarai & Sunting Pelajar")
    df = load_students()

    # Quick add form
    with st.expander("➕ Tambah Pelajar Baharu"):
        with st.form("add_student"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Nama")
            ic = c2.text_input("No. KP")
            c3, c4 = st.columns(2)
            ting = c3.selectbox("Tingkatan", ["4","5"])
            kelas = c4.selectbox("Kelas", ["Inovatif","Bestari","Dinamik","Kreatif"])
            mengaji_amt = st.number_input("Amaun Yuran Mengaji", min_value=0.0, step=1.0, value=0.0)
            silat_amt = st.number_input("Amaun Yuran Silat", min_value=0.0, step=1.0, value=0.0)
            submitted = st.form_submit_button("Tambah")
        if submitted:
            new_row = {
                "NAMA": name, "NO_KP": ic, "TINGKATAN": ting, "KELAS": kelas,
                "MENGAJI_STATUS": "Belum Bayar", "MENGAJI_AMOUNT": float(mengaji_amt), "MENGAJI_DATE": "",
                "SILAT_STATUS": "Belum Bayar", "SILAT_AMOUNT": float(silat_amt), "SILAT_DATE": ""
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_students(ensure_columns(df))
            st.success("Pelajar ditambah.")

    st.caption("Edit terus dalam jadual, kemudian klik **Simpan Perubahan**. Untuk buang pelajar, pilih dan tekan **Padam**.")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "MENGAJI_STATUS": st.column_config.SelectboxColumn("MENGAJI_STATUS", options=["Belum Bayar","Sudah Bayar"]),
            "SILAT_STATUS": st.column_config.SelectboxColumn("SILAT_STATUS", options=["Belum Bayar","Sudah Bayar"]),
        }
    )
    c1, c2 = st.columns(2)
    if c1.button("💾 Simpan Perubahan Data"):
        save_students(ensure_columns(edited_df))
        st.success("Perubahan disimpan.")

    # Delete selected rows
    with st.expander("🗑️ Padam Pelajar"):
        to_delete = st.multiselect(
            "Pilih baris untuk dipadam",
            options=list(range(len(edited_df))),
            format_func=lambda i: f"{edited_df.loc[i,'NAMA']} • {edited_df.loc[i,'NO_KP']}"
        )
        if st.button("Padam Dipilih"):
            if to_delete:
                new_df = edited_df.drop(index=to_delete).reset_index(drop=True)
                save_students(ensure_columns(new_df))
                st.success(f"{len(to_delete)} rekod dipadam. Sila refresh untuk lihat perubahan.")
            else:
                st.warning("Tiada pilihan dipadam.")

with tab_receipt:
    st.subheader("Jana Resit (Individu / Bulk) & Cetak")
    os.makedirs(RECEIPTS_DIR, exist_ok=True)

    df = load_students()
    if df.empty:
        st.warning("Tiada data pelajar.")
    else:
        # Search
        q = st.text_input("Cari Nama / No. KP / Tingkatan / Kelas", "")
        filtered = df.copy()
        if q.strip():
            s = q.lower()
            mask = (
                df["NAMA"].str.lower().str.contains(s, na=False) |
                df["NO_KP"].str.lower().str.contains(s, na=False) |
                df["TINGKATAN"].astype(str).str.lower().str.contains(s, na=False) |
                df["KELAS"].str.lower().str.contains(s, na=False)
            )
            filtered = df[mask].reset_index(drop=True)

        col1, col2, col3 = st.columns([1,1,1])
        fee_choice = col1.selectbox("Jenis Yuran", [cfg["ui_labels"]["mengaji"], cfg["ui_labels"]["silat"]])
        fee_key = "MENGAJI" if fee_choice == cfg["ui_labels"]["mengaji"] else "SILAT"
        only_paid = col2.checkbox("Hanya yang Sudah Bayar", value=True)
        status_col = "MENGAJI_STATUS" if fee_key=="MENGAJI" else "SILAT_STATUS"
        list_df = filtered[filtered[status_col]=="Sudah Bayar"] if only_paid else filtered

        st.write(f"**{len(list_df)}** rekod dipaparkan.")
        selected_idx = st.multiselect(
            "Pilih pelajar (untuk resit):",
            options=list_df.index.tolist(),
            format_func=lambda i: f"{list_df.loc[i,'NAMA']} • {list_df.loc[i,'NO_KP']} • T{list_df.loc[i,'TINGKATAN']} {list_df.loc[i,'KELAS']}"
        )

        cA, cB, cC = st.columns(3)

        # Individual
        with cA:
            if st.button("🧾 Jana Resit Individu"):
                if not selected_idx:
                    st.warning("Sila pilih seorang pelajar.")
                else:
                    row = list_df.loc[selected_idx[0]]
                    pdf_bytes = generate_single_pdf_bytes(cfg, row, fee_key)
                    # save to receipts folder
                    safe_name = row["NAMA"].replace(" ", "_")
                    fname = f"resit_{fee_key.lower()}_{safe_name}.pdf"
                    with open(os.path.join(RECEIPTS_DIR, fname), "wb") as f:
                        f.write(pdf_bytes)
                    st.download_button("Muat Turun Resit PDF", data=pdf_bytes, file_name=fname, mime="application/pdf")
                    st.info("Resit disimpan ke folder 'receipts'. Buka PDF dan cetak (Share → Print di iPad).")

        # Bulk -> single big PDF
        with cB:
            if st.button("📄📄 Jana Bulk (Satu Fail PDF)"):
                if not selected_idx:
                    st.warning("Sila pilih sekurang-kurangnya seorang.")
                else:
                    subset = list_df.loc[selected_idx]
                    pdf_bytes = generate_bulk_one_pdf(cfg, subset, fee_key)
                    fname = f"bulk_{fee_key.lower()}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    with open(os.path.join(RECEIPTS_DIR, fname), "wb") as f:
                        f.write(pdf_bytes)
                    st.download_button("Muat Turun PDF (Semua Dalam Satu)", data=pdf_bytes, file_name=fname, mime="application/pdf")
                    st.info("Setiap pelajar berada pada halaman berasingan dalam fail ini.")

        # Bulk -> separate PDFs, zipped
        with cC:
            if st.button("🧾📦 Jana Bulk (Pisah Setiap Pelajar, ZIP)"):
                if not selected_idx:
                    st.warning("Sila pilih sekurang-kurangnya seorang.")
                else:
                    mem_zip = io.BytesIO()
                    subset = list_df.loc[selected_idx]
                    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                        for _, row in subset.iterrows():
                            pdf_bytes = generate_single_pdf_bytes(cfg, row, fee_key)
                            safe_name = row["NAMA"].replace(" ","_")
                            file_name = f"resit_{fee_key.lower()}_{safe_name}.pdf"
                            zf.writestr(file_name, pdf_bytes)
                            # also save to receipts folder
                            with open(os.path.join(RECEIPTS_DIR, file_name), "wb") as f:
                                f.write(pdf_bytes)
                    mem_zip.seek(0)
                    zip_name = f"resit_zip_{fee_key.lower()}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
                    st.download_button("Muat Turun ZIP Resit", data=mem_zip.getvalue(), file_name=zip_name, mime="application/zip")
                    st.info("Semua resit individu turut disimpan dalam folder 'receipts'.")

with tab_settings:
    st.subheader("Tetapan UI & Resit")
    cfg = load_config()
    cfg["app_title"] = st.text_input("Tajuk Aplikasi", value=cfg.get("app_title", DEFAULT_CONFIG["app_title"]))
    cfg["branding_text"] = st.text_input("Teks Branding (atas resit)", value=cfg.get("branding_text", DEFAULT_CONFIG["branding_text"]))
    cfg["receipt_prefix"] = st.text_input("Prefix No. Resit", value=cfg.get("receipt_prefix","DN"))
    cfg["currency"] = st.text_input("Mata Wang", value=cfg.get("currency","RM"))
    cfg["receipt_logo_path"] = st.text_input("Laluan Logo (optional, PNG/JPG)", value=cfg.get("receipt_logo_path",""))

    st.write("**Label UI**")
    c1, c2 = st.columns(2)
    cfg["ui_labels"]["mengaji"] = c1.text_input("Label Yuran Mengaji", value=cfg["ui_labels"].get("mengaji","Yuran Mengaji"))
    cfg["ui_labels"]["silat"] = c2.text_input("Label Yuran Silat", value=cfg["ui_labels"].get("silat","Yuran Silat"))

    st.write("**Templat Resit**")
    cfg["receipt_left_label_block"] = st.text_area("Blok Kiri", value=cfg.get("receipt_left_label_block", DEFAULT_CONFIG["receipt_left_label_block"]), height=120)
    st.caption("Placeholder: {NAMA} {NO_KP} {TINGKATAN} {KELAS} {FEE_TYPE} {AMOUNT} {DATE} {RECEIPT_NO} {CURRENCY}")
    cfg["receipt_right_label_block"] = st.text_area("Blok Kanan", value=cfg.get("receipt_right_label_block", DEFAULT_CONFIG["receipt_right_label_block"]), height=120)

    cfg["receipt_footer"] = st.text_input("Footer Resit", value=cfg.get("receipt_footer", DEFAULT_CONFIG["receipt_footer"]))

    if st.button("💾 Simpan Tetapan"):
        save_config(cfg)
        st.success("Tetapan disimpan.")
