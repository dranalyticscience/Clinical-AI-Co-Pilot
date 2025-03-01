# Import libraries
import pandas as pd
import streamlit as st
import ast
import sqlite3
from io import BytesIO
import base64
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from sklearn.linear_model import LinearRegression
import numpy as np
import requests
import json

# Custom CSS
st.markdown("""
    <style>
    .main {background-color: #f5f7fa;}
    .stButton>button {background-color: #4CAF50; color: white; border-radius: 5px;}
    .stSelectbox {background-color: #ffffff; border-radius: 5px;}
    .stTextArea {background-color: #ffffff; border-radius: 5px;}
    </style>
""", unsafe_allow_html=True)

# SQLite setup
conn = sqlite3.connect("patient_notes.db")
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS notes (patient_id INTEGER PRIMARY KEY, note TEXT)")
conn.commit()

# PDF function
def df_to_pdf(df, notes):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    for _, row in df.iterrows():
        text = (f"ID: {row['id']}\nMeds: {row['meds']}\nInsight: {row['insight']}\n"
                f"Recommendation: {row['med_suggestion']}\nBMI: {row['bmi']:.1f}\n"
                f"Social: {row['social_note']}\nGlucose Trend: {row['trend']}\nNotes: {notes}\n---")
        story.append(Paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 12))
    doc.build(story)
    buffer.seek(0)
    return buffer

# Load mock FHIR data
@st.cache_data
def load_fhir_data():
    # Use HAPI FHIR public server (mock data)
    url = "http://hapi.fhir.org/baseR4/Observation?code=2339-0&_count=100"  # Glucose observations
    try:
        response = requests.get(url)
        data = response.json()
        patients_list = []
        for i, entry in enumerate(data.get("entry", [])[:100]):  # Limit to 100
            glucose = entry["resource"].get("valueQuantity", {}).get("value", 150)
            patient_id = i + 1
            patients_list.append({
                "id": patient_id,
                "glucose": [glucose + np.random.randint(-20, 20) for _ in range(4)],  # Simulate 4 days
                "meds": np.random.choice(["metformin", "insulin", "none"]),
                "zip_code": np.random.choice(["60601", "90210", "33101", "10001", "75201", "94102", "30301", "85001", "98101", "20001"]),
                "hba1c": np.random.uniform(5.5, 10.0),
                "weight_kg": np.random.randint(60, 110),
                "height_m": np.random.uniform(1.5, 1.9)
            })
        return pd.DataFrame(patients_list)
    except:
        # Fallback to CSV if FHIR fails
        df = pd.read_csv("patients_data.csv")
        df["glucose"] = df["glucose"].apply(ast.literal_eval)
        return df

patients = load_fhir_data()
patients["bmi"] = patients["weight_kg"] / (patients["height_m"] ** 2)

# Functions
def check_glucose(glucose_list, hba1c):
    avg = sum(glucose_list) / len(glucose_list)
    if avg > 150 or hba1c > 7.0:
        return f"High risk (avg {avg:.1f}, HbA1c {hba1c:.1f}%) - review meds"
    else:
        return f"Stable (avg {avg:.1f}, HbA1c {hba1c:.1f}%)"

def check_social(zip_code):
    zip_map = {
        "60601": "Urban - good access", "90210": "High income - good resources",
        "33101": "Check affordability", "10001": "Urban - mixed access",
        "75201": "Assess local resources", "94102": "Urban - variable access",
        "30301": "Mixed - check insurance", "85001": "Rural - limited access",
        "98101": "Urban - good resources", "20001": "Urban - mixed resources"
    }
    return zip_map.get(zip_code, "Unknown - assess locally")

def suggest_med(insight, current_meds, hba1c, bmi):
    avg = float(insight.split("avg ")[1].split(",")[0])
    bmi_note = " (high BMI may impact dosing)" if bmi > 30 else ""
    if hba1c > 9.0 and current_meds == "none":
        return f"Start metformin urgently (ADA: HbA1c >9%){bmi_note}"
    elif hba1c > 7.0 and current_meds == "none":
        return f"Start metformin (ADA: first-line for HbA1c >7%){bmi_note}"
    elif (hba1c > 7.0 or avg > 150) and current_meds == "metformin":
        return f"Add insulin (ADA: combo for uncontrolled glucose/HbA1c){bmi_note}"
    elif (hba1c > 7.0 or avg > 150) and current_meds == "insulin":
        return f"Adjust insulin dose or consult endocrinologist{bmi_note}"
    elif hba1c <= 7.0 and avg <= 130:
        return "No change needed (glucose and HbA1c well-controlled)"
    else:
        return "Monitor closely or consult specialist"

def suggest_notes(insight, med_suggestion):
    if "High risk" in insight and "urgently" in med_suggestion:
        return "Urgent consult needed within 24-48 hours."
    elif "High risk" in insight:
        return "Schedule follow-up in 1 week."
    else:
        return "Routine monitoring, next visit in 1 month."

