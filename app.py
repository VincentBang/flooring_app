import io
import re
import uuid
import datetime
from typing import List, Dict, Any

import pandas as pd
import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


# =========================
# PAGE CONFIG (ONLY ONCE, FIRST)
# =========================
st.set_page_config(page_title="Flooring Quote Prototype", layout="wide")

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzzwZm_t6A48lvX3yg7W62FOtS1GK4L6ri1bgcQ4cFB0oERpqOlbJVLP9KvYQvFHsNh8w/exec"
SHEET_ID = "10G98m8XHdySRTMWjbAUlQCZMH1NXCD6uca82xN0p4fY"

# =========================
# COMPANY DETAILS
# =========================
COMPANY = {
    "name": "Oz Timber Floor Pty Ltd",
    "abn": "ABN: 84 168 475 358",
    "phone": "Phone: 0435 496 975",
    "email": "Email: info@oztimberfloor.com.au",
    "website": "Website: oztimberfloor.com.au",
    "address": "Address line (optional)",
}
LOGO_PATH = "logo.png"

BRAND = {
    "header_rgb": (0.10, 0.10, 0.10),
    "accent_rgb": (0.18, 0.42, 0.78),
    "light_gray_rgb": (0.94, 0.94, 0.94),
    "mid_gray_rgb": (0.75, 0.75, 0.75),
}

DEFAULT_WASTAGE_PCT = 10.0
DEFAULT_FURNITURE_PER_ROOM = 50.0
GST_RATE = 0.10

# =========================
# FALLBACK DATA (SAFETY)
# =========================
PRODUCTS = [
    {"id": "p1", "brand": "BrandA", "name": "Engineered Oak 14mm", "type": "Engineered", "sell_per_m2": 120.0},
    {"id": "p2", "brand": "BrandB", "name": "Hybrid 6.5mm", "type": "Hybrid", "sell_per_m2": 75.0},
    {"id": "p3", "brand": "BrandC", "name": "Solid Timber 19mm", "type": "Solid", "sell_per_m2": 165.0},
]

INSTALL_ONLY = [
    {"id": "i1", "name": "Installation only – Engineered timber", "install_per_m2": 55.0},
    {"id": "i2", "name": "Installation only – Hybrid", "install_per_m2": 38.0},
    {"id": "i3", "name": "Installation only – Solid timber", "install_per_m2": 70.0},
]

REMOVAL_TYPES = [
    {"id": "r1", "name": "Carpet", "remove_per_m2": 12.0},
    {"id": "r2", "name": "Floating floor", "remove_per_m2": 18.0},
    {"id": "r3", "name": "Glued floor", "remove_per_m2": 28.0},
    {"id": "r4", "name": "Timber", "remove_per_m2": 35.0},
]

SKIRTING = [
    {"id": "s67", "height_mm": 67, "price_per_lm": 12.0},
    {"id": "s90", "height_mm": 90, "price_per_lm": 15.0},
    {"id": "s120", "height_mm": 120, "price_per_lm": 19.0},
]

# =========================
# GOOGLE SHEET LOAD
# =========================
@st.cache_data(ttl=300)
def load_sheet(tab_name: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={tab_name}"
    try:
        df = pd.read_csv(url)
    except Exception:
        return pd.DataFrame()

    if "active" in df.columns:
        active = df["active"].astype(str).str.strip().str.lower()
        df = df[active.isin(["true", "1", "yes", "y"])]

    return df


# =========================
# HELPERS
# =========================
def safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)

def money0(x: float) -> str:
    return f"${float(x):,.0f}"

def norm_phone(s: str) -> str:
    return re.sub(r"\D+", "", (s or "").strip())

def find_by_id(items: List[dict], item_id: str) -> dict:
    for it in items:
        if str(it.get("id")) == str(item_id):
            return it
    raise KeyError(item_id)

def line_item(label: str, qty_str: str, unit_price: float, total: float) -> dict:
    return {"label": str(label), "qty_str": str(qty_str), "unit_price": float(unit_price), "total": float(total)}

def safe_pick_id(df: pd.DataFrame, current_id: str, id_col: str = "id") -> str:
    if df is None or df.empty or id_col not in df.columns:
        return str(current_id or "")
    ids = df[id_col].astype(str).tolist()
    if not ids:
        return ""
    return str(current_id) if str(current_id) in ids else ids[0]

def _fmt_num(x: float) -> str:
    x = float(x)
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.1f}".rstrip("0").rstrip(".")

def fmt_dims(length: float, width: float) -> str:
    l = float(length or 0.0)
    w = float(width or 0.0)
    if l == 0.0 and w == 0.0:
        return ""
    return f"{_fmt_num(l)}x{_fmt_num(w)}"

