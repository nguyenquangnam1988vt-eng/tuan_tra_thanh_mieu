import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pyrebase
import json
import time
import os

# ---------- 1. Cấu hình Firebase từ secrets ----------
firebase_config = dict(st.secrets["firebase"])
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()

# ---------- 2. Cấu hình xác thực ----------
with open('config.yaml') as file:
    config = yaml.load(file, Loader=SafeLoader)
config['cookie']['key'] = st.secrets["auth"]["cookie_key"]

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

# ---------- 3. Giao diện đăng nhập ----------
st.set_page_config(page_title="Tuần tra cơ động", layout="wide")
st.title("🚔 Hệ thống theo dõi và phối hợp tuần tra")

authenticator.login(location='main')
authentication_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

if authentication_status == False:
    st.error("Sai tên đăng nhập hoặc mật khẩu")
    st.stop()
elif authentication_status == None:
    st.warning("Vui lòng nhập thông tin đăng nhập")
    st.stop()

# ---------- 4. Sau đăng nhập ----------
authenticator.logout('Đăng xuất', 'sidebar')
st.sidebar.success(f"Xin chào {name}")

if 'sharing' not in st.session_state:
    st.session_state.sharing = False

# ---------- 5. Nút bắt đầu / dừng chia sẻ vị trí ----------
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

# ---------- 6. JavaScript lấy GPS và gửi lên Firebase ----------
if st.session_state.sharing:
    js_code = f"""
    <script>
    const firebaseConfig = {json.dumps(firebase_config)};
    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ getDatabase, ref, set, onDisconnect }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";
    
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
                console.error("Lỗi GPS:", error);
            }},
            {{ enableHighAccuracy: true, maximumAge: 0, timeout: 5000 }}
        );
    }}
    </script>
    <div id="gps-status">📡 Đang chia sẻ vị trí...</div>
    """
    st.components.v1.html(js_code, height=50)

# ---------- 7. Công cụ phối hợp (Sidebar) ----------
st.sidebar.markdown("---")
st.sidebar.subheader("🚨 Công cụ phối hợp")

# Gửi báo động
if st.sidebar.button("🚨 Gửi báo động (vị trí hiện tại)"):
    user_data = db.child("officers").child(username).get().val()
    if user_data:
        alert_data = {
            'from': username,
            'name': name,
            'lat': user_data['lat'],
            'lng': user_data['lng'],
            'timestamp': int(time.time()*1000)
        }
        db.child("alerts").push(alert_data)
        st.sidebar.success("Đã gửi báo động!")
    else:
        st.sidebar.error("Bạn chưa chia sẻ vị trí!")

# Đánh dấu vùng
with st.sidebar.expander("📍 Đánh dấu vùng cần chú ý"):
    current_pos = db.child("officers").child(username).get().val()
    default_lat = current_pos['lat'] if current_pos else 21.0285
    default_lng = current_pos['lng'] if current_pos else 105.8542
    lat_input = st.number_input("Vĩ độ", value=default_lat, format="%.6f")
    lng_input = st.number_input("Kinh độ", value=default_lng, format="%.6f")
    note = st.text_area("Ghi chú", placeholder="Mô tả điểm cần chú ý...")
    if st.button("Thêm điểm"):
        if note.strip() == "":
            st.warning("Vui lòng nhập ghi chú")
        else:
            marker_data = {
                'created_by': name,
                'lat': lat_input,
                'lng': lng_input,
                'note': note,
                'timestamp': int(time.time()*1000)
            }
            db.child("markers").push(marker_data)
            st.sidebar.success("Đã thêm điểm đánh dấu!")

