import streamlit as st
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.hasher import Hasher
import yaml
from yaml.loader import SafeLoader
import pyrebase
import json
import time
from streamlit_autorefresh import st_autorefresh
from datetime import datetime, timezone, timedelta
import base64
import requests
import math

# ==============================
# 0. HÀM TIỆN ÍCH
# ==============================
def get_base64(file_path):
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        return ""

def haversine(lat1, lng1, lat2, lng2):
    R = 6371e3
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def is_valid_coordinate(lat, lng):
    if lat is None or lng is None:
        return False
    try:
        lat = float(lat)
        lng = float(lng)
        return True
    except:
        return False

# ==============================
# 1. UPLOAD ẢNH
# ==============================
def upload_to_imgbb(image_file, api_key):
    try:
        url = "https://api.imgbb.com/1/upload"
        payload = {"key": api_key, "expiration": 86400}
        files = {"image": (image_file.name, image_file.getvalue(), image_file.type)}
        response = requests.post(url, data=payload, files=files)
        data = response.json()
        if data.get("success"):
            return data["data"]["url"], None
        return None, data.get("error", {}).get("message", "Lỗi không xác định")
    except Exception as e:
        return None, str(e)

# ==============================
# 2. CẤU HÌNH FIREBASE
# ==============================
firebase_config = dict(st.secrets["firebase"])
firebase = pyrebase.initialize_app(firebase_config)
db = firebase.database()

# ==============================
# 3. AUTHENTICATION
# ==============================
def load_credentials_from_firebase():
    try:
        auth_data = db.child("auth_credentials").get().val()
        if not auth_data or "usernames" not in auth_data:
            default_password = "admin123"
            hashed = Hasher([default_password]).generate()[0]
            default_admin = {
                "usernames": {
                    "admin": {
                        "email": "admin@example.com",
                        "name": "Quản trị viên",
                        "password": hashed,
                        "role": "admin",
                        "color": "#FFD700"
                    }
                }
            }
            db.child("auth_credentials").set(default_admin)
            return default_admin
        usernames = auth_data.get("usernames", {})
        clean_users = {}
        for u, info in usernames.items():
            if not isinstance(info, dict):
                continue
            clean_users[u] = {
                "email": info.get("email", ""),
                "name": info.get("name", u),
                "password": info.get("password", ""),
                "role": info.get("role", "officer"),
                "color": info.get("color", "#0066cc")
            }
        return {"usernames": clean_users}
    except Exception as e:
        st.error(f"Lỗi tải credentials: {e}")
        return {"usernames": {}}

def save_credentials_to_firebase(credentials):
    try:
        db.child("auth_credentials").set(credentials)
        return True
    except Exception as e:
        st.error(f"Lỗi lưu credentials: {e}")
        return False

credentials_data = load_credentials_from_firebase()

try:
    with open("config.yaml") as file:
        config_yaml = yaml.load(file, Loader=SafeLoader)
        cookie_config = config_yaml.get("cookie", {})
except:
    cookie_config = {}

config = {
    "credentials": credentials_data,
    "cookie": {
        "expiry_days": cookie_config.get("expiry_days", 7),
        "key": st.secrets["auth"]["cookie_key"],
        "name": cookie_config.get("name", "tuan_tra_cookie")
    }
}

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

# ==============================
# 4. CẤU HÌNH TRANG VÀ CSS
# ==============================
st.set_page_config(page_title="Tuần tra cơ động", layout="wide")

# ===== CSS NÂNG CẤP =====
st.markdown("""
<style>
    /* Ẩn header, footer, menu */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    .stApp { margin-top: -60px; }

    /* Top bar cố định */
    .top-bar {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 60px;
        background: rgba(0,0,0,0.85);
        backdrop-filter: blur(10px);
        color: white;
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 30px;
        font-family: 'Inter', sans-serif;
        box-shadow: 0 2px 10px rgba(0,0,0,0.3);
    }
    .top-bar .logo {
        font-size: 1.4rem;
        font-weight: bold;
        letter-spacing: 1px;
    }
    .top-bar .user-info {
        display: flex;
        align-items: center;
        gap: 20px;
    }
    .top-bar button {
        background: #ff5500;
        border: none;
        padding: 6px 15px;
        border-radius: 20px;
        color: white;
        font-weight: 600;
        cursor: pointer;
    }

    /* Panel bên trái */
    .panel {
        background: rgba(0,0,0,0.75);
        backdrop-filter: blur(12px);
        border-radius: 20px;
        padding: 20px;
        color: white;
        height: calc(100vh - 80px);
        overflow-y: auto;
        margin-top: 70px;
        margin-left: 15px;
        width: 320px;
        z-index: 1000;
        box-shadow: 0 5px 20px rgba(0,0,0,0.3);
        font-family: 'Inter', sans-serif;
    }
    .panel h3 {
        margin-top: 0;
        border-left: 4px solid #ff8800;
        padding-left: 10px;
    }
    .panel .stButton button {
        width: 100%;
        margin: 5px 0;
        background: linear-gradient(135deg, #ff8800, #ff5500);
        border: none;
        border-radius: 12px;
        padding: 8px;
        font-weight: 600;
    }
    .panel .stButton button:hover {
        transform: scale(1.02);
        box-shadow: 0 0 12px rgba(255,136,0,0.5);
    }
    .dashboard-item {
        background: rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 10px;
        margin: 10px 0;
        text-align: center;
    }
    .chat-container {
        background: rgba(0,0,0,0.6);
        border-radius: 16px;
        margin-top: 20px;
        padding: 10px;
        max-height: 300px;
        overflow-y: auto;
    }
    .chat-message {
        margin-bottom: 8px;
        display: flex;
    }
    .chat-message.me {
        justify-content: flex-end;
    }
    .chat-bubble {
        max-width: 85%;
        padding: 8px 12px;
        border-radius: 18px;
        font-size: 0.9rem;
    }
    .chat-bubble.me {
        background: #ff8800;
        color: white;
        border-bottom-right-radius: 4px;
    }
    .chat-bubble.other {
        background: #2c3e50;
        color: white;
        border-bottom-left-radius: 4px;
    }

    /* Map container */
    .map-container {
        position: fixed;
        top: 60px;
        right: 0;
        bottom: 0;
        left: 350px;
        z-index: 1;
    }
    @media (max-width: 768px) {
        .panel { width: 280px; margin-left: 5px; }
        .map-container { left: 300px; }
    }
</style>
""", unsafe_allow_html=True)

# ===== TOP BAR =====
st.markdown(f"""
<div class="top-bar">
    <div class="logo">🚔 HỆ THỐNG TUẦN TRA CƠ ĐỘNG</div>
    <div class="user-info">
        <span>👤 {st.session_state.get('name', '')}</span>
        <button onclick="document.querySelector('.stButton button').click()">Đăng xuất</button>
    </div>
</div>
""", unsafe_allow_html=True)

# ===== ĐĂNG NHẬP =====
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

