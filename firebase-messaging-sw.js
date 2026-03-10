// firebase-messaging-sw.js
importScripts('https://www.gstatic.com/firebasejs/9.22.0/firebase-app.js');
importScripts('https://www.gstatic.com/firebasejs/9.22.0/firebase-messaging.js');

// Cấu hình Firebase của bạn (LẤY TỪ FIREBASE CONSOLE)
// ⚠️ QUAN TRỌNG: Phải copy chính xác các thông số từ project Firebase của bạn
const firebaseConfig = {
    apiKey: "AIzaSy...",                // Từ Firebase Console
    authDomain: "tuan-tra-thanh-mieu.firebaseapp.com",
    projectId: "tuan-tra-thanh-mieu",
    storageBucket: "tuan-tra-thanh-mieu.firebasestorage.app",
    messagingSenderId: "297474184636",  // Từ Firebase Console
    appId: "1:297474184636:web:b2434c75ac3ae393e487b9"
};

// Khởi tạo Firebase
firebase.initializeApp(firebaseConfig);

// Lấy instance messaging
const messaging = firebase.messaging();

// Xử lý thông báo khi ứng dụng ở background (khi người dùng không mở trang)
messaging.onBackgroundMessage((payload) => {
    console.log('[firebase-messaging-sw.js] Nhận thông báo nền: ', payload);

    // Tùy chỉnh thông báo hiển thị
    const notificationTitle = payload.notification?.title || 'Thông báo từ hệ thống';
    const notificationOptions = {
        body: payload.notification?.body || 'Bạn có thông báo mới',
        icon: '/icon.png', // (Tùy chọn) Đường dẫn đến icon hiển thị
        badge: '/badge.png', // (Tùy chọn) Icon nhỏ trên thanh trạng thái
        vibrate: [200, 100, 200], // Rung điện thoại (nếu hỗ trợ)
        sound: '/alert.mp3', // (Tùy chọn) Âm thanh thông báo
        data: payload.data // Đính kèm dữ liệu nếu có
    };

    // Hiển thị thông báo
    self.registration.showNotification(notificationTitle, notificationOptions);
});

// Xử lý khi người dùng click vào thông báo (tùy chọn)
self.addEventListener('notificationclick', (event) => {
    console.log('Notification click Received.', event.notification);
    event.notification.close();

    // Mở một URL cụ thể khi click vào thông báo
    // Ví dụ: mở trang chính của ứng dụng
    const urlToOpen = event.notification.data?.url || 'https://tuan-tra-thanh-mieu.streamlit.app';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // Nếu đã có tab đang mở, focus vào tab đó
            for (const client of clientList) {
                if (client.url === urlToOpen && 'focus' in client) {
                    return client.focus();
                }
            }
            // Nếu không, mở tab mới
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});
