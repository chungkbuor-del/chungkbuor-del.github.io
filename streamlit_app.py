import streamlit as st
import json
import requests
import urllib.parse
from datetime import datetime
import gspread 
from google.oauth2.service_account import Credentials as ServiceAccountCredentials 
from PIL import Image
import os 
from typing import Dict, Any

# --- CẤU HÌNH VÀ HẰNG SỐ (GIỮ NGUYÊN) ---
BASE_URL = "https://wms.ssc.shopee.vn"
WEBHOOK_URL = "https://openapi.seatalk.io/webhook/group/K7reBE2PRrOj7aPfyLA6QQ"
SERVICE_ACCOUNT_FILE = "JSON4.json" 
LOGO_FILE = "logo-shopee.jpg" 

# Cấu hình Google Sheet
COOKIE_SHEET_ID = "1QRaq07g9d14bw_rpW0Q-c8f7e1qRYQRq8_vI426yUro"
COOKIE_WORKSHEET_NAME = "WMS"
COOKIE_CELL = "A2"
G_SHEET_ID = "1isi7V0KL9oMDUTcaNjPyFn6RyiyIkhjdmT1rgY53RuE"
G_SHEET_NAME = "TBS_Picker"

# Danh sách lựa chọn
ISSUE_OPTIONS = [
    "Thiếu hàng - Dư tại loc",
    "Thiếu hàng - Không dư tại loc",
    "Sai hàng - Dư tại loc",
    "Sai hàng - Không dư tại loc",
    "Dư hàng - Hàng thiếu tại loc",
    "Dư hàng - Hàng không dư tại loc",
    "Khác (Nhập thủ công)"
]

MENTION_MAP = {
    "hien.thunguyen@shopee.com": "Hiền | VNS | OB",
    "nhu.tranthi@shopee.com": "Như Trần | VNS OB SBS🪷🌷",
    "ngoctran.kimthi@shopee.com": "Ngọc Trần | VNS | OB",
    "tu.nguyenthien@shopee.com": "Thiên Tữ | VNS | OB",
    "xa.dangvan@shopee.com": "Đặng Văn Xạ | VNS | OB 🇻🇳",
    "kimloan.nguyenthi@shopee.com": "Kim Loan | VNS | OB🥦",
    "@all": "@all" 
}
MENTION_OPTIONS_EMAIL = list(MENTION_MAP.keys())

# --- CÁC HÀM XỬ LÝ API VÀ GSHEET (KHÔNG ĐỔI LOGIC) ---

def get_google_sheet_worksheet_by_id(spreadsheet_id, worksheet_name):
    """Kết nối tới Google Sheet bằng Service Account."""
    try:
        creds = ServiceAccountCredentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(worksheet_name)
        return worksheet
    except Exception as e:
        st.error(f"Lỗi kết nối Google Sheet: {e}")
        return None

def write_to_google_sheet(data_row: Dict[str, Any]):
    """Ghi dữ liệu B:G và I vào dòng tiếp theo mà KHÔNG xóa các cột khác."""
    worksheet = get_google_sheet_worksheet_by_id(G_SHEET_ID, G_SHEET_NAME)
    if not worksheet:
        return False, "Không thể kết nối/xác thực Google Sheet Báo Cáo."
    
    try:
        next_row = len(worksheet.col_values(2)) + 1 
        
        data_main = [
            data_row["picking_task_id"], # B
            data_row["sku_id"],          # C
            data_row["sku_name"],        # D
            data_row["location"],        # E
            data_row["qty"],             # F 
            data_row["operator"]         # G
        ]
        
        worksheet.update(f'B{next_row}', [data_main])
        worksheet.update_cell(next_row, 9, data_row["issue"])
        
        return True, "Ghi dữ liệu lên Google Sheet thành công."
    except Exception as e:
        return False, f"Lỗi khi ghi lên Google Sheet: {e.__class__.__name__}: {e}"

def load_headers_from_sheet():
    """Tải chuỗi cookie từ Google Sheet và tạo headers."""
    try:
        worksheet = get_google_sheet_worksheet_by_id(COOKIE_SHEET_ID, COOKIE_WORKSHEET_NAME)
        if not worksheet:
            raise Exception("Không thể kết nối/xác thực Google Sheet Cookie.")
            
        cookie_string = worksheet.acell(COOKIE_CELL).value
        
        if not cookie_string:
            raise ValueError(f"Ô '{COOKIE_CELL}' trên Sheet '{COOKIE_WORKSHEET_NAME}' trống.")

        base_headers = {
            "Sec-CH-UA": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Referer": f"{BASE_URL}/",
            "Origin": BASE_URL,
            "Cookie": cookie_string
        }
        return base_headers

    except Exception as e:
        st.error(f"Lỗi Cookie/Sheet: {e}")
        return None