# ---------- 8. HIỂN THỊ BẢN ĐỒ REAL-TIME (component HTML) ----------
# Tạo HTML cho bản đồ với Leaflet và Firebase listener
map_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Bản đồ tuần tra</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <!-- Firebase SDK (phiên bản 9+) -->
    <script type="module">
        import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
        import {{ getDatabase, ref, onValue, onChildAdded, onChildChanged, onChildRemoved }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

        // Cấu hình Firebase (lấy từ Python)
        const firebaseConfig = {json.dumps(firebase_config)};
        const app = initializeApp(firebaseConfig);
        const database = getDatabase(app);

        // Khởi tạo bản đồ
        const map = L.map('map').setView([21.0285, 105.8542], 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        }}).addTo(map);

        // Object lưu các marker
        const markers = {{}};  // key: officer id, alert id, marker id -> marker object

        // ---- 1. Theo dõi officers (cán bộ) ----
        const officersRef = ref(database, 'officers');
        onChildAdded(officersRef, (data) => {{
            const officer = data.val();
            const id = data.key;
            const marker = L.marker([officer.lat, officer.lng], {{
                title: officer.name,
                icon: L.icon({{
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-blue.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                }})
            }}).addTo(map);
            marker.bindPopup(`<b>${{officer.name}}</b><br>Độ chính xác: ${{officer.accuracy}}m`);
            markers[id] = marker;
        }});

        onChildChanged(officersRef, (data) => {{
            const officer = data.val();
            const id = data.key;
            if (markers[id]) {{
                markers[id].setLatLng([officer.lat, officer.lng]);
                markers[id].setPopupContent(`<b>${{officer.name}}</b><br>Độ chính xác: ${{officer.accuracy}}m`);
            }}
        }});

        onChildRemoved(officersRef, (data) => {{
            const id = data.key;
            if (markers[id]) {{
                map.removeLayer(markers[id]);
                delete markers[id];
            }}
        }});

        // ---- 2. Theo dõi alerts (báo động) ----
        const alertsRef = ref(database, 'alerts');
        onChildAdded(alertsRef, (data) => {{
            const alert = data.val();
            const id = data.key;
            const marker = L.marker([alert.lat, alert.lng], {{
                icon: L.icon({{
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                }})
            }}).addTo(map);
            marker.bindPopup(`🚨 <b>Báo động từ ${{alert.name}}</b><br>${{new Date(alert.timestamp).toLocaleString()}}`);
            markers[`alert_${{id}}`] = marker;
        }});

        // ---- 3. Theo dõi markers (điểm đánh dấu) ----
        const markersRef = ref(database, 'markers');
        onChildAdded(markersRef, (data) => {{
            const markerData = data.val();
            const id = data.key;
            const marker = L.marker([markerData.lat, markerData.lng], {{
                icon: L.icon({{
                    iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-orange.png',
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                }})
            }}).addTo(map);
            marker.bindPopup(`📍 <b>Điểm đánh dấu</b><br>Người tạo: ${{markerData.created_by}}<br>Ghi chú: ${{markerData.note}}<br>${{new Date(markerData.timestamp).toLocaleString()}}`);
            markers[`marker_${{id}}`] = marker;
        }});
    </script>
    <style>
        #map {{
            height: 600px;
            width: 100%;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
</body>
</html>
"""

# Hiển thị bản đồ
st.components.v1.html(map_html, height=620)

# ---------- 9. Hiển thị danh sách online (vẫn dùng Streamlit) ----------
def load_officers():
    return db.child("officers").get().val() or {}

officers = load_officers()
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Cán bộ trực tuyến")
if officers:
    for uid, info in officers.items():
        st.sidebar.write(f"• {info['name']} {'(bạn)' if uid==username else ''}")
else:
    st.sidebar.write("Chưa có ai chia sẻ vị trí")

# ---------- 10. Xem gần đây ----------
# (có thể giữ nguyên như cũ, nhưng không cần refresh nữa)
alerts = db.child("alerts").get().val() or {}
markers = db.child("markers").get().val() or {}

with st.sidebar.expander("📋 Báo động gần đây"):
    if alerts:
        sorted_alerts = sorted(alerts.items(), key=lambda x: x[1]['timestamp'], reverse=True)[:5]
        for key, alert in sorted_alerts:
            st.write(f"🚨 {alert['name']} - {time.ctime(alert['timestamp']/1000)}")
    else:
        st.write("Chưa có báo động nào.")

with st.sidebar.expander("📌 Điểm đánh dấu gần đây"):
    if markers:
        sorted_markers = sorted(markers.items(), key=lambda x: x[1]['timestamp'], reverse=True)[:5]
        for key, marker in sorted_markers:
            st.write(f"📍 {marker['created_by']}: {marker['note'][:30]}...")
    else:
        st.write("Chưa có điểm đánh dấu nào.")
