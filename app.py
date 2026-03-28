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
# 4. ĐĂNG NHẬP
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
# 8. GPS SCRIPT (giữ nguyên)
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

# ==============================
# 11. STATIONARY OFFICERS
# ==============================
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
# 12. SIDEBAR CÔNG CỤ
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("🚨 Công cụ phối hợp")

if st.sidebar.button("🚨 Gửi báo động"):
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

        st.sidebar.success("Đã gửi yêu cầu báo động")
    else:
        st.sidebar.error("Bạn chưa chia sẻ vị trí hợp lệ")

with st.sidebar.expander("📍 Đánh dấu điểm"):
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
            st.sidebar.success("Đã thêm điểm")
        else:
            st.sidebar.warning("Chưa chia sẻ vị trí hợp lệ hoặc ghi chú trống")

# THÊM: Commander có thể xóa toàn bộ ghi chú
if user_role == "commander":
    with st.sidebar.expander("🗑️ Xóa ghi chú (toàn bộ)"):
        if st.button("⚠️ Xóa tất cả ghi chú", help="Xóa toàn bộ markers của tất cả người dùng"):
            try:
                db.child("markers").remove()
                st.sidebar.success("Đã xóa toàn bộ ghi chú!")
            except Exception as e:
                st.sidebar.error(f"Lỗi xóa: {e}")

with st.sidebar.expander("📸 Chụp ảnh hiện trường"):
    uploaded_file = st.file_uploader("Chọn ảnh", type=['jpg', 'jpeg', 'png'])
    note_photo = st.text_input("Ghi chú (tùy chọn)")
    if st.button("📤 Gửi ảnh"):
        if not st.session_state.sharing:
            st.sidebar.warning("Bạn cần bật chia sẻ vị trí trước")
        elif uploaded_file is None:
            st.sidebar.warning("Vui lòng chọn ảnh")
        else:
            current = db.child("officers").child(username).get().val()
            if current and is_valid_coordinate(current.get("lat"), current.get("lng")):
                imgbb_api_key = st.secrets["imgbb"]["api_key"]
                image_url, error = upload_to_imgbb(uploaded_file, imgbb_api_key)
                if error:
                    st.sidebar.error(f"Lỗi upload: {error}")
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
                    st.sidebar.success("Đã gửi ảnh hiện trường! Ảnh sẽ tự động xóa sau 24h.")
            else:
                st.sidebar.error("Không có vị trí hợp lệ")

# ==============================
# 13. NHIỆM VỤ
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("📋 Nhiệm vụ")
if st.sidebar.button("✅ Nhận nhiệm vụ gần nhất"):
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
                st.sidebar.success("Đã nhận nhiệm vụ")
                found = True
                break
        if not found:
            st.sidebar.info("Không có nhiệm vụ nào cho bạn")
    else:
        st.sidebar.info("Không có báo động nào")

# ==============================
# 14. QUẢN LÝ USER (ADMIN)
# ==============================
if user_role == "admin":
    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 Quản lý tài khoản")
    
    with st.sidebar.expander("➕ Thêm user mới"):
        new_username = st.text_input("Tên đăng nhập")
        new_email = st.text_input("Email")
        new_name = st.text_input("Tên hiển thị")
        new_password = st.text_input("Mật khẩu", type="password")
        new_role = st.selectbox("Vai trò", ["admin", "commander", "officer"])
        new_color = st.color_picker("Màu sắc", "#0066cc")
        
        if st.button("Tạo tài khoản"):
            if not new_username or not new_name or not new_password:
                st.sidebar.error("Vui lòng nhập đầy đủ: tên đăng nhập, tên hiển thị và mật khẩu")
            elif new_username in config["credentials"]["usernames"]:
                st.sidebar.error("Tên đăng nhập đã tồn tại")
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
                    st.sidebar.success(f"Đã thêm user {new_username}")
                    st.rerun()
                else:
                    st.sidebar.error("Lỗi lưu dữ liệu")
    
    with st.sidebar.expander("🗑️ Xóa user"):
        users = list(config["credentials"]["usernames"].keys())
        if users:
            user_to_delete = st.selectbox("Chọn user để xóa", users)
            if st.button("Xóa user"):
                if user_to_delete == username:
                    st.sidebar.error("Không thể xóa chính mình")
                else:
                    del config["credentials"]["usernames"][user_to_delete]
                    if save_credentials_to_firebase(config["credentials"]):
                        st.sidebar.success(f"Đã xóa user {user_to_delete}")
                        st.rerun()
                    else:
                        st.sidebar.error("Lỗi lưu dữ liệu")
        else:
            st.sidebar.info("Không có user nào")