def fetch_sku_info(headers, sub_pickup_id, sku_id):
    """Call API 1 để lấy SKU Name (Location không dùng)."""
    if not headers:
        return None
    full_sub_pickup_id = f"{sub_pickup_id}_0"
    encoded_sub_pickup_id = urllib.parse.quote(full_sub_pickup_id)
    api_url = f"{BASE_URL}/api/v2/apps/process/taskcenter/pickingtask/get_sales_sub_picking_sku_list?count=20&pageno=1&sub_pickup_id={encoded_sub_pickup_id}"
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("retcode") == 0 and data.get("data") and data["data"].get("sub_picking_sku_list"):
            sku_list = data["data"]["sub_picking_sku_list"]
            for sku_item in sku_list:
                if sku_item.get("sku_id") == sku_id:
                    result = {
                        "sku_name": sku_item.get("sku_name", "N/A"),
                        "api_location": sku_item.get("actual_locations", ["N/A"])[0], 
                        "api_qty": sku_item.get("picked_quantity", 0), 
                        "message": f"Tìm thấy SKU: **{sku_item.get('sku_name', 'N/A')}**"
                    }
                    return result
            return {"message": f"Không tìm thấy SKU ID: **{sku_id}** trong danh sách.", "sku_name": "N/A", "api_location": "N/A", "api_qty": "N/A"}
        else:
            return {"message": f"Lỗi API 1 hoặc không có dữ liệu: {data.get('message', 'Lỗi không rõ')}", "sku_name": "N/A", "api_location": "N/A", "api_qty": "N/A"}
    except requests.exceptions.RequestException as e:
        return {"message": f"Lỗi kết nối API 1: {e}", "sku_name": "N/A", "api_location": "N/A", "api_qty": "N/A"}
    except Exception as e:
        return {"message": f"Lỗi xử lý JSON/dữ liệu API 1: {e}", "sku_name": "N/A", "api_location": "N/A", "api_qty": "N/A"}

def fetch_operator_by_status(headers, sub_pickup_id, status_to_find=2):
    """Call API 2 để lấy operator tương ứng với 'status': 2."""
    if not headers:
        return None
    full_sub_pickup_id = f"{sub_pickup_id}_0"
    encoded_sub_pickup_id = urllib.parse.quote(full_sub_pickup_id)
    api_url = f"{BASE_URL}/api/v2/apps/process/outbound/trackinglog/get_outbound_task_tracking_log?task_type=5&task_number={encoded_sub_pickup_id}"
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("retcode") == 0 and data.get("data") and data["data"].get("list"):
            tracking_list = data["data"]["list"]
            for log_item in tracking_list:
                if log_item.get("status") == status_to_find:
                    operator = log_item.get("operator", "N/A")
                    ctime_ts = log_item.get("ctime")
                    ctime_str = datetime.fromtimestamp(ctime_ts).strftime('%Y-%m-%d %H:%M:%S') if ctime_ts else "N/A"
                    return {
                        "operator": operator,
                        "ctime": ctime_str,
                        "message": f"Operator (Status {status_to_find}): **{operator}** (Thời gian: {ctime_str})"
                    }
            return {"message": f"Không tìm thấy log có status: **{status_to_find}**.", "operator": "N/A"}
        else:
            return {"message": f"Lỗi API 2 hoặc không có dữ liệu: {data.get('message', 'Lỗi không rõ')}", "operator": "N/A"}
    except requests.exceptions.RequestException as e:
        return {"message": f"Lỗi kết nối API 2: {e}", "operator": "N/A"}
    except Exception as e:
        return {"message": f"Lỗi xử lý JSON/dữ liệu API 2: {e}", "operator": "N/A"}

