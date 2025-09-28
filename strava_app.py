import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# === Hemligheter från Streamlit Cloud (Settings → Secrets) ===
CLIENT_ID = st.secrets["CLIENT_ID"]
CLIENT_SECRET = st.secrets["CLIENT_SECRET"]
REFRESH_TOKEN = st.secrets["REFRESH_TOKEN"]

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_BASE = "https://www.strava.com/api/v3"

st.set_page_config(page_title="Strava Export Dashboard", layout="wide")
st.title("📊 Strava Export Dashboard")

# Hjälp: dumpa svar säkert
def show_error(prefix, resp: requests.Response):
    try:
        payload = resp.json()
    except Exception:
        payload = resp.text
    st.error(f"{prefix}: HTTP {resp.status_code}\n\n{payload}")

# Rensa cache-knapp
colA, colB = st.columns([1,3])
with colA:
    if st.button("🔄 Rensa cache"):
        st.cache_data.clear()
        st.success("Cache rensad – kör igen.")

# 1) Hämta access_token via refresh
@st.cache_data(ttl=60*60)
def get_access_token():
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
    }
    r = requests.post(STRAVA_TOKEN_URL, data=payload)
    if r.status_code != 200:
        raise RuntimeError(f"token_refresh_failed::{r.status_code}::{r.text}")
    data = r.json()
    return data["access_token"], data.get("scope", ""), data.get("athlete", {}).get("id")

# 2) En liten “hälsa på Strava”-check
def sanity_check(token: str):
    # Hämta /athlete för att se att token funkar
    r = requests.get(STRAVA_BASE + "/athlete", headers={"Authorization": f"Bearer {token}"})
    return r

# 3) Hämta aktiviteter
def fetch_activities(days_back=30, per_page=100):
    token, scope, athlete_id = get_access_token()
    # Visa en statusrad
    st.info(f"Token OK • Scopes: {scope or '(okänt)'} • Athlete: {athlete_id or '(okänt)'}")

    # Snabb sanity-check
    r0 = sanity_check(token)
    if r0.status_code != 200:
        show_error("Athlete-check misslyckades", r0)
        r0.raise_for_status()

    since = int((datetime.utcnow() - timedelta(days=days_back)).timestamp())
    r = requests.get(
        STRAVA_BASE + "/athlete/activities",
        headers={"Authorization": f"Bearer {token}"},
        params={"after": since, "per_page": per_page}
    )
    if r.status_code != 200:
        show_error("Aktivitetsanrop misslyckades", r)
        r.raise_for_status()
    return r.json()

# ---- UI ----
days = st.slider("Hur många dagar bakåt?", 7, 180, 30)

try:
    activities = fetch_activities(days_back=days, per_page=200)
except RuntimeError as e:
    # Visar tydligt om refresh-token inte fungerar
    msg = str(e)
    if msg.startswith("token_refresh_failed::"):
        parts = msg.split("::", 2)
        code = parts[1] if len(parts) > 1 else "?"
        body = parts[2] if len(parts) > 2 else ""
        st.error(f"Token refresh misslyckades (HTTP {code}).\n\n{body}")
    raise

if not activities:
    st.warning("Inga aktiviteter hittades i intervallet.")
    st.stop()

df = pd.DataFrame([{
    "id": a["id"],
    "name": a["name"],
    "date": a["start_date_local"],
    "distance_km": round(a["distance"]/1000, 2) if a.get("distance") else None,
    "time_min": round(a["moving_time"]/60, 1) if a.get("moving_time") else None,
    "avg_hr": a.get("average_heartrate"),
    "max_hr": a.get("max_heartrate")
} for a in activities])

st.subheader("Dina aktiviteter")
st.dataframe(df, use_container_width=True)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Ladda ner CSV", csv, "strava_aktiviteter.csv", "text/csv")

st.subheader("Puls för en aktivitet")
activity_id = st.selectbox("Välj aktivitet ID", df["id"])
def fetch_heartrate(activity_id):
    token, _, _ = get_access_token()
    url = f"{STRAVA_BASE}/activities/{activity_id}/streams"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                     params={"keys": "heartrate,time", "key_by_type": "true"})
    if r.status_code != 200:
        show_error("Pulsström misslyckades", r)
        r.raise_for_status()
    return r.json()

if st.button("Visa puls"):
    streams = fetch_heartrate(int(activity_id))
    hr = streams.get("heartrate", {}).get("data", [])
    t = streams.get("time", {}).get("data", list(range(len(hr))))
    if hr:
        hr_df = pd.DataFrame({"Time (s)": t, "HR": hr})
        st.line_chart(hr_df.set_index("Time (s)"))
        st.download_button("⬇️ Ladda ner HR-CSV",
                           hr_df.to_csv(index=False).encode("utf-8"),
                           f"hr_{activity_id}.csv",
                           "text/csv")
    else:
        st.info("Ingen pulsström för denna aktivitet.")