def parse_dims(text: str):
    if not text:
        return None, None
    s = text.strip().lower()
    s = s.replace("×", "x").replace("*", "x").replace(" ", "").replace(",", "x")
    m = re.match(r"^(\d+(\.\d+)?)[x](\d+(\.\d+)?)$", s)
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(3))
    except Exception:
        return None, None


# =========================
# STATE
# =========================
def ensure_state():
    ss = st.session_state

    # measurements
    ss.setdefault("rooms", [{"length": 0.0, "width": 0.0}])
    if not isinstance(ss["rooms"], list) or not ss["rooms"]:
        ss["rooms"] = [{"length": 0.0, "width": 0.0}]

    # pricing meta
    ss.setdefault("wastage_pct", float(DEFAULT_WASTAGE_PCT))
    ss.setdefault("job_mode", "Supply & Install")  # chosen after wastage
    ss.setdefault("product_id", "")
    ss.setdefault("install_id", "")
    ss.setdefault("quote_type", "Retail")          # chosen after timber

    # add-ons
    ss.setdefault("skirting_id", SKIRTING[0]["id"])
    ss.setdefault("skirting_lm", 0.0)
    ss.setdefault("furniture_rate", float(DEFAULT_FURNITURE_PER_ROOM))

    # client details (moved to end)
    ss.setdefault("client_name", "")
    ss.setdefault("client_phone", "")
    ss.setdefault("client_email", "")
    ss.setdefault("site_address", "")

    # save flags
    ss.setdefault("quote_saved", False)
    ss.setdefault("last_quote_id", "")

ensure_state()

def clear_dynamic_keys():
    ss = st.session_state
    for k in list(ss.keys()):
        if str(k).startswith(("dim_", "addon_", "addon_qty_", "addon_price_", "removal_rate_")):
            del ss[k]

def reset_quote():
    ss = st.session_state
    keys_to_remove = [
        "rooms",
        "wastage_pct",
        "job_mode",
        "product_id",
        "install_id",
        "quote_type",
        "skirting_id",
        "skirting_lm",
        "furniture_rate",
        "client_name",
        "client_phone",
        "client_email",
        "site_address",
        "quote_saved",
        "last_quote_id",
    ]
    for k in keys_to_remove:
        if k in ss:
            del ss[k]
    clear_dynamic_keys()
    ensure_state()

# =========================
# APPS SCRIPT I/O
# =========================
def save_quote_to_sheet(payload: dict) -> str:
    quote_id = f"Q-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    created_at = datetime.datetime.now().isoformat(timespec="seconds")

    record = {
        "sheet_id": SHEET_ID,
        "quote_id": quote_id,
        "created_at": created_at,
        "quote_type": payload.get("quote_type", ""),
        "job_mode": payload.get("job_mode", ""),

        "client_name": payload.get("client_name", ""),
        "client_phone": payload.get("client_phone", ""),
        "client_phone_norm": payload.get("client_phone_norm", ""),
        "client_email": payload.get("client_email", ""),
        "site_address": payload.get("site_address", ""),

        "total_area": payload.get("total_area", 0),
        "chargeable_area": payload.get("chargeable_area", 0),
        "wastage_pct": payload.get("wastage_pct", 0),
        "subtotal_ex_gst": payload.get("subtotal_ex_gst", 0),
        "gst": payload.get("gst", 0),
        "total_inc_gst": payload.get("total_inc_gst", 0),

        "payload_json": payload,
        "line_items": payload.get("line_items", []),
    }

    r = requests.post(APPS_SCRIPT_URL, json=record, timeout=20)
    r.raise_for_status()
    return quote_id

def search_quotes(phone=None, address=None, name=None):
    """
    NOTE:
    - Your Apps Script MUST support these query params to work well:
      phone OR address OR name (one at a time).
    - If your script doesn't support name yet, name search will return [].
    """
    phone = (phone or "").strip()
    address = (address or "").strip()
    name = (name or "").strip()

    params = {"sheet_id": SHEET_ID}
    if phone:
        params["phone"] = phone
    elif address:
        params["address"] = address
    elif name:
        params["name"] = name
    else:
        return []

    r = requests.get(APPS_SCRIPT_URL, params=params, timeout=20)

    ct = (r.headers.get("Content-Type") or "").lower()
    if "application/json" not in ct:
        snippet = (r.text or "")[:1200]
        st.error(f"Apps Script did NOT return JSON.\nStatus: {r.status_code}\nContent-Type: {ct}")
        st.code(snippet)
        return []

    try:
        return r.json()
    except Exception:
        st.error("Apps Script returned JSON content-type but body is not valid JSON.")
        st.code((r.text or "")[:1200])
        return []

