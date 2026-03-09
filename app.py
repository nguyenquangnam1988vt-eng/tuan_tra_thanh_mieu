import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pyrebase
import json
import time
from streamlit_autorefresh import st_autorefresh

# ==============================
# 1. CẤU HÌNH FIREBASE
# ==============================

firebase_config = dict(st.secrets["firebase"])
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()

# ==============================
# 2. AUTHENTICATION
# ==============================

with open("config.yaml") as file:
    config = yaml.load(file, Loader=SafeLoader)

config["cookie"]["key"] = st.secrets["auth"]["cookie_key"]

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

# ==============================
# 3. GIAO DIỆN ĐĂNG NHẬP
# ==============================

st.set_page_config(page_title="Tuần tra cơ động", layout="wide")

st.title("🚔 Hệ thống theo dõi và phối hợp tuần tra")

authenticator.login(location="main")

authentication_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

if authentication_status == False:
    st.error("Sai tên đăng nhập hoặc mật khẩu")
    st.stop()

elif authentication_status == None:
    st.warning("Vui lòng đăng nhập")
    st.stop()

authenticator.logout("Đăng xuất", "sidebar")
st.sidebar.success(f"Xin chào {name}")

# ==============================
# 4. STATE CHIA SẺ VỊ TRÍ
# ==============================

if "sharing" not in st.session_state:
    st.session_state.sharing = False

col1, col2 = st.columns([1, 5])

with col1:

    if not st.session_state.sharing:
        if st.button("📡 Bắt đầu chia sẻ vị trí"):
            st.session_state.sharing = True
            st.rerun()

    else:
        if st.button("🛑 Dừng chia sẻ"):
            db.child("officers").child(username).remove()
            st.session_state.sharing = False
            st.rerun()

# ==============================
# 5. JAVASCRIPT LẤY GPS (SỬA: thêm type="module")
# ==============================

if st.session_state.sharing:

    gps_script = f"""
    <script type="module">

    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ getDatabase, ref, set, onDisconnect }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

    const firebaseConfig = {json.dumps(firebase_config)};

    const app = initializeApp(firebaseConfig);
    const database = getDatabase(app);

    const username = "{username}";
    const officerName = "{name}";

    if (navigator.geolocation) {{

        navigator.geolocation.watchPosition(

            (position) => {{

                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                const accuracy = position.coords.accuracy;

                const officerRef = ref(database, 'officers/' + username);

                set(officerRef, {{
                    name: officerName,
                    lat: lat,
                    lng: lng,
                    accuracy: accuracy,
                    lastUpdate: Date.now()
                }});

                onDisconnect(officerRef).remove();
            }},

            (error) => {{
                console.error("GPS error:", error);
            }},

            {{
                enableHighAccuracy: true,
                maximumAge: 0,
                timeout: 5000
            }}
        );
    }}

    </script>

    <div>📡 Đang chia sẻ vị trí...</div>
    """

    st.components.v1.html(gps_script, height=40)

# ==============================
# 6. SIDEBAR CÔNG CỤ
# ==============================

st.sidebar.markdown("---")
st.sidebar.subheader("🚨 Công cụ phối hợp")

# ==============================
# GỬI BÁO ĐỘNG
# ==============================

if st.sidebar.button("🚨 Gửi báo động"):

    user_data = db.child("officers").child(username).get().val()

    if user_data:

        alert_data = {
            "from": username,
            "name": name,
            "lat": user_data["lat"],
            "lng": user_data["lng"],
            "timestamp": int(time.time() * 1000),
        }

        db.child("alerts").push(alert_data)

        st.sidebar.success("Đã gửi báo động")

    else:

        st.sidebar.error("Bạn chưa chia sẻ vị trí")

# ==============================
# ĐÁNH DẤU ĐIỂM
# ==============================

with st.sidebar.expander("📍 Đánh dấu điểm"):

    current = db.child("officers").child(username).get().val()

    lat = current["lat"] if current else 21.0285
    lng = current["lng"] if current else 105.8542

    lat_input = st.number_input("Vĩ độ", value=lat, format="%.6f")
    lng_input = st.number_input("Kinh độ", value=lng, format="%.6f")

    note = st.text_area("Ghi chú")

    if st.button("Thêm điểm"):

        if note.strip() == "":
            st.warning("Nhập ghi chú")

        else:

            marker_data = {
                "created_by": name,
                "lat": lat_input,
                "lng": lng_input,
                "note": note,
                "timestamp": int(time.time() * 1000),
            }

            db.child("markers").push(marker_data)

            st.sidebar.success("Đã thêm điểm")

