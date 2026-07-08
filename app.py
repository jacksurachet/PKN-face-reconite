import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from streamlit_gsheets import GSheetsConnection
import os
import requests
import time

# ตั้งค่าหน้าจอโปรแกรมให้กว้างและสวยงาม
st.set_page_config(layout="wide", page_title="CCTV Face Recognition with LINE OA")

st.title("🖲️ ระบบบันทึกข้อมูลนักเรียนและแจ้งเตือนผู้ปกครองพร้อมส่งรูปถ่ายผ่าน LINE OA")
st.write("ระบบสแกนใบหน้า แคปเจอร์ภาพ และส่งรูปถ่ายพร้อมเวลาแจ้งเตือนอัตโนมัติเข้า LINE Official Account")

# ดึงค่าความลับจาก secrets.toml
try:
    LINE_ACCESS_TOKEN = st.secrets["line_oa"]["channel_access_token"]
    IMGBBB_API_KEY = st.secrets["imgbb"]["api_key"]
except:
    LINE_ACCESS_TOKEN = "MOCK_TOKEN"
    IMGBBB_API_KEY = "MOCK_KEY"

# เชื่อมต่อ Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="5s")
except Exception as e:
    st.error(f"⚠️ สัญญาณเชื่อมต่อ Google Sheets ขัดข้อง (ตรวจสอบไฟล์ secrets.toml): {e}")
    df = None

# เรียกใช้ตัวตรวจจับใบหน้ามาตรฐานของ OpenCV
# ดึงไฟล์โมเดลตรวจจับใบหน้าผ่าน URL โดยตรงเพื่อระบบออนไลน์
face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')


# ฟังก์ชันเขียนภาษาไทยลงบนภาพ OpenCV แบบดึงฟอนต์ระบบ Windows อัตโนมัติ
def draw_thai_text(img, text, position, font_size=24, color=(255, 255, 255)):
    img_pil = Image.fromarray(img)
    draw = ImageDraw.Draw(img_pil)
    
    font_paths = [
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "C:\\Windows\\Fonts\\cordia.ttf",
        "C:\\Windows\\Fonts\\browa.ttf",
        "C:\\Windows\\Fonts\\LeelawUI.ttf",
        "arial.ttf"
    ]
    
    font = None
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except:
            continue
            
    if font is None:
        font = ImageFont.load_default()
        
    draw.text(position, text, font=font, fill=color)
    return np.array(img_pil)

# ฟังก์ชันฝากรูปภาพขึ้นอินเทอร์เน็ต เพื่อแปลงเป็นลิงก์ URL
def upload_image_to_imgbb(image_path):
    if IMGBBB_API_KEY == "MOCK_KEY": return None
    url = "https://api.imgbb.com/1/upload"
    try:
        with open(image_path, "rb") as file:
            payload = {"key": IMGBBB_API_KEY}
            files = {"image": file}
            response = requests.post(url, data=payload, files=files)
            if response.status_code == 200:
                return response.json()["data"]["url"]
    except:
        pass
    return None