# ==============================
# 15. LOAD DỮ LIỆU
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

# ==============================
# 16. AUTO REFRESH
# ==============================
st_autorefresh(interval=10000, key="auto_refresh")

# ==============================
# 17. CHECKBOX TRACK
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
# 18. CHUẨN BỊ MAP
# ==============================
alert_sound_base64 = get_base64("alert.mp3")
show_tracks_json = json.dumps(st.session_state.get("show_tracks", {}))
fcm_vapid_key = st.secrets.get("fcm", {}).get("vapid_key", "")

stationary_officers = detect_stationary_officers()
stationary_json = json.dumps(stationary_officers)
user_colors_json = json.dumps(user_colors)
user_role_json = json.dumps(user_role)

# Xóa officer lỗi
try:
    officers_old = db.child("officers").get().val()
    if officers_old:
        for uid, data in officers_old.items():
            if not is_valid_coordinate(data.get("lat"), data.get("lng")):
                db.child("officers").child(uid).remove()
                print(f"Đã xóa officer {uid} có tọa độ lỗi")
except Exception as e:
    print("Cleanup error:", e)

# ==============================
# 19. ORDER JS
# ==============================
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
# 20. MAP HTML (ĐÃ SỬA MOBILE)
# ==============================
map_html = f"""
<!DOCTYPE html><html> <head> <meta charset="utf-8"/> <meta name="viewport" content="width=device-width, initial-scale=1.0"> <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/> <link rel="stylesheet" href="https://unpkg.com/leaflet-arrowheads@1.2.0/dist/leaflet-arrowheads.css" /> <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script> <script src="https://unpkg.com/leaflet-arrowheads@1.2.0/dist/leaflet-arrowheads.js"></script> <script src="https://cdn.jsdelivr.net/npm/nosleep.js@0.12.0/dist/NoSleep.min.js"></script> <style> #map {{ height: 600px; width: 100%; }} .leaflet-container {{ will-change: transform; }} .leaflet-tooltip {{ background: transparent; border: none; box-shadow: none; font-weight: bold; color: #333; text-shadow: 1px 1px 2px white; font-size: 12px; margin-top: -15px !important; white-space: nowrap; }} .alert-marker {{ width: 24px; height: 24px; background: red; border-radius: 50%; border: 3px solid white; box-shadow: 0 0 15px red; animation: blink 1s infinite; }} @keyframes blink {{ 0% {{ transform: scale(1); opacity: 1; }} 50% {{ transform: scale(1.4); opacity: 0.6; }} 100% {{ transform: scale(1); opacity: 1; }} }} .incident-icon {{ background: #ffaa00; width: 30px; height: 30px; border-radius: 50%; text-align: center; line-height: 30px; font-size: 18px; border: 2px solid white; }} .selection-info {{ background: white; padding: 8px 15px; border-radius: 8px; border: 2px solid #ff8800; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }} .cancel-btn {{ background: #ff4444; color: white; border: none; border-radius: 5px; padding: 5px 12px; margin-left: 10px; cursor: pointer; font-size: 14px; }} </style> <body> {order_js} <div id="map"></div> <script type="module"> import {{ initializeApp }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js"; import {{ getDatabase, ref, onChildAdded, onChildChanged, onChildRemoved, onValue, query, limitToLast, update, push, onDisconnect, get, serverTimestamp, off }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-database.js"; import {{ getMessaging, getToken, onMessage }} from "https://www.gstatic.com/firebasejs/9.22.0/firebase-messaging.js";

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

console.log("👤 Username:", myUsername);
console.log("👤 Role:", userRole);

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
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 20,
    updateWhenZooming: false
}}).addTo(map);

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
let selectionClickHandler = null;
let hasSelected = false;  // chống double tap

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
            <span>📍 Chạm vào bản đồ để chọn điểm cho <b>${{officerName}}</b></span>
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

    const handleSelect = (e) => {{
        if (hasSelected) return;
        hasSelected = true;
        const endLat = e.latlng.lat;
        const endLng = e.latlng.lng;
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
            
            // Phản hồi trực quan
            const marker = L.marker([endLat, endLng]).addTo(map);
            marker.bindPopup("📍 Đã chọn điểm đến").openPopup();
            setTimeout(() => map.removeLayer(marker), 5000);
            
            const line = L.polyline([[startLatLng.lat, startLatLng.lng], [endLat, endLng]], {{
                color: '#ff8800', weight: 4, dashArray: '5, 10'
            }}).addTo(map);
            if (line.arrowheads) line.arrowheads({{ size: '12px', color: '#ff8800' }});
            setTimeout(() => map.removeLayer(line), 5000);
            
            map.flyTo([endLat, endLng], 18);
            
            if (navigator.vibrate) navigator.vibrate(100);
        }}
        deactivateSelectionMode();
    }};
    
    selectionClickHandler = handleSelect;
    map.on('click', selectionClickHandler);
    map.on('touchend', selectionClickHandler);  // hỗ trợ mobile
}}

function deactivateSelectionMode() {{
    if (!selectionMode) return;
    if (tempInfoControl) map.removeControl(tempInfoControl);
    if (selectionClickHandler) {{
        map.off('click', selectionClickHandler);
        map.off('touchend', selectionClickHandler);
    }}
    map.getContainer().style.cursor = '';
    selectionMode = false;
    selectedOfficerId = null;
    selectedOfficerName = null;
    tempInfoControl = null;
    selectionClickHandler = null;
    hasSelected = false;
}}

// Thêm marker officer
onChildAdded(officersRef, (data) => {{
    const officer = data.val();
    const id = data.key;
    if (!isValidVNCoordinate(officer.lat, officer.lng)) {{
        console.log("⚠️ Bỏ qua officer có tọa độ lỗi:", id, officer.lat, officer.lng);
        return;
    }}
    const color = getOfficerColor(id);
    const marker = L.circleMarker([officer.lat, officer.lng], {{
        radius: 7,
        color: color,
        fillColor: color,
        fillOpacity: 0.9,
        weight: 1,
        renderer: L.canvas()
    }}).addTo(map);
    marker.bindTooltip(officer.name, {{
        permanent: true, direction: 'top', offset: [0, -8], className: 'officer-label'
    }});
    
    officerMarkers[id] = marker;
    if (id === myUsername && !zoomedToMe) {{
        map.setView([officer.lat, officer.lng], 16);
        zoomedToMe = true;
        sessionStorage.setItem('zoomedToMe', 'true');
    }}
}});

// Cập nhật marker
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

// Online status
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
                    marker.setStyle({{ color: '#aaa', fillColor: '#aaa' }});
                }} else {{
                    const originalColor = getOfficerColor(uid);
                    marker.setStyle({{ color: originalColor, fillColor: originalColor }});
                }}
            }}
        }});
    }}).catch(console.error);
}}
setInterval(updateOnlineStatus, 30000);

// Alerts
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

// Markers và incidents
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

// Ghi chú touch cho officer
if (userRole !== 'commander') {{
    let pressTimer;
    map.on('touchstart', (e) => {{
        if (!e.originalEvent.touches || e.originalEvent.touches.length === 0) return;
        const touch = e.originalEvent.touches[0];
        const latlng = map.mouseEventToLatLng(touch);
        pressTimer = setTimeout(() => {{
            const note = prompt("Nhập ghi chú cho điểm này:");
            if (note && note.trim()) {{
                push(ref(db, 'markers/{username}'), {{
                    created_by: "{name}",
                    lat: latlng.lat,
                    lng: latlng.lng,
                    note: note,
                    timestamp: Date.now()
                }});
            }}
        }}, 2000);
    }});
    map.on('touchend', () => clearTimeout(pressTimer));
    map.on('touchcancel', () => clearTimeout(pressTimer));
}}
map.on('contextmenu', (e) => {{
    e.originalEvent.preventDefault();
    const note = prompt("Nhập ghi chú cho điểm này:");
    if (note && note.trim()) {{
        push(ref(db, 'markers/{username}'), {{
            created_by: "{name}",
            lat: e.latlng.lat,
            lng: e.latlng.lng,
            note: note,
            timestamp: Date.now()
        }});
    }}
}});

// Tracks
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

// Move orders
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

// Xử lý pending order (chờ marker load)
if (window.pendingOrder && window.pendingOrder.officerId) {{
    const checkInterval = setInterval(() => {{
        if (officerMarkers[window.pendingOrder.officerId]) {{
            clearInterval(checkInterval);
            activateSelectionMode(window.pendingOrder.officerId, window.pendingOrder.officerName);
        }}
    }}, 200);
}}
</script> </body> </html> """