def load_snapshot_into_state(snapshot: Dict[str, Any]):
    ss = st.session_state

    # client
    ss["client_name"] = str(snapshot.get("client_name", "") or "")
    ss["client_phone"] = str(snapshot.get("client_phone", "") or "")
    ss["client_email"] = str(snapshot.get("client_email", "") or "")
    ss["site_address"] = str(snapshot.get("site_address", "") or "")

    # meta
    ss["job_mode"] = str(snapshot.get("job_mode", ss.get("job_mode", "Supply & Install")) or "Supply & Install")
    ss["quote_type"] = str(snapshot.get("quote_type", ss.get("quote_type", "Retail")) or "Retail")
    ss["wastage_pct"] = float(snapshot.get("wastage_pct", ss.get("wastage_pct", DEFAULT_WASTAGE_PCT)) or DEFAULT_WASTAGE_PCT)

    # rooms
    rooms = snapshot.get("rooms", [])
    restored_rooms = []
    if isinstance(rooms, list) and rooms:
        for r in rooms:
            try:
                restored_rooms.append({"length": float(r.get("length", 0.0) or 0.0), "width": float(r.get("width", 0.0) or 0.0)})
            except Exception:
                continue
    ss["rooms"] = restored_rooms if restored_rooms else [{"length": 0.0, "width": 0.0}]

    # allow resave
    ss["quote_saved"] = False
    ss["last_quote_id"] = ""

    clear_dynamic_keys()
    ensure_state()


# =========================
# MOBILE TEXT OUTPUT
# =========================
def build_mobile_quote_text(payload: dict) -> str:
    def money0_local(x: float) -> str:
        return f"${float(x):,.0f}"

    def qty_pretty(qty_str: str) -> tuple[str, str]:
        s = (qty_str or "").strip()
        if not s:
            return ("", "")
        parts = s.split()
        if len(parts) == 1:
            return (parts[0], "")
        qty_raw = parts[0]
        unit = " ".join(parts[1:])
        try:
            q = float(qty_raw)
            if abs(q - round(q)) < 1e-9:
                qty_fmt = f"{int(round(q))}"
            else:
                qty_fmt = f"{q:.1f}".rstrip("0").rstrip(".")
            return (qty_fmt, unit)
        except Exception:
            return (qty_raw, unit)

    lines = []
    for li in payload.get("line_items", []):
        label = str(li.get("label", "")).strip()
        qty_str = str(li.get("qty_str", "")).strip()
        unit_price = float(li.get("unit_price", 0.0))
        total = float(li.get("total", 0.0))

        qty_num, qty_unit = qty_pretty(qty_str)
        qty_display = f"{qty_num} {qty_unit}".strip()

        lines.append(label)
        lines.append(f"{qty_display} x {money0_local(unit_price)} = {money0_local(total)}")
        lines.append("")

    subtotal_ex_gst = float(payload.get("subtotal_ex_gst", 0.0))
    lines.append(f"Total: {money0_local(subtotal_ex_gst)}")
    return "\n".join(lines).strip()


