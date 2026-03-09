import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
import pyrebase
import json
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
from streamlit_geolocation import streamlit_geolocation
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

# ---------- 5. Khởi tạo session state ----------
if 'sharing' not in st.session_state:
    st.session_state.sharing = False
if 'last_location' not in st.session_state:
    st.session_state.last_location = None

# ---------- 6. Nút bắt đầu / dừng chia sẻ vị trí ----------
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
            st.session_state.last_location = None
            st.rerun()

# ---------- 7. Lấy GPS và gửi lên Firebase (khi đang chia sẻ) ----------
if st.session_state.sharing:
    # Lấy vị trí từ trình duyệt
    location = streamlit_geolocation()
    if location and location.get('latitude') and location.get('longitude'):
        lat = location['latitude']
        lng = location['longitude']
        accuracy = location.get('accuracy', 0)
        
        # Chỉ gửi lên Firebase nếu vị trí thay đổi đáng kể (ví dụ > 10m)
        if (st.session_state.last_location is None or
            abs(lat - st.session_state.last_location[0]) > 0.0001 or
            abs(lng - st.session_state.last_location[1]) > 0.0001):
            
            # Ghi lên Firebase
            db.child("officers").child(username).set({
                'name': name,
                'lat': lat,
                'lng': lng,
                'accuracy': accuracy,
                'lastUpdate': int(time.time()*1000)
            })
            st.session_state.last_location = (lat, lng)
            st.sidebar.success(f"📍 Đã gửi vị trí: {lat:.5f}, {lng:.5f}")
    else:
        st.sidebar.warning("Đang chờ tín hiệu GPS...")

# ---------- 8. Công cụ phối hợp (Sidebar) ----------
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

# ---------- 9. Tự động refresh bản đồ (mỗi 5 giây) ----------
REFRESH_INTERVAL = 5000
count = st_autorefresh(interval=REFRESH_INTERVAL, key="map_refresh")

# ---------- 10. Đọc dữ liệu từ Firebase ----------
def load_data():
    officers = db.child("officers").get().val() or {}
    alerts = db.child("alerts").get().val() or {}
    markers = db.child("markers").get().val() or {}
    return officers, alerts, markers

officers, alerts, markers = load_data()

# ---------- 11. Vẽ bản đồ bằng Folium ----------
if officers:
    # Tính trung tâm bản đồ
    avg_lat = sum(o['lat'] for o in officers.values()) / len(officers)
    avg_lng = sum(o['lng'] for o in officers.values()) / len(officers)
    m = folium.Map(location=[avg_lat, avg_lng], zoom_start=14)
else:
    m = folium.Map(location=[21.0285, 105.8542], zoom_start=12)

# Marker cán bộ
for uid, info in officers.items():
    color = "blue" if uid == username else "green"
    popup_text = f"<b>{info['name']}</b><br>Độ chính xác: {info.get('accuracy', 'N/A')}m"
    folium.Marker(
        [info['lat'], info['lng']],
        popup=folium.Popup(popup_text, max_width=250),
        tooltip=info['name'],
        icon=folium.Icon(color=color)
    ).add_to(m)

# Marker báo động (đỏ)
if alerts:
    for key, alert in alerts.items():
        folium.Marker(
            [alert['lat'], alert['lng']],
            popup=folium.Popup(f"🚨 <b>Báo động từ {alert['name']}</b><br>{time.ctime(alert['timestamp']/1000)}", max_width=250),
            tooltip="Báo động!",
            icon=folium.Icon(color="red", icon="warning-sign", prefix="glyphicon")
        ).add_to(m)

# Marker đánh dấu (vàng)
if markers:
    for key, marker in markers.items():
        folium.Marker(
            [marker['lat'], marker['lng']],
            popup=folium.Popup(f"📍 <b>Điểm đánh dấu</b><br>Người tạo: {marker['created_by']}<br>Ghi chú: {marker['note']}<br>{time.ctime(marker['timestamp']/1000)}", max_width=300),
            tooltip=marker['note'][:30] + "...",
            icon=folium.Icon(color="orange", icon="info-sign", prefix="glyphicon")
        ).add_to(m)

# Hiển thị bản đồ bằng st_folium (thay vì folium_static)
st_folium(m, width=1000, height=600)

# ---------- 12. Hiển thị danh sách online ----------
st.sidebar.markdown("---")
st.sidebar.subheader("👥 Cán bộ trực tuyến")
if officers:
    for uid, info in officers.items():
        st.sidebar.write(f"• {info['name']} {'(bạn)' if uid==username else ''}")
else:
    st.sidebar.write("Chưa có ai chia sẻ vị trí")

# ---------- 13. Xem gần đây ----------
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
