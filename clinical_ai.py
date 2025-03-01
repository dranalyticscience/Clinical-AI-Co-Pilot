# Import libraries
import pandas as pd
import streamlit as st
import ast
from io import BytesIO
import base64
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# Custom CSS
st.markdown("""
    <style>
    .main {background-color: #f5f7fa;}
    .stButton>button {background-color: #4CAF50; color: white; border-radius: 5px;}
    .stSelectbox {background-color: #ffffff; border-radius: 5px;}
    .stTextArea {background-color: #ffffff; border-radius: 5px;}
    </style>
""", unsafe_allow_html=True)

# PDF function
def df_to_pdf(df, notes):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    for _, row in df.iterrows():
        text = (f"ID: {row['id']}\nMeds: {row['meds']}\nInsight: {row['insight']}\n"
                f"Recommendation: {row['med_suggestion']}\nBMI: {row['bmi']:.1f}\n"
                f"Social: {row['social_note']}\nNotes: {notes}\n---")
        story.append(Paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 12))
    doc.build(story)
    buffer.seek(0)
    return buffer

# Load data
patients = pd.read_csv("patients_data.csv")
patients["glucose"] = patients["glucose"].apply(ast.literal_eval)
patients["bmi"] = patients["weight_kg"] / (patients["height_m"] ** 2)

# Functions
def check_glucose(glucose_list, hba1c):
    avg = sum(glucose_list) / len(glucose_list)
    if avg > 150 or hba1c > 7.0:
        return f"High risk (avg {avg:.1f}, HbA1c {hba1c}%) - review meds"
    else:
        return f"Stable (avg {avg:.1f}, HbA1c {hba1c}%)"

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

# Apply functions
patients["insight"] = patients.apply(lambda row: check_glucose(row["glucose"], row["hba1c"]), axis=1)
patients["social_note"] = patients["zip_code"].apply(check_social)
patients["med_suggestion"] = patients.apply(lambda row: suggest_med(row["insight"], row["meds"], row["hba1c"], row["bmi"]), axis=1)

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
    st.write(f"**Height**: {selected_patient['height_m']} m")
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

# Notes section with AI suggestion
st.subheader("Doctor’s Notes", divider="blue")
default_notes = suggest_notes(selected_patient["insight"], selected_patient["med_suggestion"])
notes = st.text_area("Add notes for this patient:", value=default_notes, height=100, key=f"notes_{patient_id}")

# Glucose graph
st.subheader("Glucose Trend", divider="blue")
glucose_data = pd.DataFrame({
    "Day": [f"Day {i+1}" for i in range(len(selected_patient["glucose"]))],
    "Glucose": selected_patient["glucose"]
})
st.line_chart(glucose_data.set_index("Day"), height=300, use_container_width=True)

# Status summary table
st.subheader("All Patients Overview", divider="blue")
summary = patients[["id", "insight", "med_suggestion"]].copy()
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
st.write("Built by a physician for physicians | Data as of Feb 28, 2025")