def send_webhook_report(data, tag_input):
    """Gửi dữ liệu báo cáo lên Webhook Seatalk, tag người dùng được chọn ở cuối."""
    
    tag_nickname = MENTION_MAP.get(tag_input, tag_input)

    tag_mention = ""
    if tag_nickname.strip():
        tag_mention = f"@{tag_nickname.strip()}"
        
    report_message_content = (
        f"**REPORT ISSUE PICKER**\n"
        f"---\n"
        f"**Picking Task ID:** {data['picking_task_id']}\n"
        f"**Operator:** {data['operator']}\n"
        f"**SKU ID:** {data['sku_id']}\n"
        f"**SKU NAME:** {data['sku_name']}\n"
        f"**QTY:** {data['qty']}\n" 
        f"**LOCATION:** {data['location']}\n" 
        f"**ISSUE:** {data['issue']}\n"
        f"---\n"
        f"Thời gian báo cáo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{tag_mention}" 
    )

    payload = {
        "tag": "text",
        "text": {
            "content": report_message_content
        }
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        
        try:
            response_data = response.json()
        except json.JSONDecodeError:
             response_data = {"ok": False, "message": "Phản hồi không phải JSON hoặc lỗi nội bộ Seatalk"}
        
        if response.status_code == 200 and response_data.get("code") == 0:
             return True, "Gửi Webhook thành công!"
        else:
             return False, f"Lỗi từ Seatalk: Status {response.status_code}, Response: {response_data}"

    except requests.exceptions.RequestException as e:
        return False, f"Lỗi kết nối khi gửi Webhook: {e}"
    except Exception as e:
        return False, f"Lỗi không xác định khi gửi Webhook: {e}"

# --- HÀM CHÍNH CHO STREAMLIT ---

def run_streamlit_app():
    # 1. Thiết lập trang
    st.set_page_config(page_title="WMS Report Tool", layout="centered")

    # 2. Thêm Logo
    try:
        img = Image.open(LOGO_FILE)
        st.image(img, width=100)
    except Exception:
        st.title("WMS Auto-Report Tool")

    st.markdown("---")
    st.header("Công cụ WMS Shopee - Báo cáo Lỗi")

    # 3. Form nhập liệu
    with st.form(key='wms_form'):
        col1, col2 = st.columns(2)
        
        # Cột 1: ID và Qty
        sub_pickup_id = col1.text_input("Sub Pickup ID:")
        qty_input = col1.text_input("Qty:")
        
        # Cột 2: SKU và Location
        sku_id = col2.text_input("SKU ID:")
        location_input = col2.text_input("Location:")

        # Hàng dưới: Issue và Tag
        issue = st.selectbox("Issue:", options=ISSUE_OPTIONS)
        tag_input_email = st.selectbox("Acc Tag:", options=MENTION_OPTIONS_EMAIL)
        
        submitted = st.form_submit_button("Chạy Tác vụ API & Gửi BÁO CÁO")

    # 4. Xử lý logic khi nhấn nút
    if submitted:
        if not all([sub_pickup_id, sku_id, qty_input, location_input, issue, tag_input_email]):
            st.warning("⚠️ Vui lòng nhập đầy đủ tất cả các trường.")
            return

        # Khởi tạo kết quả
        results_container = st.empty()
        results_container.info("Đang xử lý, vui lòng chờ...")
        
        # Lấy headers (Cookie)
        headers = load_headers_from_sheet()
        if not headers:
            results_container.error("❌ Lỗi: Không thể tải Cookie.")
            return
        
        # Khởi tạo dữ liệu
        full_sub_pickup_id = f"{sub_pickup_id}_0"
        sku_name = "N/A"
        operator = "N/A"
        
        results_text = f"--- Báo cáo Tác vụ cho Sub Pickup ID: {full_sub_pickup_id} ---\n\n"

        # Tác vụ API
        sku_info = fetch_sku_info(headers, sub_pickup_id, sku_id)
        operator_info = fetch_operator_by_status(headers, sub_pickup_id)

        # Cập nhật kết quả hiển thị
        sku_name = sku_info.get('sku_name', 'N/A')
        operator = operator_info.get('operator', 'N/A')
        api_qty = sku_info.get('api_qty', 'N/A')
        api_location = sku_info.get('api_location', 'N/A')

        results_text += f"## 🏷️ Tác vụ 1: Lấy SKU Name và Location\n"
        results_text += f"**Trạng thái:** {sku_info.get('message')}\n"
        results_text += f" - SKU Name: {sku_name}\n"
        results_text += f" - QTY (API): {api_qty}\n" 
        results_text += f" - QTY (Input): {qty_input}\n" 
        results_text += f" - Location (API): {api_location}\n" 
        results_text += f" - Location (Input): {location_input}\n\n" 
        results_text += f"## 🧑‍💻 Tác vụ 2: Lấy Operator (Status 2)\n"
        results_text += f"**Trạng thái:** {operator_info.get('message')}\n"
        results_text += f" - Operator: {operator}\n"
        results_text += f" - Ctime Log: {operator_info.get('ctime', 'N/A')}\n\n"

        # Chuẩn bị dữ liệu cho Webhook và Google Sheet
        report_data = {
            "picking_task_id": full_sub_pickup_id,
            "operator": operator,
            "sku_id": sku_id,
            "sku_name": sku_name,
            "location": location_input, 
            "qty": qty_input, 
            "issue": issue
        }
        
        # Gửi báo cáo và ghi sheet
        webhook_success, webhook_message = send_webhook_report(report_data, tag_input_email)
        gsheet_success, gsheet_message = write_to_google_sheet(report_data)

        # Cập nhật kết quả cuối cùng
        results_text += "--- BÁO CÁO WEBHOOK ---\n"
        results_text += f"**Trạng thái Gửi:** {'THÀNH CÔNG' if webhook_success else 'THẤT BẠI'}\n"
        results_text += f"**Thông báo:** {webhook_message}\n"
        results_text += "--- GHI GOOGLE SHEET ---\n"
        results_text += f"**Trạng thái Ghi:** {'THÀNH CÔNG' if gsheet_success else 'THẤT BẠI'}\n"
        results_text += f"**Thông báo:** {gsheet_message}\n"

        # Hiển thị kết quả trong giao diện
        if webhook_success and gsheet_success:
            results_container.success("✅ Đã hoàn thành tất cả tác vụ và gửi báo cáo thành công!")
        else:
            results_container.error("❌ Tác vụ thất bại! Vui lòng xem chi tiết bên dưới.")
            
        st.text_area("Chi tiết Kết quả & Trạng thái Báo cáo:", results_text, height=350)


if __name__ == '__main__':
    run_streamlit_app()
