"""
Namma Pothole Assistant — Streamlit App
========================================
Two personas, two tabs:
  🧑 Citizen  — Report pothole (photo + voice), Route planner
  🏛️  BBMP     — Hotspot heatmap, Maintenance logging

Run:
  streamlit run streamlit_app.py
"""

import base64
import time
from pathlib import Path

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

# ── Config ─────────────────────────────────────────────────────────────────────
API_BASE   = "http://localhost:8000/v1"
BBMP_TOKEN = "dev-secret-change-me"
BENGALURU_CENTER = [12.9716, 77.5946]

SEVERITY_COLOUR = {
    "low":      "#22c55e",
    "medium":   "#f59e0b",
    "high":     "#ef4444",
    "critical": "#7f1d1d",
}
SCORE_COLOUR = {
    "Excellent": "#22c55e",
    "Good":      "#84cc16",
    "Fair":      "#f59e0b",
    "Poor":      "#ef4444",
    "Critical":  "#7f1d1d",
}

# ── Page setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Namma Pothole Assistant",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .persona-tab-citizen { color: #1d4ed8; font-weight: 700; }
    .persona-tab-bbmp    { color: #854d0e; font-weight: 700; }
    .story-box {
        background: #f8fafc;
        border-left: 4px solid #3b82f6;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 14px;
        font-size: 13.5px;
        color: #334155;
    }
    .bbmp-story {
        border-left-color: #f59e0b;
    }
    div[data-testid="stTabs"] button {
        font-size: 16px;
        font-weight: 600;
        padding: 10px 28px;
    }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def api_post(path: str, payload: dict, token: str = None) -> dict | None:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_get(path: str, params: dict = None) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=15)
        return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def img_to_b64(uploaded) -> str:
    return base64.b64encode(uploaded.read()).decode("utf-8")


@st.cache_data(ttl=300, show_spinner=False)
def reverse_geocode(lat: float, lng: float) -> str:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 16},
            headers={"User-Agent": "BengaluruPotholeAssistant/0.1"},
            timeout=5,
        )
        data = r.json()
        addr = data.get("address", {})
        parts = [
            addr.get("road") or addr.get("pedestrian") or addr.get("footway"),
            addr.get("neighbourhood") or addr.get("suburb"),
            addr.get("city") or addr.get("town"),
        ]
        return ", ".join(p for p in parts if p) or f"{lat:.4f}, {lng:.4f}"
    except Exception:
        return f"{lat:.5f}, {lng:.5f}"


def poll_report(report_id: str) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}/reports/{report_id}", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ── Session state ──────────────────────────────────────────────────────────────
for _k in ["report_result", "voice_result", "route_result", "maintenance_result"]:
    if _k not in st.session_state:
        st.session_state[_k] = None
if "report_pin" not in st.session_state:
    st.session_state.report_pin = {"lat": 12.9716, "lng": 77.5946}


