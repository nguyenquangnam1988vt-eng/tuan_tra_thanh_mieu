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
            db.child("alerts").child(username).remove()
            st.session_state.sharing = False
            st.rerun()

# ==============================
# 5. JAVASCRIPT LẤY GPS VÀ XỬ LÝ BÁO ĐỘNG
# ==============================

if st.session_state.sharing:

    gps_script = f"""
    <script type="module">

    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ getDatabase, ref, set, onDisconnect, onChildAdded }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

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

# ==============================
# GỬI BÁO ĐỘNG
# ==============================

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

# ==============================
# ĐÁNH DẤU ĐIỂM
# ==============================

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
            db.child("markers").push(marker_data)
            st.sidebar.success("Đã thêm điểm")
        else:
            st.sidebar.warning("Chưa chia sẻ vị trí hoặc ghi chú trống")

# ==============================
# 7. HÀM LOAD DỮ LIỆU
# ==============================

def safe_get(node):
    try:
        result = db.child(node).get().val()
        return result if result else {}
    except Exception as e:
        st.error(f"Lỗi Firebase: {e}")
        return {}

@st.cache_data(ttl=5)
def load_officers():
    return safe_get("officers")

@st.cache_data(ttl=5)
def load_markers():
    return safe_get("markers")

# ==============================
# 8. TỰ ĐỘNG REFRESH (cho danh sách online)
# ==============================
st_autorefresh(interval=5000, key="auto_refresh")

# ==============================
# 9. HTML BẢN ĐỒ REALTIME (đã sửa lỗi f-string)
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
        }}
    </style>
    <script type="module">
    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ getDatabase, ref, onChildAdded, onChildChanged, onChildRemoved, set, push, serverTimestamp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

    const firebaseConfig = {json.dumps(firebase_config)};
    const app = initializeApp(firebaseConfig);
    const db = getDatabase(app);

    // Khởi tạo bản đồ
    const map = L.map('map').setView([21.0285, 105.8542], 13);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    // Objects lưu các marker
    const officerMarkers = {{}};      // chấm xanh + tên
    const alertMarkers = {{}};        // chấm đỏ
    const pointMarkers = {{}};        // chấm vàng

    // ===== 1. XỬ LÝ OFFICERS (CÁN BỘ) =====
    const officersRef = ref(db, 'officers');
    
    onChildAdded(officersRef, (data) => {{
        const officer = data.val();
        const id = data.key;
        
        // Tạo chấm tròn xanh nhỏ (circleMarker)
        const marker = L.circleMarker([officer.lat, officer.lng], {{
            radius: 8,
            color: '#3388ff',
            fillColor: '#3388ff',
            fillOpacity: 0.8,
            weight: 1
        }}).addTo(map);
        
        // Tooltip hiển thị tên phía trên
        marker.bindTooltip(officer.name, {{
            permanent: true,
            direction: 'top',
            offset: [0, -15],
            className: 'officer-label'
        }});
        
        officerMarkers[id] = marker;
    }});
    
    onChildChanged(officersRef, (data) => {{
        const officer = data.val();
        const id = data.key;
        if (officerMarkers[id]) {{
            officerMarkers[id].setLatLng([officer.lat, officer.lng]);
            officerMarkers[id].setTooltipContent(officer.name);
        }}
    }});
    
    onChildRemoved(officersRef, (data) => {{
        const id = data.key;
        if (officerMarkers[id]) {{
            map.removeLayer(officerMarkers[id]);
            delete officerMarkers[id];
        }}
    }});

    // ===== 2. XỬ LÝ ALERTS (BÁO ĐỘNG) =====
    const alertsRef = ref(db, 'alerts');
    
    onChildAdded(alertsRef, (data) => {{
        const alert = data.val();
        const id = data.key;
        
        // Chấm đỏ nhỏ
        const marker = L.circleMarker([alert.lat, alert.lng], {{
            radius: 8,
            color: '#ff4444',
            fillColor: '#ff4444',
            fillOpacity: 0.8,
            weight: 1
        }}).addTo(map);
        
        marker.bindTooltip(`🚨 ${{alert.name}}`, {{
            permanent: true,
            direction: 'top',
            offset: [0, -15]
        }});
        
        alertMarkers[id] = marker;
    }});
    
    onChildRemoved(alertsRef, (data) => {{
        const id = data.key;
        if (alertMarkers[id]) {{
            map.removeLayer(alertMarkers[id]);
            delete alertMarkers[id];
        }}
    }});

    // ===== 3. XỬ LÝ MARKERS (ĐIỂM ĐÁNH DẤU) =====
    const markersRef = ref(db, 'markers');
    
    onChildAdded(markersRef, (data) => {{
        const point = data.val();
        const id = data.key;
        
        // Chấm vàng nhỏ
        const marker = L.circleMarker([point.lat, point.lng], {{
            radius: 6,
            color: '#ffaa00',
            fillColor: '#ffaa00',
            fillOpacity: 0.8,
            weight: 1
        }}).addTo(map);
        
        marker.bindPopup(`<b>${{point.created_by}}</b><br>${{point.note}}<br>${{new Date(point.timestamp).toLocaleString()}}`);
        
        pointMarkers[id] = marker;
    }});
    
    onChildRemoved(markersRef, (data) => {{
        const id = data.key;
        if (pointMarkers[id]) {{
            map.removeLayer(pointMarkers[id]);
            delete pointMarkers[id];
        }}
    }});

    // ===== 4. THÊM ĐIỂM BẰNG CÁCH NHẤN GIỮ BẢN ĐỒ =====
    let pressTimer;
    
    // Desktop: click chuột phải
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
            push(ref(db, 'markers'), newPoint);
        }}
    }});
    
    // Mobile: nhấn giữ 5 giây
    map.on('touchstart', (e) => {{
        pressTimer = setTimeout(() => {{
            const note = prompt("Nhập ghi chú cho điểm này:");
            if (note && note.trim()) {{
                const newPoint = {{
                    created_by: "{name}",
                    lat: e.latlng.lat,
                    lng: e.latlng.lng,
                    note: note,
                    timestamp: Date.now()
                }};
                push(ref(db, 'markers'), newPoint);
            }}
        }}, 5000); // 5 giây
    }});
    
    map.on('touchend', (e) => {{
        clearTimeout(pressTimer);
    }});
    
    map.on('touchcancel', (e) => {{
        clearTimeout(pressTimer);
    }});

    // Tự động zoom đến cán bộ đầu tiên khi có dữ liệu
    let firstOfficer = true;
    onChildAdded(officersRef, (data) => {{
        if (firstOfficer) {{
            const officer = data.val();
            map.setView([officer.lat, officer.lng], 15);
            firstOfficer = false;
        }}
    }});
    </script>
</head>
<body>
    <div id="map"></div>
</body>
</html>
"""

st.components.v1.html(map_html, height=620)

# ==============================
# 10. DANH SÁCH CÁN BỘ ONLINE
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
# 11. ĐIỂM ĐÁNH DẤU GẦN ĐÂY
# ==============================

markers = load_markers()

with st.sidebar.expander("📌 Điểm đánh dấu gần đây"):
    if markers:
        sorted_markers = sorted(
            markers.items(),
            key=lambda x: x[1]["timestamp"],
            reverse=True
        )[:5]
        for _, m in sorted_markers:
            st.write(f"📍 {m['created_by']}: {m['note'][:30]}...")
    else:
        st.write("Chưa có điểm đánh dấu")
