import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pyrebase
import json
import time
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone, timedelta
import base64

# ==============================
# 0. HÀM ĐỌC FILE ÂM THANH BASE64 (CÓ XỬ LÝ LỖI)
# ==============================
def get_base64(file_path):
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        st.warning(f"Không tìm thấy file âm thanh {file_path}, âm thanh báo động sẽ không hoạt động.")
        return ""
    except Exception as e:
        st.warning(f"Lỗi đọc file âm thanh: {e}")
        return ""

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
            # Không xóa alerts vì alert có key tự động
            st.session_state.sharing = False
            st.rerun()

# ==============================
# 5. JAVASCRIPT LẤY GPS VÀ XỬ LÝ BÁO ĐỘNG (TIMEOUT 10s)
# ==============================
if st.session_state.sharing:
    gps_script = f"""
    <script type="module">
    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ 
        getDatabase, 
        ref, 
        set, 
        get, 
        push, 
        onDisconnect, 
        onChildAdded 
    }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

    const firebaseConfig = {json.dumps(firebase_config)};
    const app = initializeApp(firebaseConfig);
    const database = getDatabase(app);

    const username = "{username}";
    const officerName = "{name}";

    // ===== XỬ LÝ GPS =====
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
            (error) => {{
                console.error("GPS error:", error);
            }},
            {{
                enableHighAccuracy: true,
                maximumAge: 0,
                timeout: 10000  // Tăng lên 10s cho Android
            }}
        );
    }}

    // ===== XỬ LÝ BÁO ĐỘNG =====
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
# 6. SIDEBAR CÔNG CỤ
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
with st.sidebar.expander("📍 Đánh dấu điểm (nhấn giữ bản đồ)"):
    st.caption("Trên bản đồ: nhấn giữ 5 giây để thêm điểm")
    note = st.text_area("Ghi chú (nếu thêm bằng sidebar)")
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
# 7. HÀM LOAD DỮ LIỆU (TỐI ƯU)
# ==============================
def safe_get(node):
    try:
        result = db.child(node).get().val()
        return result if result else {}
    except Exception as e:
        st.error(f"Lỗi Firebase: {e}")
        return {}

# Chỉ load officers một lần và dùng cache
@st.cache_data(ttl=5)
def load_officers_cached():
    return safe_get("officers")

# ==============================
# 8. CHECKBOX HIỂN THỊ TRACK
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("🗺️ Lịch sử di chuyển")

if 'show_tracks' not in st.session_state:
    st.session_state.show_tracks = {}

# Lấy officers từ cache
officers = load_officers_cached()
if officers:
    for uid, info in officers.items():
        key = f"track_{uid}"
        checked = st.sidebar.checkbox(
            f"Track của {info['name']}",
            value=st.session_state.show_tracks.get(uid, False),
            key=key
        )
        st.session_state.show_tracks[uid] = checked

# ==============================
# 9. HÀM DỌN DẸP DỮ LIỆU CŨ
# ==============================
def cleanup_old_data():
    now = int(time.time() * 1000)
    max_age_map = {
        "messages": 24 * 60 * 60 * 1000,
        "alerts": 24 * 60 * 60 * 1000,
        "markers": 48 * 60 * 60 * 1000,
        "tracks": 7 * 24 * 60 * 60 * 1000,
    }
    for node, max_age in max_age_map.items():
        try:
            data = db.child(node).get().val()
            if not data:
                continue
            if isinstance(data, dict):
                for key, item in data.items():
                    # Xử lý tracks đặc biệt vì có cấu trúc phức tạp
                    if node == "tracks":
                        # Với tracks, ta xóa toàn bộ node user nếu tất cả points cũ
                        # Ở đây ta đơn giản hóa: xóa các điểm cũ trong points
                        if isinstance(item, dict) and "points" in item:
                            points = item.get("points", {})
                            if isinstance(points, dict):
                                for point_key, point in points.items():
                                    if now - point.get("timestamp", 0) > max_age:
                                        db.child(f"{node}/{key}/points/{point_key}").remove()
                    else:
                        # messages, alerts, markers
                        if now - item.get("timestamp", 0) > max_age:
                            db.child(f"{node}/{key}").remove()
        except Exception as e:
            st.warning(f"Lỗi cleanup {node}: {e}")

# Chạy dọn dẹp mỗi 6 tiếng (dùng session state để tránh chạy liên tục)
if "last_cleanup" not in st.session_state:
    st.session_state.last_cleanup = 0
if time.time() - st.session_state.last_cleanup > 6 * 3600:
    cleanup_old_data()
    st.session_state.last_cleanup = time.time()

# ==============================
# 10. CHUẨN BỊ DỮ LIỆU CHO MAP
# ==============================
alert_sound_base64 = get_base64("alert.mp3")
show_tracks_json = json.dumps(st.session_state.get("show_tracks", {}))

# ==============================
# 11. HTML BẢN ĐỒ REALTIME (HOÀN CHỈNH)
# ==============================
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
            background: transparent;
            border: none;
            box-shadow: none;
            font-weight: bold;
            color: #333;
            text-shadow: 1px 1px 2px white;
            font-size: 12px;
            margin-top: -15px !important;
            white-space: nowrap;
        }}
        /* Marker nhấp nháy cho báo động */
        .alert-marker {{
            width: 24px;
            height: 24px;
            background: red;
            border-radius: 50%;
            border: 3px solid white;
            box-shadow: 0 0 15px red;
            animation: blink 1s infinite;
        }}
        @keyframes blink {{
            0% {{ transform: scale(1); opacity: 1; }}
            50% {{ transform: scale(1.4); opacity: 0.6; }}
            100% {{ transform: scale(1); opacity: 1; }}
        }}
    </style>
    <script type="module">
    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ 
        getDatabase, 
        ref, 
        onChildAdded, 
        onChildChanged, 
        onChildRemoved, 
        onValue, 
        query, 
        limitToLast, 
        set,
        push, 
        onDisconnect 
    }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

    const firebaseConfig = {json.dumps(firebase_config)};
    const app = initializeApp(firebaseConfig);
    const db = getDatabase(app);

    // 👇 Các biến từ Python
    const myUsername = "{username}";
    const myName = "{name}";
    const showTracks = {show_tracks_json};

    console.log("👤 Username:", myUsername);

    // Khởi tạo map
    const map = L.map('map').setView([21.0285, 105.8542], 13);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    // Object lưu marker
    const officerMarkers = {{}};
    const alertMarkers = {{}};   // lưu marker báo động (để có thể xóa)
    const pointMarkers = {{}};   // điểm đánh dấu thường
    const trackPolylines = {{}}; // polyline track
    const trackListeners = {{}}; // tránh tạo nhiều listener track

    // Biến flag zoom vào bản thân
    let zoomedToMe = false;

    // Âm thanh báo động (base64)
    const alertSound = new Audio("data:audio/mp3;base64,{alert_sound_base64}");
    alertSound.preload = "auto";

    // Icon nhấp nháy cho alert
    const alertIcon = L.divIcon({{
        className: '',
        html: '<div class="alert-marker"></div>',
        iconSize: [24, 24],
        popupAnchor: [0, -12]
    }});

    // ===== FALLBACK GPS (zoom ngay nếu có) =====
    if (navigator.geolocation) {{
        navigator.geolocation.getCurrentPosition(
            (position) => {{
                const {{ latitude: lat, longitude: lng }} = position.coords;
                if (!zoomedToMe) {{
                    map.setView([lat, lng], 16);
                    zoomedToMe = true;
                }}
            }},
            (error) => console.warn("GPS fallback error:", error),
            {{ enableHighAccuracy: true, timeout: 10000 }}
        );
    }}

    // ===== 1. OFFICERS =====
    const officersRef = ref(db, 'officers');
    onChildAdded(officersRef, (data) => {{
        const officer = data.val();
        const id = data.key;
        const marker = L.circleMarker([officer.lat, officer.lng], {{
            radius: 8,
            color: '#0066cc',
            fillColor: '#0066cc',
            fillOpacity: 0.8,
            weight: 1
        }}).addTo(map);
        marker.bindTooltip(officer.name, {{
            permanent: true,
            direction: 'top',
            offset: [0, -8],
            className: 'officer-label'
        }});
        officerMarkers[id] = marker;

        // Zoom vào chính mình lần đầu
        if (id === myUsername && !zoomedToMe) {{
            map.setView([officer.lat, officer.lng], 16);
            zoomedToMe = true;
        }}
    }});

    onChildChanged(officersRef, (data) => {{
        const officer = data.val();
        const id = data.key;
        if (officerMarkers[id]) {{
            officerMarkers[id].setLatLng([officer.lat, officer.lng]);
            officerMarkers[id].setTooltipContent(officer.name);
            if (id === myUsername) {{
                // Di chuyển map theo (giữ nguyên zoom)
                map.setView([officer.lat, officer.lng], map.getZoom());
            }}
        }}
    }});

    onChildRemoved(officersRef, (data) => {{
        const id = data.key;
        if (officerMarkers[id]) {{
            map.removeLayer(officerMarkers[id]);
            delete officerMarkers[id];
        }}
    }});

    // ===== 2. ALERTS (nhấp nháy + zoom + âm thanh) =====
    const alertsRef = ref(db, 'alerts');
    const oneDayAgo = Date.now() - 24 * 60 * 60 * 1000; // 24h

    onChildAdded(alertsRef, (data) => {{
        const alert = data.val();
        const id = data.key;
        // Chỉ hiển thị alert trong vòng 24h
        if (alert.timestamp && alert.timestamp > oneDayAgo) {{
            const marker = L.marker([alert.lat, alert.lng], {{ icon: alertIcon }})
                .addTo(map)
                .bindPopup(`🚨 <b>Báo động từ ${{alert.name}}</b><br>${{new Date(alert.timestamp).toLocaleString()}}`);
            alertMarkers[id] = marker;

            // Nếu không phải do mình gửi, phát âm thanh và zoom
            if (alert.name !== myName) {{
                alertSound.currentTime = 0;
                alertSound.play().catch(e => console.log("Audio play error:", e));
                map.flyTo([alert.lat, alert.lng], 17, {{ animate: true, duration: 1.5 }});
            }}
        }}
    }});

    onChildRemoved(alertsRef, (data) => {{
        const id = data.key;
        if (alertMarkers[id]) {{
            map.removeLayer(alertMarkers[id]);
            delete alertMarkers[id];
        }}
    }});

    // ===== 3. MARKERS (điểm đánh dấu thường) – có TTL 48h =====
    const markersRootRef = ref(db, 'markers');
    onChildAdded(markersRootRef, (userSnapshot) => {{
        const userId = userSnapshot.key;
        const userMarkersRef = ref(db, `markers/${{userId}}`);
        onChildAdded(userMarkersRef, (markerSnapshot) => {{
            const point = markerSnapshot.val();
            const markerId = markerSnapshot.key;
            const fullId = `${{userId}}_${{markerId}}`;

            // Kiểm tra TTL (48h)
            const age = Date.now() - point.timestamp;
            const maxAge = 48 * 60 * 60 * 1000;
            if (age > maxAge) {{
                // Xóa marker cũ
                set(ref(db, `markers/${{userId}}/${{markerId}}`), null);
                return;
            }}

            const marker = L.circleMarker([point.lat, point.lng], {{
                radius: 6,
                color: '#ffaa00',
                fillColor: '#ffaa00',
                fillOpacity: 0.8,
                weight: 1
            }}).addTo(map);
            marker.bindPopup(`<b>${{point.created_by}}</b><br>${{point.note}}<br>${{new Date(point.timestamp).toLocaleString()}}`);
            pointMarkers[fullId] = marker;
        }});
        onChildRemoved(userMarkersRef, (markerSnapshot) => {{
            const markerId = markerSnapshot.key;
            const fullId = `${{userId}}_${{markerId}}`;
            if (pointMarkers[fullId]) {{
                map.removeLayer(pointMarkers[fullId]);
                delete pointMarkers[fullId];
            }}
        }});
    }});

    // ===== 4. THÊM ĐIỂM BẰNG NHẤN GIỮ (ĐÃ SỬA LATLNG) =====
    let pressTimer;
    map.on('contextmenu', (e) => {{
        e.originalEvent.preventDefault();
        const note = prompt("Nhập ghi chú cho điểm này:");
        if (note && note.trim()) {{
            const newPoint = {{
                created_by: "{name}",
                lat: e.latlng.lat,
                lng: e.latlng.lng,
                note: note,
                timestamp: Date.now()
            }};
            const userMarkerRef = ref(db, 'markers/{username}');
            push(userMarkerRef, newPoint);
        }}
    }});

    // Sửa touchstart: lấy tọa độ từ touches[0]
    map.on('touchstart', (e) => {{
        if (!e.originalEvent.touches || e.originalEvent.touches.length === 0) return;
        const touch = e.originalEvent.touches[0];
        const latlng = map.mouseEventToLatLng(touch);
        pressTimer = setTimeout(() => {{
            const note = prompt("Nhập ghi chú cho điểm này:");
            if (note && note.trim()) {{
                const newPoint = {{
                    created_by: "{name}",
                    lat: latlng.lat,
                    lng: latlng.lng,
                    note: note,
                    timestamp: Date.now()
                }};
                const userMarkerRef = ref(db, 'markers/{username}');
                push(userMarkerRef, newPoint);
            }}
        }}, 5000);
    }});
    map.on('touchend', () => clearTimeout(pressTimer));
    map.on('touchcancel', () => clearTimeout(pressTimer));

    // ===== 5. VẼ TRACK (tối ưu, tránh duplicate listener) =====
    function loadUserTracks(userId, userName, show) {{
        const tracksRef = ref(db, 'tracks/' + userId + '/points');
        const tracksQuery = query(tracksRef, limitToLast(200));

        if (!show) {{
            if (trackPolylines[userId]) {{
                map.removeLayer(trackPolylines[userId]);
                delete trackPolylines[userId];
            }}
            return;
        }}

        // Nếu đã có listener thì không tạo lại
        if (trackListeners[userId]) return;
        trackListeners[userId] = true;

        onValue(tracksQuery, (snapshot) => {{
            const points = snapshot.val();
            if (!points) return;
            const latlngs = Object.values(points)
                .filter(p => p.lat && p.lng)
                .map(p => [p.lat, p.lng]);

            if (trackPolylines[userId]) {{
                // Cập nhật polyline thay vì tạo mới (mượt hơn)
                trackPolylines[userId].setLatLngs(latlngs);
            }} else {{
                const hue = (userName.split('').reduce((a,b) => a + b.charCodeAt(0), 0) * 31) % 360;
                const color = `hsl(${{hue}}, 70%, 50%)`;
                const polyline = L.polyline(latlngs, {{
                    color: color,
                    weight: 3,
                    opacity: 0.6,
                    smoothFactor: 1.5
                }}).addTo(map);
                trackPolylines[userId] = polyline;
            }}
        }});
    }}

    // Theo dõi officers để load track khi cần
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
</body>
</html>
"""

