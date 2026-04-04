import streamlit as st
import streamlit_authenticator as stauth
from streamlit_authenticator.utilities.hasher import Hasher
import yaml
from yaml.loader import SafeLoader
import pyrebase
import json
import time
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
        if lat == 0 and lng == 0:
            return False
        if lat < 8 or lat > 24 or lng < 102 or lng > 110:
            return False
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

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

* {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: #f3f4f6;
}

section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e5e7eb;
}
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stText,
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stCheckbox label {
    color: #1f2937 !important;
}
section[data-testid="stSidebar"] .stButton button {
    background: #2563eb;
    color: white;
    border-radius: 8px;
    font-weight: 500;
}
section[data-testid="stSidebar"] .stButton button:hover {
    background: #1d4ed8;
}
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {
    background-color: #f9fafb;
    border-color: #d1d5db;
}
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stTextArea textarea {
    background-color: #f9fafb;
    border-color: #d1d5db;
    color: #1f2937;
}

.stButton button {
    border-radius: 8px;
    font-weight: 500;
    border: none;
    transition: 0.2s;
}

.dashboard-card {
    background: white;
    padding: 20px;
    border-radius: 20px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.05);
    margin-bottom: 20px;
}

.custom-header {
    margin-bottom: 1.5rem;
}
.custom-header h2 {
    color: #1f2937;
    margin-bottom: 0;
    font-weight: 700;
}
.custom-header p {
    color: #6b7280;
    margin-top: 4px;
}