# Ẩn nút đăng xuất của authenticator (ta sẽ dùng nút custom)
# Vẫn giữ logout trong sidebar để dễ xử lý session, nhưng ẩn sidebar
st.sidebar.empty()
authenticator.logout("Đăng xuất", "sidebar")  # vẫn cần để có session state

# ==============================
# 5. THÔNG TIN USER
# ==============================
user_role = config["credentials"]["usernames"][username].get("role", "officer")
user_color = config["credentials"]["usernames"][username].get("color", "#0066cc")

user_colors = {}
for uid, data in config["credentials"]["usernames"].items():
    role = data.get("role", "officer")
    if role == "admin":
        user_colors[uid] = "#FFD700"
    elif role == "commander":
        user_colors[uid] = "#FF4500"
    else:
        user_colors[uid] = data.get("color", "#0066cc")

db.child("users").child(username).set({
    "name": name,
    "role": user_role,
    "color": user_colors[username],
    "last_seen": int(time.time() * 1000)
})

# ==============================
# 6. CHIA SẺ VỊ TRÍ
# ==============================
if "sharing" not in st.session_state:
    st.session_state.sharing = False

# ==============================
# 7. CÁC HÀM HỖ TRỢ
# ==============================
def find_nearest_officers(lat, lng, limit=3):
    officers = db.child("officers").get().val()
    if not officers:
        return []
    distances = []
    for uid, data in officers.items():
        if is_valid_coordinate(data.get("lat"), data.get("lng")):
            d = haversine(lat, lng, data["lat"], data["lng"])
            distances.append((uid, d))
    distances.sort(key=lambda x: x[1])
    return [uid for uid, _ in distances[:limit]]

