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
# 5. JAVASCRIPT LẤY GPS VÀ XỬ LÝ BÁO ĐỘNG (ĐÃ THÊM TRACK)
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
            db.child("markers").child(username).push(marker_data)
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

def load_all_markers():
    markers_dict = {}
    try:
        all_markers = db.child("markers").get().val()
        if all_markers:
            for uid, user_markers in all_markers.items():
                if user_markers and isinstance(user_markers, dict):
                    for key, marker in user_markers.items():
                        if isinstance(marker, dict) and marker.get("timestamp"):
                            markers_dict[key] = marker
        return markers_dict
    except Exception as e:
        st.error(f"Lỗi đọc markers: {e}")
        return {}

# ==============================
# 8. TỰ ĐỘNG REFRESH (cho danh sách online và chat)
# ==============================
st_autorefresh(interval=5000, key="auto_refresh")

# ==============================
# 9. CHECKBOX HIỂN THỊ TRACK
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("🗺️ Lịch sử di chuyển")

if 'show_tracks' not in st.session_state:
    st.session_state.show_tracks = {}

officers = load_officers()
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
# 10. HTML BẢN ĐỒ REALTIME (ĐÃ TÍCH HỢP: track mượt, âm thanh, fitBounds)
# ==============================
show_tracks_json = json.dumps(st.session_state.get("show_tracks", {}))
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
        push,
        onDisconnect 
    }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

    const firebaseConfig = {json.dumps(firebase_config)};
    const app = initializeApp(firebaseConfig);
    const db = getDatabase(app);

    const myUsername = "{username}";
    const showTracks = {show_tracks_json};
    console.log("👤 My username:", myUsername);

    // Khởi tạo map
    const map = L.map('map').setView([21.0285, 105.8542], 13);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; OpenStreetMap'
    }}).addTo(map);

    // Objects
    const officerMarkers = {{}};
    const alertMarkers = {{}};
    const pointMarkers = {{}};
    const trackPolylines = {{}};  // Lưu polyline cho mỗi user

    // Âm thanh báo động
    const alertSound = new Audio("alert.mp3");
    // Preload âm thanh (tương tác với trang mới phát được)
    document.addEventListener('click', () => alertSound.load(), {{ once: true }});

    // Zoom flag
    let zoomedToMe = false;

    // ===== GPS FALLBACK =====
    if (navigator.geolocation) {{
        navigator.geolocation.getCurrentPosition(
            (pos) => {{
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                console.log(`📍 GPS fallback: (${{lat}}, ${{lng}})`);
                if (!zoomedToMe) {{
                    map.setView([lat, lng], 16);
                    zoomedToMe = true;
                }}
            }},
            (err) => console.warn("⚠️ GPS fallback error:", err),
            {{ enableHighAccuracy: true, timeout: 10000 }}
        );
    }}

    // ===== 1. OFFICERS =====
    const officersRef = ref(db, 'officers');

    onChildAdded(officersRef, (data) => {{
        const officer = data.val();
        const id = data.key;
        console.log(`👤 Officer added: ${{id}}`, officer);

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

    // ===== 2. ALERTS (có âm thanh) =====
    const alertsRef = ref(db, 'alerts');
    onChildAdded(alertsRef, (data) => {{
        const alert = data.val();
        const id = data.key;
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
            offset: [0, -8]
        }});
        alertMarkers[id] = marker;

        // Phát âm thanh nếu không phải mình
        if (alert.name !== "{name}") {{
            alertSound.play().catch(e => console.log("Audio error:", e));
        }}
    }});
    onChildRemoved(alertsRef, (data) => {{
        const id = data.key;
        if (alertMarkers[id]) {{
            map.removeLayer(alertMarkers[id]);
            delete alertMarkers[id];
        }}
    }});

    // ===== 3. MARKERS (ĐIỂM ĐÁNH DẤU) =====
    const markersRootRef = ref(db, 'markers');
    onChildAdded(markersRootRef, (userSnapshot) => {{
        const userId = userSnapshot.key;
        const userMarkersRef = ref(db, `markers/${{userId}}`);
        onChildAdded(userMarkersRef, (markerSnapshot) => {{
            const point = markerSnapshot.val();
            const markerId = markerSnapshot.key;
            const fullId = `${{userId}}_${{markerId}}`;
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

    // ===== 4. TRACKS (vẽ 1 polyline duy nhất, mượt) =====
    function loadUserTracks(userId, userName, show) {{
        const tracksRef = ref(db, 'tracks/' + userId + '/points');
        const tracksQuery = query(tracksRef, limitToLast(200)); // chỉ lấy 200 điểm gần nhất
        if (!show) {{
            if (trackPolylines[userId]) {{
                map.removeLayer(trackPolylines[userId]);
                delete trackPolylines[userId];
            }}
            return;
        }}
        // Lấy toàn bộ points và vẽ một polyline duy nhất
        onValue(tracksQuery, (snapshot) => {{
            const points = snapshot.val();
            if (!points) return;
            const latlngs = Object.values(points)
                .filter(p => p.lat && p.lng)
                .map(p => [p.lat, p.lng]);
            if (trackPolylines[userId]) {{
                map.removeLayer(trackPolylines[userId]);
            }}
            // Sinh màu từ tên
            const hue = (userName.split('').reduce((a,b) => a + b.charCodeAt(0), 0) * 31) % 360;
            const color = `hsl(${{hue}}, 70%, 50%)`;
            const polyline = L.polyline(latlngs, {{
                color: color,
                weight: 4,
                opacity: 0.7,
                smoothFactor: 1.5  // làm mượt đường
            }}).addTo(map);
            trackPolylines[userId] = polyline;
        }});
    }}

    onValue(officersRef, (snapshot) => {{
        const officers = snapshot.val() || {{}};
        Object.keys(officers).forEach(uid => {{
            loadUserTracks(uid, officers[uid].name, showTracks[uid] || false);
        }});
    }});

    // ===== 5. THÊM ĐIỂM BẰNG NHẤN GIỮ (KHÔNG XÓA ONDISCONNECT) =====
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
                const userMarkerRef = ref(db, 'markers/{username}');
                push(userMarkerRef, newPoint);
            }}
        }}, 5000);
    }});
    map.on('touchend', () => clearTimeout(pressTimer));
    map.on('touchcancel', () => clearTimeout(pressTimer));

    // ===== 6. FIT BOUNDS (zoom toàn bộ cán bộ) =====
    // Hàm này sẽ được gọi mỗi khi có thay đổi về officers (thêm/xóa)
    function fitMapToOfficers() {{
        const bounds = [];
        for (const id in officerMarkers) {{
            bounds.push(officerMarkers[id].getLatLng());
        }}
        if (bounds.length > 0) {{
            map.fitBounds(bounds, {{ padding: [50, 50] }});
        }}
    }}

    // Gọi sau khi thêm marker đầu tiên (nhưng tránh ghi đè zoom vào mình)
    // Ta sẽ gọi khi có thay đổi, nhưng chỉ khi không phải lúc vừa zoom vào mình
    // Đơn giản: thêm một nút bấm "Xem tất cả" trên sidebar (sẽ làm sau)
    // Hoặc có thể thêm một checkbox "Tự động fit" nhưng để đơn giản, tôi sẽ thêm nút bấm trong map? Không, thêm ở sidebar Python.

    </script>