# ==============================
# 7. CACHE DỮ LIỆU (giảm tải Firebase)
# ==============================

@st.cache_data(ttl=5)  # tự động refresh sau 5 giây
def load_officers():
    return db.child("officers").get().val() or {}

@st.cache_data(ttl=5)
def load_alerts():
    return db.child("alerts").get().val() or {}

@st.cache_data(ttl=5)
def load_markers():
    return db.child("markers").get().val() or {}

# ==============================
# 8. TỰ ĐỘNG REFRESH (để cập nhật danh sách online)
# ==============================
st_autorefresh(interval=5000, key="auto_refresh")  # refresh mỗi 5 giây

# ==============================
# 9. HTML BẢN ĐỒ REALTIME (sửa: tự động zoom vào cán bộ đầu tiên)
# ==============================

map_html = f"""
<!DOCTYPE html>
<html>

<head>

<meta charset="utf-8"/>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script type="module">

import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
import {{ getDatabase, ref, onChildAdded, onChildChanged, onChildRemoved }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

const firebaseConfig = {json.dumps(firebase_config)};

const app = initializeApp(firebaseConfig);
const db = getDatabase(app);

// Khởi tạo map với view mặc định Hà Nội
const map = L.map('map').setView([21.0285,105.8542],13);

L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png').addTo(map);

const markers = {{}};
const circles = {{}};

// Biến để kiểm tra lần đầu có dữ liệu
let firstOfficer = true;

const officersRef = ref(db,'officers');

onChildAdded(officersRef,(data)=>{{

    const officer = data.val();
    const id = data.key;

    const marker = L.marker([officer.lat,officer.lng]).addTo(map);
    marker.bindPopup(`<b>${{officer.name}}</b>`);

    const circle = L.circle([officer.lat,officer.lng],{{
        radius: officer.accuracy,
        color:'blue',
        fillOpacity:0.1
    }}).addTo(map);

    markers[id] = marker;
    circles[id] = circle;

    // Tự động zoom đến officer đầu tiên
    if (firstOfficer) {{
        map.setView([officer.lat, officer.lng], 15);
        firstOfficer = false;
    }}

}});

onChildChanged(officersRef,(data)=>{{

    const officer = data.val();
    const id = data.key;

    if(markers[id]){{
        markers[id].setLatLng([officer.lat,officer.lng]);
        circles[id].setLatLng([officer.lat,officer.lng]);
        circles[id].setRadius(officer.accuracy);
    }}

}});

onChildRemoved(officersRef,(data)=>{{

    const id = data.key;

    if(markers[id]){{
        map.removeLayer(markers[id]);
        map.removeLayer(circles[id]);
        delete markers[id];
        delete circles[id];
    }}

}});

</script>

<style>

#map{{
height:600px;
width:100%;
}}

</style>

</head>

<body>

<div id="map"></div>

</body>

</html>
"""

st.components.v1.html(map_html, height=620)

# ==============================
# 10. DANH SÁCH ONLINE
# ==============================

officers = load_officers()

st.sidebar.markdown("---")
st.sidebar.subheader("👥 Cán bộ trực tuyến")

if officers:

    for uid, info in officers.items():

        label = "(bạn)" if uid == username else ""

        st.sidebar.write(f"• {info['name']} {label}")

else:

    st.sidebar.write("Chưa có ai chia sẻ vị trí")

# ==============================
# 11. ALERT GẦN ĐÂY
# ==============================

alerts = load_alerts()

with st.sidebar.expander("📋 Báo động gần đây"):

    if alerts:

        sorted_alerts = sorted(
            alerts.items(),
            key=lambda x: x[1]["timestamp"],
            reverse=True
        )[:5]

        for _, alert in sorted_alerts:

            st.write(
                f"🚨 {alert['name']} - {time.ctime(alert['timestamp']/1000)}"
            )

    else:

        st.write("Chưa có báo động")