# =========================
# PDF OUTPUT
# =========================
def build_quote_pdf(payload: dict) -> bytes:
    def _rgb(t):
        return colors.Color(t[0], t[1], t[2])

    def money_pdf(x: float) -> str:
        return f"${float(x):,.2f}"

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    left = 42
    right = width - 42
    table_w = right - left

    header_h = 18
    row_h = 16

    def draw_company_header() -> float:
        logo_w, logo_h = 120, 42
        logo_x = left
        logo_y = height - 42 - logo_h

        logo_drawn = False
        try:
            logo = ImageReader(LOGO_PATH)
            c.drawImage(logo, logo_x, logo_y, width=logo_w, height=logo_h, mask="auto", preserveAspectRatio=True)
            logo_drawn = True
        except Exception:
            pass

        y_local = height - 48
        if logo_drawn:
            y_local = logo_y - 14

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, y_local, COMPANY.get("name", ""))
        y_local -= 16

        c.setFont("Helvetica", 9)
        if COMPANY.get("abn"):
            c.drawString(left, y_local, COMPANY.get("abn", ""))
            y_local -= 12

        c.drawString(left, y_local, f"{COMPANY.get('phone','')}  |  {COMPANY.get('email','')}")
        y_local -= 12

        if COMPANY.get("website"):
            c.drawString(left, y_local, COMPANY.get("website", ""))
            y_local -= 12

        y_local -= 6
        c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
        c.setLineWidth(0.8)
        c.line(left, y_local, right, y_local)
        y_local -= 22
        return y_local

    def new_page():
        nonlocal width, height, left, right, table_w
        c.showPage()
        c.setPageSize(A4)
        width, height = A4
        left = 42
        right = width - 42
        table_w = right - left

    y = draw_company_header()

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, "Quotation")
    y -= 10
    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Client Details")
    y -= 14

    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Client: {payload.get('client_name','')}")
    y -= 14
    c.drawString(left, y, f"Phone: {payload.get('client_phone','')}")
    y -= 14
    c.drawString(left, y, f"Email: {payload.get('client_email','')}")
    y -= 14
    c.drawString(left, y, f"Site: {payload.get('site_address','')}")
    y -= 14
    c.drawString(left, y, f"Mode: {payload.get('job_mode','')}")
    y -= 14
    c.drawString(left, y, f"Quote type: {payload.get('quote_type','')}")
    y -= 18

    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 18

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Scope & Pricing (ex GST)")
    y -= 14

    c.setFillColor(_rgb(BRAND["light_gray_rgb"]))
    c.rect(left, y - header_h + 4, table_w, header_h, stroke=0, fill=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)

    col_item = left + 6
    col_qty = right - 170
    col_price = right - 90
    col_total = right - 6

    c.drawString(col_item, y, "Item")
    c.drawRightString(col_qty, y, "Qty")
    c.drawRightString(col_price, y, "Price")
    c.drawRightString(col_total, y, "Total")
    y -= row_h

    c.setFont("Helvetica", 9)
    items = payload.get("line_items", []) or []

    for idx, li in enumerate(items):
        if y < 120:
            new_page()
            y = draw_company_header()
            c.setFont("Helvetica-Bold", 11)
            c.drawString(left, y, "Scope & Pricing (ex GST) (continued)")
            y -= 14
            c.setFillColor(_rgb(BRAND["light_gray_rgb"]))
            c.rect(left, y - header_h + 4, table_w, header_h, stroke=0, fill=1)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(col_item, y, "Item")
            c.drawRightString(col_qty, y, "Qty")
            c.drawRightString(col_price, y, "Price")
            c.drawRightString(col_total, y, "Total")
            y -= row_h
            c.setFont("Helvetica", 9)

        if idx % 2 == 1:
            c.setFillColor(_rgb((0.98, 0.98, 0.98)))
            c.rect(left, y - 12, table_w, row_h, stroke=0, fill=1)

        c.setFillColor(colors.black)
        label = str(li.get("label", ""))
        if len(label) > 78:
            label = label[:75] + "..."
        qty_str = str(li.get("qty_str", ""))
        unit_price = safe_float(li.get("unit_price", 0.0), 0.0)
        total = safe_float(li.get("total", 0.0), 0.0)

        c.drawString(col_item, y, label)
        c.drawRightString(col_qty, y, qty_str)
        c.drawRightString(col_price, y, money_pdf(unit_price))
        c.drawRightString(col_total, y, money_pdf(total))
        y -= row_h

    y -= 10
    box_w, box_h = 220, 70
    box_x = right - box_w
    box_y = y - box_h + 10

    c.setFillColor(_rgb((0.97, 0.97, 0.97)))
    c.rect(box_x, box_y, box_w, box_h, stroke=1, fill=1)

    subtotal = safe_float(payload.get("subtotal_ex_gst", 0.0), 0.0)
    gst = safe_float(payload.get("gst", 0.0), 0.0)
    total_inc = safe_float(payload.get("total_inc_gst", 0.0), 0.0)

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(box_x + 10, box_y + 48, "Subtotal (ex GST)")
    c.drawRightString(box_x + box_w - 10, box_y + 48, money_pdf(subtotal))

    c.drawString(box_x + 10, box_y + 30, "GST")
    c.drawRightString(box_x + box_w - 10, box_y + 30, money_pdf(gst))

    c.setFont("Helvetica-Bold", 11)
    c.drawString(box_x + 10, box_y + 12, "Total (inc GST)")
    c.drawRightString(box_x + box_w - 10, box_y + 12, money_pdf(total_inc))

    y = box_y - 18
    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 16

    if y < 80:
        new_page()
        y = draw_company_header()

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Terms")
    y -= 14
    c.setFont("Helvetica", 9)

    for t in (payload.get("terms", []) or []):
        if y < 60:
            new_page()
            y = draw_company_header()
            c.setFont("Helvetica", 9)
        c.drawString(left, y, f"• {t}")
        y -= 12

    c.save()
    buf.seek(0)
    return buf.read()