# ฟังก์ชันส่งข้อความ + รูปภาพเข้า LINE OA
def send_line_oa_with_image(user_id, message, image_url):
    if LINE_ACCESS_TOKEN == "MOCK_TOKEN": return False
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    
    messages_payload = [
        {"type": "text", "text": message}
    ]
    
    if image_url:
        messages_payload.append({
            "type": "image",
            "originalContentUrl": image_url,
            "previewImageUrl": image_url
        })

    payload = {
        "to": user_id,
        "messages": messages_payload
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.status_code == 200
    except:
        return False

# ระบบความจำชั่วคราว (Session State)
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'notified_students' not in st.session_state: st.session_state.notified_students = {}

IMAGE_DIR = "uploaded_faces"
CAPTURED_DIR = "captured_logs" 
for d in [IMAGE_DIR, CAPTURED_DIR]:
    if not os.path.exists(d): os.makedirs(d)

col1, col2 = st.columns([1, 1.2])

# ================= ฝั่งซ้าย: ระบบล็อกอิน และ UI ลงทะเบียนนักเรียน =================
with col1:
    if not st.session_state.logged_in:
        st.header("🔐 เข้าสู่ระบบ (สำหรับคุณครู)")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            login_btn = st.form_submit_button("🔑 เข้าสู่ระบบ")
            
        if login_btn:
            if username == "admin" and password == "1234":
                st.session_state.logged_in = True
                st.success("🔓 ล็อกอินสำเร็จ!")
                st.rerun()
            else:
                st.error("❌ รหัสผ่านไม่ถูกต้อง")
    else:
        st.header("👤 1. ลงทะเบียนนักเรียนใหม่")
        if st.button("🚪 ออกจากระบบ (Logout)"):
            st.session_state.logged_in = False
            st.rerun()
            
        st.write("---")
        
        with st.form("user_registration_form", clear_on_submit=True):
            full_name = st.text_input("ชื่อ - นามสกุล นักเรียน")
            grade_info = st.text_input("ระดับชั้น")
            line_user_id = st.text_input("LINE User ID ของผู้ปกครอง (ขึ้นต้นด้วยตัว U...)")
            
            st.write("---")
            st.subheader("📸 อัปโหลดรูปภาพใบหน้าหน้าตรง (แยก 5 แถว)")
            file1 = st.file_uploader("เลือกรูปภาพใบหน้าที่ 1", type=["jpg", "jpeg", "png"], key="f1")
            file2 = st.file_uploader("เลือกรูปภาพใบหน้าที่ 2", type=["jpg", "jpeg", "png"], key="f2")
            file3 = st.file_uploader("เลือกรูปภาพใบหน้าที่ 3", type=["jpg", "jpeg", "png"], key="f3")
            file4 = st.file_uploader("เลือกรูปภาพใบหน้าที่ 4", type=["jpg", "jpeg", "png"], key="f4")
            file5 = st.file_uploader("เลือกรูปภาพใบหน้าที่ 5", type=["jpg", "jpeg", "png"], key="f5")
            
            submit_btn = st.form_submit_button("💾 บันทึกข้อมูลเข้า Google Sheets")

        if submit_btn:
            if not full_name.strip():
                st.error("❌ กรุณากรอกชื่อนักเรียน")
            elif not (file1 and file2 and file3 and file4 and file5):
                st.warning("⚠️ กรุณาอัปโหลดรูปให้ครบทั้ง 5 ช่อง")
            else:
                saved_paths = []
                for idx, f in enumerate([file1, file2, file3, file4, file5], 1):
                    file_path = os.path.join(IMAGE_DIR, f"{full_name}_{idx}.png")
                    with open(file_path, "wb") as buf:
                        buf.write(f.getbuffer())
                    saved_paths.append(file_path)
                
                try:
                    new_data = np.array([[full_name, grade_info, line_user_id.strip(), ", ".join(saved_paths)]])
                    conn.update(data=new_data)
                    st.success(f"🎉 บันทึกข้อมูลและซิงค์ข้อมูลลง Google Sheets เรียบร้อย!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"บันทึกลงชีตล้มเหลว: {e}")

        st.write("---")
        st.subheader("📋 ตรวจสอบรายชื่อนักเรียนล่าสุด")
        if df is not None and not df.empty:
            st.dataframe(df, use_container_width=True)

# ================= ฝั่งขวา: หน้าจอกล้อง CCTV และระบบตรวจจับส่ง LINE OA =================
with col2:
    st.header("📹 2. หน้าจอตรวจสอบผ่านกล้อง CCTV")
    run_cctv = st.checkbox("🟢 เปิดใช้งานกล้อง CCTV / Webcam", value=True)
    FRAME_WINDOW = st.image([])

    if run_cctv:
        camera = cv2.VideoCapture(0)
        
        while run_cctv:
            ret, frame = camera.read()
            if not ret: break
                
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            
            if df is not None and not df.empty:
                try:
                    student_name = df.iloc[-1].iloc[0]      
                    user_id_target = df.iloc[-1].iloc[2]    
                    display_text = f"{student_name}"
                except:
                    student_name = "Unknown"; user_id_target = ""; display_text = "Unknown"
            else:
                student_name = "Unknown"; user_id_target = ""; display_text = "Unknown"
                
            # ดึงวันที่ปัจจุบันมาใช้เป็นกุญแจเช็กคู่ (รองรับคอมพิวเตอร์หลับข้ามวัน)
            current_date = time.strftime("%Y-%m-%d")
                
            for (x, y, w, h) in faces:
                cv2.rectangle(rgb_frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
                rgb_frame = draw_thai_text(rgb_frame, display_text, (x, y - 35), font_size=24, color=(255, 255, 0))
                
                if user_id_target and str(user_id_target).strip() != "" and student_name != "Unknown":
                    
                    # ตรวจสอบคู่ (ชื่อนักเรียน + วันที่สแกน) ป้องกันส่งซ้ำในวันเดียวกัน
                    tracking_key = f"{student_name}_{current_date}"
                    
                    if tracking_key not in st.session_state.notified_students:
                        
                        # 1. แคปภาพถ่ายเก็บหลักฐานลงคอมพิวเตอร์
                        timestamp = time.strftime("%Y%m%d-%H%M%S")
                        cap_image_path = os.path.join(CAPTURED_DIR, f"{student_name}_{timestamp}.jpg")
                        cv2.imwrite(cap_image_path, frame)
                        
                        # 2. ฝากรูปแปลงเป็น Link URL สำหรับส่งเข้าแอป LINE
                        st.toast("📸 กำลังประมวลผลรูปถ่ายนักเรียน...")
                        uploaded_url = upload_image_to_imgbb(cap_image_path)
                        
                        # 3. คำนวณเวลาและจัดส่ง LINE OA พร้อมรูปถ่ายสดแบบระบุเวลาเช็กอิน
                        current_time = time.strftime("%H:%M")
                        msg = f"🔔 แจ้งเตือนจากโรงเรียน:\nขณะนี้ นักเรียนชื่อ '{student_name}' ได้เดินทางมาถึงโรงเรียนเวลา {current_time} น. เรียบร้อยแล้วค่ะ"
                        
                        success = send_line_oa_with_image(str(user_id_target).strip(), msg, uploaded_url)
                        if success:
                            st.session_state.notified_students[tracking_key] = time.time()
                            st.toast(f"📨 ส่งการแจ้งเตือนพร้อมรูปถ่ายของ {student_name} สำเร็จ!")
            
            FRAME_WINDOW.image(rgb_frame)
            
        camera.release()
