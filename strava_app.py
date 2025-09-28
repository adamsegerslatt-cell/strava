import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# === Läs credentials från Streamlit Secrets ===
CLIENT_ID = st.secrets["CLIENT_ID"]
CLIENT_SECRET = st.secrets["CLIENT_SECRET"]
REFRESH_TOKEN = st.secrets["REFRESH_TOKEN"]

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_BASE = "https://www.strava.com/api/v3"


@st.cache_data(ttl=60*60)
def get_access_token():
    r = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN
    })
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_activities(days_back=30, per_page=100):
    token = get_access_token()
    since = int((datetime.utcnow() - timedelta(days=days_back)).timestamp())
    resp = requests.get(
        STRAVA_BASE + "/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"after": since, "per_page": per_page}
    )
    resp.raise_for_status()
    return resp.json()


def fetch_heartrate(activity_id):
    token = get_access_token()
    url = f"{STRAVA_BASE}/activities/{activity_id}/streams"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params={"keys": "heartrate,time", "key_by_type": "true"}
    )
    resp.raise_for_status()
    return resp.json()


st.title("📊 Strava Export Dashboard")

days = st.slider("Hur många dagar bakåt?", 7, 180, 30)
activities = fetch_activities(days_back=days)

if not activities:
    st.warning("Inga aktiviteter hittades.")
    st.stop()

df = pd.DataFrame([{
    "id": a["id"],
    "name": a["name"],
    "date": a["start_date_local"],
    "distance_km": round(a["distance"]/1000, 2),
    "time_min": round(a["moving_time"]/60, 1),
    "avg_hr": a.get("average_heartrate"),
    "max_hr": a.get("max_heartrate")
} for a in activities])

st.subheader("Dina aktiviteter")
st.dataframe(df)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Ladda ner CSV", csv, "strava_aktiviteter.csv", "text/csv")

st.subheader("Puls för en aktivitet")
activity_id = st.selectbox("Välj aktivitet ID", df["id"])
if st.button("Visa puls"):
    streams = fetch_heartrate(activity_id)
    hr = streams.get("heartrate", {}).get("data", [])
    t = streams.get("time", {}).get("data", list(range(len(hr))))
    if hr:
        hr_df = pd.DataFrame({"Time (s)": t, "HR": hr})
        st.line_chart(hr_df.set_index("Time (s)"))
        csv_hr = hr_df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Ladda ner HR-CSV", csv_hr, f"hr_{activity_id}.csv", "text/csv")
    else:
        st.info("Ingen pulsström för denna aktivitet.")
