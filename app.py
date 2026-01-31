# 7-Eleven Receipt OCR Expense Tracker
# Uses Gemini AI to extract structured data from receipt images

import streamlit as st
import pandas as pd
import os
import google.generativeai as genai
import PIL.Image
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# STEP 0: ADMIN CONTROLS
# =========================================================
with st.sidebar:
    st.header("⚙️ Admin Tools")
    st.info("Use this if the app feels 'stuck' or shows old data.")

    if st.button("🗑️ Hard Reset App"):
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()

    st.divider()

# --- 1. INITIALIZATION ---
if 'master_db' not in st.session_state:
    st.session_state.master_db = pd.DataFrame(columns=["Timestamp", "Item", "Category", "Price", "Size"])

# --- 2. TIME-AWARE AI OCR ---
def run_smart_ocr(image_path):
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found. Please set it in your .env file.")
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')

    try:
        img = PIL.Image.open(image_path)
        prompt = """Analyze this 7-Eleven receipt. Return a JSON LIST of objects with these keys:
                  "Timestamp", "Item", "Category", "Price", "Size".
                  Format Timestamp as YYYY-MM-DD HH:MM.
                  If you can't find a date, use '2026-01-03 12:00'."""

        response = model.generate_content([prompt, img])
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_json)
        df = pd.DataFrame(data)

        # Handle missing Timestamp column
        if 'Timestamp' not in df.columns:
            df['Timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M")

        df['Timestamp'] = df['Timestamp'].fillna(datetime.now().strftime("%Y-%m-%d %H:%M"))
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
        return df

    except Exception as e:
        st.error(f"⚠️ Parsing Error: {e}")
        return None

# --- 3. UI & ANALYTICS ---
st.title("📅 Time-Period Expense Tracker")

uploaded_file = st.file_uploader("Upload Receipt", type=["jpg", "png"])

if uploaded_file:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("🖼️ Uploaded Receipt")
        st.image(uploaded_file, use_container_width=True)

    with col2:
        st.subheader("🔍 OCR Verification")
        if st.button("🚀 Analyze Receipt"):
            with st.spinner("AI is reading..."):
                with open("temp.jpg", "wb") as f:
                    f.write(uploaded_file.getbuffer())

                st.session_state.current_scan = run_smart_ocr("temp.jpg")

        if 'current_scan' in st.session_state and st.session_state.current_scan is not None:
            st.info("💡 Edit the table below to correct any AI errors.")

            edited_results = st.data_editor(
                st.session_state.current_scan,
                use_container_width=True,
                key="ocr_editor"
            )

            if st.button("💾 Save to History"):
                st.session_state.master_db = pd.concat([st.session_state.master_db, edited_results]).drop_duplicates()
                st.success("Data saved to Master File!")
                del st.session_state.current_scan
                st.rerun()

# --- 4. TIME-PERIOD ANALYSIS ---
if not st.session_state.master_db.empty:
    st.divider()
    st.subheader("🕒 Spending Over Time")

    time_data = st.session_state.master_db.copy()
    time_data['Date'] = time_data['Timestamp'].dt.date
    daily_spend = time_data.groupby('Date')['Price'].sum()

    st.line_chart(daily_spend)

    with st.expander("📄 View Full Transaction History"):
        st.dataframe(st.session_state.master_db.sort_values("Timestamp", ascending=False))

# --- 5. CATEGORY SUMMARY SECTION ---
if not st.session_state.master_db.empty:
    st.divider()
    st.header("📊 Spending Summary by Category")

    df_clean = st.session_state.master_db.copy()
    df_clean["Price"] = pd.to_numeric(df_clean["Price"], errors='coerce').fillna(0)

    # Exclude total/summary rows from Thai receipts
    exclude_keywords = [
        "ยอดสุทธิ", "ยอดรวม", "Total", "ชำระเงิน", "ทรูวอลเล็ท", "รวมทั้งสิ้น",
        "ตราปั๊มจังหวัด", "ภารกิจช้อปครบ", "รับเงินภารกิจช้อปหน้าร้าน", "สิทธิ์แลกซื้อสุดคุ้มAMB", "บริการ"
    ]

    mask = df_clean["Item"].str.contains('|'.join(exclude_keywords), na=False)
    df_items_only = df_clean[~mask]

    category_summary = df_items_only.groupby("Category")["Price"].sum().reset_index()

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.subheader("Summary Table")
        st.dataframe(category_summary, use_container_width=True, hide_index=True)

    with col_b:
        st.subheader("Spending Chart")
        st.bar_chart(data=category_summary, x="Category", y="Price")

    total_spent = float(category_summary["Price"].sum())
    st.metric("Total Overall Spending", f"{total_spent:,.2f} THB")