def predict_glucose_trend(glucose_list):
    X = np.array(range(len(glucose_list))).reshape(-1, 1)
    y = np.array(glucose_list)
    model = LinearRegression()
    model.fit(X, y)
    next_day = len(glucose_list)
    predicted = model.predict([[next_day]])[0]
    trend = "rising" if model.coef_[0] > 0 else "falling" if model.coef_[0] < 0 else "stable"
    return f"Predicted next day: {predicted:.1f} mg/dL (trend: {trend})"

# Apply functions
patients["insight"] = patients.apply(lambda row: check_glucose(row["glucose"], row["hba1c"]), axis=1)
patients["social_note"] = patients["zip_code"].apply(check_social)
patients["med_suggestion"] = patients.apply(lambda row: suggest_med(row["insight"], row["meds"], row["hba1c"], row["bmi"]), axis=1)
patients["trend"] = patients["glucose"].apply(predict_glucose_trend)

# Sidebar
with st.sidebar:
    st.header("Control Panel", divider="blue")
    risk_filter = st.selectbox("Risk Level:", ["All", "High risk", "Stable"])
    if risk_filter == "High risk":
        filtered_patients = patients[patients["insight"].str.contains("High risk")]
    elif risk_filter == "Stable":
        filtered_patients = patients[patients["insight"].str.contains("Stable")]
    else:
        filtered_patients = patients
    high_risk_count = len(patients[patients["insight"].str.contains("High risk")])
    stable_count = len(patients[patients["insight"].str.contains("Stable")])
    st.metric("High Risk Patients", high_risk_count)
    st.metric("Stable Patients", stable_count)

# Main display
st.subheader("Patient Dashboard", divider="blue")
patient_id = st.selectbox("Select Patient ID:", filtered_patients["id"], key="patient_select")

selected_patient = filtered_patients[filtered_patients["id"] == patient_id].iloc[0]
col1, col2 = st.columns([1, 1.5])

with col1:
    st.markdown("### Patient Profile")
    st.write(f"**Current Meds**: {selected_patient['meds']}")
    st.write(f"**Weight**: {selected_patient['weight_kg']} kg")
    st.write(f"**Height**: {selected_patient['height_m']:.2f} m")
    st.write(f"**BMI**: {selected_patient['bmi']:.1f} kg/m²")
    st.write(f"**Social Context**: {selected_patient['social_note']}")

with col2:
    st.markdown("### Clinical Assessment")
    if "High risk" in selected_patient["insight"]:
        st.markdown(f"**Status**: <span style='color:red'>{selected_patient['insight']}</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"**Status**: <span style='color:green'>{selected_patient['insight']}</span>", unsafe_allow_html=True)
    if "urgently" in selected_patient["med_suggestion"]:
        st.markdown(f"**Recommendation**: <span style='color:orange'>{selected_patient['med_suggestion']}</span>", unsafe_allow_html=True)
    else:
        st.write(f"**Recommendation**: {selected_patient['med_suggestion']}")
    st.write(f"**Target HbA1c**: <7.0% (ADA guideline)")
    st.write(f"**Glucose Trend**: {selected_patient['trend']}")

# Notes section with SQLite
st.subheader("Doctor’s Notes", divider="blue")
c.execute("SELECT note FROM notes WHERE patient_id = ?", (patient_id,))
saved_note = c.fetchone()
default_notes = suggest_notes(selected_patient["insight"], selected_patient["med_suggestion"])
notes = st.text_area("Add notes for this patient:", value=saved_note[0] if saved_note else default_notes, height=100, key=f"notes_{patient_id}")
if st.button("Save Notes"):
    c.execute("INSERT OR REPLACE INTO notes (patient_id, note) VALUES (?, ?)", (patient_id, notes))
    conn.commit()
    st.success("Notes saved to database!")

# Glucose graph
st.subheader("Glucose Trend", divider="blue")
glucose_data = pd.DataFrame({
    "Day": [f"Day {i+1}" for i in range(len(selected_patient["glucose"]))] + ["Day 5 (Pred)"],
    "Glucose": selected_patient["glucose"] + [float(selected_patient["trend"].split(": ")[1].split(" ")[0])]
})
st.line_chart(glucose_data.set_index("Day"), height=300, use_container_width=True)

# Status summary table
st.subheader("All Patients Overview", divider="blue")
summary = patients[["id", "insight", "med_suggestion", "trend"]].copy()
summary["Status"] = summary["insight"].apply(lambda x: "High Risk" if "High risk" in x else "Stable")
st.dataframe(summary.style.applymap(lambda x: "color: red" if "High Risk" in str(x) else "color: green", subset=["Status"]))

# Download PDF
st.subheader("Export Report", divider="blue")
pdf_buffer = df_to_pdf(filtered_patients[filtered_patients["id"] == patient_id], notes)
st.download_button(
    label="Download Patient Report (PDF)",
    data=pdf_buffer,
    file_name=f"patient_{patient_id}_report.pdf",
    mime="application/pdf"
)

# Footer
st.markdown("---")
st.write("Built by a physician for physicians | Data as of Feb 28, 2025 | Hosted on Streamlit Cloud")
conn.close()
conn.close()