# ==============================
# 12. TABS: BẢN ĐỒ VÀ CHAT
# ==============================
tab1, tab2 = st.tabs(["🗺️ Bản đồ", "💬 Chat nội bộ"])

with tab1:
    st.components.v1.html(map_html, height=620)

with tab2:
    st.subheader("💬 Chat nội bộ")
    
    # Tự động xóa tin nhắn cũ (24h)
    def cleanup_old_chat():
        now = int(time.time() * 1000)
        max_age = 24 * 60 * 60 * 1000
        msgs = db.child("messages").get().val()
        if msgs:
            for key, msg in msgs.items():
                if now - msg.get("timestamp", 0) > max_age:
                    db.child("messages").child(key).remove()
    
    cleanup_old_chat()
    
    st_autorefresh(interval=3000, key="chat_refresh")

    # Hiển thị tin nhắn
    messages = db.child("messages").order_by_child("timestamp").limit_to_last(50).get()
    if messages.val():
        sorted_msgs = sorted(messages.val().items(), key=lambda x: x[1]["timestamp"])
        for key, msg in sorted_msgs:
            is_me = (msg["from"] == username)
            align = "right" if is_me else "left"
            bg_color = "#dcf8c6" if is_me else "#f1f0f0"
            
            # Chuyển timestamp sang giờ Việt Nam (UTC+7)
            vn_time = datetime.fromtimestamp(
                msg["timestamp"] / 1000,
                tz=timezone(timedelta(hours=7))
            ).strftime("%H:%M")
            
            st.markdown(
                f"<div style='display: flex; justify-content: {align}; margin:5px;'>"
                f"<div style='background-color: {bg_color}; padding:8px 12px; border-radius:10px; max-width:70%;'>"
                f"<b>{msg['name']}</b> {vn_time}<br>{msg['message']}"
                f"</div></div>",
                unsafe_allow_html=True
            )
    else:
        st.info("Chưa có tin nhắn nào.")
    
    # Tự động cuộn xuống cuối
    st.markdown(
        """
        <script>
        window.scrollTo(0, document.body.scrollHeight);
        </script>
        """,
        unsafe_allow_html=True
    )

    # Form gửi tin nhắn
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        with col1:
            message = st.text_input("Tin nhắn", placeholder="Nhập tin nhắn...", label_visibility="collapsed")
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

# ==============================
# 13. DANH SÁCH CÁN BỘ ONLINE (dùng cache)
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Cán bộ trực tuyến")

# Dùng lại officers từ cache
if officers:
    for uid, info in officers.items():
        label = "(bạn)" if uid == username else ""
        st.sidebar.write(f"• {info['name']} {label}")
else:
    st.sidebar.write("Chưa có ai chia sẻ vị trí")

# ==============================
# 14. ĐIỂM ĐÁNH DẤU GẦN ĐÂY
# ==============================
all_markers = safe_get("markers")
markers_list = []
if all_markers:
    for uid, user_markers in all_markers.items():
        if isinstance(user_markers, dict):
            for key, marker in user_markers.items():
                if isinstance(marker, dict) and marker.get("timestamp"):
                    markers_list.append(marker)
with st.sidebar.expander("📌 Điểm đánh dấu gần đây"):
    if markers_list:
        sorted_markers = sorted(markers_list, key=lambda x: x["timestamp"], reverse=True)[:5]
        for m in sorted_markers:
            st.write(f"📍 {m.get('created_by', 'Unknown')}: {m.get('note', '')[:30]}...")
    else:
        st.write("Chưa có điểm đánh dấu")
