import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pyrebase
import json
import time
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

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
# 4. KHỞI TẠO SESSION STATE
# ==============================
if "sharing" not in st.session_state:
    st.session_state.sharing = False
if "show_tracks" not in st.session_state:
    st.session_state.show_tracks = {}

# ==============================
# 5. NÚT BẮT ĐẦU / DỪNG CHIA SẺ VỊ TRÍ
# ==============================
col1, col2 = st.columns([1, 5])
with col1:
    if not st.session_state.sharing:
        if st.button("📡 Bắt đầu chia sẻ vị trí"):
            st.session_state.sharing = True
            st.rerun()
    else:
        if st.button("🛑 Dừng chia sẻ"):
            db.child("officers").child(username).remove()
            db.child("alerts").child(username).remove()
            st.session_state.sharing = False
            st.rerun()

# ==============================
# 6. JAVASCRIPT LẤY GPS VÀ XỬ LÝ BÁO ĐỘNG + TRACK
# ==============================
if st.session_state.sharing:
    gps_script = f"""
    <script type="module">
    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ getDatabase, ref, set, onDisconnect, onChildAdded, push, get }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

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

                // Gửi vị trí hiện tại
                const officerRef = ref(database, 'officers/' + username);
                set(officerRef, {{
                    name: officerName,
                    lat: lat,
                    lng: lng,
                    accuracy: accuracy,
                    lastUpdate: Date.now()
                }});
                onDisconnect(officerRef).remove();

                // Lưu track (chỉ khi di chuyển >20m hoặc quá 60 giây)
                const lastTrackRef = ref(database, 'tracks/' + username + '/last');
                get(lastTrackRef).then((snapshot) => {{
                    const last = snapshot.val();
                    const now = Date.now();
                    if (!last || 
                        Math.abs(lat - last.lat) > 0.00018 ||
                        Math.abs(lng - last.lng) > 0.00018 ||
                        now - last.timestamp > 60000) {{
                        const trackPoint = {{ lat, lng, timestamp: now }};
                        push(ref(database, 'tracks/' + username + '/points'), trackPoint);
                        set(lastTrackRef, {{lat, lng, timestamp: now}});
                    }}
                }});
            }},
            (error) => console.error("GPS error:", error),
            {{ enableHighAccuracy: true, maximumAge: 0, timeout: 5000 }}
        );
    }}

    // Xử lý yêu cầu báo động
    const alertRequestsRef = ref(database, 'alert_requests');
    onChildAdded(alertRequestsRef, (data) => {{
        const req = data.val();
        if (req.username === username) {{
            const alertRef = ref(database, 'alerts/' + username);
            set(alertRef, {{
                name: req.name,
                lat: req.lat,
                lng: req.lng,
                timestamp: req.timestamp
            }});
            set(ref(database, 'alert_requests/' + data.key), null);
            onDisconnect(alertRef).remove();
        }}
    }});
    </script>
    <div style="text-align: center; color: green;">📡 Đang chia sẻ vị trí...</div>
    """
    st.components.v1.html(gps_script, height=60)

# ==============================
# 7. SIDEBAR: CÔNG CỤ
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("🚨 Công cụ phối hợp")

# Gửi báo động
if st.sidebar.button("🚨 Gửi báo động"):
    user_data = db.child("officers").child(username).get().val()
    if user_data:
        request_data = {
            "username": username,
            "name": name,
            "lat": user_data["lat"],
            "lng": user_data["lng"],
            "timestamp": int(time.time() * 1000)
        }
        db.child("alert_requests").push(request_data)
        st.sidebar.success("Đã gửi yêu cầu báo động")
    else:
        st.sidebar.error("Bạn chưa chia sẻ vị trí")

# Đánh dấu điểm
with st.sidebar.expander("📍 Đánh dấu điểm"):
    note = st.text_area("Ghi chú")
    if st.button("Thêm điểm tại vị trí hiện tại"):
        current = db.child("officers").child(username).get().val()
        if current and note.strip():
            marker_data = {
                "created_by": name,
                "lat": current["lat"],
                "lng": current["lng"],
                "note": note,
                "timestamp": int(time.time() * 1000),
            }
            db.child("markers").child(username).push(marker_data)
            st.sidebar.success("Đã thêm điểm")
        else:
            st.sidebar.warning("Chưa chia sẻ vị trí hoặc ghi chú trống")

