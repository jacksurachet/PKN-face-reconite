import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from streamlit_gsheets import GSheetsConnection
import os
import requests
import time
import pandas as pd
import datetime
import plotly.express as px
from io import BytesIO

# ตั้งค่าหน้าจอโปรแกรมให้กว้างเต็มตา
st.set_page_config(layout="wide", page_title="CCTV Face Recognition & Dashboard")

# 1. เชื่อมต่อฐานข้อมูล Google Sheets
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df_students = conn.read(worksheet="ชีต1", ttl="120s")
except Exception as e:
    st.error(f"⚠️ การเชื่อมต่อฐานข้อมูลรายชื่อขัดข้อง: {e}")
    df_students = None

# ----------------- เมนูหลักแยกหน้าตาโปรแกรม (Sidebar Navigation) -----------------
st.sidebar.title("📌 เมนูการใช้งาน")
menu = st.sidebar.radio("เลือกหน้าต่างที่ต้องการ:", ["📹 ระบบสแกนใบหน้าหน้างาน", "📊 รายงานสรุปผลสถิติ (Dashboard)"])

# =========================================================================
# หน้าที่ 1: ระบบสแกนใบหน้าและลงทะเบียน
# =========================================================================
if menu == "📹 ระบบสแกนใบหน้าหน้างาน":
    st.title("🖲️ ระบบบันทึกข้อมูลนักเรียนและแจ้งเตือนผ่าน LINE OA")
    st.write("ระบบดึงกล้องตรวจจับใบหน้า ล็อกสิทธิ์การบันทึกและส่งไลน์เข้ากลุ่มวันละ 1 ครั้ง")
    
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    def draw_thai_text(img, text, position, font_size=24, color=(0, 255, 0)):
        img_pil = Image.fromarray(img)
        draw = ImageDraw.Draw(img_pil)
        font_paths = ["C:\\Windows\\Fonts\\tahoma.ttf", "C:\\Windows\\Fonts\\LeelawUI.ttf", "arial.ttf"]
        font = None
        for path in font_paths:
            try: font = ImageFont.truetype(path, font_size); break
            except: continue
        if font is None: font = ImageFont.load_default()
        draw.text(position, text, font=font, fill=color)
        return np.array(img_pil)

    def upload_to_imgbb(image_path):
        try:
            api_key = st.secrets["imgbb"]["api_key"]
            url = "https://api.imgbb.com/1/upload"
            with open(image_path, "rb") as file:
                payload = {"key": api_key}
                files = {"image": file}
                response = requests.post(url, data=payload, files=files)
                if response.status_code == 200: return response.json()["data"]["url"]
        except: pass
        return None

    # 🛠️ ปรับปรุงฟังก์ชันส่งข้อความ LINE OA ให้รองรับการยิงเข้า Group ID (บับเบิ้ลคู่แยกข้อความกับรูป)
    def send_line_message(target_id, message, image_url):
        try:
            token = st.secrets["line_oa"]["channel_access_token"]
            url = "https://api.line.me/v2/bot/message/push"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            # โครงสร้างข้อความรองรับทั้งส่งส่วนตัว (U...) และส่งเข้ากลุ่ม (C...)
            messages_payload = [{"type": "text", "text": message}]
            
            if image_url:
                messages_payload.append({
                    "type": "image",
                    "originalContentUrl": image_url,
                    "previewImageUrl": image_url
                })
                
            payload = {"to": target_id, "messages": messages_payload}
            res = requests.post(url, headers=headers, json=payload)
            return res.status_code == 200
        except:
            return False

    IMAGE_DIR = "uploaded_faces"
    CAPTURED_DIR = "captured_logs"
    for d in [IMAGE_DIR, CAPTURED_DIR]:
        if not os.path.exists(d): os.makedirs(d)

    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if 'local_check_in_cache' not in st.session_state: st.session_state.local_check_in_cache = {}

    col1, col2 = st.columns([1, 1.2])

    with col1:
        st.header("📋 จัดการข้อมูลนักเรียน")
        if not st.session_state.logged_in:
            st.subheader("🔐 เข้าสู่ระบบเพื่อเปิดฟอร์มลงทะเบียน")
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                login_btn = st.form_submit_button("🔑 เข้าสู่ระบบ")
            if login_btn:
                if username == "admin" and password == "1234":
                    st.session_state.logged_in = True; st.success("🔓 เข้าสู่ระบบสำเร็จ!"); st.rerun()
                else: st.error("❌ Username หรือ Password ไม่ถูกต้อง")
        else:
            st.subheader("👤 ลงทะเบียนนักเรียนใหม่")
            if st.button("🚪 ออกจากระบบ (Logout)"): st.session_state.logged_in = False; st.rerun()
                
            with st.form("student_registration_form", clear_on_submit=True):
                full_name = st.text_input("ชื่อ - นามสกุล นักเรียน")
                grade_info = st.text_input("ระดับชั้น / ตำแหน่ง")
                line_user_id = st.text_input("LINE ID (ระบุ User ID หรือ Group ID)")
                st.write("---")
                st.caption("📸 อัปโหลดรูปภาพใบหน้าหน้าตรง (แยก 5 แถว)")
                file1 = f1 = st.file_uploader("รูปที่ 1", type=["jpg", "jpeg", "png"], key="f1")
                file2 = f2 = st.file_uploader("รูปที่ 2", type=["jpg", "jpeg", "png"], key="f2")
                file3 = f3 = st.file_uploader("รูปที่ 3", type=["jpg", "jpeg", "png"], key="f3")
                file4 = f4 = st.file_uploader("รูปที่ 4", type=["jpg", "jpeg", "png"], key="f4")
                file5 = f5 = st.file_uploader("รูปที่ 5", type=["jpg", "jpeg", "png"], key="f5")
                submit_btn = st.form_submit_button("💾 บันทึกข้อมูลและซิงค์ลง Google Sheets")

            if submit_btn:
                if not full_name.strip(): st.error("❌ กรุณาระบุชื่อ-นามสกุล")
                elif not (file1 and file2 and file3 and file4 and file5): st.warning("⚠️ กรุณาอัปโหลดรูปภาพให้ครบ")
                else:
                    saved_paths = []
                    for idx, f in enumerate([file1, file2, file3, file4, file5], 1):
                        file_path = os.path.join(IMAGE_DIR, f"{full_name}_{idx}.png")
                        with open(file_path, "wb") as buf: buf.write(f.getbuffer())
                        saved_paths.append(file_path)
                    try:
                        new_student_data = pd.DataFrame([{"ชื่อ - นามสกุล": full_name, "ระดับชั้น": grade_info, "LINE ID": line_user_id.strip(), "ไฟล์ภาพ": ", ".join(saved_paths)}])
                        conn.update(worksheet="ชีต1", data=new_student_data)
                        st.success(f"🎉 บันทึกรายชื่อคุณ {full_name} เรียบร้อย!")
                        st.cache_data.clear(); st.rerun()
                    except Exception as register_err: st.error(f"บันทึกรายชื่อขัดข้อง: {register_err}")

        st.write("---")
        st.subheader("🗂️ รายชื่อฐานข้อมูลปัจจุบัน (ดึงจาก ชีต1)")
        if df_students is not None and not df_students.empty:
            st.dataframe(df_students, use_container_width=True)

    with col2:
        st.header("📹 กล้องสแกนใบหน้า CCTV Real-time")
        run_camera = st.checkbox("🟢 เปิดการใช้งานกล้องในเครื่องคอมพิวเตอร์", value=True)
        FRAME_WINDOW = st.image([])
        st.write("---")
        st.subheader("📊 ข้อมูลบันทึกเวลล่าสุด ( Log_Attendance )")
        log_table_area = st.empty()

        if run_camera:
            camera = cv2.VideoCapture(0)
            last_sheet_read_time = 0
            df_current_log = None
            
            while run_camera and camera.isOpened():
                ret, frame = camera.read()
                if not ret: break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
                
                date_now = time.strftime("%Y-%m-%d")
                time_now = time.strftime("%H:%M:%S")
                
                if df_students is not None and not df_students.empty:
                    try:
                        name_target = df_students.iloc[-1].iloc[0]
                        grade_target = df_students.iloc[-1].iloc[1]
                        line_id_target = df_students.iloc[-1].iloc[2]
                    except: name_target = "บุคคลทั่วไป"; grade_target = "ทั่วไป"; line_id_target = ""
                else: name_target = "บุคคลทั่วไป"; grade_target = "ทั่วไป"; line_id_target = ""

                for (x, y, w, h) in faces:
                    cv2.rectangle(rgb_frame, (x, y), (x+w, y+h), (0, 255, 0), 3)
                    rgb_frame = draw_thai_text(rgb_frame, f"{name_target} ({grade_target})", (x, y - 35))
                    
                    track_key = f"{name_target}_{date_now}"
                    already_exists = False
                    
                    if track_key in st.session_state.local_check_in_cache:
                        already_exists = True
                    else:
                        current_loop_time = time.time()
                        if current_loop_time - last_sheet_read_time > 60:
                            try:
                                df_current_log = conn.read(worksheet="Log_Attendance", ttl="60s")
                                last_sheet_read_time = current_loop_time
                            except: pass
                        if df_current_log is not None and not df_current_log.empty:
                            match_condition = (df_current_log["ชื่อ - นามสกุล"].astype(str) == str(name_target)) & (df_current_log["วันที่"].astype(str) == str(date_now))
                            if match_condition.any():
                                already_exists = True
                                st.session_state.local_check_in_cache[track_key] = True

                    if not already_exists:
                        st.session_state.local_check_in_cache[track_key] = True
                        img_path = os.path.join(CAPTURED_DIR, f"face_{time.strftime('%Y%m%d_%H%M%S')}.jpg")
                        cv2.imwrite(img_path, frame)
                        st.toast("📸 ตรวจพบข้อมูล! กำลังส่งรายงานแจ้งเตือนเข้ากลุ่ม...")
                        uploaded_url = upload_to_imgbb(img_path)
                        msg_text = f"🔔 แจ้งเตือนจากโรงเรียน:\nขณะนี้ '{name_target}' ({grade_target}) ได้เดินทางมาถึงโรงเรียนแล้วเมื่อเวลา {time.strftime('%H:%M')} น."
                        
                        if line_id_target: 
                            send_line_message(str(line_id_target).strip(), msg_text, uploaded_url)
                            
                        try:
                            new_log_row = pd.DataFrame([{"ชื่อ - นามสกุล": name_target, "ระดับชั้น": grade_target, "วันที่": date_now, "เวลา": time_now}])
                            conn.update(worksheet="Log_Attendance", data=new_log_row)
                            st.toast("📊 บันทึกประวัติลง Google Sheets สำเร็จเรียบร้อย!")
                            st.cache_data.clear()
                        except Exception as sheet_err: st.write(f"⚠️ บันทึกข้อมูลลงชีตขัดข้อง: {sheet_err}")

                try:
                    df_log_show = conn.read(worksheet="Log_Attendance", ttl="60s")
                    if df_log_show is not None and not df_log_show.empty:
                        log_table_area.dataframe(df_log_show.tail(5), use_container_width=True)
                except: pass
                FRAME_WINDOW.image(rgb_frame)
            camera.release()