# =========================
# UI STYLE
# =========================
st.markdown(
    """
<style>
.block-container { padding-top: 1rem; padding-bottom: 1rem; }
div[data-testid="stNumberInput"] input { padding: 0.25rem 0.5rem; font-size: 0.95rem; }
label[data-testid="stWidgetLabel"] { margin-bottom: 0.1rem; }
div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
div[data-testid="stHorizontalBlock"] > div { min-width: 0; }
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# LOAD SHEETS
# =========================
products_df = load_sheet("products")
install_df = load_sheet("install_only")
addons_df = load_sheet("addons")


# =========================
# HEADER
# =========================
st.title("📱 Flooring Quote Prototype (V1)")
st.caption(f"{COMPANY['name']} • {COMPANY['abn']} • {COMPANY['phone']} • {COMPANY['email']}")

c_reset, c_blank = st.columns([1, 3])
with c_reset:
    if st.button("🧼 New Quote (reset)", use_container_width=True):
        reset_quote()
        st.rerun()

# =========================
# RETRIEVE EXISTING QUOTE (phone / address / name)
# =========================
st.divider()
st.subheader("Retrieve Existing Quote")

with st.form("quote_search_form", clear_on_submit=False):
    s1, s2, s3 = st.columns(3)
    with s1:
        search_phone = st.text_input("Search by phone", key="search_phone")
    with s2:
        search_address = st.text_input("Search by address", key="search_address")
    with s3:
        search_name = st.text_input("Search by name", key="search_name")

    submitted = st.form_submit_button("Search", use_container_width=True)

if submitted:
    phone_norm = norm_phone(search_phone)
    addr = (search_address or "").strip()
    name = (search_name or "").strip()

    # priority: phone -> address -> name
    if phone_norm:
        results = search_quotes(phone=phone_norm)
    elif addr:
        results = search_quotes(address=addr)
    elif name:
        results = search_quotes(name=name)
    else:
        results = []
        st.warning("Enter a phone, address, or name to search.")

    if not results:
        st.warning("No matching quotes found.")
        st.caption("If name search returns nothing, your Apps Script may not support ?name= yet.")
    else:
        for r in results:
            qid = r.get("quote_id", "")
            st.markdown(f"**{qid}** — {r.get('created_at','')}")
            if st.button(f"Load {qid}", key=f"load_quote_{qid}"):
                snapshot = r.get("payload_json", {}) or {}
                load_snapshot_into_state(snapshot)
                st.success("Quote loaded successfully.")
                st.rerun()

# =========================
# MAIN PAGE STARTS WITH MEASUREMENTS
# =========================
st.divider()
st.subheader("Measurements")
st.caption("Type dimensions like 3.2x4 (metres). Used for pricing only; not shown in the PDF.")

def add_room():
    st.session_state["rooms"].append({"length": 0.0, "width": 0.0})

def remove_room(idx: int):
    if len(st.session_state["rooms"]) > 1:
        st.session_state["rooms"].pop(idx)
        for k in list(st.session_state.keys()):
            if str(k).startswith("dim_"):
                del st.session_state[k]
        st.rerun()

h1, h2, h3 = st.columns([2, 1, 0.6], gap="small")
h1.markdown("**Length x Width (m)**")
h2.markdown("**Area (m²)**")
h3.markdown("")

updated_rooms = []
for i, room in enumerate(st.session_state["rooms"]):
    default_text = fmt_dims(room.get("length", 0.0), room.get("width", 0.0))

    c1, c2, c3 = st.columns([2, 1, 0.6], gap="small")

    with c1:
        s = st.text_input(
            "Dimensions",
            value=default_text,
            key=f"dim_{i}",
            placeholder="e.g. 3.2x4",
            label_visibility="collapsed",
        ).strip()

        new_room = {"length": float(room.get("length", 0.0)), "width": float(room.get("width", 0.0))}
        if s == "":
            new_room["length"] = 0.0
            new_room["width"] = 0.0
        else:
            l, w = parse_dims(s)
            if l is not None and w is not None:
                new_room["length"] = float(l)
                new_room["width"] = float(w)

    with c2:
        area = float(new_room["length"]) * float(new_room["width"])
        st.markdown(f"<div style='padding-top:0.55rem;font-size:1rem;'>{area:.2f}</div>", unsafe_allow_html=True)

    with c3:
        if len(st.session_state["rooms"]) > 1:
            if st.button("✕", key=f"remove_{i}"):
                remove_room(i)

    updated_rooms.append(new_room)

st.session_state["rooms"] = updated_rooms
st.button("➕ Add Room", on_click=add_room)

total_area = sum(float(r["length"]) * float(r["width"]) for r in st.session_state["rooms"])

# WASTAGE AFTER MEASUREMENT
st.markdown("---")
st.subheader("Wastage (after measurement)")
wastage_pct = st.number_input(
    "Wastage (%)",
    min_value=0.0,
    max_value=25.0,
    value=float(st.session_state.get("wastage_pct", DEFAULT_WASTAGE_PCT)),
    step=0.5,
    key="wastage_pct",
)
chargeable_area = total_area * (1.0 + float(wastage_pct) / 100.0)

a, b, ccol = st.columns(3)
a.metric("Total area (m²)", f"{total_area:.2f}")
b.metric("Wastage (%)", f"{float(wastage_pct):.1f}")
ccol.metric("Chargeable area (m²)", f"{chargeable_area:.2f}")

# JOB MODE AFTER WASTAGE, BEFORE TIMBER
st.divider()
st.subheader("Work Type (after wastage)")
st.radio(
    "Work type",
    ["Supply & Install", "Installation Only"],
    horizontal=True,
    key="job_mode",
)

# SELECT TIMBER / INSTALLATION AFTER THAT
st.divider()
st.subheader("Select Timber / Installation")

if st.session_state.get("job_mode") == "Supply & Install":
    if not products_df.empty and "id" in products_df.columns:
        product_options = products_df["id"].astype(str).tolist()
        st.session_state["product_id"] = safe_pick_id(products_df, st.session_state.get("product_id", ""), "id")

        st.selectbox(
            "Select timber product (Supply & Install)",
            options=product_options,
            index=product_options.index(str(st.session_state["product_id"])),
            format_func=lambda pid: (
                f"{products_df.loc[products_df['id'].astype(str)==str(pid),'brand'].values[0]} — "
                f"{products_df.loc[products_df['id'].astype(str)==str(pid),'name'].values[0]}"
            ),
            key="product_id",
        )
    else:
        st.selectbox(
            "Select timber product (Supply & Install)",
            options=[p["id"] for p in PRODUCTS],
            format_func=lambda pid: f"{find_by_id(PRODUCTS, pid)['brand']} — {find_by_id(PRODUCTS, pid)['name']}",
            key="product_id",
        )
else:
    st.selectbox(
        "Select installation type (Installation Only)",
        options=[i["id"] for i in INSTALL_ONLY],
        format_func=lambda iid: find_by_id(INSTALL_ONLY, iid)["name"],
        key="install_id",
    )

# RETAIL/BUILDER AFTER SELECT TIMBER
st.divider()
st.subheader("Quote Type (after timber selection)")
st.selectbox("Quote type (for your own tracking)", ["Retail", "Builder"], key="quote_type")

# =========================
# QUOTE BUILD
# =========================
st.divider()
st.subheader("Quote Items (Core + Add-ons)")

line_items: List[dict] = []
subtotal = 0.0

# CORE MODE
if st.session_state.get("job_mode") == "Supply & Install":
    st.markdown("#### Core: Supply & Install")

    unit_price_default = 0.0
    product_label = "Supply & install"

    if not products_df.empty and "id" in products_df.columns:
        pid = str(st.session_state.get("product_id", ""))
        match = products_df[products_df["id"].astype(str) == pid]
        product_row = match.iloc[0] if not match.empty else products_df.iloc[0]

        if "sell_price" in products_df.columns:
            unit_price_default = safe_float(product_row.get("sell_price", 0.0), 0.0)
        elif "sell_per_m2" in products_df.columns:
            unit_price_default = safe_float(product_row.get("sell_per_m2", 0.0), 0.0)

        brand = str(product_row.get("brand", "")).strip()
        name = str(product_row.get("name", "")).strip()
        product_label = f"Supply & install — {brand} {name}".strip()
    else:
        p = find_by_id(PRODUCTS, st.session_state.get("product_id", PRODUCTS[0]["id"]))
        unit_price_default = safe_float(p.get("sell_per_m2", 0.0), 0.0)
        product_label = f"Supply & install — {p['brand']} {p['name']}"

    unit_price = st.number_input(
        "Supply & Install price ($/m²)",
        min_value=0.0,
        value=float(unit_price_default),
        step=1.0,
        key="supply_install_price_override",
    )

    total = chargeable_area * unit_price
    line_items.append(line_item(product_label, f"{chargeable_area:.2f} m²", unit_price, total))
    subtotal += total

else:
    st.markdown("#### Core: Installation Only")
    ins = find_by_id(INSTALL_ONLY, st.session_state.get("install_id", INSTALL_ONLY[0]["id"]))

    unit_price = st.number_input(
        "Installation price ($/m²)",
        min_value=0.0,
        value=float(ins["install_per_m2"]),
        step=1.0,
        key="install_only_price_override",
    )

    total = total_area * unit_price
    line_items.append(line_item(ins["name"], f"{total_area:.2f} m²", unit_price, total))
    subtotal += total


# =========================
# ADD-ONS UI: normal rows (checkbox + qty + price one line)
# =========================

st.divider()
st.subheader("Add-ons")

def add_addon_row(addon_key: str, label: str, unit: str, qty_default: float, price_default: float, step_qty: float):
    checked = st.checkbox(label, key=f"addon_{addon_key}")
    if not checked:
        return 0.0

    c1, c2 = st.columns([1.1, 1.0], gap="small")
    with c1:
        qty = st.number_input(
            "Qty",
            min_value=0.0,
            value=float(st.session_state.get(f"addon_qty_{addon_key}", qty_default)),
            step=step_qty,
            key=f"addon_qty_{addon_key}",
            label_visibility="collapsed",
        )
        st.caption(unit)

    with c2:
        unit_price = st.number_input(
            "Price",
            min_value=0.0,
            value=float(st.session_state.get(f"addon_price_{addon_key}", price_default)),
            step=1.0,
            key=f"addon_price_{addon_key}",
            label_visibility="collapsed",
        )
        st.caption(f"per {unit}")

    total = float(qty) * float(unit_price)
    line_items.append(line_item(label, f"{qty:.2f} {unit}", float(unit_price), total))
    return total


# ----------------------------------------------------
# 1️⃣ Removal & Disposal
# ----------------------------------------------------
st.markdown("### Removal & Disposal")

for r in REMOVAL_TYPES:
    subtotal += add_addon_row(
        addon_key=f"removal_{r['id']}",
        label=f"Removal & disposal — {r['name']}",
        unit="m²",
        qty_default=float(total_area),
        price_default=float(r.get("remove_per_m2", 0.0)),
        step_qty=0.1,
    )


# ----------------------------------------------------
# 2️⃣ STAIRS GROUP (NEW)
# ----------------------------------------------------
st.markdown("### Stairs")

with st.container():
    st.caption("Grouped stair pricing")

    subtotal += add_addon_row(
        addon_key="stair_steps",
        label="Normal step",
        unit="step",
        qty_default=0.0,
        price_default=120.0,
        step_qty=1.0,
    )

    subtotal += add_addon_row(
        addon_key="stair_triangle",
        label="Triangle step",
        unit="si",
        qty_default=1.0,
        price_default=250.0,
        step_qty=1.0,
    )

    subtotal += add_addon_row(
        addon_key="stair_landing",
        label="Landing step",
        unit="side",
        qty_default=1.0,
        price_default=250.0,
        step_qty=1.0,
    )

    subtotal += add_addon_row(
        addon_key="stair_side_1",
        label="Open step 1 side",
        unit="side",
        qty_default=1.0,
        price_default=250.0,
        step_qty=1.0,
    )

    subtotal += add_addon_row(
        addon_key="stair_side_2",
        label="Open step 2 sides",
        unit="side",
        qty_default=1.0,
        price_default=250.0,
        step_qty=1.0,
    )

# ----------------------------------------------------
# 3️⃣ Furniture
# ----------------------------------------------------
st.markdown("### Furniture Handling")

subtotal += add_addon_row(
    addon_key="furniture",
    label="Furniture handling",
    unit="room",
    qty_default=float(len(st.session_state["rooms"])),
    price_default=float(st.session_state.get("furniture_rate", DEFAULT_FURNITURE_PER_ROOM)),
    step_qty=1.0,
)


# ----------------------------------------------------
# 4️⃣ Other Add-ons (INCLUDING SKIRTING NOW)
# ----------------------------------------------------
st.markdown("### Other Add-ons")

# --- Skirting moved here ---
st.session_state.setdefault("skirting_id", SKIRTING[0]["id"])
st.selectbox(
    "Skirting height",
    options=[s["id"] for s in SKIRTING],
    format_func=lambda sid: f"{find_by_id(SKIRTING, sid)['height_mm']}mm",
    key="skirting_id",
)

sk = find_by_id(SKIRTING, st.session_state.get("skirting_id", SKIRTING[0]["id"]))

subtotal += add_addon_row(
    addon_key=f"skirting_{sk['id']}",
    label=f"Skirting — {sk['height_mm']}mm",
    unit="lm",
    qty_default=float(st.session_state.get("skirting_lm", 0.0)),
    price_default=float(sk.get("price_per_lm", 0.0)),
    step_qty=1.0,
)

# --- Sheet based add-ons ---
if addons_df is not None and not addons_df.empty:
    for _, row in addons_df.iterrows():
        addon_id = str(row.get("id", "")).strip()
        label = str(row.get("label", "")).strip()
        unit_raw = str(row.get("unit", "")).strip() or "each"
        default_price = safe_float(row.get("price", 0.0), 0.0)

        if not addon_id or not label:
            continue

        unit_norm = unit_raw.lower().replace(" ", "")
        if unit_norm in ("m2", "m²"):
            qty_default = float(chargeable_area)
            unit_display = "m²"
            step_qty = 0.1
        elif unit_norm in ("room", "rooms"):
            qty_default = float(len(st.session_state["rooms"]))
            unit_display = "room"
            step_qty = 1.0
        else:
            qty_default = 1.0
            unit_display = unit_raw
            step_qty = 1.0

        subtotal += add_addon_row(
            addon_key=f"sheet_{addon_id}",
            label=label,
            unit=unit_display,
            qty_default=qty_default,
            price_default=float(default_price),
            step_qty=step_qty,
        )

# =========================
# TOTALS
# =========================
st.divider()
gst = subtotal * GST_RATE
total_inc = subtotal + gst
t1, t2, t3 = st.columns(3)
t1.metric("Subtotal (ex GST)", money0(subtotal))
t2.metric("GST", money0(gst))
t3.metric("Total (inc GST)", money0(total_inc))


# =========================
# CLIENT DETAILS MOVED TO END (right before output)
# =========================
st.divider()
st.subheader("Client Details (fill in at the end)")

c1, c2 = st.columns(2)
with c1:
    st.text_input("Client name", key="client_name")
    st.text_input("Client phone", key="client_phone")
with c2:
    st.text_input("Client email", key="client_email")
    st.text_input("Site address", key="site_address")


# =========================
# TERMS + PAYLOAD
# =========================
st.divider()
st.subheader("Terms")

terms_default = [
    "Quote valid for 30 days.",
    "",
    "Payment Terms:",
    "A 10% deposit is required to secure the stock and confirm the scheduled installation date.",
    "60% is payable upon delivery of materials and commencement of works on site.",
    "The remaining 30% balance is due immediately upon completion of the installation.",
]
terms_text = st.text_area("Terms (one per line — editable)", "\n".join(terms_default), height=180)
terms = [t.strip() for t in terms_text.splitlines() if t.strip()]

rooms_out = []
for i, r in enumerate(st.session_state["rooms"]):
    rooms_out.append(
        {
            "name": f"Room {i+1}",
            "length": float(r["length"]),
            "width": float(r["width"]),
            "area": float(r["length"]) * float(r["width"]),
        }
    )

payload = {
    "client_name": (st.session_state.get("client_name", "") or "").strip(),
    "client_phone": (st.session_state.get("client_phone", "") or "").strip(),
    "client_phone_norm": norm_phone(st.session_state.get("client_phone", "")),
    "client_email": (st.session_state.get("client_email", "") or "").strip(),
    "site_address": (st.session_state.get("site_address", "") or "").strip(),

    "job_mode": st.session_state.get("job_mode", ""),
    "quote_type": st.session_state.get("quote_type", ""),

    "rooms": rooms_out,
    "total_area": float(total_area),
    "wastage_pct": float(wastage_pct),
    "chargeable_area": float(chargeable_area),

    "line_items": line_items,
    "subtotal_ex_gst": float(subtotal),
    "gst": float(gst),
    "total_inc_gst": float(total_inc),

    "terms": terms,
}

with st.expander("DEBUG — client fields in payload (must NOT be blank)", expanded=False):
    st.write(
        {
            "client_name": payload["client_name"],
            "client_phone": payload["client_phone"],
            "client_email": payload["client_email"],
            "site_address": payload["site_address"],
        }
    )

st.session_state.setdefault("quote_saved", False)

def handle_save():
    if not st.session_state.get("quote_saved", False):
        qid = save_quote_to_sheet(payload)
        st.session_state["quote_saved"] = True
        st.session_state["last_quote_id"] = qid
        st.success(f"Quote saved: {qid}")


# =========================
# OUTPUT
# =========================
st.divider()
st.subheader("Save & Generate Quote")

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("💾 Save Quote", use_container_width=True):
        try:
            handle_save()
        except Exception as e:
            st.error(f"Save failed: {e}")

with col2:
    if st.button("Generate PDF & Download", use_container_width=True):
        try:
            handle_save()
            pdf_bytes = build_quote_pdf(payload)
            st.download_button(
                "Click to Download PDF",
                data=pdf_bytes,
                file_name=f"{st.session_state.get('last_quote_id','Quote')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF failed: {e}")

with col3:
    if st.button("Download Quote.txt", use_container_width=True):
        try:
            handle_save()
            mobile_text = build_mobile_quote_text(payload)
            st.download_button(
                "Click to Download TXT",
                data=mobile_text.encode("utf-8"),
                file_name=f"{st.session_state.get('last_quote_id','Quote')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"TXT failed: {e}")

st.divider()
st.subheader("Mobile-friendly quote (copy/paste)")
mobile_text = build_mobile_quote_text(payload)
st.text_area("Copy this and paste into SMS/WhatsApp/email (ex GST)", value=mobile_text, height=260)