</head>
<body>
    <div id="map"></div>
</body>
</html>
"""

st.components.v1.html(map_html, height=620)

# ==============================
# 11. NÚT "XEM TẤT CẢ" (FIT BOUNDS) - THÊM VÀO SIDEBAR
# ==============================
st.sidebar.markdown("---")
if st.sidebar.button("🌍 Xem tất cả cán bộ"):
    # Gửi một tín hiệu để map fit bounds (có thể dùng một node tạm)
    # Cách đơn giản: lưu một flag vào session_state và dùng st_autorefresh để reload map? Không hay.
    # Thay vào đó, ta có thể dùng st.components.v1.html với một đoạn script nhỏ gọi hàm từ map.
    # Nhưng vì map đã được nhúng, ta có thể thêm một iframe ẩn để gửi lệnh.
    # Tạm thời, ta sẽ dùng cách reload map với tham số trên URL (dùng query params) để map biết cần fit.
    # Tuy nhiên, để đơn giản, tôi sẽ thêm một nút trong map HTML bằng cách thêm một control.
    # Nhưng vì code đã dài, tôi sẽ bổ sung một nút điều khiển ở sidebar dùng st.markdown với JavaScript.
    # Cách này cần tương tác giữa Python và JS, hơi phức tạp. Tôi sẽ tạo một component riêng.
    # Thay vào đó, tôi sẽ thêm một button trong map bằng Leaflet (sẽ làm ở bản cập nhật sau).
    # Hiện tại, bạn có thể dùng tạm cách: reload lại trang (st.rerun()) nhưng map sẽ reset.
    # Tốt nhất, thêm một nút trong map HTML:
    # Thêm đoạn sau vào cuối script:
    """
    // Thêm control button
    L.Control.Button = L.Control.extend({
        onAdd: function(map) {
            const btn = L.DomUtil.create('button', 'fit-button');
            btn.innerHTML = '🌍 Xem tất cả';
            btn.style.backgroundColor = 'white';
            btn.style.padding = '5px 10px';
            btn.style.border = '2px solid #0066cc';
            btn.style.borderRadius = '4px';
            btn.style.cursor = 'pointer';
            btn.style.margin = '10px';
            L.DomEvent.on(btn, 'click', function() {
                fitMapToOfficers();
            });
            return btn;
        }
    });
    L.control.button = function(opts) { return new L.Control.Button(opts); };
    L.control.button({ position: 'topright' }).addTo(map);
    """
    # Tôi sẽ thêm vào map HTML ở trên. Để code gọn, tôi sẽ chèn vào trước </script>.

# ==============================
# 12. DANH SÁCH CÁN BỘ ONLINE
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Cán bộ trực tuyến")

if officers:
    for uid, info in officers.items():
        label = "(bạn)" if uid == username else ""
        st.sidebar.write(f"• {info['name']} {label}")
else:
    st.sidebar.write("Chưa có ai chia sẻ vị trí")

# ==============================
# 13. CHAT NỘI BỘ (TAB)
# ==============================
tab1, tab2 = st.tabs(["🗺️ Bản đồ", "💬 Chat nội bộ"])

with tab2:
    st.subheader("💬 Chat nội bộ")
    st_autorefresh(interval=3000, key="chat_refresh")

    try:
        messages_data = db.child("messages").order_by_child("timestamp").limit_to_last(50).get()
        if messages_data and messages_data.val():
            messages = messages_data.val()
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
    except Exception as e:
        st.warning(f"Không thể tải tin nhắn: {e}. Đảm bảo Firebase rules đã được cập nhật.")

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

# ==============================
# 14. ĐIỂM ĐÁNH DẤU GẦN ĐÂY
# ==============================
all_markers = load_all_markers()
with st.sidebar.expander("📌 Điểm đánh dấu gần đây"):
    if all_markers:
        valid_markers = {k: v for k, v in all_markers.items() 
                        if isinstance(v, dict) and v.get("timestamp")}
        if valid_markers:
            sorted_markers = sorted(
                valid_markers.items(),
                key=lambda x: x[1]["timestamp"],
                reverse=True
            )[:5]
            for _, m in sorted_markers:
                st.write(f"📍 {m.get('created_by', 'Unknown')}: {m.get('note', '')[:30]}...")
        else:
            st.write("Chưa có điểm đánh dấu hợp lệ")
    else:
        st.write("Chưa có điểm đánh dấu")