# =========================================================================
# หน้าที่ 2: ระบบรายงานสรุปผลอัจฉริยะ (เรียงตามระดับชั้น)
# =========================================================================
elif menu == "📊 รายงานสรุปผลสถิติ (Dashboard)":
    st.title("📊 รายงานสรุปผลการเข้าโรงเรียนสถิตินักเรียน")
    st.write("หน้าวิเคราะห์ข้อมูล ดึงข้อมูลตรงจากแท็บ `Log_Attendance` และทำการเรียงลำดับตามระดับชั้นให้โดยอัตโนมัติ")

    try:
        df_log = conn.read(worksheet="Log_Attendance", ttl="10s")
    except Exception as e:
        st.error(f"ไม่สามารถเชื่อมต่อแท็บ Log_Attendance ได้: {e}")
        df_log = None

    if df_log is not None and not df_log.empty:
        df_log['วันที่'] = pd.to_datetime(df_log['วันที่']).dt.date
        today = datetime.date.today()

        st.subheader("🔍 ตัวเลือกการกรองข้อมูลรายงาน")
        filter_type = st.selectbox("เลือกประเภทรายงานที่ต้องการดู:", ["รายวัน (วันนี้)", "รายสัปดาห์ (7 วันย้อนหลัง)", "รายเดือน (30 วันย้อนหลัง)", "รายปี (365 วันย้อนหลัง)", "เลือกช่วงเวลาเองผ่านปฏิทิน 📅"])

        start_date, end_date = today, today
        
        if filter_type == "รายวัน (วันนี้)":
            start_date, end_date = today, today
        elif filter_type == "รายสัปดาห์ (7 วันย้อนหลัง)":
            start_date = today - datetime.timedelta(days=7); end_date = today
        elif filter_type == "รายเดือน (30 วันย้อนหลัง)":
            start_date = today - datetime.timedelta(days=30); end_date = today
        elif filter_type == "รายปี (365 วันย้อนหลัง)":
            start_date = today - datetime.timedelta(days=365); end_date = today
        elif filter_type == "เลือกช่วงเวลาเองผ่านปฏิทิน 📅":
            date_range = st.date_input("เลือกช่วงระหว่างวันที่ต้องการค้นหา:", [today - datetime.timedelta(days=7), today])
            if len(date_range) == 2: start_date, end_date = date_range[0], date_range[1]
            else: start_date = date_range[0]; end_date = date_range[0]

        df_filtered = df_log[(df_log['วันที่'] >= start_date) & (df_log['วันที่'] <= end_date)]

        st.write("---")
        m1, m2, m3 = st.columns(3)
        with m1: st.metric(label="📈 จำนวนครั้งสแกนรวมในช่วงนี้", value=f"{len(df_filtered)} ครั้ง")
        with m2: st.metric(label="🧑‍🎓 จำนวนนักเรียนที่มาสแกน (ไม่นับชื่อซ้ำ)", value=f"{df_filtered['ชื่อ - นามสกุล'].nunique()} คน")
        with m3: st.metric(label="📅 ช่วงเวลาที่กำลังแสดง", value=f"{start_date.strftime('%d/%m/%Y')} ถึง {end_date.strftime('%d/%m/%Y')}")

        st.write("---")
        g1, g2 = st.columns([1.3, 1])
        
        with g1:
            st.subheader("📋 ตารางข้อมูลประวัติ (จัดกลุ่มเรียงตามระดับชั้น)")
            if not df_filtered.empty and "ระดับชั้น" in df_filtered.columns:
                df_sorted_by_grade = df_filtered.sort_values(by=["ระดับชั้น", "วันที่", "เวลา"], ascending=[True, False, False])
                st.dataframe(df_sorted_by_grade, use_container_width=True)
                
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_sorted_by_grade.to_excel(writer, index=False, sheet_name='Sorted_By_Grade')
                processed_data = output.getvalue()
                
                st.download_button(
                    label="📥 ดาวน์โหลดรายงานแบบเรียงระดับชั้น (.xlsx)",
                    data=processed_data,
                    file_name=f"รายงานสแกนแยกชั้น_{start_date}_ถึง_{end_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.dataframe(df_filtered, use_container_width=True)

        with g2:
            st.subheader("📊 สรุปสถิติจำนวนรวมแยกตามระดับชั้น")
            if not df_filtered.empty and "ระดับชั้น" in df_filtered.columns:
                df_count_grade = df_filtered['ระดับชั้น'].value_counts().reset_index()
                df_count_grade.columns = ['ระดับชั้น / ตำแหน่ง', 'จำนวนครั้งที่พบ (ครั้ง)']
                st.table(df_count_grade)
                
                df_pie = df_filtered['ระดับชั้น'].value_counts().reset_index()
                df_pie.columns = ['ระดับชั้น', 'จำนวนครั้ง']
                fig = px.pie(df_pie, values='จำนวนครั้ง', names='ระดับชั้น', hole=0.3, color_discrete_sequence=px.colors.sequential.Plotly3)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("💡 ไม่มีข้อมูลระดับชั้นมาคำนวณในเวลานี้")

    else:
        st.info("💡 ปัจจุบันยังไม่มีข้อมูลประวัติในแท็บ Log_Attendance หรือ Google Sheets ยังว่างเปล่าอยู่ครับคุณแจ็ค")