def send_fcm_notification(title, body, target_token, server_key):
    url = "https://fcm.googleapis.com/fcm/send"
    headers = {
        "Authorization": f"key={server_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": target_token,
        "notification": {
            "title": title,
            "body": body,
            "sound": "default"
        }
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        print("FCM error:", e)
        return None

# ==============================
# 8. CLEANUP
# ==============================
def cleanup_old_data():
    try:
        incidents = db.child("incidents").get().val()
        if incidents:
            now = int(time.time() * 1000)
            for key, inc in incidents.items():
                if now - inc.get("timestamp", 0) > 24 * 3600 * 1000:
                    db.child("incidents").child(key).remove()
    except Exception as e:
        print("Cleanup error:", e)

def cleanup_offline_officers():
    try:
        officers = db.child("officers").get().val()
        if not officers:
            return
        now = int(time.time() * 1000)
        limit = 30 * 60 * 1000
        for uid, data in officers.items():
            offline_at = data.get("offlineAt")
            if offline_at and now - offline_at > limit:
                db.child("officers").child(uid).remove()
    except Exception as e:
        print("Cleanup offline officers error:", e)

def cleanup_old_tracks():
    try:
        tracks = db.child("tracks").get().val()
        if not tracks:
            return
        now = int(time.time() * 1000)
        limit = 24 * 3600 * 1000
        for uid, data in tracks.items():
            points = data.get("points")
            if not points:
                continue
            for key, point in points.items():
                if now - point.get("timestamp", 0) > limit:
                    db.child("tracks").child(uid).child("points").child(key).remove()
    except Exception as e:
        print("Track cleanup error:", e)

def limit_tracks():
    try:
        tracks = db.child("tracks").get().val()
        if not tracks:
            return
        for uid, data in tracks.items():
            points = data.get("points", {})
            if len(points) > 500:
                sorted_points = sorted(points.items(), key=lambda x: x[1].get("timestamp", 0))
                for k, _ in sorted_points[:-500]:
                    db.child("tracks").child(uid).child("points").child(k).remove()
    except Exception as e:
        print("Limit tracks error:", e)

if "last_cleanup" not in st.session_state or time.time() - st.session_state.last_cleanup > 300:
    cleanup_old_data()
    cleanup_offline_officers()
    cleanup_old_tracks()
    limit_tracks()
    st.session_state.last_cleanup = time.time()

def detect_stationary_officers():
    try:
        officers = db.child("officers").get().val()
        if not officers:
            return []
        now = int(time.time() * 1000)
        threshold = 15 * 60 * 1000
        stationary = []
        for uid, data in officers.items():
            if is_valid_coordinate(data.get("lat"), data.get("lng")):
                last = data.get("lastUpdate")
                if last and (now - int(last)) > threshold:
                    stationary.append({
                        "uid": uid,
                        "name": data.get("name"),
                        "lat": data["lat"],
                        "lng": data["lng"],
                        "lastUpdate": last
                    })
        return stationary
    except Exception as e:
        print("Stationary detection error:", e)
        return []

# ==============================
# 9. GPS SCRIPT
# ==============================
if st.session_state.sharing:
    gps_script = f"""
    <script type="module">
    import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
    import {{ 
        getDatabase, 
        ref, 
        update, 
        push, 
        onDisconnect, 
        onChildAdded,
        serverTimestamp
    }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

    const firebaseConfig = {json.dumps(firebase_config)};
    const app = initializeApp(firebaseConfig);
    const database = getDatabase(app);

    const username = "{username}";
    const officerName = "{name}";
    const officerRef = ref(database, 'officers/' + username);

    update(officerRef, {{
        name: officerName,
        lastUpdate: serverTimestamp()
    }});

    let lastLat = null;
    let lastLng = null;
    let lastPoint = null;
    let prevPoint = null;
    let lastBearing = null;
    let trackBuffer = [];
    let lastSendTime = 0;
    const SEND_INTERVAL = 5000;

    function isValidVNCoordinate(lat, lng) {{
        if (typeof lat !== 'number' || typeof lng !== 'number') return false;
        if (lat === 0 && lng === 0) return false;
        return true;
    }}

    function distance(lat1, lon1, lat2, lon2) {{
        const R = 6371000;
        const dLat = (lat2-lat1) * Math.PI/180;
        const dLon = (lon2-lon1) * Math.PI/180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                  Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) *
                  Math.sin(dLon/2) * Math.sin(dLon/2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        return R * c;
    }}

    function getBearing(lat1, lon1, lat2, lon2) {{
        const toRad = d => d * Math.PI/180;
        const toDeg = r => r * 180/Math.PI;
        const dLon = toRad(lon2 - lon1);
        const y = Math.sin(dLon) * Math.cos(toRad(lat2));
        const x = Math.cos(toRad(lat1))*Math.sin(toRad(lat2)) -
                  Math.sin(toRad(lat1))*Math.cos(toRad(lat2))*Math.cos(dLon);
        return (toDeg(Math.atan2(y,x)) + 360) % 360;
    }}

    function shouldSavePoint(p1, p2, p3) {{
        const b1 = getBearing(p1.lat, p1.lng, p2.lat, p2.lng);
        const b2 = getBearing(p2.lat, p2.lng, p3.lat, p3.lng);
        let angle = Math.abs(b1 - b2);
        if (angle > 180) angle = 360 - angle;
        return angle >= 10;
    }}

    function stabilizeLine(lat,lng){{
        trackBuffer.push({{lat,lng}});
        if(trackBuffer.length>3) trackBuffer.shift();
        if(trackBuffer.length<3) return {{lat,lng}};
        const p1=trackBuffer[0], p2=trackBuffer[1], p3=trackBuffer[2];
        const b1=getBearing(p1.lat,p1.lng,p2.lat,p2.lng);
        const b2=getBearing(p2.lat,p2.lng,p3.lat,p3.lng);
        if(Math.abs(b1-b2)<15){{
            lat=(p1.lat+p2.lat+p3.lat)/3;
            lng=(p1.lng+p2.lng+p3.lng)/3;
        }}
        return {{lat,lng}};
    }}

    let fallbackLat = null;
    let fallbackLng = null;
    fetch("https://ipapi.co/json/")
        .then(res => res.json())
        .then(data => {{
            if (data.latitude && data.longitude && isValidVNCoordinate(data.latitude, data.longitude)) {{
                fallbackLat = data.latitude;
                fallbackLng = data.longitude;
                console.log("🌐 IP location:", fallbackLat, fallbackLng);
            }} else {{
                fallbackLat = 21.0285;
                fallbackLng = 105.8542;
                console.log("🌐 Dùng fallback Hà Nội");
            }}
        }})
        .catch(err => {{
            fallbackLat = 21.0285;
            fallbackLng = 105.8542;
            console.log("🌐 Lỗi IP, dùng fallback Hà Nội");
        }});

    if (navigator.geolocation) {{
        navigator.geolocation.watchPosition(function(position){{
            console.log("GPS OK:", position.coords);
            let accuracy = position.coords.accuracy;
            if(accuracy > 100) return;

            let lat = position.coords.latitude;
            let lng = position.coords.longitude;

            if (!isValidVNCoordinate(lat, lng)) {{
                console.log("❌ GPS ngoài VN:", lat, lng);
                if (fallbackLat && fallbackLng) {{
                    lat = fallbackLat;
                    lng = fallbackLng;
                    console.log("✅ Dùng fallback:", lat, lng);
                }} else {{
                    return;
                }}
            }}

            let shouldSend = true;
            if(lastLat !== null){{
                const dist = distance(lastLat, lastLng, lat, lng);
                if(dist < 3) shouldSend = false;
            }}
            if(!shouldSend) return;

            if(lastLat!==null){{
                lat = lastLat*0.7 + lat*0.3;
                lng = lastLng*0.7 + lng*0.3;
            }}

            if(lastPoint){{
                const bearing = getBearing(lastPoint.lat, lastPoint.lng, lat, lng);
                if(lastBearing!==null){{
                    const diff = Math.abs(bearing - lastBearing);
                    if(diff>60 && diff<300){{
                        lat = lastPoint.lat*0.85 + lat*0.15;
                        lng = lastPoint.lng*0.85 + lng*0.15;
                    }}
                }}
                lastBearing = bearing;
            }}

            const stabilized = stabilizeLine(lat,lng);
            lat = stabilized.lat;
            lng = stabilized.lng;
            const now = Date.now();

            update(officerRef, {{
                name: officerName,
                lat: lat,
                lng: lng,
                accuracy: accuracy,
                lastUpdate: serverTimestamp()
            }});
            onDisconnect(officerRef).update({{
                lastUpdate: 0,
                offlineAt: serverTimestamp()
            }});

            if (now - lastSendTime < SEND_INTERVAL) return;
            lastSendTime = now;

            const trackPoint = {{ lat, lng, timestamp: serverTimestamp() }};

            if(lastPoint){{
                const dist = distance(lastPoint.lat, lastPoint.lng, lat, lng);
                if(dist>5 && dist<60){{
                    const midLat = (lastPoint.lat+lat)/2;
                    const midLng = (lastPoint.lng+lng)/2;
                    push(ref(database, 'tracks/'+username+'/points'), {{
                        lat: midLat,
                        lng: midLng,
                        timestamp: serverTimestamp()
                    }});
                }}
            }}

            if (lastPoint && prevPoint) {{
                if (!shouldSavePoint(prevPoint, lastPoint, trackPoint)) {{
                    prevPoint = lastPoint;
                    lastPoint = trackPoint;
                    return;
                }}
            }}

            if(Math.random() < 0.5) {{
                push(ref(database, 'tracks/'+username+'/points'), trackPoint);
            }}
            prevPoint = lastPoint;
            lastPoint = trackPoint;
            lastLat = lat;
            lastLng = lng;

        }}, function(error){{
            console.log("GPS error:", error);
            if (fallbackLat && fallbackLng) {{
                update(officerRef, {{
                    name: officerName,
                    lat: fallbackLat,
                    lng: fallbackLng,
                    accuracy: 0,
                    lastUpdate: serverTimestamp()
                }});
            }}
        }}, {{
            enableHighAccuracy: true,
            maximumAge: 5000,
            timeout: 10000
        }});
    }}

    const alertRequestsRef = ref(database, 'alert_requests');
    onChildAdded(alertRequestsRef, (data) => {{
        const req = data.val();
        if (req.username === username) {{
            const alertRef = ref(database, 'alerts/' + username);
            update(alertRef, {{
                name: req.name,
                lat: req.lat,
                lng: req.lng,
                assigned: req.assigned || [],
                status: req.status || "pending",
                timestamp: serverTimestamp()
            }});
            update(ref(database, 'alert_requests/' + data.key), null);
            onDisconnect(alertRef).remove();
        }}
    }});
    </script>
    <div style="text-align: center; color: green;">📡 Đang chia sẻ vị trí...</div>
    """
    st.components.v1.html(gps_script, height=60)

# ==============================
# 10. LOAD DỮ LIỆU
# ==============================
@st.cache_data(ttl=5)
def load_officers():
    try:
        result = db.child("officers").get().val()
        if result:
            filtered = {uid: data for uid, data in result.items()
                        if is_valid_coordinate(data.get("lat"), data.get("lng"))}
            return filtered
        return {}
    except Exception as e:
        st.error(f"Lỗi Firebase: {e}")
        return {}

def load_all_markers():
    try:
        all_markers = db.child("markers").get().val()
        markers_dict = {}
        if all_markers:
            for uid, user_markers in all_markers.items():
                if user_markers and isinstance(user_markers, dict):
                    for key, marker in user_markers.items():
                        if isinstance(marker, dict) and marker.get("timestamp") and is_valid_coordinate(marker.get("lat"), marker.get("lng")):
                            markers_dict[key] = marker
        return markers_dict
    except Exception as e:
        st.error(f"Lỗi đọc markers: {e}")
        return {}

def load_incidents():
    try:
        incidents = db.child("incidents").get().val()
        incidents_dict = {}
        if incidents:
            for key, inc in incidents.items():
                if isinstance(inc, dict) and inc.get("timestamp") and is_valid_coordinate(inc.get("lat"), inc.get("lng")):
                    incidents_dict[key] = inc
        return incidents_dict
    except Exception as e:
        st.error(f"Lỗi đọc incidents: {e}")
        return {}

officers = load_officers()
all_markers = load_all_markers()
incidents = load_incidents()
stationary_officers = detect_stationary_officers()

# ==============================
# 11. PANEL BÊN TRÁI
# ==============================
with st.container():
    st.markdown('<div class="panel">', unsafe_allow_html=True)

    # Dashboard mini
    st.markdown(f"""
    <div class="dashboard-item">
        <b>📊 Tổng quan</b><br>
        👥 Online: {len(officers)}<br>
        📍 Marker: {len(all_markers)}<br>
        📸 Ảnh: {len(incidents)}<br>
        ⚠️ Báo động: {len(db.child("alerts").get().val() or {})}
    </div>
    """, unsafe_allow_html=True)

    # Chia sẻ vị trí
    if not st.session_state.sharing:
        if st.button("📡 BẮT ĐẦU CHIA SẺ VỊ TRÍ"):
            st.session_state.sharing = True
            st.rerun()
    else:
        if st.button("🛑 DỪNG CHIA SẺ"):
            db.child("officers").child(username).remove()
            st.session_state.sharing = False
            st.rerun()

    # Các nút công cụ
    if st.button("🚨 GỬI BÁO ĐỘNG"):
        user_data = db.child("officers").child(username).get().val()
        if user_data and is_valid_coordinate(user_data.get("lat"), user_data.get("lng")):
            lat = user_data["lat"]
            lng = user_data["lng"]
            nearest = find_nearest_officers(lat, lng)
            request_data = {
                "username": username,
                "name": name,
                "lat": lat,
                "lng": lng,
                "assigned": nearest,
                "status": "pending",
                "timestamp": int(time.time() * 1000)
            }
            db.child("alert_requests").push(request_data)

            server_key = st.secrets.get("fcm", {}).get("server_key", "")
            if server_key:
                tokens = db.child("fcm_tokens").get().val() or {}
                for uid, token in tokens.items():
                    if uid != username:
                        send_fcm_notification("🚨 BÁO ĐỘNG", f"Báo động từ {name}", token, server_key)

            st.success("Đã gửi yêu cầu báo động", icon="✅")
        else:
            st.error("Bạn chưa chia sẻ vị trí hợp lệ")

    with st.expander("📍 Đánh dấu điểm"):
        note = st.text_area("Ghi chú", key="note_marker")
        if st.button("Thêm điểm tại vị trí hiện tại"):
            current = db.child("officers").child(username).get().val()
            if current and is_valid_coordinate(current.get("lat"), current.get("lng")) and note.strip():
                marker_data = {
                    "created_by": name,
                    "lat": current["lat"],
                    "lng": current["lng"],
                    "note": note,
                    "timestamp": int(time.time() * 1000),
                }
                db.child("markers").child(username).push(marker_data)
                st.success("Đã thêm điểm")
            else:
                st.warning("Chưa chia sẻ vị trí hợp lệ hoặc ghi chú trống")

    with st.expander("📸 Chụp ảnh hiện trường"):
        uploaded_file = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
        note_photo = st.text_input("Ghi chú (tùy chọn)")
        if st.button("📤 Gửi ảnh"):
            if not st.session_state.sharing:
                st.warning("Bạn cần bật chia sẻ vị trí trước")
            elif uploaded_file is None:
                st.warning("Vui lòng chọn ảnh")
            else:
                current = db.child("officers").child(username).get().val()
                if current and is_valid_coordinate(current.get("lat"), current.get("lng")):
                    imgbb_api_key = st.secrets["imgbb"]["api_key"]
                    image_url, error = upload_to_imgbb(uploaded_file, imgbb_api_key)
                    if error:
                        st.error(f"Lỗi upload: {error}")
                    else:
                        incident_data = {
                            "created_by": name,
                            "lat": current["lat"],
                            "lng": current["lng"],
                            "note": note_photo,
                            "image_url": image_url,
                            "timestamp": int(time.time() * 1000)
                        }
                        db.child("incidents").push(incident_data)
                        st.success("Đã gửi ảnh hiện trường!")
                else:
                    st.error("Không có vị trí hợp lệ")

    if st.button("✅ NHẬN NHIỆM VỤ GẦN NHẤT"):
        alerts = db.child("alerts").get().val()
        if alerts:
            found = False
            for key, alert in alerts.items():
                assigned = alert.get("assigned", [])
                if username in assigned:
                    db.child("alerts").child(key).update({
                        "status": "accepted",
                        "accepted_by": name
                    })
                    st.success("Đã nhận nhiệm vụ")
                    found = True
                    break
            if not found:
                st.info("Không có nhiệm vụ nào cho bạn")
        else:
            st.info("Không có báo động nào")

    # Quản lý user (admin)
    if user_role == "admin":
        st.markdown("---")
        with st.expander("👤 Quản lý tài khoản"):
            with st.form("add_user_form"):
                new_username = st.text_input("Tên đăng nhập")
                new_email = st.text_input("Email")
                new_name = st.text_input("Tên hiển thị")
                new_password = st.text_input("Mật khẩu", type="password")
                new_role = st.selectbox("Vai trò", ["admin", "commander", "officer"])
                new_color = st.color_picker("Màu sắc", "#0066cc")
                if st.form_submit_button("Tạo tài khoản"):
                    if not new_username or not new_name or not new_password:
                        st.error("Vui lòng nhập đầy đủ")
                    elif new_username in config["credentials"]["usernames"]:
                        st.error("Tên đăng nhập đã tồn tại")
                    else:
                        hashed = Hasher([new_password]).generate()[0]
                        config["credentials"]["usernames"][new_username] = {
                            "email": new_email,
                            "name": new_name,
                            "password": hashed,
                            "role": new_role,
                            "color": new_color
                        }
                        if save_credentials_to_firebase(config["credentials"]):
                            st.success(f"Đã thêm user {new_username}")
                            st.rerun()
                        else:
                            st.error("Lỗi lưu dữ liệu")
            with st.form("delete_user_form"):
                users = list(config["credentials"]["usernames"].keys())
                if users:
                    user_to_delete = st.selectbox("Chọn user để xóa", users)
                    if st.form_submit_button("Xóa user"):
                        if user_to_delete == username:
                            st.error("Không thể xóa chính mình")
                        else:
                            del config["credentials"]["usernames"][user_to_delete]
                            if save_credentials_to_firebase(config["credentials"]):
                                st.success(f"Đã xóa user {user_to_delete}")
                                st.rerun()
                            else:
                                st.error("Lỗi lưu dữ liệu")
                else:
                    st.info("Không có user nào")

    # Lệnh di chuyển (commander)
    if user_role == "commander" and officers:
        st.markdown("---")
        st.subheader("🚶 Ra lệnh di chuyển")
        officer_options = {uid: info['name'] for uid, info in officers.items() if uid != username}
        if officer_options:
            selected_officer = st.selectbox(
                "Chọn cán bộ",
                options=list(officer_options.keys()),
                format_func=lambda x: officer_options[x]
            )
            if st.button("📍 BẮT ĐẦU CHỌN ĐIỂM ĐẾN"):
                st.session_state['order_officer_id'] = selected_officer
                st.session_state['order_officer_name'] = officer_options[selected_officer]
                st.rerun()
        else:
            st.info("Không có cán bộ khác trực tuyến")

    # Track checkbox
    st.markdown("---")
    st.subheader("🗺️ Lịch sử di chuyển")
    if 'show_tracks' not in st.session_state:
        st.session_state.show_tracks = {}
    if officers:
        for uid, info in officers.items():
            key = f"track_{uid}"
            checked = st.checkbox(
                f"Track của {info['name']}",
                value=st.session_state.show_tracks.get(uid, False),
                key=key
            )
            st.session_state.show_tracks[uid] = checked

    # Chat nội bộ
    st.markdown("---")
    st.subheader("💬 Chat nội bộ")
    # Hiển thị tin nhắn
    messages_ref = db.child("messages").order_by_child("timestamp").limit_to_last(50)
    messages = messages_ref.get().val()
    if messages:
        sorted_msgs = sorted(messages.items(), key=lambda x: x[1]["timestamp"])
        for key, msg in sorted_msgs:
            vn_time = datetime.fromtimestamp(
                msg["timestamp"]/1000, tz=timezone(timedelta(hours=7))
            ).strftime("%H:%M")
            is_me = (msg["from"] == username)
            align = "me" if is_me else "other"
            st.markdown(f"""
            <div class="chat-message {align}">
                <div class="chat-bubble {align}">
                    <b>{msg['name']}</b> <span style="font-size:11px;">{vn_time}</span><br>
                    {msg['message']}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Chưa có tin nhắn nào.")
    # Ô nhập tin nhắn
    with st.form("chat_form", clear_on_submit=True):
        message = st.text_input("Tin nhắn", placeholder="Nhập tin nhắn...", label_visibility="collapsed")
        sent = st.form_submit_button("Gửi")
        if sent and message.strip():
            chat_data = {
                "from": username,
                "name": name,
                "message": message,
                "timestamp": int(time.time() * 1000)
            }
            db.child("messages").push(chat_data)
            # Giới hạn 200 tin nhắn
            all_msgs = db.child("messages").order_by_child("timestamp").get().val()
            if all_msgs and len(all_msgs) > 200:
                sorted_all = sorted(all_msgs.items(), key=lambda x: x[1]["timestamp"])
                for k, _ in sorted_all[:-200]:
                    db.child("messages").child(k).remove()
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# 12. MAP (NÂNG CẤP)
# ==============================
alert_sound_base64 = get_base64("alert.mp3")
show_tracks_json = json.dumps(st.session_state.get("show_tracks", {}))
fcm_vapid_key = st.secrets.get("fcm", {}).get("vapid_key", "")
user_colors_json = json.dumps(user_colors)
user_role_json = json.dumps(user_role)
stationary_json = json.dumps(stationary_officers)

order_js = ""
if user_role == "commander" and st.session_state.get('order_officer_id'):
    order_js = f"""
    <script>
        window.pendingOrder = {{
            officerId: "{st.session_state['order_officer_id']}",
            officerName: "{st.session_state['order_officer_name']}"
        }};
    </script>
    """
    del st.session_state['order_officer_id']
    del st.session_state['order_officer_name']
else:
    order_js = "<script>window.pendingOrder = null;</script>"

map_html = f"""
<!DOCTYPE html><html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet-arrowheads@1.2.0/dist/leaflet-arrowheads.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet-arrowheads@1.2.0/dist/leaflet-arrowheads.js"></script>
<script src="https://cdn.jsdelivr.net/npm/nosleep.js@0.12.0/dist/NoSleep.min.js"></script>
<style>
    #map {{ height: 100%; width: 100%; }}
    .leaflet-container {{ will-change: transform; }}
    .leaflet-tooltip {{ background: transparent; border: none; box-shadow: none; font-weight: bold; color: #fff; text-shadow: 1px 1px 2px black; font-size: 12px; margin-top: -15px !important; white-space: nowrap; }}
    .alert-marker {{ width: 24px; height: 24px; background: red; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 20px red; animation: pulse 1s infinite; }}
    @keyframes pulse {{
        0% {{ transform: scale(1); opacity: 1; }}
        50% {{ transform: scale(1.5); opacity: 0.5; }}
        100% {{ transform: scale(1); opacity: 1; }}
    }}
    .incident-icon {{ background: #ffaa00; width: 30px; height: 30px; border-radius: 50%; text-align: center; line-height: 30px; font-size: 18px; border: 2px solid white; }}
    .selection-info {{ background: rgba(0,0,0,0.8); color: white; padding: 8px 15px; border-radius: 8px; border: 2px solid #ff8800; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }}
    .cancel-btn {{ background: #ff4444; color: white; border: none; border-radius: 5px; padding: 5px 12px; margin-left: 10px; cursor: pointer; font-size: 14px; }}
    * {{
        -webkit-user-select: none;
        user-select: none;
        -webkit-touch-callout: none;
    }}
</style>
</head>
<body>
{order_js}
<div id="map"></div>
<script type="module">
import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js";
import {{ getDatabase, ref, onChildAdded, onChildChanged, onChildRemoved, onValue, query, limitToLast, update, push, onDisconnect, get, serverTimestamp, off }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";
import {{ getMessaging, getToken, onMessage }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-messaging.js";

const firebaseConfig = {json.dumps(firebase_config)};
const app = initializeApp(firebaseConfig);
const db = getDatabase(app);
const messaging = getMessaging(app);

const myUsername = "{username}";
const myName = "{name}";
const userRole = {user_role_json};
const showTracks = {show_tracks_json};
const stationaryOfficers = {stationary_json};
const userColors = {user_colors_json};

function isValidVNCoordinate(lat, lng) {{
    if (typeof lat !== 'number' || typeof lng !== 'number') return false;
    if (lat === 0 && lng === 0) return false;
    return true;
}}

function haversine(lat1, lng1, lat2, lng2) {{
    const R = 6371e3;
    const φ1 = lat1 * Math.PI/180;
    const φ2 = lat2 * Math.PI/180;
    const Δφ = (lat2 - lat1) * Math.PI/180;
    const Δλ = (lng2 - lng1) * Math.PI/180;
    const a = Math.sin(Δφ/2)**2 + Math.cos(φ1)*Math.cos(φ2)*Math.sin(Δλ/2)**2;
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}}

let noSleep = new NoSleep();
document.addEventListener('click', function enableNoSleep() {{
    noSleep.enable();
    document.removeEventListener('click', enableNoSleep);
}});

if ('serviceWorker' in navigator && "{fcm_vapid_key}" !== "") {{
    navigator.serviceWorker.register('/firebase-messaging-sw.js')
        .then(registration => getToken(messaging, {{ vapidKey: "{fcm_vapid_key}" }}))
        .then(currentToken => {{
            if (currentToken) update(ref(db, 'fcm_tokens/' + myUsername), {{ token: currentToken }});
        }})
        .catch(err => console.log('FCM error:', err));
}}
onMessage(messaging, payload => {{
    new Notification(payload.notification.title, {{ body: payload.notification.body }});
}});

const savedCenter = sessionStorage.getItem('mapCenter');
const savedZoom = sessionStorage.getItem('mapZoom');
let map;
if (savedCenter && savedZoom) {{
    map = L.map('map', {{ preferCanvas: true, zoomAnimation: false, fadeAnimation: false, inertia: false }})
        .setView(JSON.parse(savedCenter), parseInt(savedZoom));
}} else {{
    map = L.map('map', {{ preferCanvas: true, zoomAnimation: false, fadeAnimation: false, inertia: false }})
        .setView([21.0285, 105.8542], 13);
}}

// LAYER CONTROL
const darkLayer = L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    maxZoom: 20,
    attribution: '&copy; Stadia Maps'
}});
const streetLayer = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
}});
darkLayer.addTo(map);
L.control.layers({{ "🌙 Dark": darkLayer, "🗺️ Street": streetLayer }}).addTo(map);
map.zoomControl.setPosition('bottomright');

map.on('moveend', () => {{
    const center = map.getCenter();
    sessionStorage.setItem('mapCenter', JSON.stringify([center.lat, center.lng]));
    sessionStorage.setItem('mapZoom', map.getZoom());
}});

const officerMarkers = {{}};
const alertMarkers = {{}};
const pointMarkers = {{}};
const incidentMarkers = {{}};
const trackPolylines = {{}};
const trackListeners = {{}};
const moveOrderLines = {{}};

let zoomedToMe = sessionStorage.getItem('zoomedToMe') === 'true';
let selectionMode = false;
let selectedOfficerId = null;
let selectedOfficerName = null;
let tempInfoControl = null;
let hasSelected = false;
let holdTimer = null;

const alertSound = new Audio("data:audio/mp3;base64,{alert_sound_base64}");
alertSound.preload = "auto";
if (!sessionStorage.getItem('audioActivated')) {{
    document.addEventListener("click", () => {{
        alertSound.load();
        sessionStorage.setItem('audioActivated', 'true');
    }}, {{ once: true }});
}} else {{
    alertSound.load();
}}

const alertIcon = L.divIcon({{
    className: '', html: '<div class="alert-marker"></div>',
    iconSize: [24, 24], popupAnchor: [0, -12]
}});
const incidentIcon = L.divIcon({{
    className: '', html: '<div class="incident-icon">📷</div>',
    iconSize: [30, 30], popupAnchor: [0, -15]
}});

if (navigator.geolocation && !zoomedToMe) {{
    navigator.geolocation.getCurrentPosition(
        (position) => {{
            const {{ latitude: lat, longitude: lng }} = position.coords;
            if (isValidVNCoordinate(lat, lng)) {{
                map.setView([lat, lng], 16);
                zoomedToMe = true;
                sessionStorage.setItem('zoomedToMe', 'true');
            }}
        }},
        (error) => console.warn("GPS fallback error:", error),
        {{ enableHighAccuracy: true, timeout: 10000 }}
    );
}}

stationaryOfficers.forEach(officer => {{
    if (isValidVNCoordinate(officer.lat, officer.lng)) {{
        L.circleMarker([officer.lat, officer.lng], {{
            radius: 8, color: 'orange', fillColor: 'orange', fillOpacity: 0.8, weight: 2,
            renderer: L.canvas()
        }}).addTo(map).bindTooltip(`⚠ ${{officer.name}} đứng yên >15 phút`);
    }}
}});

const officersRef = ref(db, 'officers');

function getOfficerColor(uid) {{
    return userColors[uid] || '#0066cc';
}}

function activateSelectionMode(officerId, officerName) {{
    if (selectionMode) return;
    selectionMode = true;
    selectedOfficerId = officerId;
    selectedOfficerName = officerName;
    hasSelected = false;

    const infoControl = L.control({{ position: 'topright' }});
    infoControl.onAdd = () => {{
        const div = L.DomUtil.create('div', 'selection-info');
        div.innerHTML = `
            <span>📍 Giữ 5 giây trên map để chọn điểm cho <b>${{officerName}}</b></span>
            <button id="cancel-order-btn" class="cancel-btn">Hủy</button>
        `;
        div.style.cursor = 'default';
        L.DomEvent.disableClickPropagation(div);
        return div;
    }};
    infoControl.addTo(map);
    tempInfoControl = infoControl;

    setTimeout(() => {{
        const cancelBtn = document.getElementById('cancel-order-btn');
        if (cancelBtn) {{
            cancelBtn.onclick = () => {{
                deactivateSelectionMode();
            }};
        }}
    }}, 100);

    map.getContainer().style.cursor = 'crosshair';

    map.on('touchstart', (e) => {{
        if (!selectionMode || hasSelected) return;
        const touch = e.originalEvent.touches[0];
        const latlng = map.mouseEventToLatLng(touch);
        holdTimer = setTimeout(() => {{
            if (hasSelected) return;
            hasSelected = true;
            const endLat = latlng.lat;
            const endLng = latlng.lng;
            const startMarker = officerMarkers[selectedOfficerId];
            if (startMarker) {{
                const startLatLng = startMarker.getLatLng();
                const orderData = {{
                    officerId: selectedOfficerId,
                    fromLat: startLatLng.lat,
                    fromLng: startLatLng.lng,
                    toLat: endLat,
                    toLng: endLng,
                    commanderName: myName,
                    commanderId: myUsername,
                    timestamp: Date.now(),
                    status: 'active'
                }};
                push(ref(db, 'move_orders'), orderData);
                const marker = L.marker([endLat, endLng]).addTo(map);
                marker.bindPopup("📍 Đã chọn điểm (giữ 5s)").openPopup();
                setTimeout(() => map.removeLayer(marker), 5000);
                if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
            }}
            deactivateSelectionMode();
        }}, 5000);
    }});
    map.on('touchend', () => {{
        clearTimeout(holdTimer);
    }});
    map.on('touchcancel', () => {{
        clearTimeout(holdTimer);
    }});
}}

function deactivateSelectionMode() {{
    if (!selectionMode) return;
    if (tempInfoControl) map.removeControl(tempInfoControl);
    map.getContainer().style.cursor = '';
    if (holdTimer) clearTimeout(holdTimer);
    selectionMode = false;
    selectedOfficerId = null;
    selectedOfficerName = null;
    tempInfoControl = null;
    hasSelected = false;
}}

// MARKER VỚI TÊN
function createOfficerMarker(lat, lng, name, color) {{
    const icon = L.divIcon({{
        html: `
            <div style="display:flex; flex-direction:column; align-items:center;">
                <div style="
                    width:22px;
                    height:22px;
                    background:${{color}};
                    border-radius:50%;
                    border:3px solid white;
                    box-shadow:0 0 12px ${{color}};
                "></div>
                <div style="
                    font-size:11px;
                    color:white;
                    margin-top:2px;
                    text-shadow: 1px 1px 0 black;
                ">${{name}}</div>
            </div>
        `,
        className: '',
        iconSize: [40, 40],
        popupAnchor: [0, -15]
    }});
    return L.marker([lat, lng], {{ icon: icon }});
}}

onChildAdded(officersRef, (data) => {{
    const officer = data.val();
    const id = data.key;
    if (!isValidVNCoordinate(officer.lat, officer.lng)) return;
    const color = getOfficerColor(id);
    const marker = createOfficerMarker(officer.lat, officer.lng, officer.name, color).addTo(map);
    marker.bindTooltip(officer.name, {{ permanent: true, direction: 'top', offset: [0, -22], className: 'officer-label' }});
    marker.on('click', () => {{
        map.flyTo(marker.getLatLng(), 18);
    }});
    officerMarkers[id] = marker;
    if (id === myUsername && !zoomedToMe) {{
        map.setView([officer.lat, officer.lng], 16);
        zoomedToMe = true;
        sessionStorage.setItem('zoomedToMe', 'true');
    }}
}});

onChildChanged(officersRef, (data) => {{
    const officer = data.val();
    const id = data.key;
    if (!isValidVNCoordinate(officer.lat, officer.lng)) return;
    const marker = officerMarkers[id];
    if (!marker) return;
    const start = marker.getLatLng();
    const end = L.latLng(officer.lat, officer.lng);
    const steps = 5;
    let step = 0;
    function animate() {{
        step++;
        const lat = start.lat + (end.lat - start.lat) * (step / steps);
        const lng = start.lng + (end.lng - start.lng) * (step / steps);
        marker.setLatLng([lat, lng]);
        // Cập nhật lại icon (giữ tên)
        marker.setIcon(createOfficerMarker(lat, lng, officer.name, getOfficerColor(id)).options.icon);
        if (step < steps) requestAnimationFrame(animate);
    }}
    animate();
    marker.setTooltipContent(officer.name);
    if (id === myUsername) {{
        map.setView([officer.lat, officer.lng], map.getZoom());
    }}
}});

onChildRemoved(officersRef, (data) => {{
    const id = data.key;
    if (officerMarkers[id]) {{
        map.removeLayer(officerMarkers[id]);
        delete officerMarkers[id];
    }}
}});

// ONLINE STATUS
const OFFLINE_TIMEOUT = 60000;
function updateOnlineStatus() {{
    const now = Date.now();
    get(officersRef).then((snapshot) => {{
        const officers = snapshot.val() || {{}};
        Object.keys(officers).forEach(uid => {{
            const marker = officerMarkers[uid];
            if (marker) {{
                const lastUpdate = officers[uid].lastUpdate;
                if (lastUpdate === 0 || now - lastUpdate > OFFLINE_TIMEOUT) {{
                    // Đổi màu xám
                    marker.setIcon(createOfficerMarker(marker.getLatLng().lat, marker.getLatLng().lng, officers[uid].name, '#aaa').options.icon);
                }} else {{
                    const originalColor = getOfficerColor(uid);
                    marker.setIcon(createOfficerMarker(marker.getLatLng().lat, marker.getLatLng().lng, officers[uid].name, originalColor).options.icon);
                }}
            }}
        }});
    }}).catch(console.error);
}}
setInterval(updateOnlineStatus, 30000);

// ALERTS
const alertsRef = ref(db, 'alerts');
const oneDayAgo = Date.now() - 24*60*60*1000;
function getAlertPopupContent(alert) {{
    let distanceText = "";
    if (officerMarkers[myUsername]) {{
        const myLatLng = officerMarkers[myUsername].getLatLng();
        const distance = haversine(myLatLng.lat, myLatLng.lng, alert.lat, alert.lng);
        distanceText = `<br>Khoảng cách: ${{(distance/1000).toFixed(2)}} km`;
    }}
    let statusText = "";
    if (alert.status === "pending") statusText = "🟥 Chưa xử lý";
    else if (alert.status === "accepted") {{
        if (alert.accepted_by) statusText = `🟨 Đang xử lý bởi ${{alert.accepted_by}}`;
        else statusText = "🟨 Đang xử lý";
    }}
    else if (alert.status === "resolved") statusText = "🟩 Đã xong";
    else statusText = "Không rõ";
    return `🚨 <b>Báo động từ ${{alert.name}}</b><br> Trạng thái: ${{statusText}}${{distanceText}}<br> ${{new Date(alert.timestamp).toLocaleString()}}`;
}}
onChildAdded(alertsRef, (data) => {{
    const alert = data.val();
    const id = data.key;
    if (alert.timestamp && alert.timestamp > oneDayAgo && isValidVNCoordinate(alert.lat, alert.lng)) {{
        const marker = L.marker([alert.lat, alert.lng], {{ icon: alertIcon }})
            .addTo(map)
            .bindPopup(getAlertPopupContent(alert));
        alertMarkers[id] = marker;
        if (alert.name !== myName) {{
            alertSound.currentTime = 0;
            alertSound.play().catch(e => console.log("Audio play error:", e));
            map.flyTo([alert.lat, alert.lng], 17, {{ animate: true, duration: 1.5 }});
        }}
    }}
}});
onChildChanged(alertsRef, (data) => {{
    const alert = data.val();
    const id = data.key;
    if (alertMarkers[id]) alertMarkers[id].setPopupContent(getAlertPopupContent(alert));
}});
onChildRemoved(alertsRef, (data) => {{
    const id = data.key;
    if (alertMarkers[id]) {{
        map.removeLayer(alertMarkers[id]);
        delete alertMarkers[id];
    }}
}});

// MARKERS (ghi chú)
const markersRootRef = ref(db, 'markers');
onChildAdded(markersRootRef, (userSnapshot) => {{
    const userId = userSnapshot.key;
    const userMarkersRef = ref(db, `markers/${{userId}}`);
    onChildAdded(userMarkersRef, (markerSnapshot) => {{
        const point = markerSnapshot.val();
        const markerId = markerSnapshot.key;
        const fullId = `${{userId}}_${{markerId}}`;
        const age = Date.now() - point.timestamp;
        if (age > 24*60*60*1000) {{
            update(ref(db, `markers/${{userId}}/${{markerId}}`), null);
            return;
        }}
        if (isValidVNCoordinate(point.lat, point.lng)) {{
            const marker = L.circleMarker([point.lat, point.lng], {{
                radius: 6, color: '#ffaa00', fillColor: '#ffaa00', fillOpacity: 0.8, weight: 1,
                renderer: L.canvas()
            }}).addTo(map);
            marker.bindPopup(`<b>${{point.created_by}}</b><br>${{point.note}}<br>${{new Date(point.timestamp).toLocaleString()}}`);
            pointMarkers[fullId] = marker;
        }}
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

// INCIDENTS
const incidentsRef = ref(db, 'incidents');
onChildAdded(incidentsRef, (data) => {{
    const inc = data.val();
    const id = data.key;
    const age = Date.now() - inc.timestamp;
    if (age > 24*60*60*1000) {{
        update(ref(db, 'incidents/' + id), null);
        return;
    }}
    if (isValidVNCoordinate(inc.lat, inc.lng)) {{
        const marker = L.marker([inc.lat, inc.lng], {{ icon: incidentIcon }})
            .addTo(map)
            .bindPopup(`<b>${{inc.created_by}}</b><br> ${{inc.note}}<br> <img src="${{inc.image_url}}" style="max-width:200px; max-height:200px;"><br> ${{new Date(inc.timestamp).toLocaleString()}}`);
        incidentMarkers[id] = marker;
    }}
}});
onChildRemoved(incidentsRef, (data) => {{
    const id = data.key;
    if (incidentMarkers[id]) {{
        map.removeLayer(incidentMarkers[id]);
        delete incidentMarkers[id];
    }}
}});

// GHI CHÚ BẰNG GIỮ 2 GIÂY (CHỈ KHI KHÔNG Ở CHẾ ĐỘ CHỌN LỆNH)
if (userRole !== 'commander') {{
    let pressTimerMarker = null;
    map.on('touchstart', (e) => {{
        if (selectionMode) return;
        const touch = e.originalEvent.touches[0];
        const latlng = map.mouseEventToLatLng(touch);
        pressTimerMarker = setTimeout(() => {{
            const note = prompt("Nhập ghi chú cho điểm này:");
            if (note && note.trim()) {{
                push(ref(db, 'markers/' + myUsername), {{
                    created_by: myName,
                    lat: latlng.lat,
                    lng: latlng.lng,
                    note: note,
                    timestamp: Date.now()
                }});
            }}
        }}, 2000);
    }});
    map.on('touchend', () => clearTimeout(pressTimerMarker));
    map.on('touchcancel', () => clearTimeout(pressTimerMarker));
}}
map.on('contextmenu', (e) => {{
    if (selectionMode) return;
    e.originalEvent.preventDefault();
    const note = prompt("Nhập ghi chú cho điểm này:");
    if (note && note.trim()) {{
        push(ref(db, 'markers/' + myUsername), {{
            created_by: myName,
            lat: e.latlng.lat,
            lng: e.latlng.lng,
            note: note,
            timestamp: Date.now()
        }});
    }}
}});

// TRACKS
function loadUserTracks(userId, userName, show) {{
    const tracksRef = ref(db, 'tracks/' + userId + '/points');
    const tracksQuery = query(tracksRef, limitToLast(30));
    if (!show) {{
        if (trackPolylines[userId]) {{
            map.removeLayer(trackPolylines[userId]);
            delete trackPolylines[userId];
        }}
        if (trackListeners[userId]) {{
            off(tracksQuery);
            trackListeners[userId] = false;
        }}
        return;
    }}
    if (trackListeners[userId]) return;
    trackListeners[userId] = true;
    if (!trackPolylines[userId]) {{
        const hue = (userName.split('').reduce((a,b) => a + b.charCodeAt(0), 0) * 31) % 360;
        const color = `hsl(${{hue}}, 70%, 50%)`;
        trackPolylines[userId] = L.polyline([], {{
            color: color, weight: 3, opacity: 0.7, smoothFactor: 5, noClip: true, renderer: L.canvas()
        }}).addTo(map);
    }}
    onChildAdded(tracksQuery, (snapshot) => {{
        const point = snapshot.val();
        if (point && point.lat && point.lng && isValidVNCoordinate(point.lat, point.lng)) {{
            trackPolylines[userId].addLatLng([point.lat, point.lng]);
            if (trackPolylines[userId].getLatLngs().length > 30) {{
                const latlngs = trackPolylines[userId].getLatLngs();
                const smoothed = latlngs.filter((_, i) => i % 2 === 0);
                trackPolylines[userId].setLatLngs(smoothed);
            }}
        }}
    }});
}}
onValue(officersRef, (snapshot) => {{
    const officers = snapshot.val() || {{}};
    Object.keys(officers).forEach(uid => {{
        loadUserTracks(uid, officers[uid].name, showTracks[uid] || false);
    }});
}});

// MOVE ORDERS
const moveOrdersRef = ref(db, 'move_orders');
onChildAdded(moveOrdersRef, (snapshot) => {{
    const order = snapshot.val();
    const orderId = snapshot.key;
    if (!order || order.status !== 'active') return;
    if (!isValidVNCoordinate(order.toLat, order.toLng)) return;
    const latlngs = [[order.fromLat, order.fromLng], [order.toLat, order.toLng]];
    const polyline = L.polyline(latlngs, {{
        color: '#ff8800', weight: 4, opacity: 0.8, dashArray: '5, 10',
        renderer: L.canvas()
    }}).addTo(map);
    if (polyline.arrowheads) polyline.arrowheads({{ size: '12px', frequency: 'all', color: '#ff8800' }});
    const officerName = officerMarkers[order.officerId]?.getTooltip()?.getContent() || order.officerId;
    polyline.bindPopup(`📍 Lệnh di chuyển<br>Từ: ${{order.commanderName}}<br>Đến: ${{officerName}}<br>Điểm đến: ${{order.toLat.toFixed(6)}}, ${{order.toLng.toFixed(6)}}`);
    moveOrderLines[orderId] = polyline;
    if (order.officerId === myUsername) {{
        L.popup()
            .setLatLng([order.toLat, order.toLng])
            .setContent(`🚶 Bạn được lệnh di chuyển đến đây từ ${{order.commanderName}}`)
            .openOn(map);
    }}
}});
onChildRemoved(moveOrdersRef, (snapshot) => {{
    const orderId = snapshot.key;
    if (moveOrderLines[orderId]) {{
        map.removeLayer(moveOrderLines[orderId]);
        delete moveOrderLines[orderId];
    }}
}});
function checkOrdersCompletion() {{
    get(moveOrdersRef).then((snapshot) => {{
        const orders = snapshot.val() || {{}};
        for (const [orderId, order] of Object.entries(orders)) {{
            if (order.status !== 'active') continue;
            const officer = officerMarkers[order.officerId];
            if (!officer) continue;
            const officerPos = officer.getLatLng();
            const dist = haversine(officerPos.lat, officerPos.lng, order.toLat, order.toLng);
            if (dist < 20) {{
                update(ref(db, 'move_orders/' + orderId), null);
            }}
        }}
    }}).catch(console.error);
}}
setInterval(checkOrdersCompletion, 5000);

function zoomToAllOfficers() {{
    const markers = Object.values(officerMarkers);
    if (markers.length === 0) return;
    const group = L.featureGroup(markers);
    map.fitBounds(group.getBounds(), {{ padding: [50, 50], animate: false }});
}}
onValue(officersRef, (snapshot) => {{
    const officers = snapshot.val() || {{}};
    if (Object.keys(officers).length > 1) zoomToAllOfficers();
}});

// XỬ LÝ PENDING ORDER (chờ marker load)
if (window.pendingOrder && window.pendingOrder.officerId) {{
    const checkInterval = setInterval(() => {{
        if (officerMarkers[window.pendingOrder.officerId]) {{
            clearInterval(checkInterval);
            activateSelectionMode(window.pendingOrder.officerId, window.pendingOrder.officerName);
        }}
    }}, 200);
}}
</script>
</body></html>
"""

# Đặt map trong container
st.markdown('<div class="map-container">', unsafe_allow_html=True)
st.components.v1.html(map_html, height=800)
st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# 13. AUTO REFRESH
# ==============================
st_autorefresh(interval=10000, key="auto_refresh")