.sidebar-group {
    margin-bottom: 24px;
}
.sidebar-group h3 {
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #6b7280;
    margin-bottom: 12px;
    font-weight: 600;
}
.sidebar-card {
    background: #f9fafb;
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 12px;
    border: 1px solid #e5e7eb;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="custom-header">
    <h2>🚔 Hệ thống điều hành tuần tra</h2>
    <p>Realtime tracking & coordination</p>
</div>
""", unsafe_allow_html=True)

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

# Xóa dữ liệu vị trí cũ nếu quá hạn (20 phút)
existing = db.child("officers").child(username).get().val()
if existing:
    last_update = existing.get("lastUpdate")
    now_ms = int(time.time() * 1000)
    if last_update and (now_ms - int(last_update)) > 20 * 60 * 1000:
        db.child("officers").child(username).remove()
        st.sidebar.info("Đã xóa dữ liệu vị trí cũ (quá hạn). Vui lòng bắt đầu chia sẻ lại.")
    else:
        st.sidebar.info("Đã khôi phục vị trí từ phiên trước.")

db.child("users").child(username).set({
    "name": name,
    "role": user_role,
    "color": user_colors[username],
    "last_seen": int(time.time() * 1000)
})

# ==============================
# 6. CHIA SẺ VỊ TRÍ (có lưu session_state)
# ==============================
if "sharing" not in st.session_state:
    existing = db.child("officers").child(username).get().val()
    if existing and existing.get("lastUpdate"):
        st.session_state.sharing = True
    else:
        st.session_state.sharing = False

# Lưu vị trí cuối cùng của Commander vào session_state để dùng khi rerun
if "last_position" not in st.session_state:
    st.session_state.last_position = None

col1, col2 = st.columns([1, 5])
with col1:
    if not st.session_state.sharing:
        if st.button("📡 Bắt đầu chia sẻ vị trí"):
            db.child("officers").child(username).remove()
            st.session_state.sharing = True
            # Xóa vị trí cũ trong session_state
            st.session_state.last_position = None
            st.rerun()
    else:
        if st.button("🛑 Dừng chia sẻ"):
            db.child("officers").child(username).remove()
            st.session_state.sharing = False
            st.session_state.last_position = None
            st.rerun()

# ==============================
# 7. TÌM CÁN BỘ GẦN NHẤT
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

# ==============================
# 8. GPS SCRIPT (cập nhật Firebase)
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
        serverTimestamp
    }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js";

    const firebaseConfig = {json.dumps(firebase_config)};
    const app = initializeApp(firebaseConfig);
    const database = getDatabase(app);

    const username = "{username}";
    const officerName = "{name}";
    const officerRef = ref(database, 'officers/' + username);

    onDisconnect(officerRef).remove();

    update(officerRef, {{
        name: officerName,
        lastUpdate: serverTimestamp()
    }});

    let lastLat = null;
    let lastLng = null;
    let lastSendTime = 0;
    const SEND_INTERVAL = 5000;
    const MIN_DISTANCE = 10;

    function isValidVNCoordinate(lat, lng) {{
        if (typeof lat !== 'number' || typeof lng !== 'number') return false;
        if (lat === 0 && lng === 0) return false;
        if (lat < 8 || lat > 24 || lng < 102 || lng > 110) return false;
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

    let fallbackLat = null;
    let fallbackLng = null;
    fetch("https://ipapi.co/json/")
        .then(res => res.json())
        .then(data => {{
            if (data.latitude && data.longitude && isValidVNCoordinate(data.latitude, data.longitude)) {{
                fallbackLat = data.latitude;
                fallbackLng = data.longitude;
            }} else {{
                fallbackLat = 21.0285;
                fallbackLng = 105.8542;
            }}
        }})
        .catch(err => {{
            fallbackLat = 21.0285;
            fallbackLng = 105.8542;
        }});

    if (navigator.geolocation) {{
        navigator.geolocation.watchPosition(function(position){{
            let accuracy = position.coords.accuracy;
            if(accuracy > 100) return;

            let lat = position.coords.latitude;
            let lng = position.coords.longitude;

            if (!isValidVNCoordinate(lat, lng)) {{
                if (fallbackLat && fallbackLng) {{
                    lat = fallbackLat;
                    lng = fallbackLng;
                }} else {{
                    return;
                }}
            }}

            if(lastLat !== null){{
                const dist = distance(lastLat, lastLng, lat, lng);
                if(dist < MIN_DISTANCE) return;
            }}

            const now = Date.now();
            if (now - lastSendTime < SEND_INTERVAL) return;
            lastSendTime = now;

            update(officerRef, {{
                name: officerName,
                lat: lat,
                lng: lng,
                accuracy: accuracy,
                lastUpdate: serverTimestamp()
            }});

            if(lastLat !== null && distance(lastLat, lastLng, lat, lng) > 15) {{
                push(ref(database, 'tracks/'+username+'/points'), {{
                    lat: lat,
                    lng: lng,
                    timestamp: serverTimestamp()
                }});
            }}
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
    </script>
    <div style="text-align: center; color: green;">📡 Đang chia sẻ vị trí...</div>
    """
    st.components.v1.html(gps_script, height=60)

# ==============================
# 9. FCM
# ==============================
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
# 10. CLEANUP
# ==============================
def cleanup_old_data():
    try:
        incidents = db.child("incidents").get().val()
        if incidents:
            now = int(time.time() * 1000)
            for key, inc in incidents.items():
                if now - inc.get("timestamp", 0) > 24 * 3600 * 1000:
                    db.child("incidents").child(key).remove()
        
        alerts = db.child("alerts").get().val()
        if alerts:
            now = int(time.time() * 1000)
            for key, alert in alerts.items():
                if now - alert.get("timestamp", 0) > 60 * 60 * 1000:
                    db.child("alerts").child(key).remove()
        
        drawings = db.child("drawings").get().val()
        if drawings:
            now = int(time.time() * 1000)
            for key, drawing in drawings.items():
                if now - drawing.get("timestamp", 0) > 24 * 3600 * 1000:
                    db.child("drawings").child(key).remove()
        
        markers = db.child("markers").get().val()
        if markers:
            now = int(time.time() * 1000)
            for uid, user_markers in markers.items():
                if user_markers and isinstance(user_markers, dict):
                    for marker_key, marker in user_markers.items():
                        if now - marker.get("timestamp", 0) > 24 * 3600 * 1000:
                            db.child("markers").child(uid).child(marker_key).remove()
        
        move_orders = db.child("move_orders").get().val()
        if move_orders:
            now = int(time.time() * 1000)
            for key, order in move_orders.items():
                if now - order.get("timestamp", 0) > 30 * 60 * 1000:
                    db.child("move_orders").child(key).remove()
                    
    except Exception as e:
        print("Cleanup error:", e)

def cleanup_offline_officers():
    try:
        officers = db.child("officers").get().val()
        if not officers:
            return
        now = int(time.time() * 1000)
        limit = 20 * 60 * 1000
        for uid, data in officers.items():
            last_update = data.get("lastUpdate")
            if last_update and now - int(last_update) > limit:
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
            if len(points) > 150:
                sorted_points = sorted(points.items(), key=lambda x: x[1].get("timestamp", 0))
                for k, _ in sorted_points[:-150]:
                    db.child("tracks").child(uid).child("points").child(k).remove()
    except Exception as e:
        print("Limit tracks error:", e)

if "last_cleanup" not in st.session_state or time.time() - st.session_state.last_cleanup > 60:
    cleanup_old_data()
    cleanup_offline_officers()
    cleanup_old_tracks()
    limit_tracks()
    st.session_state.last_cleanup = time.time()

# ==============================
# 11. STATIONARY OFFICERS
# ==============================
def detect_stationary_officers():
    try:
        officers = db.child("officers").get().val()
        if not officers:
            return []
        now = int(time.time() * 1000)
        online_limit = 20 * 60 * 1000
        threshold = 15 * 60 * 1000
        stationary = []
        for uid, data in officers.items():
            last = data.get("lastUpdate")
            if last and (now - int(last)) < online_limit and is_valid_coordinate(data.get("lat"), data.get("lng")):
                if (now - int(last)) > threshold:
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
# 12. SIDEBAR (CÁC CHỨC NĂNG)
# ==============================
st.sidebar.markdown('<div class="sidebar-group"><h3>🚨 ĐIỀU HÀNH</h3></div>', unsafe_allow_html=True)
with st.sidebar:
    st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
    if st.button("🚨 Gửi báo động", key="alert_btn"):
        user_data = db.child("officers").child(username).get().val()
        if user_data and is_valid_coordinate(user_data.get("lat"), user_data.get("lng")):
            lat = user_data["lat"]
            lng = user_data["lng"]
            nearest = find_nearest_officers(lat, lng)
            alert_data = {
                "name": name,
                "lat": lat,
                "lng": lng,
                "assigned": nearest,
                "status": "pending",
                "timestamp": int(time.time() * 1000),
                "created_by": username
            }
            db.child("alerts").push(alert_data)
            server_key = st.secrets.get("fcm", {}).get("server_key", "")
            if server_key:
                tokens = db.child("fcm_tokens").get().val() or {}
                for uid in nearest:
                    if uid != username and uid in tokens:
                        token = tokens[uid].get("token") if isinstance(tokens[uid], dict) else tokens[uid]
                        if token:
                            send_fcm_notification("🚨 BÁO ĐỘNG", f"Báo động từ {name}", token, server_key)
            st.success("Đã gửi báo động!")
        else:
            st.error("Bạn chưa chia sẻ vị trí hợp lệ hoặc vị trí không xác định")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
    if st.button("✅ Nhận nhiệm vụ gần nhất", key="accept_mission"):
        alerts = db.child("alerts").get().val()
        if alerts:
            found = False
            for key, alert in alerts.items():
                assigned = alert.get("assigned", [])
                if username in assigned and alert.get("status") == "pending":
                    try:
                        resolved_data = {
                            "original_id": key,
                            "name": alert.get("name"),
                            "lat": alert.get("lat"),
                            "lng": alert.get("lng"),
                            "assigned": assigned,
                            "accepted_by": name,
                            "accepted_at": int(time.time() * 1000),
                            "timestamp": alert.get("timestamp")
                        }
                        db.child("resolved_alerts").push(resolved_data)
                        db.child("alerts").child(key).remove()
                        chat_message = {
                            "from": "system",
                            "name": "Hệ thống",
                            "message": f"✅ {name} đã nhận và xử lý báo động từ {alert.get('name', 'cán bộ')}",
                            "timestamp": int(time.time() * 1000)
                        }
                        db.child("messages").push(chat_message)
                        st.success(f"✅ Đã nhận và xóa báo động từ {alert.get('name', 'cán bộ')}")
                        found = True
                        break
                    except Exception as e:
                        st.error(f"Lỗi khi nhận nhiệm vụ: {e}")
            if not found:
                st.info("Không có nhiệm vụ nào đang chờ xử lý cho bạn")
        else:
            st.info("Không có báo động nào")
    st.markdown('</div>', unsafe_allow_html=True)

st.sidebar.markdown('<div class="sidebar-group"><h3>📍 TÁC VỤ CÁ NHÂN</h3></div>', unsafe_allow_html=True)
with st.sidebar:
    with st.expander("📍 Đánh dấu điểm"):
        note = st.text_area("Ghi chú")
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

if user_role in ["commander", "admin"]:
    st.sidebar.markdown('<div class="sidebar-group"><h3>⚙️ HỆ THỐNG</h3></div>', unsafe_allow_html=True)
    if user_role == "commander":
        with st.sidebar:
            st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
            if st.button("🗑️ Xóa ghi chú (toàn bộ)", key="delete_all_markers"):
                try:
                    db.child("markers").remove()
                    st.success("Đã xóa toàn bộ ghi chú!")
                except Exception as e:
                    st.error(f"Lỗi xóa: {e}")
            st.markdown('</div>', unsafe_allow_html=True)

    if user_role == "admin":
        with st.sidebar:
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

st.sidebar.markdown('<div class="sidebar-group"><h3>🗺️ LỊCH SỬ DI CHUYỂN</h3></div>', unsafe_allow_html=True)
with st.sidebar:
    if 'show_tracks' not in st.session_state:
        st.session_state.show_tracks = {}

# ==============================
# 13. LOAD DỮ LIỆU VỚI CACHE (TTL ngắn để lấy dữ liệu mới)
# ==============================
@st.cache_data(ttl=5, show_spinner=False)
def load_officers_cached():
    try:
        result = db.child("officers").get().val()
        if result:
            now = int(time.time() * 1000)
            online_limit = 20 * 60 * 1000
            filtered = {}
            for uid, data in result.items():
                last_update = data.get("lastUpdate")
                if last_update and (now - int(last_update)) < online_limit:
                    if is_valid_coordinate(data.get("lat"), data.get("lng")):
                        filtered[uid] = data
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

# ==============================
# 14. CHECKBOX TRACK
# ==============================
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
# 15. CHUẨN BỊ MAP (truyền initialOfficers)
# ==============================
alert_sound_base64 = get_base64("alert.mp3")
show_tracks_json = json.dumps(st.session_state.get("show_tracks", {}))
fcm_vapid_key = st.secrets.get("fcm", {}).get("vapid_key", "")

stationary_officers = detect_stationary_officers()
stationary_json = json.dumps(stationary_officers)
user_colors_json = json.dumps(user_colors)
user_role_json = json.dumps(user_role)

# Lấy danh sách officers hiện tại (bao gồm cả Commander nếu đang online)
initial_officers = load_officers_cached()
# Chuyển đổi thành dict phù hợp với cấu trúc JavaScript
initial_officers_json = json.dumps(initial_officers)

try:
    officers_old = db.child("officers").get().val()
    if officers_old:
        now = int(time.time() * 1000)
        online_limit = 20 * 60 * 1000
        for uid, data in officers_old.items():
            last_update = data.get("lastUpdate")
            if last_update and (now - int(last_update)) > online_limit:
                db.child("officers").child(uid).remove()
except Exception as e:
    print("Cleanup error:", e)

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

# ==============================
# 16. MAP HTML HOÀN CHỈNH (có initialOfficers)
# ==============================
map_html = f"""
<!DOCTYPE html><html> <head> <meta charset="utf-8"/> <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes"> 
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/> 
<link rel="stylesheet" href="https://unpkg.com/leaflet-arrowheads@1.2.0/dist/leaflet-arrowheads.css" /> 
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script> 
<script src="https://unpkg.com/leaflet-arrowheads@1.2.0/dist/leaflet-arrowheads.js"></script> 
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://cdn.jsdelivr.net/npm/nosleep.js@0.12.0/dist/NoSleep.min.js"></script> 
<style> 
    #map {{ height: 600px; width: 100%; }} 
    .leaflet-container {{ will-change: transform; }} 
    .leaflet-tooltip {{ background: transparent; border: none; box-shadow: none; font-weight: bold; color: #333; text-shadow: 1px 1px 2px white; font-size: 12px; margin-top: -15px !important; white-space: nowrap; }} 
    .alert-marker {{ width: 24px; height: 24px; background: red; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 20px red; animation: pulse 1s infinite; }} 
    @keyframes pulse {{ 0% {{ transform: scale(1); opacity: 1; }} 50% {{ transform: scale(1.5); opacity: 0.5; }} 100% {{ transform: scale(1); opacity: 1; }} }} 
    .incident-icon {{ background: #ffaa00; width: 30px; height: 30px; border-radius: 50%; text-align: center; line-height: 30px; font-size: 18px; border: 2px solid white; }} 
    .selection-info {{ background: white; padding: 8px 15px; border-radius: 8px; border: 2px solid #ff8800; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }} 
    .cancel-btn {{ background: #ff4444; color: white; border: none; border-radius: 5px; padding: 5px 12px; margin-left: 10px; cursor: pointer; font-size: 14px; }} 
    .leaflet-marker-icon {{ transition: transform 0.2s ease; }}
    .leaflet-marker-icon:hover {{ transform: scale(1.3); }}
    * {{ -webkit-user-select: none; user-select: none; -webkit-touch-callout: none; }}
    .custom-dialog {{
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: white;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        z-index: 2000;
        width: 280px;
        padding: 16px;
        font-family: sans-serif;
    }}
    .custom-dialog h4 {{ margin-top: 0; margin-bottom: 12px; }}
    .custom-dialog input, .custom-dialog select {{ width: 100%; padding: 8px; margin-bottom: 12px; border: 1px solid #ccc; border-radius: 6px; }}
    .custom-dialog button {{ padding: 8px 12px; margin-right: 8px; border: none; border-radius: 6px; cursor: pointer; }}
    .dialog-overlay {{ position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1999; }}
    .delete-btn {{ background: #ff4444; color: white; border: none; border-radius: 4px; padding: 4px 8px; cursor: pointer; font-size: 12px; margin-top: 5px; }}
    .clear-orders-btn {{ position: absolute; top: 10px; right: 10px; background: #ff8800; color: white; border: none; border-radius: 4px; padding: 6px 12px; cursor: pointer; z-index: 1000; font-size: 14px; font-weight: bold; }}
    .drawing-toolbar button {{
        cursor: pointer;
        border: none;
        border-radius: 4px;
        font-size: 14px;
        margin: 2px;
        padding: 4px 8px;
    }}
    .drawing-toolbar button:hover {{
        opacity: 0.8;
    }}
    .drawing-info {{
        background: white;
        padding: 5px 10px;
        border-radius: 8px;
        font-weight: bold;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }}
    .delete-drawing {{
        background: #ff4444;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 4px 8px;
        margin-top: 5px;
        cursor: pointer;
    }}
</style>
<body> {order_js} <div id="map"></div> 
<script type="module"> 
import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js"; 
import {{ getDatabase, ref, onChildAdded, onChildChanged, onChildRemoved, onValue, query, limitToLast, update, push, onDisconnect, get, serverTimestamp, off, remove }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js"; 
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
const initialOfficers = {initial_officers_json};

let map = null;
let officerClusterGroup = null;
let allOfficers = {{}};
let officerMarkersInCluster = {{}};
let alertMarkers = {{}};
let alertTimeouts = {{}};
let pointMarkers = {{}};
let incidentMarkers = {{}};
let trackPolylines = {{}};
let trackListeners = {{}};
let moveOrderLines = {{}};
let zoomedToMe = false;
let selectionMode = false;
let selectedOfficerId = null;
let selectedOfficerName = null;
let tempInfoControl = null;
let hasSelected = false;
let holdTimer = null;
let alertSound = null;
let audioActivated = false;

let drawingMode = false;
let tempPoints = [];
let tempPolyline = null;
let drawingColor = '#ff0000';
let drawingWeight = 3;

let renderTimeout = null;
const RENDER_DEBOUNCE = 100;
const VIEWPORT_PADDING = 0.1;

function isValidVNCoordinate(lat, lng) {{
    if (typeof lat !== 'number' || typeof lng !== 'number') return false;
    if (lat === 0 && lng === 0) return false;
    if (lat < 8 || lat > 24 || lng < 102 || lng > 110) return false;
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

function initAudio() {{
    if (alertSound) return;
    alertSound = new Audio("data:audio/mp3;base64,{alert_sound_base64}");
    alertSound.preload = "auto";
    alertSound.loop = false;
}}

function stopAlertSound() {{
    if (alertSound && !alertSound.paused) {{
        alertSound.pause();
        alertSound.currentTime = 0;
    }}
}}

function removeAlertMarker(alertId) {{
    if (alertMarkers[alertId]) {{
        map.removeLayer(alertMarkers[alertId]);
        delete alertMarkers[alertId];
    }}
    if (alertTimeouts[alertId]) {{
        clearTimeout(alertTimeouts[alertId]);
        delete alertTimeouts[alertId];
    }}
    if (Object.keys(alertMarkers).length === 0) stopAlertSound();
}}

function createOfficerIcon(color) {{
    return L.divIcon({{
        className: '',
        html: `<div style="background:${{color}}; width:22px; height:22px; border-radius:50%; border:3px solid white; box-shadow:0 0 12px ${{color}};"></div>`,
        iconSize: [22, 22],
        popupAnchor: [0, -12]
    }});
}}

function getOfficerColorWithStatus(uid, lastUpdate) {{
    if (uid === myUsername) return userColors[uid] || '#0066cc';
    const now = Date.now();
    const diff = now - lastUpdate;
    if (diff > 5 * 60 * 1000 && diff < 20 * 60 * 1000) {{
        return '#9ca3af';
    }}
    return userColors[uid] || '#0066cc';
}}

function renderVisibleOfficers() {{
    if (!map || !officerClusterGroup) return;
    const bounds = map.getBounds();
    const sw = bounds.getSouthWest();
    const ne = bounds.getNorthEast();
    const latPad = (ne.lat - sw.lat) * VIEWPORT_PADDING;
    const lngPad = (ne.lng - sw.lng) * VIEWPORT_PADDING;
    const paddedBounds = L.latLngBounds(
        [sw.lat - latPad, sw.lng - lngPad],
        [ne.lat + latPad, ne.lng + lngPad]
    );
    Object.entries(allOfficers).forEach(([uid, officer]) => {{
        if (!officer || !isValidVNCoordinate(officer.lat, officer.lng)) return;
        const isVisible = paddedBounds.contains([officer.lat, officer.lng]);
        const existingMarker = officerMarkersInCluster[uid];
        const lastUpdate = officer.lastUpdate || 0;
        const color = getOfficerColorWithStatus(uid, lastUpdate);
        if (isVisible) {{
            if (!existingMarker) {{
                const marker = L.marker([officer.lat, officer.lng], {{ icon: createOfficerIcon(color) }});
                marker.bindTooltip(officer.name || uid, {{ permanent: true, direction: 'top', offset: [0, -12] }});
                officerClusterGroup.addLayer(marker);
                officerMarkersInCluster[uid] = marker;
            }} else {{
                existingMarker.setLatLng([officer.lat, officer.lng]);
                existingMarker.setIcon(createOfficerIcon(color));
                existingMarker.setTooltipContent(officer.name || uid);
            }}
        }} else {{
            if (existingMarker) {{
                officerClusterGroup.removeLayer(existingMarker);
                delete officerMarkersInCluster[uid];
            }}
        }}
    }});
}}

function scheduleRender() {{
    if (renderTimeout) clearTimeout(renderTimeout);
    renderTimeout = setTimeout(() => renderVisibleOfficers(), RENDER_DEBOUNCE);
}}

function initMap() {{
    const savedCenter = sessionStorage.getItem('mapCenter');
    const savedZoom = sessionStorage.getItem('mapZoom');
    if (savedCenter && savedZoom) {{
        map = L.map('map', {{ preferCanvas: true, zoomAnimation: false, fadeAnimation: false, inertia: false }})
            .setView(JSON.parse(savedCenter), parseInt(savedZoom));
    }} else {{
        map = L.map('map', {{ preferCanvas: true, zoomAnimation: false, fadeAnimation: false, inertia: false }})
            .setView([21.0285, 105.8542], 13);
    }}
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 20,
        updateWhenZooming: false
    }}).addTo(map);
    officerClusterGroup = L.markerClusterGroup({{
        chunkedLoading: true,
        maxClusterRadius: 80,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true
    }});
    map.addLayer(officerClusterGroup);
    map.on('moveend', () => {{
        const center = map.getCenter();
        sessionStorage.setItem('mapCenter', JSON.stringify([center.lat, center.lng]));
        sessionStorage.setItem('mapZoom', map.getZoom());
        scheduleRender();
    }});
    if (navigator.geolocation && !sessionStorage.getItem('zoomedToMe')) {{
        navigator.geolocation.getCurrentPosition(
            (position) => {{
                const {{ latitude: lat, longitude: lng }} = position.coords;
                if (isValidVNCoordinate(lat, lng)) {{
                    map.setView([lat, lng], 16);
                    sessionStorage.setItem('zoomedToMe', 'true');
                }}
            }},
            (error) => console.warn("GPS fallback error:", error),
            {{ enableHighAccuracy: true, timeout: 10000 }}
        );
    }}
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

initMap();
initAudio();

document.addEventListener("click", () => {{
    if (!audioActivated && alertSound) {{
        alertSound.load();
        audioActivated = true;
    }}
}});

// Khởi tạo allOfficers từ dữ liệu ban đầu (đảm bảo Commander hiện ngay)
for (const [uid, officer] of Object.entries(initialOfficers)) {{
    if (officer && isValidVNCoordinate(officer.lat, officer.lng)) {{
        allOfficers[uid] = officer;
    }}
}}
// Render ngay lập tức
scheduleRender();

// Sau đó mới lắng nghe realtime từ Firebase
const officersRef = ref(db, 'officers');
onDisconnect(ref(db, 'officers/' + myUsername)).remove();

onChildAdded(officersRef, (snapshot) => {{
    const id = snapshot.key;
    const officer = snapshot.val();
    if (!officer) return;
    if (typeof officer.lat !== 'number' || typeof officer.lng !== 'number') return;
    if (!isValidVNCoordinate(officer.lat, officer.lng)) return;
    allOfficers[id] = officer;
    scheduleRender();
    if (id === myUsername && !sessionStorage.getItem('zoomedToMe')) {{
        map.setView([officer.lat, officer.lng], 16);
        sessionStorage.setItem('zoomedToMe', 'true');
    }}
}});

onChildChanged(officersRef, (snapshot) => {{
    const id = snapshot.key;
    const officer = snapshot.val();
    if (!officer) return;
    if (typeof officer.lat !== 'number' || typeof officer.lng !== 'number') return;
    if (!isValidVNCoordinate(officer.lat, officer.lng)) return;
    allOfficers[id] = officer;
    scheduleRender();
}});

onChildRemoved(officersRef, (snapshot) => {{
    const id = snapshot.key;
    delete allOfficers[id];
    if (officerMarkersInCluster[id]) {{
        officerClusterGroup.removeLayer(officerMarkersInCluster[id]);
        delete officerMarkersInCluster[id];
    }}
}});

stationaryOfficers.forEach(officer => {{
    if (isValidVNCoordinate(officer.lat, officer.lng)) {{
        L.circleMarker([officer.lat, officer.lng], {{
            radius: 8, color: 'orange', fillColor: 'orange', fillOpacity: 0.8, weight: 2,
            renderer: L.canvas()
        }}).addTo(map).bindTooltip(`⚠ ${{officer.name}} đứng yên >15 phút`);
    }}
}});

// ==================== ALERTS ====================
const alertsRef = ref(db, 'alerts');
const oneDayAgo = Date.now() - 24*60*60*1000;
const playedAlerts = new Set(JSON.parse(sessionStorage.getItem("playedAlerts") || "[]"));
function savePlayedAlerts() {{ sessionStorage.setItem("playedAlerts", JSON.stringify([...playedAlerts])); }}

function getAlertPopupContent(alert) {{
    let distanceText = "";
    const myPos = allOfficers[myUsername];
    if (myPos && isValidVNCoordinate(myPos.lat, myPos.lng)) {{
        const distance = haversine(myPos.lat, myPos.lng, alert.lat, alert.lng);
        distanceText = `<br>Khoảng cách: ${{(distance/1000).toFixed(2)}} km`;
    }}
    let statusText = "";
    if (alert.status === "pending") statusText = "🟥 Chưa xử lý";
    else if (alert.status === "accepted") statusText = `🟨 Đang xử lý bởi ${{alert.accepted_by || ""}}`;
    else if (alert.status === "resolved") statusText = "🟩 Đã xong";
    else if (alert.status === "expired") statusText = "⏰ Hết hạn";
    else statusText = "Không rõ";
    return `🚨 <b>Báo động từ ${{alert.name}}</b><br> Trạng thái: ${{statusText}} ${{distanceText}}<br> ${{new Date(alert.timestamp).toLocaleString()}}`;
}}

const alertIcon = L.divIcon({{ className: '', html: '<div class="alert-marker"></div>', iconSize: [24, 24], popupAnchor: [0, -12] }});

onChildAdded(alertsRef, (data) => {{
    const alert = data.val();
    const id = data.key;
    if (!alert.timestamp || alert.timestamp < oneDayAgo) return;
    if (!isValidVNCoordinate(alert.lat, alert.lng)) return;
    if (!alertMarkers[id]) {{
        const marker = L.marker([alert.lat, alert.lng], {{ icon: alertIcon }})
            .addTo(map)
            .bindPopup(getAlertPopupContent(alert));
        alertMarkers[id] = marker;
    }}
    const now = Date.now();
    const isMyAlert = (alert.created_by === myUsername);
    const isRecent = (now - alert.timestamp) < 15000;
    if (!isMyAlert && isRecent && !playedAlerts.has(id)) {{
        playedAlerts.add(id);
        savePlayedAlerts();
        if (audioActivated && alertSound) {{
            alertSound.currentTime = 0;
            alertSound.play().catch(() => {{}});
        }}
        if (!map._animatingZoom) map.flyTo([alert.lat, alert.lng], 17, {{ animate: true, duration: 1.5 }});
        setTimeout(() => {{
            if (alertSound && !alertSound.paused) {{ alertSound.pause(); alertSound.currentTime = 0; }}
        }}, 15000);
        alertTimeouts[id] = setTimeout(() => {{
            get(ref(db, 'alerts/' + id)).then((snapshot) => {{
                const currentAlert = snapshot.val();
                if (currentAlert && currentAlert.status === 'pending') {{
                    removeAlertMarker(id);
                    update(ref(db, 'alerts/' + id), {{ status: 'expired' }});
                }}
            }});
        }}, 20000);
    }}
}});

onChildChanged(alertsRef, (data) => {{
    const alert = data.val();
    const id = data.key;
    if (alertMarkers[id]) {{
        alertMarkers[id].setPopupContent(getAlertPopupContent(alert));
        if (["accepted", "resolved", "expired"].includes(alert.status)) removeAlertMarker(id);
    }}
}});
onChildRemoved(alertsRef, (data) => {{ const id = data.key; removeAlertMarker(id); }});

// ==================== MARKERS ====================
const markersRootRef = ref(db, 'markers');
onChildAdded(markersRootRef, (userSnapshot) => {{
    const userId = userSnapshot.key;
    const userMarkersRef = ref(db, `markers/${{userId}}`);
    onChildAdded(userMarkersRef, (markerSnapshot) => {{
        const point = markerSnapshot.val();
        const markerId = markerSnapshot.key;
        const fullId = `${{userId}}_${{markerId}}`;
        const age = Date.now() - point.timestamp;
        if (age > 24*60*60*1000) {{ remove(ref(db, `markers/${{userId}}/${{markerId}}`)); return; }}
        if (isValidVNCoordinate(point.lat, point.lng)) {{
            const marker = L.circleMarker([point.lat, point.lng], {{
                radius: 6, color: '#ffaa00', fillColor: '#ffaa00', fillOpacity: 0.8, weight: 1,
                renderer: L.canvas()
            }}).addTo(map);
            let popupContent = `<b>${{point.created_by}}</b><br>${{point.note}}<br>${{new Date(point.timestamp).toLocaleString()}}`;
            const canDelete = (point.created_by === myName) || (userRole === 'commander') || (userRole === 'admin');
            if (canDelete) {{
                popupContent += `<br><button class="delete-btn" data-fullid="${{fullId}}" data-userid="${{userId}}" data-markerid="${{markerId}}">🗑️ Xoá điểm</button>`;
            }}
            marker.bindPopup(popupContent);
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

// ==================== INCIDENTS ====================
const incidentsRef = ref(db, 'incidents');
const incidentIcon = L.divIcon({{ className: '', html: '<div class="incident-icon">📷</div>', iconSize: [30, 30], popupAnchor: [0, -15] }});
onChildAdded(incidentsRef, (data) => {{
    const inc = data.val();
    const id = data.key;
    const age = Date.now() - inc.timestamp;
    if (age > 24*60*60*1000) {{ remove(ref(db, 'incidents/' + id)); return; }}
    if (isValidVNCoordinate(inc.lat, inc.lng)) {{
        const marker = L.marker([inc.lat, inc.lng], {{ icon: incidentIcon }}).addTo(map)
            .bindPopup(`<b>${{inc.created_by}}</b><br> ${{inc.note}}<br> <img src="${{inc.image_url}}" style="max-width:200px; max-height:200px;"><br> ${{new Date(inc.timestamp).toLocaleString()}}`);
        incidentMarkers[id] = marker;
    }}
}});
onChildRemoved(incidentsRef, (data) => {{ const id = data.key; if (incidentMarkers[id]) {{ map.removeLayer(incidentMarkers[id]); delete incidentMarkers[id]; }} }});

// ==================== TRACKS ====================
function loadUserTracks(userId, userName, show) {{
    const tracksRef = ref(db, 'tracks/' + userId + '/points');
    const tracksQuery = query(tracksRef, limitToLast(30));
    if (!show) {{
        if (trackPolylines[userId]) {{ map.removeLayer(trackPolylines[userId]); delete trackPolylines[userId]; }}
        if (trackListeners[userId]) {{ off(tracksQuery); trackListeners[userId] = false; }}
        return;
    }}
    if (trackListeners[userId]) return;
    trackListeners[userId] = true;
    if (!trackPolylines[userId]) {{
        const hue = (userName.split('').reduce((a,b) => a + b.charCodeAt(0), 0) * 31) % 360;
        const color = `hsl(${{hue}}, 70%, 50%)`;
        trackPolylines[userId] = L.polyline([], {{ color: color, weight: 3, opacity: 0.7, smoothFactor: 5, noClip: true, renderer: L.canvas() }}).addTo(map);
    }}
    onChildAdded(tracksQuery, (snapshot) => {{
        const point = snapshot.val();
        if (point && point.lat && point.lng && isValidVNCoordinate(point.lat, point.lng)) {{
            trackPolylines[userId].addLatLng([point.lat, point.lng]);
            if (trackPolylines[userId].getLatLngs().length > 30) {{
                const latlngs = trackPolylines[userId].getLatLngs();
                const simplified = [];
                for (let i = 0; i < latlngs.length; i++) {{
                    if (i === 0 || i === latlngs.length-1) {{
                        simplified.push(latlngs[i]);
                        continue;
                    }}
                    const prev = latlngs[i-1];
                    const curr = latlngs[i];
                    const next = latlngs[i+1];
                    const angle = Math.abs(getBearing(prev.lat, prev.lng, curr.lat, curr.lng) - getBearing(curr.lat, curr.lng, next.lat, next.lng));
                    if (angle > 15 && haversine(prev.lat, prev.lng, curr.lat, curr.lng) > 5) {{
                        simplified.push(curr);
                    }}
                }}
                trackPolylines[userId].setLatLngs(simplified);
            }}
        }}
    }});
}}

// ==================== MOVE ORDERS ====================
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
    const officerName = allOfficers[order.officerId]?.name || order.officerId;
    let popupContent = `📍 Lệnh di chuyển<br>Từ: ${{order.commanderName}}<br>Đến: ${{officerName}}<br>Điểm đến: ${{order.toLat.toFixed(6)}}, ${{order.toLng.toFixed(6)}}<br>Ghi chú: ${{order.note || 'không'}}`;
    const canCancel = (order.commanderId === myUsername) || (userRole === 'commander') || (userRole === 'admin');
    if (canCancel) {{
        popupContent += `<br><button class="delete-btn" data-orderid="${{orderId}}">❌ Huỷ lệnh</button>`;
    }}
    polyline.bindPopup(popupContent);
    moveOrderLines[orderId] = polyline;
    if (order.officerId === myUsername) {{
        L.popup().setLatLng([order.toLat, order.toLng]).setContent(`🚶 Bạn được lệnh di chuyển đến đây từ ${{order.commanderName}}<br>Ghi chú: ${{order.note || 'không'}}`).openOn(map);
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
            const officerPos = allOfficers[order.officerId];
            if (!officerPos) continue;
            const dist = haversine(officerPos.lat, officerPos.lng, order.toLat, order.toLng);
            if (dist < 20) {{
                remove(ref(db, 'move_orders/' + orderId));
            }}
        }}
    }}).catch(console.error);
}}
setInterval(checkOrdersCompletion, 5000);

function zoomToAllOfficers() {{
    const officersList = Object.values(allOfficers).filter(o => isValidVNCoordinate(o.lat, o.lng));
    if (officersList.length === 0) return;
    const bounds = L.latLngBounds(officersList.map(o => [o.lat, o.lng]));
    map.fitBounds(bounds, {{ padding: [50, 50], animate: false }});
}}
setTimeout(zoomToAllOfficers, 2000);

// ==================== NÚT XOÁ TOÀN BỘ LỆNH DI CHUYỂN ====================
if (userRole === 'commander' || userRole === 'admin') {{
    const clearBtn = document.createElement('button');
    clearBtn.textContent = '🗑️ Xoá tất cả nét vẽ (lệnh di chuyển)';
    clearBtn.className = 'clear-orders-btn';
    clearBtn.onclick = async () => {{
        if (confirm('Bạn có chắc muốn xoá TOÀN BỘ lệnh di chuyển đang hoạt động?')) {{
            await remove(moveOrdersRef);
            Object.keys(moveOrderLines).forEach(orderId => {{
                if (moveOrderLines[orderId]) {{
                    map.removeLayer(moveOrderLines[orderId]);
                    delete moveOrderLines[orderId];
                }}
            }});
            alert('Đã xoá tất cả lệnh di chuyển.');
        }}
    }};
    document.body.appendChild(clearBtn);
}}

// ==================== DRAWING TOOLBAR (chỉ commander/admin) ====================
if (userRole === 'commander' || userRole === 'admin') {{
    const toolbar = L.control({{ position: 'topright' }});
    toolbar.onAdd = () => {{
        const div = L.DomUtil.create('div', 'drawing-toolbar');
        div.innerHTML = `
            <div style="background:white; padding:8px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.2);">
                <button id="draw-toggle" style="margin:2px; padding:4px 8px;">✏️ Vẽ</button>
                <button id="draw-finish" style="margin:2px; padding:4px 8px; display:none; background:#4caf50; color:white;">✅ Hoàn tất</button>
                <input type="color" id="draw-color" value="${{drawingColor}}" style="width:30px; height:30px; margin:2px;">
                <input type="range" id="draw-weight" min="2" max="10" step="1" value="${{drawingWeight}}" style="width:80px; margin:2px;">
                <button id="clear-all-drawings" style="margin:2px; padding:4px 8px; background:#ff4444; color:white;">🗑️ Xóa tất cả nét vẽ</button>
            </div>
        `;
        L.DomEvent.disableClickPropagation(div);
        return div;
    }};
    toolbar.addTo(map);

    const drawToggle = document.getElementById('draw-toggle');
    const drawFinish = document.getElementById('draw-finish');
    drawToggle.addEventListener('click', () => {{
        drawingMode = !drawingMode;
        if (drawingMode) {{
            drawToggle.style.background = '#4caf50';
            drawToggle.style.color = 'white';
            drawFinish.style.display = 'inline-block';
            startDrawing();
        }} else {{
            drawToggle.style.background = '';
            drawToggle.style.color = '';
            drawFinish.style.display = 'none';
            cancelDrawing();
        }}
    }});
    drawFinish.addEventListener('click', () => {{
        if (drawingMode && tempPoints.length >= 2) {{
            saveDrawing();
        }}
        drawingMode = false;
        drawToggle.style.background = '';
        drawToggle.style.color = '';
        drawFinish.style.display = 'none';
        cancelDrawing();
    }});
    document.getElementById('draw-color').addEventListener('change', (e) => {{
        drawingColor = e.target.value;
    }});
    document.getElementById('draw-weight').addEventListener('change', (e) => {{
        drawingWeight = parseInt(e.target.value);
    }});
    document.getElementById('clear-all-drawings').addEventListener('click', async () => {{
        if (confirm('Xóa tất cả nét vẽ?')) {{
            await remove(ref(db, 'drawings'));
        }}
    }});
}}

function startDrawing() {{
    tempPoints = [];
    if (tempPolyline) map.removeLayer(tempPolyline);
    const info = L.control({{ position: 'bottomleft' }});
    info.onAdd = () => {{
        const div = L.DomUtil.create('div', 'drawing-info');
        div.innerHTML = '🎨 Đang vẽ: chạm (tap) để thêm điểm, bấm "Hoàn tất" để kết thúc.';
        return div;
    }};
    info.addTo(map);
    window.drawingInfo = info;

    function addPoint(e) {{
        const {{ lat, lng }} = e.latlng;
        tempPoints.push([lat, lng]);
        if (tempPolyline) map.removeLayer(tempPolyline);
        tempPolyline = L.polyline(tempPoints, {{ color: drawingColor, weight: drawingWeight, opacity: 0.8 }}).addTo(map);
    }}
    function addPointOnTouch(e) {{
        if (e.originalEvent.touches && e.originalEvent.touches.length === 1) {{
            const touch = e.originalEvent.touches[0];
            const latlng = map.mouseEventToLatLng(touch);
            addPoint({{ latlng }});
            e.originalEvent.preventDefault();
        }}
    }}
    function deactivateDrawing() {{
        map.off('click', addPoint);
        map.off('touchstart', addPointOnTouch);
        if (window.drawingInfo) map.removeControl(window.drawingInfo);
        if (tempPolyline) map.removeLayer(tempPolyline);
        tempPoints = [];
        tempPolyline = null;
        drawingMode = false;
        const drawToggle = document.getElementById('draw-toggle');
        if (drawToggle) {{
            drawToggle.style.background = '';
            drawToggle.style.color = '';
        }}
        const drawFinish = document.getElementById('draw-finish');
        if (drawFinish) drawFinish.style.display = 'none';
    }}
    map.on('click', addPoint);
    map.on('touchstart', addPointOnTouch);
    window.deactivateDrawing = deactivateDrawing;
}}

function cancelDrawing() {{
    if (window.deactivateDrawing) window.deactivateDrawing();
}}

async function saveDrawing() {{
    if (tempPoints.length < 2) return;
    const drawing = {{
        points: tempPoints.map(p => ({{ lat: p[0], lng: p[1] }})),
        color: drawingColor,
        weight: drawingWeight,
        author: myName,
        authorId: myUsername,
        timestamp: Date.now()
    }};
    try {{
        await push(ref(db, 'drawings'), drawing);
        console.log("🟢 Đã lưu nét vẽ:", drawing);
    }} catch (err) {{
        console.error("❌ Lỗi lưu drawing:", err);
    }}
    cancelDrawing();
}}

// ==================== DRAWINGS - INCREMENTAL ====================
let drawingLayers = {{}};
const drawingsRef = ref(db, 'drawings');
const recentDrawingsQuery = query(drawingsRef, limitToLast(50));

document.addEventListener('click', async (e) => {{
    if (e.target && e.target.classList.contains('delete-drawing')) {{
        const id = e.target.getAttribute('data-id');
        if (!id) return;
        if (confirm("Xóa nét vẽ này?")) {{
            await remove(ref(db, 'drawings/' + id));
        }}
    }}
}});

get(recentDrawingsQuery).then((snapshot) => {{
    const data = snapshot.val() || {{}};
    Object.entries(data).forEach(([id, drawing]) => {{
        if (!drawing || !drawing.points || drawing.points.length < 2) return;
        const latlngs = drawing.points.map(p => [p.lat, p.lng]);
        const polyline = L.polyline(latlngs, {{
            color: drawing.color || '#ff0000',
            weight: drawing.weight || 3,
            opacity: 0.8
        }}).addTo(map);
        let popupContent = `✏️ Vẽ bởi: ${{drawing.author}}<br>${{new Date(drawing.timestamp).toLocaleString()}}`;
        const canDelete = (userRole === 'commander' || userRole === 'admin' || drawing.authorId === myUsername);
        if (canDelete) {{
            popupContent += `<br><button class="delete-drawing" data-id="${{id}}">🗑️ Xóa nét vẽ</button>`;
        }}
        polyline.bindPopup(popupContent);
        drawingLayers[id] = polyline;
    }});
}});
onChildAdded(recentDrawingsQuery, (snapshot) => {{
    const id = snapshot.key;
    const drawing = snapshot.val();
    if (!drawing || !drawing.points || drawing.points.length < 2) return;
    if (drawingLayers[id]) return;
    const latlngs = drawing.points.map(p => [p.lat, p.lng]);
    const polyline = L.polyline(latlngs, {{
        color: drawing.color || '#ff0000',
        weight: drawing.weight || 3,
        opacity: 0.8
    }}).addTo(map);
    let popupContent = `✏️ Vẽ bởi: ${{drawing.author}}<br>${{new Date(drawing.timestamp).toLocaleString()}}`;
    const canDelete = (userRole === 'commander' || userRole === 'admin' || drawing.authorId === myUsername);
    if (canDelete) {{
        popupContent += `<br><button class="delete-drawing" data-id="${{id}}">🗑️ Xóa nét vẽ</button>`;
    }}
    polyline.bindPopup(popupContent);
    drawingLayers[id] = polyline;
}});
onChildRemoved(recentDrawingsQuery, (snapshot) => {{
    const id = snapshot.key;
    if (drawingLayers[id]) {{
        map.removeLayer(drawingLayers[id]);
        delete drawingLayers[id];
    }}
}});

// ==================== DIALOG THÊM ĐIỂM ====================
function showPointDialog(latlng) {{
    if (drawingMode) return;
    const oldOverlay = document.getElementById('dialog-overlay');
    if (oldOverlay) oldOverlay.remove();
    const overlay = document.createElement('div');
    overlay.id = 'dialog-overlay';
    overlay.className = 'dialog-overlay';
    document.body.appendChild(overlay);
    const dialog = document.createElement('div');
    dialog.className = 'custom-dialog';
    
    if (userRole === 'officer') {{
        dialog.innerHTML = `
            <h4>📍 Đánh dấu điểm</h4>
            <input type="text" id="point-note" placeholder="Ghi chú (bắt buộc)" />
            <div style="margin-top: 12px;">
                <button id="dialog-ok">Đánh dấu</button>
                <button id="dialog-cancel">Hủy</button>
            </div>
        `;
    }} else {{
        dialog.innerHTML = `
            <h4>📍 Tùy chọn tại điểm</h4>
            <input type="text" id="point-note" placeholder="Ghi chú (bắt buộc nếu đánh dấu điểm)" />
            <select id="officer-select">
                <option value="">-- Chọn cán bộ để ra lệnh (không chọn = đánh dấu điểm) --</option>
            </select>
            <div style="margin-top: 12px;">
                <button id="dialog-ok">Xác nhận</button>
                <button id="dialog-cancel">Hủy</button>
            </div>
        `;
    }}
    document.body.appendChild(dialog);
    
    if (userRole !== 'officer') {{
        const select = dialog.querySelector('#officer-select');
        for (const [uid, officer] of Object.entries(allOfficers)) {{
            if (uid !== myUsername) {{
                const name = officer.name || uid;
                const option = document.createElement('option');
                option.value = uid;
                option.textContent = name;
                select.appendChild(option);
            }}
        }}
    }}
    
    const okBtn = dialog.querySelector('#dialog-ok');
    const cancelBtn = dialog.querySelector('#dialog-cancel');
    const noteInput = dialog.querySelector('#point-note');
    okBtn.onclick = () => {{
        const note = noteInput.value.trim();
        if (!note) {{
            alert("Vui lòng nhập ghi chú.");
            return;
        }}
        if (userRole === 'officer') {{
            push(ref(db, 'markers/' + myUsername), {{
                created_by: myName,
                lat: latlng.lat,
                lng: latlng.lng,
                note: note,
                timestamp: Date.now()
            }});
        }} else {{
            const selectedOfficerUid = document.getElementById('officer-select')?.value;
            if (!selectedOfficerUid) {{
                push(ref(db, 'markers/' + myUsername), {{
                    created_by: myName,
                    lat: latlng.lat,
                    lng: latlng.lng,
                    note: note,
                    timestamp: Date.now()
                }});
            }} else {{
                const startOfficer = allOfficers[selectedOfficerUid];
                if (!startOfficer || !isValidVNCoordinate(startOfficer.lat, startOfficer.lng)) {{
                    alert("Không tìm thấy vị trí cán bộ này.");
                    dialog.remove();
                    overlay.remove();
                    return;
                }}
                const orderData = {{
                    officerId: selectedOfficerUid,
                    fromLat: startOfficer.lat,
                    fromLng: startOfficer.lng,
                    toLat: latlng.lat,
                    toLng: latlng.lng,
                    commanderName: myName,
                    commanderId: myUsername,
                    timestamp: Date.now(),
                    status: 'active',
                    note: note
                }};
                push(ref(db, 'move_orders'), orderData);
                const tempMarker = L.marker([latlng.lat, latlng.lng]).addTo(map);
                const selectName = document.querySelector('#officer-select option:checked')?.text;
                tempMarker.bindPopup(`📍 Đã ra lệnh cho ${{selectName}}`).openPopup();
                setTimeout(() => map.removeLayer(tempMarker), 5000);
            }}
        }}
        dialog.remove();
        overlay.remove();
    }};
    cancelBtn.onclick = () => {{
        dialog.remove();
        overlay.remove();
    }};
}}

map.on('contextmenu', (e) => {{
    if (selectionMode || drawingMode) return;
    e.originalEvent.preventDefault();
    showPointDialog(e.latlng);
}});
let touchTimer = null;
map.on('touchstart', (e) => {{
    if (selectionMode || drawingMode) return;
    const touch = e.originalEvent.touches[0];
    const latlng = map.mouseEventToLatLng(touch);
    touchTimer = setTimeout(() => {{
        showPointDialog(latlng);
    }}, 800);
}});
map.on('touchend', () => {{ if (touchTimer) clearTimeout(touchTimer); }});
map.on('touchcancel', () => {{ if (touchTimer) clearTimeout(touchTimer); }});

// ==================== RA LỆNH TỪ SIDEBAR (chỉ commander/admin) ====================
if (userRole === 'commander' || userRole === 'admin') {{
    function activateSelectionMode(officerId, officerName) {{
        if (selectionMode) return;
        selectionMode = true;
        selectedOfficerId = officerId;
        selectedOfficerName = officerName;
        hasSelected = false;
        const infoControl = L.control({{ position: 'topright' }});
        infoControl.onAdd = () => {{
            const div = L.DomUtil.create('div', 'selection-info');
            div.innerHTML = `<span>📍 Giữ 5 giây trên map để chọn điểm cho <b>${{officerName}}</b></span><button id="cancel-order-btn" class="cancel-btn">Hủy</button>`;
            L.DomEvent.disableClickPropagation(div);
            return div;
        }};
        infoControl.addTo(map);
        tempInfoControl = infoControl;
        setTimeout(() => {{
            const cancelBtn = document.getElementById('cancel-order-btn');
            if (cancelBtn) cancelBtn.onclick = () => deactivateSelectionMode();
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
                const startOfficer = allOfficers[selectedOfficerId];
                if (startOfficer) {{
                    const orderData = {{
                        officerId: selectedOfficerId,
                        fromLat: startOfficer.lat,
                        fromLng: startOfficer.lng,
                        toLat: endLat,
                        toLng: endLng,
                        commanderName: myName,
                        commanderId: myUsername,
                        timestamp: Date.now(),
                        status: 'active',
                        note: ""
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
        map.on('touchend', () => clearTimeout(holdTimer));
        map.on('touchcancel', () => clearTimeout(holdTimer));
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
    if (window.pendingOrder && window.pendingOrder.officerId) {{
        const checkInterval = setInterval(() => {{
            if (allOfficers[window.pendingOrder.officerId]) {{
                clearInterval(checkInterval);
                activateSelectionMode(window.pendingOrder.officerId, window.pendingOrder.officerName);
            }}
        }}, 200);
    }}
}}
</script> </body> </html> """

# ==============================
# 17. HIỂN THỊ MAP VÀ CHAT
# ==============================
st.markdown('<div class="dashboard-card">', unsafe_allow_html=True)
tab1, tab2 = st.tabs(["🗺️ Bản đồ", "💬 Chat nội bộ"])
with tab1:
    st.components.v1.html(map_html, height=620)
with tab2:
    st.subheader("💬 Chat nội bộ")
    # Tự động refresh mỗi 7 giây (có thể dùng st_autorefresh nhưng không bắt buộc)
    # Để tránh lỗi, ta dùng một placeholder refresh đơn giản
    def cleanup_old_messages():
        msgs = db.child("messages").get().val()
        if not msgs: return
        now = int(time.time() * 1000)
        for key, msg in msgs.items():
            if now - msg.get("timestamp", 0) > 24*3600*1000:
                db.child("messages").child(key).remove()
    cleanup_old_messages()
    
    messages = db.child("messages").order_by_child("timestamp").limit_to_last(50).get()
    if messages.val():
        sorted_msgs = sorted(messages.val().items(), key=lambda x: x[1]["timestamp"])
        for key, msg in sorted_msgs:
            vn_time = datetime.fromtimestamp(
                msg["timestamp"]/1000, tz=timezone(timedelta(hours=7))
            ).strftime("%H:%M")
            is_system = msg["from"] == "system"
            if is_system:
                avatar = "🤖"
                bg_color = "#e5e7eb"
                align = "center"
            else:
                is_me = (msg["from"] == username)
                avatar = msg['name'][0].upper()
                bg_color = "#dcf8c6" if is_me else "#f1f0f0"
                align = "right" if is_me else "left"
            st.markdown(
                f"""
                <div style='display:flex; justify-content:{align}; margin:10px 0;'>
                    <div style='display:flex; align-items:flex-end; max-width:80%; gap:8px;'>
                        {"<div style='order:2;' " if not is_system and is_me else ""}
                            <div style='background:{bg_color}; padding:10px 15px; border-radius:15px; box-shadow:0 2px 8px rgba(0,0,0,0.1);'>
                                <b>{msg['name']}</b> <span style='font-size:10px; color:gray'>{vn_time}</span><br>
                                {msg['message']}
                            </div>
                        {"</div>" if not is_system and is_me else ""}
                        <div style='width:36px; height:36px; background: #2563eb; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:bold; color:white;'>
                            {avatar}
                        </div>
                        {"<div style='order:2;' " if not is_system and not is_me else ""}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        st.markdown("<script>window.scrollTo(0, document.body.scrollHeight);</script>", unsafe_allow_html=True)
    else:
        st.info("Chưa có tin nhắn nào.")
    
    if 'last_chat_time' not in st.session_state:
        st.session_state.last_chat_time = 0
    
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5,1])
        with col1:
            message = st.text_input("Tin nhắn", placeholder="Nhập tin nhắn...", label_visibility="collapsed")
        with col2:
            sent = st.form_submit_button("Gửi")
        if sent and message.strip():
            now = time.time()
            if now - st.session_state.last_chat_time < 2:
                st.warning("Vui lòng chờ 2 giây trước khi gửi tin nhắn tiếp theo.")
            else:
                st.session_state.last_chat_time = now
                chat_data = {
                    "from": username, "name": name, "message": message,
                    "timestamp": int(time.time() * 1000)
                }
                db.child("messages").push(chat_data)
                all_msgs = db.child("messages").order_by_child("timestamp").get().val()
                if all_msgs and len(all_msgs) > 200:
                    sorted_all = sorted(all_msgs.items(), key=lambda x: x[1]["timestamp"])
                    for k, _ in sorted_all[:-200]:
                        db.child("messages").child(k).remove()
                st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# 18. THÔNG TIN PHỤ TRONG SIDEBAR
# ==============================
st.sidebar.markdown('<div class="sidebar-group"><h3>👥 TRỰC TUYẾN</h3></div>', unsafe_allow_html=True)
if officers:
    for uid, info in officers.items():
        label = "(bạn)" if uid == username else ""
        st.sidebar.write(f"• {info['name']} {label}")
else:
    st.sidebar.write("Chưa có ai chia sẻ vị trí hợp lệ")

all_markers = load_all_markers()
incidents = load_incidents()
st.sidebar.markdown('<div class="sidebar-group"><h3>📌 ĐIỂM ĐÁNH DẤU GẦN ĐÂY</h3></div>', unsafe_allow_html=True)
if all_markers:
    valid_markers = {k: v for k, v in all_markers.items() if isinstance(v, dict) and v.get("timestamp")}
    if valid_markers:
        sorted_markers = sorted(valid_markers.items(), key=lambda x: x[1]["timestamp"], reverse=True)[:5]
        for _, m in sorted_markers:
            st.sidebar.write(f"📍 {m.get('created_by', 'Unknown')}: {m.get('note', '')[:30]}...")
    else:
        st.sidebar.write("Chưa có điểm đánh dấu hợp lệ")
else:
    st.sidebar.write("Chưa có điểm đánh dấu")

st.sidebar.markdown('<div class="sidebar-group"><h3>📸 ẢNH HIỆN TRƯỜNG GẦN ĐÂY</h3></div>', unsafe_allow_html=True)
if incidents:
    sorted_inc = sorted(incidents.items(), key=lambda x: x[1]["timestamp"], reverse=True)[:5]
    for key, inc in sorted_inc:
        st.sidebar.write(f"📷 {inc['created_by']}: {inc.get('note', '')[:30]}...")
else:
    st.sidebar.write("Chưa có ảnh hiện trường")

if user_role == "commander" and officers:
    st.sidebar.markdown('<div class="sidebar-group"><h3>🚶 RA LỆNH DI CHUYỂN</h3></div>', unsafe_allow_html=True)
    st.sidebar.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
    officer_options = {uid: info['name'] for uid, info in officers.items() if uid != username}
    if officer_options:
        selected_officer = st.sidebar.selectbox(
            "Chọn cán bộ",
            options=list(officer_options.keys()),
            format_func=lambda x: officer_options[x]
        )
        if st.sidebar.button("📍 Bắt đầu chọn điểm đến"):
            st.session_state['order_officer_id'] = selected_officer
            st.session_state['order_officer_name'] = officer_options[selected_officer]
            st.rerun()
    else:
        st.sidebar.info("Không có cán bộ khác trực tuyến")
    st.sidebar.markdown('</div>', unsafe_allow_html=True)
