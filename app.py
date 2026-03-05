# app.py
import re
from datetime import date, timedelta

import requests
import pandas as pd
import streamlit as st
from requests.auth import HTTPBasicAuth
import matplotlib.pyplot as plt

# ---------------- CONFIG IMPORT ----------------
try:
    from config_local import API_URL, API_USERNAME, API_PASSWORD
except ImportError:
    st.error("Missing config_local.py. Create it from config_template.py")
    st.stop()

# ---------------- API SETTINGS ----------------
API_PARAMS = {
    "query": 'JobHistory.JobType equals "ExportSeries"',
    "fields": (
        "JobHistory.CurrentState,"
        "JobHistory.GroupKey1,"
        "JobHistory.Progress,"
        "JobHistory.ScheduledAt"
    ),
    "pageSize": -1
}

VALUE_COLUMNS = ["CurrentState", "GroupKey1", "Progress", "ScheduledAt"]

# ---------------- HELPERS ----------------
def fix_millis_format(dt_str: str) -> str:
    if not dt_str or not isinstance(dt_str, str):
        return dt_str
    return re.sub(r":(\d{3})(?=[+-]\d{4}|$)", r".\1", dt_str.strip())


@st.cache_data(ttl=300)
def fetch_json(url, params, username, password):
    s = requests.Session()
    s.auth = HTTPBasicAuth(username, password)
    r = s.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def json_to_dataframe(data: dict) -> pd.DataFrame:
    rows = data.get("rows", [])
    out = []

    for r in rows:
        obj = r.get("object", {})
        vals = r.get("values", [])

        rec = {}
        for i, col in enumerate(VALUE_COLUMNS):
            rec[col] = vals[i] if i < len(vals) else None

        rec["JobId"] = obj.get("id")
        rec["JobLabel"] = obj.get("label")
        out.append(rec)

    df = pd.DataFrame(out)

    df["CurrentState"] = df["CurrentState"].astype(str).str.strip()
    df["Progress"] = pd.to_numeric(df["Progress"], errors="coerce")

    df["ScheduledAt"] = (
        df["ScheduledAt"]
        .apply(fix_millis_format)
        .pipe(pd.to_datetime, errors="coerce", utc=True)
    )

    return df


# ---------------- UI ----------------
st.set_page_config(page_title="ExportSeries — Last 7 Days", layout="wide")
st.title("📦 ExportSeries — Last 7 Days Report")

if "raw" not in st.session_state:
    with st.spinner("Fetching ExportSeries jobs..."):
        st.session_state["raw"] = fetch_json(
            API_URL, API_PARAMS, API_USERNAME, API_PASSWORD
        )

df = json_to_dataframe(st.session_state["raw"])

# Last 7 Days Filter
today = date.today()
start_7 = today - timedelta(days=6)

df_7 = df[df["ScheduledAt"].notna()].copy()
df_7["ScheduledDate"] = df_7["ScheduledAt"].dt.date

df_7 = df_7[
    (df_7["ScheduledDate"] >= start_7) &
    (df_7["ScheduledDate"] <= today)
]

st.caption(f"Date range: {start_7} → {today}")

# KPIs
col1, col2 = st.columns(2)
col1.metric("Total Exports (7 days)", f"{len(df_7):,}")
col2.metric("Unique States", df_7["CurrentState"].nunique())

# Donut Chart (All States)
st.markdown("## 🍩 Export Status Distribution")

summary_df = (
    df_7["CurrentState"]
    .value_counts()
    .reset_index()
)

summary_df.columns = ["Status", "Count"]

if summary_df.empty:
    st.info("No export jobs found in last 7 days.")
else:
    fig, ax = plt.subplots(figsize=(6, 6))

    wedges, _ = ax.pie(
        summary_df["Count"],
        startangle=90,
        wedgeprops=dict(width=0.45)
    )

    ax.axis("equal")

    total = summary_df["Count"].sum()

    ax.text(0, 0.1, f"{total:,}", ha="center", va="center",
            fontsize=22, fontweight="bold")

    date_label = f"{start_7} → {today}"

    ax.text(
    0, -0.1,
    f"Exports\n{date_label}",
    ha="center",
    va="center",
    fontsize=11
    )

    legend_labels = [
        f"{row.Status} — {row.Count:,} ({row.Count/total:.1%})"
        for row in summary_df.itertuples()
    ]

    ax.legend(
        wedges,
        legend_labels,
        title="Job State",
        loc="center left",
        bbox_to_anchor=(1, 0.5),
        frameon=False
    )

    st.pyplot(fig)

    import io

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
    buf.seek(0)

    st.download_button(
        label="⬇ Download Chart as PNG",
        data=buf,
        file_name="export_status_chart.png",
        mime="image/png"
    )
# Table
st.markdown("## 📋 Export Details")
st.dataframe(
    df_7.drop(columns=["ScheduledDate"]).reset_index(drop=True),
    use_container_width=True,
    height=500
)

# Download
st.download_button(
    "⬇ Download CSV",
    df_7.drop(columns=["ScheduledDate"]).to_csv(index=False),
    file_name="exportseries_last_7_days.csv",
    mime="text/csv",
)