# ==============================
# 8. SIDEBAR: DANH SÁCH CÁN BỘ VÀ CHECKBOX TRACK
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Cán bộ trực tuyến")
officers = db.child("officers").get().val() or {}
if officers:
    for uid, info in officers.items():
        label = f"{info['name']} {'(bạn)' if uid==username else ''}"
        col_a, col_b = st.sidebar.columns([3,1])
        with col_a:
            st.write(f"• {label}")
        with col_b:
            key = f"track_{uid}"
            checked = st.checkbox("Track", value=st.session_state.show_tracks.get(uid, False), key=key, label_visibility="collapsed")
            st.session_state.show_tracks[uid] = checked
else:
    st.sidebar.write("Chưa có ai chia sẻ vị trí")

# ==============================
# 9. TABS: BẢN ĐỒ VÀ CHAT
# ==============================
tab1, tab2 = st.tabs(["🗺️ Bản đồ", "💬 Chat nội bộ"])

# ----- TAB 1: BẢN ĐỒ -----
with tab1:
    show_tracks_json = json.dumps(st.session_state.show_tracks)
    map_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            #map {{ height: 600px; width: 100%; }}
            .leaflet-tooltip {{
                background: transparent; border: none; box-shadow: none;
                font-weight: bold; color: #333; text-shadow: 1px 1px 2px white;
                font-size: 12px; margin-top: -15px !important; white-space: nowrap;
            }}
        </style>
        <script type="module">
        import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
        import {{ getDatabase, ref, onChildAdded, onChildChanged, onChildRemoved, onValue, query, limitToLast }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

        const firebaseConfig = {json.dumps(firebase_config)};
        const app = initializeApp(firebaseConfig);
        const db = getDatabase(app);
        const showTracks = {show_tracks_json};

        const map = L.map('map').setView([21.0285, 105.8542], 13);
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '&copy; OpenStreetMap'
        }}).addTo(map);

        // Objects
        const officerMarkers = {{}};
        const alertMarkers = {{}};
        const pointMarkers = {{}};
        const trackPolylines = {{}};

        // ----- OFFICERS -----
        const officersRef = ref(db, 'officers');
        onChildAdded(officersRef, (data) => {{
            const officer = data.val(); const id = data.key;
            const marker = L.circleMarker([officer.lat, officer.lng], {{
                radius: 8, color: '#0066cc', fillColor: '#0066cc',
                fillOpacity: 0.8, weight: 1
            }}).addTo(map);
            marker.bindTooltip(officer.name, {{ permanent: true, direction: 'top', offset: [0, -8] }});
            officerMarkers[id] = marker;
        }});
        onChildChanged(officersRef, (data) => {{
            const officer = data.val(); const id = data.key;
            if (officerMarkers[id]) {{
                officerMarkers[id].setLatLng([officer.lat, officer.lng]);
                officerMarkers[id].setTooltipContent(officer.name);
            }}
        }});
        onChildRemoved(officersRef, (data) => {{
            const id = data.key;
            if (officerMarkers[id]) {{
                map.removeLayer(officerMarkers[id]); delete officerMarkers[id];
            }}
        }});

        // ----- ALERTS (có phát âm thanh) -----
        const alertsRef = ref(db, 'alerts');
        onChildAdded(alertsRef, (data) => {{
            const alert = data.val(); const id = data.key;
            const marker = L.circleMarker([alert.lat, alert.lng], {{
                radius: 8, color: '#ff4444', fillColor: '#ff4444',
                fillOpacity: 0.8, weight: 1
            }}).addTo(map);
            marker.bindTooltip(`🚨 ${{alert.name}}`, {{ permanent: true, direction: 'top', offset: [0, -8] }});
            alertMarkers[id] = marker;

            // Phát âm thanh nếu không phải do mình gửi
            if (alert.name !== "{name}") {{
                const audio = document.getElementById('alert-sound');
                audio.play().catch(e => console.log("Audio error:", e));
            }}
        }});
        onChildRemoved(alertsRef, (data) => {{
            const id = data.key;
            if (alertMarkers[id]) {{
                map.removeLayer(alertMarkers[id]); delete alertMarkers[id];
            }}
        }});

        // ----- MARKERS (điểm đánh dấu) -----
        const markersRootRef = ref(db, 'markers');
        onChildAdded(markersRootRef, (userSnapshot) => {{
            const userId = userSnapshot.key;
            const userMarkersRef = ref(db, `markers/${{userId}}`);
            onChildAdded(userMarkersRef, (markerSnapshot) => {{
                const point = markerSnapshot.val();
                const markerId = markerSnapshot.key;
                const fullId = `${{userId}}_${{markerId}}`;
                const marker = L.circleMarker([point.lat, point.lng], {{
                    radius: 6, color: '#ffaa00', fillColor: '#ffaa00',
                    fillOpacity: 0.8, weight: 1
                }}).addTo(map);
                marker.bindPopup(`<b>${{point.created_by}}</b><br>${{point.note}}<br>${{new Date(point.timestamp).toLocaleString()}}`);
                pointMarkers[fullId] = marker;
            }});
            onChildRemoved(userMarkersRef, (markerSnapshot) => {{
                const markerId = markerSnapshot.key;
                const fullId = `${{userId}}_${{markerId}}`;
                if (pointMarkers[fullId]) {{
                    map.removeLayer(pointMarkers[fullId]); delete pointMarkers[fullId];
                }}
            }});
        }});

        // ----- TRACKS -----
        function loadUserTracks(userId, userName, show) {{
            const tracksRef = ref(db, 'tracks/' + userId + '/points');
            const tracksQuery = query(tracksRef, limitToLast(200));
            if (!show) {{
                if (trackPolylines[userId]) {{
                    map.removeLayer(trackPolylines[userId]); delete trackPolylines[userId];
                }}
                return;
            }}
            onValue(tracksQuery, (snapshot) => {{
                const points = snapshot.val();
                if (!points) return;
                const latlngs = Object.values(points).filter(p => p.lat && p.lng).map(p => [p.lat, p.lng]);
                if (trackPolylines[userId]) map.removeLayer(trackPolylines[userId]);
                const hue = (userName.split('').reduce((a,b) => a + b.charCodeAt(0), 0) * 31) % 360;
                const color = `hsl(${{hue}}, 70%, 50%)`;
                const polyline = L.polyline(latlngs, {{ color: color, weight: 3, opacity: 0.6 }}).addTo(map);
                trackPolylines[userId] = polyline;
            }});
        }}

        onValue(officersRef, (snapshot) => {{
            const officers = snapshot.val() || {{}};
            Object.keys(officers).forEach(uid => {{
                loadUserTracks(uid, officers[uid].name, showTracks[uid] || false);
            }});
        }});
        </script>
    </head>
    <body>
        <div id="map"></div>
        <audio id="alert-sound" src="alert.mp3" preload="auto"></audio>
    </body>
    </html>
    """
    st.components.v1.html(map_html, height=620)

# ----- TAB 2: CHAT NỘI BỘ -----
with tab2:
    st.subheader("💬 Chat nội bộ")
    # Tự động refresh chat mỗi 3 giây
    st_autorefresh(interval=3000, key="chat_refresh")

    # Hiển thị tin nhắn
    messages = db.child("messages").order_by_child("timestamp").limit_to_last(50).get().val()
    if messages:
        sorted_msgs = sorted(messages.items(), key=lambda x: x[1]["timestamp"])
        for key, msg in sorted_msgs:
            is_me = (msg["from"] == username)
            align = "right" if is_me else "left"
            bg_color = "#dcf8c6" if is_me else "#f1f0f0"
            st.markdown(
                f"<div style='display: flex; justify-content: {align}; margin:5px;'>"
                f"<div style='background-color: {bg_color}; padding:8px 12px; border-radius:10px; max-width:70%;'>"
                f"<b>{msg['name']}</b> {datetime.fromtimestamp(msg['timestamp']/1000).strftime('%H:%M')}<br>{msg['message']}"
                f"</div></div>",
                unsafe_allow_html=True
            )
    else:
        st.info("Chưa có tin nhắn nào.")

    # Form gửi tin nhắn
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        with col1:
            message = st.text_input("", placeholder="Nhập tin nhắn...", label_visibility="collapsed")
        with col2:
            sent = st.form_submit_button("Gửi")
        if sent and message.strip():
            chat_data = {
                "from": username,
                "name": name,
                "message": message,
                "timestamp": int(time.time() * 1000)
            }
            db.child("messages").push(chat_data)
            st.rerun()