# ── Top header ─────────────────────────────────────────────────────────────────
st.markdown("## 🛣️ Namma Pothole Assistant")
st.markdown(
    """
    <p style="font-size:15px; color:#4b5563; line-height:1.7; margin-top:-6px;">
    Bengaluru generates thousands of pothole complaints every monsoon — yet most go unresolved for weeks.
    <b>Namma Pothole Assistant</b> bridges the gap between citizens and the BBMP by letting anyone report
    a pothole in seconds using a photo or voice note. AI automatically assesses severity, pins the location
    on a live map, and scores every road in real time. Commuters get the safest route before they leave home.
    Officers see exactly which streets need urgent repair — no spreadsheets, no guesswork.
    </p>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ── Two persona tabs ───────────────────────────────────────────────────────────
tab_citizen, tab_bbmp = st.tabs([
    "🧑 Citizen — Report & Navigate",
    "🏛️ BBMP Officer — Monitor & Maintain",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CITIZEN
# ══════════════════════════════════════════════════════════════════════════════
with tab_citizen:

    st.markdown("""
<div class="story-box">
<b>🧑 Meet Ravi</b> — a daily commuter from Koramangala to Whitefield.
He hits the same pothole on Sarjapur Road every morning.
This tab lets him report it in seconds (photo or voice), and check
which route has the fewest potholes before he leaves home.
</div>
""", unsafe_allow_html=True)

    citizen_tab1, citizen_tab2 = st.tabs(["📍 Report a Pothole", "🗺️ Route Planner"])

    # ── CITIZEN SUB-TAB 1: Report a Pothole ──────────────────────────────────
    with citizen_tab1:

        st.markdown("### 📍 Report a Pothole")
        st.markdown("""
Report a pothole in **3 steps** — pin the location on the map, upload a photo
*(optional)*, and describe what you see. Can't type? Use the **🎙️ Voice** button
and speak in English, Hindi, or Kannada — the app does the rest.
        """)
        st.divider()

        # ── Step 1: map pin ───────────────────────────────────────────────────
        st.markdown("#### 📍 Step 1 — Click the map to mark the pothole location")
        st.caption("👆 Tap anywhere on the map — the pin moves to that spot automatically")

        pin = st.session_state.report_pin
        m = folium.Map(location=[pin["lat"], pin["lng"]], zoom_start=14)
        folium.Marker(
            [pin["lat"], pin["lng"]],
            popup=f"Pothole here",
            icon=folium.Icon(color="red", icon="map-marker"),
        ).add_to(m)
        map_data = st_folium(m, height=380, use_container_width=True)

        if map_data and map_data.get("last_clicked"):
            c = map_data["last_clicked"]
            st.session_state.report_pin = {"lat": c["lat"], "lng": c["lng"]}
            # clear previous result when pin moves
            st.session_state.report_result = None
            st.session_state.voice_result  = None
            st.rerun()

        pin = st.session_state.report_pin
        area_name = reverse_geocode(pin["lat"], pin["lng"])
        st.markdown(
            f"📌 **{area_name}** &nbsp; `{pin['lat']:.5f}, {pin['lng']:.5f}`",
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Step 2 + 3: photo/details OR voice ───────────────────────────────
        col_photo, col_voice = st.columns([3, 2])

        with col_photo:
            st.markdown("#### 📸 Step 2a — Photo report")
            st.caption("Upload a photo and add details, then submit")

            uploaded = st.file_uploader(
                "Upload a photo of the pothole",
                type=["jpg", "jpeg", "png"],
                help="ML engine will estimate severity from this image",
            )
            if uploaded:
                st.image(uploaded, use_container_width=True)

            description = st.text_area(
                "Describe the pothole (optional)",
                placeholder="e.g. Deep pothole near the bus stop, water-logged after rain",
                max_chars=500,
                key="photo_desc",
            )
            severity_hint = st.select_slider(
                "How severe does it look?",
                options=["low", "medium", "high", "critical"],
                value="medium",
            )

            if st.button("🚀 Submit Photo Report", type="primary", use_container_width=True):
                pin = st.session_state.report_pin
                payload = {
                    "lat": pin["lat"], "lng": pin["lng"],
                    "description": description or f"Pothole at {area_name}",
                    "source": "photo",
                    "severity_hint": severity_hint,
                }
                if uploaded:
                    uploaded.seek(0)
                    payload["image_base64"] = img_to_b64(uploaded)
                with st.spinner("Submitting…"):
                    st.session_state.report_result = api_post("/reports/", payload)
                    st.session_state.voice_result  = None

        with col_voice:
            st.markdown("#### 🎙️ Step 2b — Voice report")
            st.markdown("""
<div class="story-box" style="border-left-color:#7c3aed">
<b>Can't type or fill a form?</b> Just tap the mic and speak — like a WhatsApp
voice note. The app transcribes and translates automatically.
</div>
""", unsafe_allow_html=True)

            st.markdown("**Speak naturally in any of these languages:**")
            st.markdown("""
| Language | What to say |
|---|---|
| 🇬🇧 **English** | *"There is a big pothole here, it is very dangerous and filled with water"* |
| 🇮🇳 **Hindi** | *"यहाँ बहुत बड़ा गड्ढा है, बहुत खतरनाक है, पानी भरा हुआ है"* |
| 🏴 **Kannada** | *"ಇಲ್ಲಿ ತುಂಬಾ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ, ತುಂಬಾ ಅಪಾಯಕಾರಿ, ನೀರು ತುಂಬಿದೆ"* |
            """)
            st.caption("Mention: location, size, depth, water, nearby landmarks — the more detail the better.")

            audio_value = st.audio_input(
                "🎙️ Hold to record — release to stop",
                key="voice_mic",
            )
            lang_hint = st.selectbox(
                "Language (or auto-detect)",
                ["Auto-detect", "English (en)", "Hindi (hi)", "Kannada (kn)"],
                key="voice_lang",
            )
            selected_lang = {
                "Auto-detect": None, "English (en)": "en",
                "Hindi (hi)": "hi", "Kannada (kn)": "kn",
            }[lang_hint]

            if st.button("🎙️ Transcribe & Submit", type="primary", use_container_width=True):
                if not audio_value:
                    st.warning("Please record a voice message first — tap the mic above.")
                else:
                    pin = st.session_state.report_pin
                    audio_b64 = base64.b64encode(audio_value.read()).decode("utf-8")
                    payload = {
                        "lat": pin["lat"], "lng": pin["lng"],
                        "audio_base64": audio_b64,
                        "language_hint": selected_lang,
                    }
                    with st.spinner("Transcribing audio…"):
                        st.session_state.voice_result  = api_post("/voice-report/", payload)
                        st.session_state.report_result = None

        # ── Result display (shared, below both columns) ───────────────────────
        st.divider()

        # Photo report result
        r = st.session_state.report_result
        if r:
            if "report_id" in r:
                rid = r["report_id"]
                live = poll_report(rid)
                status   = live.get("status", r["status"]) if live else r["status"]
                severity = live.get("severity") if live else None
                conf     = live.get("ml_confidence") if live else None
                area_pct = live.get("pixel_area_pct") if live else None
                s_icon   = {"pending": "⏳", "verified": "✅", "archived": "🗄️"}.get(status, "⏳")

                rc1, rc2 = st.columns(2)
                with rc1:
                    st.success(f"{s_icon} Report received — status: **{status}**")
                    st.markdown(f"""
<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px">
<b>📍 Location confirmed</b><br>
<span style="font-size:15px">{area_name}</span><br>
<span style="color:#64748b;font-size:12px">{pin['lat']:.5f}, {pin['lng']:.5f}</span>
</div>
""", unsafe_allow_html=True)
                    st.caption(f"Report ID: `{rid[:8]}…`")

                with rc2:
                    if status == "verified" and severity:
                        sc = SEVERITY_COLOUR.get(severity, "#64748b")
                        st.markdown(f"""
<div style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px">
<b>🤖 ML Analysis Complete</b><br>
<span style="display:inline-block;padding:4px 14px;border-radius:12px;
background:{sc};color:white;font-weight:700;margin:6px 0;font-size:15px">
{severity.upper()}</span><br>
Confidence: <b>{conf:.0%}</b> &nbsp;·&nbsp; Pothole covers <b>{area_pct:.1f}%</b> of image
</div>
""", unsafe_allow_html=True)
                    elif status == "archived":
                        st.warning("🔍 ML could not confirm a pothole. Archived for manual review.")
                    else:
                        st.info("🤖 ML engine is analysing the photo in the background…")
                        if st.button("🔄 Check ML Status", key="refresh_photo"):
                            st.rerun()
            else:
                st.error(f"Submission failed: {r.get('detail', 'Unknown error')}")

        # Voice report result
        v = st.session_state.voice_result
        if v:
            if "report_id" in v:
                vc1, vc2 = st.columns(2)
                with vc1:
                    st.success("✅ Voice report filed!")
                    st.markdown(f"""
<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px">
<b>📍 Location confirmed</b><br>
<span style="font-size:15px">{area_name}</span><br>
<span style="color:#64748b;font-size:12px">{pin['lat']:.5f}, {pin['lng']:.5f}</span>
</div>
""", unsafe_allow_html=True)
                with vc2:
                    st.markdown(f"""
<div style="background:#fafafa;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px">
<b>🎙️ Transcription</b><br>
<b>Language:</b> {v.get('language_name', '–')}<br>
<b>Original:</b> <em>{v.get('original_text', '–')}</em><br>
<b>English:</b> {v.get('english_text', '–')}<br>
<b>Confidence:</b> {v.get('transcription_confidence', 0):.0%}
</div>
""", unsafe_allow_html=True)
            elif "detail" in v:
                st.error(f"Voice error: {v['detail']}")

    # ── CITIZEN SUB-TAB 2: Route Planner ─────────────────────────────────────
    with citizen_tab2:

        st.markdown("### 🗺️ Route Quality Planner")
        st.markdown("""
<div class="story-box">
Before leaving home, Ravi checks which route has fewer potholes.
The app scores each alternative based on <b>verified potholes within 50m</b>
of the road and recommends the smoothest one — sorted best first.
</div>
""", unsafe_allow_html=True)

        PRESETS = {
            "Koramangala → ITPL Whitefield":  ("12.9199,77.6230", "12.9698,77.7499"),
            "Electronic City → MG Road":      ("12.9121,77.6446", "12.9716,77.5946"),
            "Hebbal → Marathahalli ORR":       ("13.0630,77.5930", "12.9558,77.6980"),
            "Bannerghatta → Jayanagar":        ("12.8999,77.5950", "12.9279,77.5748"),
            "Custom":                          (None, None),
        }

        preset = st.selectbox("🚦 Quick-pick a Bengaluru route", list(PRESETS.keys()))
        pre_o, pre_d = PRESETS[preset]

        rc1, rc2, rc3 = st.columns([2, 2, 1])
        origin      = rc1.text_input("Origin (lat,lng)",      value=pre_o or "12.9199,77.6230")
        destination = rc2.text_input("Destination (lat,lng)", value=pre_d or "12.9698,77.7499")
        alternatives = rc3.number_input("Alternatives", 1, 5, 3)

        if st.button("🔍 Score My Route", type="primary", use_container_width=True):
            with st.spinner("Scoring routes against pothole database…"):
                st.session_state.route_result = api_get("/route/score", {
                    "origin": origin,
                    "destination": destination,
                    "alternatives": int(alternatives),
                })

        result = st.session_state.route_result
        if result and "routes" in result:
            routes = result["routes"]
            st.markdown(f"#### Results — {len(routes)} route(s) scored, best first")

            m = folium.Map(location=BENGALURU_CENTER, zoom_start=12)
            for route in routes:
                ws = route.get("worst_segment")
                if ws:
                    folium.Marker(
                        [ws["lat"], ws["lng"]],
                        popup=f"⚠️ {ws['name']}<br>Score: {ws['score']:.0f}/100",
                        icon=folium.Icon(color="red", icon="warning-sign"),
                    ).add_to(m)
            st_folium(m, height=300, use_container_width=True)

            ROUTE_VIAS = [
                "Via Silk Board – Koramangala",
                "Via Bannerghatta Road – JP Nagar",
                "Via NH44 – Hebbal Flyover",
                "Via Outer Ring Road (ORR)",
                "Via Hosur Road – Electronic City",
            ]

            for i, route in enumerate(routes):
                label  = route["quality_label"]
                sc     = SCORE_COLOUR.get(label, "#64748b")
                via    = ROUTE_VIAS[i] if i < len(ROUTE_VIAS) else f"Route {i + 1}"
                badge  = f"🏆 Recommended — {via}" if i == 0 else f"Route {i + 1} — {via}"
                delta  = f"−{routes[0]['quality_score'] - route['quality_score']:.0f} pts" if i > 0 else None
                with st.expander(
                    f"{badge} · {label} ({route['quality_score']:.0f}/100)",
                    expanded=(i == 0),
                ):
                    cc1, cc2, cc3, cc4 = st.columns(4)
                    cc1.metric(
                        "Quality Score",
                        f"{route['quality_score']:.0f} / 100",
                        delta=delta,
                        delta_color="inverse",
                    )
                    cc2.metric("Distance",  f"{route['distance_km']} km")
                    cc3.metric("ETA",       f"{route['eta_minutes']:.0f} min")
                    cc4.metric("Hotspots",  route["hotspot_count"])
                    ws = route.get("worst_segment")
                    if route["hotspot_count"] > 0:
                        if ws:
                            st.warning(f"⚠️ Worst stretch: **{ws['name']}** — score {ws['score']:.0f}/100")
                        else:
                            st.warning(f"⚠️ {route['hotspot_count']} pothole hotspot(s) detected on this route.")
                    else:
                        st.success("✅ No significant pothole hotspots on this route.")
        elif result:
            st.error("Route scoring failed. Is the API running at localhost:8000?")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — BBMP OFFICER
# ══════════════════════════════════════════════════════════════════════════════
with tab_bbmp:

    st.markdown("""
<div class="story-box bbmp-story">
<b>🏛️ BBMP Road Infrastructure Officer</b> — Every Monday morning the officer
opens this dashboard to see which roads need urgent attention.
The heatmap instantly surfaces hotspots. A repair work order can be logged
in under a minute, and the road quality score updates automatically.
</div>
""", unsafe_allow_html=True)

    bbmp_tab1, bbmp_tab2 = st.tabs(["🔥 Hotspot Heatmap", "🔧 Log Maintenance"])

    # ── BBMP SUB-TAB 1: Heatmap ───────────────────────────────────────────────
    with bbmp_tab1:

        st.markdown("### 🔥 Pothole Hotspot Heatmap")
        st.markdown("""
Each coloured hexagon represents an H3 zone (~174m across).
**Darker red = worse road quality.** Click any hexagon to see the report count
and quality score. Use this to decide where to send the repair crew this week.
        """)

        hc1, hc2 = st.columns([1, 4])
        with hc1:
            resolution  = st.slider("Granularity", 7, 10, 9,
                                    help="Higher = smaller hexagons")
            bbox_input  = st.text_input("Bengaluru bbox",
                                        "12.85,77.48,13.10,77.75",
                                        help="south,west,north,east")
            st.button("🔄 Refresh", type="primary", use_container_width=True,
                      key="heatmap_refresh")

        with st.spinner("Loading heatmap…"):
            data = api_get("/heatmap", {"bbox": bbox_input, "resolution": resolution})

        if data and "features" in data:
            features = data["features"]
            total    = sum(f["properties"]["pothole_count"] for f in features)
            critical = [f for f in features if f["properties"]["quality_score"] < 35]

            with hc1:
                st.divider()
                st.metric("Verified reports",  total)
                st.metric("Critical zones",    len(critical), delta=f"score < 35")
                st.metric("Affected H3 zones", len(features))
                st.divider()
                st.markdown("**Legend**")
                for lbl, col in SCORE_COLOUR.items():
                    st.markdown(
                        f'<span style="display:inline-block;width:13px;height:13px;border-radius:3px;'
                        f'background:{col};margin-right:6px;vertical-align:middle"></span>{lbl}',
                        unsafe_allow_html=True,
                    )

            with hc2:
                hm = folium.Map(location=BENGALURU_CENTER, zoom_start=11)
                for feat in features:
                    props  = feat["properties"]
                    score  = props["quality_score"]
                    count  = props["pothole_count"]
                    h3cell = props["h3_cell"]
                    coords = feat["geometry"]["coordinates"][0]
                    if   score >= 90: colour = "#22c55e"
                    elif score >= 75: colour = "#84cc16"
                    elif score >= 55: colour = "#f59e0b"
                    elif score >= 35: colour = "#ef4444"
                    else:             colour = "#7f1d1d"
                    folium.Polygon(
                        locations=[[c[1], c[0]] for c in coords],
                        color=colour, fill=True, fill_color=colour,
                        fill_opacity=0.55, weight=1,
                        popup=folium.Popup(
                            f"<b>Score:</b> {score:.0f}/100<br>"
                            f"<b>Reports:</b> {count}<br>"
                            f"<small>{h3cell}</small>",
                            max_width=180,
                        ),
                    ).add_to(hm)
                st_folium(hm, height=520, use_container_width=True)
        else:
            st.info("No data yet. Run: `python scripts/seed_data.py --generate --clear`")

    # ── BBMP SUB-TAB 2: Maintenance Logging ──────────────────────────────────
    with bbmp_tab2:

        st.markdown("### 🔧 Log Road Maintenance Work")
        st.markdown("""
After identifying a hotspot on the heatmap, log the repair work order here.
Once status is set to **completed**, the road quality score recalculates —
citizens checking the Route Planner will see the improvement immediately.
        """)

        mc1, mc2 = st.columns([1, 1])

        with mc1:
            st.markdown("#### Work Order")
            segment_id = st.text_input(
                "Road Segment ID",
                value="35ffb6d8-1666-4fe8-8682-035e6cdbbc04",
                help="Get this from the heatmap popup or the route score response",
            )
            work_type   = st.selectbox("Work Type",
                                       ["repair", "patching", "resurfacing", "utility_dig"])
            work_status = st.selectbox("Status",
                                       ["planned", "in_progress", "completed"], index=1)
            notes = st.text_area(
                "Notes",
                value="Repair crew assigned. 3 critical potholes identified.",
                max_chars=500,
            )

            st.markdown("#### Affected Area")
            st.caption("Enter the SW and NE corners of the repair zone")
            bc1, bc2 = st.columns(2)
            sw_lat = bc1.number_input("SW Lat", value=12.950, format="%.3f")
            sw_lng = bc1.number_input("SW Lng", value=77.690, format="%.3f")
            ne_lat = bc2.number_input("NE Lat", value=12.960, format="%.3f")
            ne_lng = bc2.number_input("NE Lng", value=77.710, format="%.3f")

            token = st.text_input("🔑 Operator Token", value=BBMP_TOKEN,
                                  type="password",
                                  help="Must match SECRET_KEY in .env")

            if st.button("📋 Log Work Order", type="primary", use_container_width=True):
                payload = {
                    "road_segment_id": segment_id,
                    "work_type":       work_type,
                    "status":          work_status,
                    "notes":           notes,
                    "affected_bbox":   [[sw_lat, sw_lng], [ne_lat, ne_lng]],
                }
                with st.spinner("Logging…"):
                    st.session_state.maintenance_result = api_post(
                        "/maintenance/", payload, token=token
                    )

        with mc2:
            st.markdown("#### Affected Area Preview")
            mm = folium.Map(
                location=[(sw_lat + ne_lat) / 2, (sw_lng + ne_lng) / 2],
                zoom_start=14,
            )
            folium.Rectangle(
                bounds=[[sw_lat, sw_lng], [ne_lat, ne_lng]],
                color="#f59e0b", fill=True, fill_opacity=0.3,
                popup="Maintenance area",
            ).add_to(mm)
            st_folium(mm, height=320, use_container_width=True)

            res = st.session_state.maintenance_result
            if res:
                if "maintenance_id" in res:
                    st.success("✅ Work order logged!")
                    st.markdown(f"""
| | |
|---|---|
| **Work Order ID** | `{res['maintenance_id'][:8]}…` |
| **Status** | `{res['status']}` |
| **Type** | `{work_type}` |
                    """)
                    if work_status == "completed":
                        st.balloons()
                        st.success("🎉 Marked complete — road quality score will update on next route check.")
                elif "detail" in res:
                    st.error(f"Error: {res['detail']}")