# ==============================
# 21. TABS
# ==============================
tab1, tab2 = st.tabs(["🗺️ Bản đồ", "💬 Chat nội bộ"])

with tab1:
    st.components.v1.html(map_html, height=620)

with tab2:
    st.subheader("💬 Chat nội bộ")
    st_autorefresh(interval=3000, key="chat_refresh")

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
            is_me = (msg["from"] == username)
            align = "right" if is_me else "left"
            bg_color = "#dcf8c6" if is_me else "#f1f0f0"
            st.markdown(
                f"<div style='display: flex; justify-content: {align}; margin:5px;'>"
                f"<div style='background-color: {bg_color}; padding:8px 12px; border-radius:10px; max-width:70%;'>"
                f"<b>{msg['name']}</b> {vn_time}<br>{msg['message']}"
                f"</div></div>",
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

# ==============================
# 22. DANH SÁCH CÁN BỘ ONLINE
# ==============================
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Cán bộ trực tuyến")

if officers:
    for uid, info in officers.items():
        label = "(bạn)" if uid == username else ""
        st.sidebar.write(f"• {info['name']} {label}")
else:
    st.sidebar.write("Chưa có ai chia sẻ vị trí hợp lệ")

# ==============================
# 23. ĐIỂM ĐÁNH DẤU GẦN ĐÂY
# ==============================
all_markers = load_all_markers()
with st.sidebar.expander("📌 Điểm đánh dấu gần đây"):
    if all_markers:
        valid_markers = {k: v for k, v in all_markers.items()
                        if isinstance(v, dict) and v.get("timestamp")}
        if valid_markers:
            sorted_markers = sorted(valid_markers.items(), key=lambda x: x[1]["timestamp"], reverse=True)[:5]
            for _, m in sorted_markers:
                st.write(f"📍 {m.get('created_by', 'Unknown')}: {m.get('note', '')[:30]}...")
        else:
            st.write("Chưa có điểm đánh dấu hợp lệ")
    else:
        st.write("Chưa có điểm đánh dấu")

# ==============================
# 24. INCIDENTS GẦN ĐÂY
# ==============================
incidents = load_incidents()
with st.sidebar.expander("📸 Ảnh hiện trường gần đây"):
    if incidents:
        sorted_inc = sorted(incidents.items(), key=lambda x: x[1]["timestamp"], reverse=True)[:5]
        for key, inc in sorted_inc:
            st.write(f"📷 {inc['created_by']}: {inc.get('note', '')[:30]}...")
    else:
        st.write("Chưa có ảnh hiện trường")

# ==============================
# 25. DROPDOWN RA LỆNH CHO COMMANDER
# ==============================
if user_role == "commander" and officers:
    st.sidebar.markdown("---")
    st.sidebar.subheader("🚶 Ra lệnh di chuyển (chạm vào map)")
    officer_options = {uid: info['name'] for uid, info in officers.items() if uid != username}
    if officer_options:
        selected_officer = st.sidebar.selectbox(
            "Chọn cán bộ",
            options=list(officer_options.keys()),
            format_func=lambda x: officer_options[x]
        )
        if st.sidebar.button("📍 Chọn điểm đến trên bản đồ"):
            st.session_state['order_officer_id'] = selected_officer
            st.session_state['order_officer_name'] = officer_options[selected_officer]
            st.rerun()
    else:
        st.sidebar.info("Không có cán bộ khác trực tuyến")
