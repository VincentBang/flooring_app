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
# CONFIG
# =========================
st.set_page_config(page_title="Flooring Quote Prototype", layout="wide")

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxQ1JZ_fH53ORWx7q4-6hdP5LirqFvAIu4kVddosla9RzyYS_MOlOqBQ7NHvIxMSXyJlQ/exec"
SHEET_ID = "10G98m8XHdySRTMWjbAUlQCZMH1NXCD6uca82xN0p4fY"

COMPANY = {
    "name": "Oz Timber Floor Pty Ltd",
    "abn": "ABN: 84 168 475 358",
    "phone": "Phone: 0435 496 975",
    "email": "Email: info@oztimberfloor.com.au",
    "website": "Website: oztimberfloor.com.au",
}
LOGO_PATH = "logo.png"

BRAND = {
    "light_gray_rgb": (0.94, 0.94, 0.94),
    "mid_gray_rgb": (0.75, 0.75, 0.75),
}

DEFAULT_WASTAGE_PCT = 10.0
GST_RATE = 0.10


# =========================
# SHEET LOADERS
# =========================
@st.cache_data(ttl=300)
def load_sheet(tab_name: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={tab_name}"
    try:
        df = pd.read_csv(url)
    except Exception:
        return pd.DataFrame()

    # filter active rows if column exists
    if "active" in [c.lower() for c in df.columns]:
        # find the real column name (case-insensitive)
        active_col = [c for c in df.columns if c.lower() == "active"][0]
        active = df[active_col].astype(str).str.strip().str.lower()
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

def line_item(label: str, qty_str: str, unit_price: float, total: float) -> dict:
    return {"label": str(label), "qty_str": str(qty_str), "unit_price": float(unit_price), "total": float(total)}

def safe_pick_id(df: pd.DataFrame, current_id: str, id_col: str = "id") -> str:
    if df is None or df.empty or id_col not in df.columns:
        return str(current_id or "")
    ids = df[id_col].astype(str).tolist()
    if not ids:
        return ""
    return str(current_id) if str(current_id) in ids else ids[0]


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
        "quote_type": payload.get("quote_type",""),
        "job_mode": payload.get("job_mode",""),
        "client_name": payload.get("client_name",""),
        "client_phone": payload.get("client_phone",""),
        "client_phone_norm": payload.get("client_phone_norm",""),
        "client_email": payload.get("client_email",""),
        "site_address": payload.get("site_address",""),
        "total_area": payload.get("total_area",0),
        "chargeable_area": payload.get("chargeable_area",0),
        "wastage_pct": payload.get("wastage_pct",0),
        "subtotal_ex_gst": payload.get("subtotal_ex_gst",0),
        "gst": payload.get("gst",0),
        "total_inc_gst": payload.get("total_inc_gst",0),
    
        # ✅ send both for compatibility
        "payload_json": payload,
        "payload": payload,
    
        "line_items": payload.get("line_items", []),
    }

    r = requests.post(APPS_SCRIPT_URL, json=record, timeout=25)
    r.raise_for_status()
    return quote_id

def search_quotes(phone=None, address=None, name=None):
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

    r = requests.get(APPS_SCRIPT_URL, params=params, timeout=25)

    ct = (r.headers.get("Content-Type") or "").lower()
    if "application/json" not in ct:
        st.error(f"Apps Script did NOT return JSON.\nStatus: {r.status_code}\nContent-Type: {ct}")
        st.code((r.text or "")[:1200])
        return []

    try:
        return r.json()
    except Exception:
        st.error("Apps Script returned JSON content-type but body is not valid JSON.")
        st.code((r.text or "")[:1200])
        return []


def load_snapshot_into_state(snapshot: Dict[str, Any], loaded_quote_id: str = ""):
    ss = st.session_state

    # --- clear dynamic widget keys ---
    for k in list(ss.keys()):
        if str(k).startswith(("dim_", "addon_", "addon_qty_", "addon_price_", "rem_", "sk_", "core_")):
            del ss[k]

    # --- restore core fields ---
    ss["client_name"] = str(snapshot.get("client_name", "") or "")
    ss["client_phone"] = str(snapshot.get("client_phone", "") or "")
    ss["client_email"] = str(snapshot.get("client_email", "") or "")
    ss["site_address"] = str(snapshot.get("site_address", "") or "")

    ss["job_mode"] = str(snapshot.get("job_mode", ss.get("job_mode", "Supply & Install")) or "Supply & Install")
    ss["quote_type"] = str(snapshot.get("quote_type", ss.get("quote_type", "Retail")) or "Retail")
    ss["wastage_pct"] = float(snapshot.get("wastage_pct", ss.get("wastage_pct", DEFAULT_WASTAGE_PCT)) or DEFAULT_WASTAGE_PCT)

    # --- restore rooms ---
    rooms = snapshot.get("rooms", [])
    restored_rooms = []
    if isinstance(rooms, list) and rooms:
        for r in rooms:
            try:
                restored_rooms.append({
                    "length": float(r.get("length", 0.0) or 0.0),
                    "width": float(r.get("width", 0.0) or 0.0),
                })
            except Exception:
                continue

    ss["rooms"] = restored_rooms if restored_rooms else [{"length": 0.0, "width": 0.0}]

    # --- IMPORTANT: pre-fill the dim_i widget keys so Streamlit displays loaded values ---
    for i, r in enumerate(ss["rooms"]):
        ss[f"dim_{i}"] = fmt_dims(float(r.get("length", 0.0)), float(r.get("width", 0.0)))

    ss["last_loaded_quote_id"] = loaded_quote_id or ""
    ss["quote_saved"] = False
    ss["last_quote_id"] = ""

# =========================
# MOBILE TEXT
# =========================
def build_mobile_quote_text(payload: dict) -> str:
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
        lines.append(f"{qty_display} x {money0(unit_price)} = {money0(total)}")
        lines.append("")

    subtotal_ex_gst = float(payload.get("subtotal_ex_gst", 0.0))
    lines.append(f"Total: {money0(subtotal_ex_gst)}")
    return "\n".join(lines).strip()


# =========================
# PDF
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

        try:
            logo = ImageReader(LOGO_PATH)
            c.drawImage(logo, logo_x, logo_y, width=logo_w, height=logo_h, mask="auto", preserveAspectRatio=True)
            y_local = logo_y - 14
        except Exception:
            y_local = height - 48

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, y_local, COMPANY.get("name", ""))
        y_local -= 16

        c.setFont("Helvetica", 9)
        c.drawString(left, y_local, COMPANY.get("abn", ""))
        y_local -= 12
        c.drawString(left, y_local, f"{COMPANY.get('phone','')}  |  {COMPANY.get('email','')}")
        y_local -= 12
        c.drawString(left, y_local, COMPANY.get("website", ""))
        y_local -= 18

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
    y -= 20

    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Client: {payload.get('client_name','')}")
    y -= 14
    c.drawString(left, y, f"Phone: {payload.get('client_phone','')}")
    y -= 14
    c.drawString(left, y, f"Email: {payload.get('client_email','')}")
    y -= 14
    c.drawString(left, y, f"Site: {payload.get('site_address','')}")
    y -= 14
    c.drawString(left, y, f"Mode: {payload.get('job_mode','')}   |   Type: {payload.get('quote_type','')}")
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

        label = str(li.get("label", ""))
        qty_str = str(li.get("qty_str", ""))
        unit_price = safe_float(li.get("unit_price", 0.0), 0.0)
        total = safe_float(li.get("total", 0.0), 0.0)

        c.drawString(col_item, y, label[:80])
        c.drawRightString(col_qty, y, qty_str)
        c.drawRightString(col_price, y, money_pdf(unit_price))
        c.drawRightString(col_total, y, money_pdf(total))
        y -= row_h

    y -= 10

    subtotal = safe_float(payload.get("subtotal_ex_gst", 0.0), 0.0)
    gst = safe_float(payload.get("gst", 0.0), 0.0)
    total_inc = safe_float(payload.get("total_inc_gst", 0.0), 0.0)

    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(right, y, f"Subtotal (ex GST): {money_pdf(subtotal)}")
    y -= 14
    c.drawRightString(right, y, f"GST: {money_pdf(gst)}")
    y -= 14
    c.drawRightString(right, y, f"Total (inc GST): {money_pdf(total_inc)}")
    y -= 20

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Terms")
    y -= 14
    c.setFont("Helvetica", 9)
    for t in (payload.get("terms", []) or []):
        c.drawString(left, y, f"• {t}")
        y -= 12
        if y < 60:
            new_page()
            y = draw_company_header()

    c.save()
    buf.seek(0)
    return buf.read()


# =========================
# STATE
# =========================
def ensure_state():
    st.session_state.setdefault("load_nonce", 0)
    st.session_state.setdefault("last_loaded_quote_id", "")
    ss = st.session_state
    ss.setdefault("rooms", [{"length": 0.0, "width": 0.0}])
    if not isinstance(ss["rooms"], list) or not ss["rooms"]:
        ss["rooms"] = [{"length": 0.0, "width": 0.0}]

    ss.setdefault("wastage_pct", float(DEFAULT_WASTAGE_PCT))
    ss.setdefault("job_mode", "Supply & Install")
    ss.setdefault("product_id", "")
    ss.setdefault("install_id", "")
    ss.setdefault("quote_type", "Retail")

    ss.setdefault("client_name", "")
    ss.setdefault("client_phone", "")
    ss.setdefault("client_email", "")
    ss.setdefault("site_address", "")

    ss.setdefault("quote_saved", False)
    ss.setdefault("last_quote_id", "")

ensure_state()


# =========================
# LOAD ALL PRICING TABLES FROM SHEET
# =========================
products_df = load_sheet("products")
install_df = load_sheet("install_only")
removal_df = load_sheet("removal")
skirting_df = load_sheet("skirting")
addons_df = load_sheet("addons")


# =========================
# UI
# =========================
st.title("📱 Flooring Quote Prototype")
st.caption(f"{COMPANY['name']} • {COMPANY['abn']} • {COMPANY['phone']} • {COMPANY['email']}")

# ---------- Retrieve quote ----------
st.divider()
st.subheader("Retrieve Existing Quote")

with st.form("quote_search_form", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        search_phone = st.text_input("Search by phone (any format)", key="search_phone")
    with c2:
        search_address = st.text_input("Search by address", key="search_address")
    with c3:
        search_name = st.text_input("Search by name", key="search_name")

    submitted = st.form_submit_button("Search", use_container_width=True)

if submitted:
    phone_norm = norm_phone(search_phone)
    addr = (search_address or "").strip()
    name = (search_name or "").strip()

    if phone_norm:
        results = search_quotes(phone=phone_norm)
    elif addr:
        results = search_quotes(address=addr)
    elif name:
        results = search_quotes(name=name)
    else:
        results = []
        st.warning("Enter phone, address, or name.")

    if not results:
        st.warning("No matching quotes found.")
    else:
        for r in results:
            qid = r.get("quote_id", "")
            st.markdown(f"**{qid}** — {r.get('created_at','')}")
            if st.button(f"Load {qid}", key=f"load_{qid}"):
                snapshot = r.get("payload_json", {}) or {}
            
                # store snapshot
                load_snapshot_into_state(snapshot)
            
                # FORCE rebuild of widgets
                st.session_state["load_nonce"] += 1
                st.session_state["last_loaded_quote_id"] = qid
            
                st.success(f"Loaded: {qid}")
                st.rerun()


# ---------- Measurements ----------
st.divider()
st.subheader("Measurements")
st.caption("Type dimensions like 3.2x4 (metres). Used for pricing only; not shown in the PDF.")

def add_room():
    st.session_state["rooms"].append({"length": 0.0, "width": 0.0})

def remove_room(idx: int):
    if len(st.session_state["rooms"]) > 1:
        st.session_state["rooms"].pop(idx)
        # clear inputs to avoid key mismatch
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
            key=f"dim_{st.session_state['load_nonce']}_{i}",
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

# wastage after measurement
st.markdown("---")
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


# ---------- Work type ----------
st.divider()
st.subheader("Work type & Product")

def on_job_mode_change():
    # Clear the other selector so UI never reuses old state
    if st.session_state.get("job_mode") == "Supply & Install":
        st.session_state["install_id"] = ""
    else:
        st.session_state["product_id"] = ""
    st.session_state["ui_nonce"] = int(st.session_state.get("ui_nonce", 0)) + 1

st.radio(
    "Work type",
    ["Supply & Install", "Installation Only"],
    horizontal=True,
    key="job_mode",
    on_change=on_job_mode_change,
)

# ---- Select product/install after wastage ----
if st.session_state.get("job_mode") == "Supply & Install":
    if products_df.empty or "id" not in products_df.columns:
        st.error("products sheet must have column: id")
        st.stop()

    # flexible column names
    brand_col = "brand" if "brand" in products_df.columns else None
    name_col = "name" if "name" in products_df.columns else ("label" if "label" in products_df.columns else None)

    if "sell_price" in products_df.columns:
        price_col = "sell_price"
    elif "sell_per_m2" in products_df.columns:
        price_col = "sell_per_m2"
    elif "price" in products_df.columns:
        price_col = "price"
    else:
        st.error("products sheet needs one of: sell_price / sell_per_m2 / price")
        st.stop()

    ids = products_df["id"].astype(str).tolist()
    if st.session_state.get("product_id") not in ids:
        st.session_state["product_id"] = ids[0] if ids else ""

    def _fmt_product(pid: str) -> str:
        row = products_df.loc[products_df["id"].astype(str) == str(pid)].iloc[0]
        b = str(row.get(brand_col, "")).strip() if brand_col else ""
        n = str(row.get(name_col, "")).strip() if name_col else str(pid)
        return f"{b} — {n}".strip(" —")

    st.selectbox(
        "Select timber product",
        options=ids,
        key="product_id",
        format_func=_fmt_product,
    )

else:
    if install_df.empty or "id" not in install_df.columns:
        st.error("install_only sheet must have column: id")
        st.stop()

    name_col = "name" if "name" in install_df.columns else ("label" if "label" in install_df.columns else None)

    # supports your sheet even if it uses 'price' (common)
    if "install_price" in install_df.columns:
        price_col = "install_price"
    elif "install_per_m2" in install_df.columns:
        price_col = "install_per_m2"
    elif "price" in install_df.columns:
        price_col = "price"
    elif "install" in install_df.columns:
        price_col = "install"
    else:
        st.error("install_only sheet needs one of: install_price / install_per_m2 / price / install")
        st.stop()

    ids = install_df["id"].astype(str).tolist()
    if st.session_state.get("install_id") not in ids:
        st.session_state["install_id"] = ids[0] if ids else ""

    def _fmt_install(iid: str) -> str:
        row = install_df.loc[install_df["id"].astype(str) == str(iid)].iloc[0]
        n = str(row.get(name_col, "")).strip() if name_col else str(iid)
        return n

    st.selectbox(
        "Select installation type",
        options=ids,
        key="install_id",
        format_func=_fmt_install,
    )

# quote type after selecting product/install
st.selectbox("Quote type", ["Retail", "Builder"], key="quote_type")



# ---------- Select product/install (all prices from sheets) ----------
st.divider()
st.subheader("Select Timber / Installation")

if st.session_state["job_mode"] == "Supply & Install":
    if products_df.empty or "id" not in products_df.columns:
        st.error("Sheet tab 'products' must have column 'id'.")
        product_label = "Supply & Install"
        unit_price_default = 0.0
    else:
        product_options = products_df["id"].astype(str).tolist()
        st.session_state["product_id"] = safe_pick_id(products_df, st.session_state.get("product_id", ""), "id")

        def _prod_fmt(pid: str) -> str:
            row = products_df[products_df["id"].astype(str) == str(pid)]
            if row.empty:
                return str(pid)
            r = row.iloc[0]
            brand = str(r.get("brand", "")).strip()
            name = str(r.get("name", "")).strip()
            return f"{brand} — {name}".strip(" —")

        st.selectbox(
            "Product",
            options=product_options,
            index=product_options.index(str(st.session_state["product_id"])),
            format_func=_prod_fmt,
            key="product_id",
        )

        product_row = products_df[products_df["id"].astype(str) == str(st.session_state["product_id"])].iloc[0]
        brand = str(product_row.get("brand", "")).strip()
        name = str(product_row.get("name", "")).strip()
        product_label = f"Supply & install — {brand} {name}".strip()

        # price columns (support either sell_price or sell_per_m2)
        if "sell_price" in products_df.columns:
            unit_price_default = safe_float(product_row.get("sell_price", 0.0), 0.0)
        elif "sell_per_m2" in products_df.columns:
            unit_price_default = safe_float(product_row.get("sell_per_m2", 0.0), 0.0)
        else:
            unit_price_default = 0.0
            st.warning("Products sheet missing 'sell_price' or 'sell_per_m2' column.")

else:
    if install_df.empty or "id" not in install_df.columns:
        st.error("Sheet tab 'install_only' must have column 'id'.")
        install_label = "Installation"
        unit_price_default = 0.0
    else:
        install_options = install_df["id"].astype(str).tolist()
        st.session_state["install_id"] = safe_pick_id(install_df, st.session_state.get("install_id", ""), "id")

        def _ins_fmt(iid: str) -> str:
            row = install_df[install_df["id"].astype(str) == str(iid)]
            if row.empty:
                return str(iid)
            r = row.iloc[0]
            return str(r.get("name", iid))

        st.selectbox(
            "Installation type",
            options=install_options,
            index=install_options.index(str(st.session_state["install_id"])),
            format_func=_ins_fmt,
            key="install_id",
        )

        ins_row = install_df[install_df["id"].astype(str) == str(st.session_state["install_id"])].iloc[0]
        install_label = str(ins_row.get("name", "Installation"))
        unit_price_default = safe_float(ins_row.get("install_per_m2", ins_row.get("install_price", 0.0)), 0.0)


# ---------- Quote type after product ----------
st.divider()
st.subheader("Quote Type")
st.selectbox("Retail or Builder", ["Retail", "Builder"], key="quote_type")


# ---------- Build line items ----------
st.divider()
st.subheader("Quote Items")

line_items: List[dict] = []
subtotal = 0.0

if st.session_state["job_mode"] == "Supply & Install":
    unit_price = st.number_input(
        "Supply & Install price ($/m²) (default from sheet)",
        min_value=0.0,
        value=float(unit_price_default),
        step=1.0,
        key="core_price_override",
    )
    total = chargeable_area * unit_price
    line_items.append(line_item(product_label, f"{chargeable_area:.2f} m²", unit_price, total))
    subtotal += total
else:
    unit_price = st.number_input(
        "Installation price ($/m²) (default from sheet)",
        min_value=0.0,
        value=float(unit_price_default),
        step=1.0,
        key="core_price_override",
    )
    total = total_area * unit_price
    line_items.append(line_item(install_label, f"{total_area:.2f} m²", unit_price, total))
    subtotal += total


# ---------- Add-ons (ALL from sheets; removal/skirting/addons tabs) ----------
st.divider()
st.subheader("Add-ons (all prices from Google Sheet)")

def addon_row(key: str, label: str, unit: str, qty_default: float, price_default: float) -> float:
    checked = st.checkbox(label, key=f"addon_{key}")
    if not checked:
        return 0.0

    unit_norm = (unit or "").strip().lower().replace(" ", "")
    if unit_norm in ("m2", "m²"):
        step_qty = 0.1
        unit_display = "m²"
    elif unit_norm in ("room", "rooms"):
        step_qty = 1.0
        unit_display = "room"
    else:
        step_qty = 1.0
        unit_display = unit if unit else "each"

    c1, c2 = st.columns([1.1, 1.0], gap="small")
    with c1:
        qty = st.number_input(
            "Qty",
            min_value=0.0,
            value=float(st.session_state.get(f"addon_qty_{key}", qty_default)),
            step=step_qty,
            key=f"addon_qty_{key}",
            label_visibility="collapsed",
        )
        st.caption(unit_display)
    with c2:
        price = st.number_input(
            "Price",
            min_value=0.0,
            value=float(st.session_state.get(f"addon_price_{key}", price_default)),
            step=1.0,
            key=f"addon_price_{key}",
            label_visibility="collapsed",
        )
        st.caption(f"per {unit_display}")

    total = float(qty) * float(price)
    line_items.append(line_item(label, f"{qty:.2f} {unit_display}", float(price), total))
    return total

# Removal from removal tab
st.markdown("### Removal & Disposal")
if removal_df.empty:
    st.caption("No rows in sheet tab 'removal'.")
else:
    # expected columns: id, name/label, remove_per_m2 or price
    def colpick(df, *names):
        for n in names:
            if n in df.columns:
                return n
        return None

    rid_col = colpick(removal_df, "id")
    name_col = colpick(removal_df, "name", "label")
    price_col = colpick(removal_df, "remove_per_m2", "price", "rate")

    if not (rid_col and name_col and price_col):
        st.error("Removal sheet needs columns: id, name(or label), remove_per_m2(or price).")
    else:
        for _, r in removal_df.iterrows():
            rid = str(r.get(rid_col, "")).strip()
            nm = str(r.get(name_col, "")).strip()
            pr = safe_float(r.get(price_col, 0.0), 0.0)
            if not rid or not nm:
                continue
            subtotal += addon_row(
                key=f"rem_{rid}",
                label=f"Removal & disposal — {nm}",
                unit="m²",
                qty_default=float(total_area),
                price_default=float(pr),
            )

# Stairs + other add-ons from addons tab (category-based)
if addons_df.empty:
    st.caption("No rows in sheet tab 'addons'.")
else:
    # normalize columns
    def norm_col(c: str) -> str:
        return str(c or "").strip().lower().replace(" ", "").replace("_", "")

    colmap = {norm_col(c): c for c in addons_df.columns}
    id_col = colmap.get("id")
    cat_col = colmap.get("category")  # you said yours is category
    label_col = colmap.get("label") or colmap.get("name")
    unit_col = colmap.get("unit")
    price_col = colmap.get("price") or colmap.get("rate")

    if not (id_col and cat_col and label_col and unit_col and price_col):
        st.error("Addons sheet needs: id, category, label, unit, price (active optional).")
    else:
        grouped: Dict[str, List[dict]] = {}
        for _, r in addons_df.iterrows():
            aid = str(r.get(id_col, "")).strip()
            cat = str(r.get(cat_col, "")).strip().lower()
            lab = str(r.get(label_col, "")).strip()
            unit = str(r.get(unit_col, "")).strip()
            pr = safe_float(r.get(price_col, 0.0), 0.0)
            if not aid or not lab:
                continue
            grouped.setdefault(cat, []).append({"id": aid, "label": lab, "unit": unit, "price": pr})

        # order: stairs ("step") below removal, then others alphabetical
        order = []
        if "step" in grouped:
            order.append("step")
        order += sorted([k for k in grouped.keys() if k != "step"])

        for cat in order:
            title = "Stairs" if cat == "step" else cat.title()
            st.markdown(f"### {title}")

            for item in grouped[cat]:
                unit_norm = (item["unit"] or "").strip().lower().replace(" ", "")
                if unit_norm in ("m2", "m²"):
                    qty_default = float(chargeable_area)
                elif unit_norm in ("room", "rooms"):
                    qty_default = float(len(st.session_state["rooms"]))
                else:
                    qty_default = 1.0

                subtotal += addon_row(
                    key=f"addon_{item['id']}",
                    label=item["label"],
                    unit=item["unit"],
                    qty_default=qty_default,
                    price_default=float(item["price"]),
                )

# Skirting from skirting tab
st.markdown("### Skirting")
if skirting_df.empty:
    st.caption("No rows in sheet tab 'skirting'.")
else:
    sid_col = "id" if "id" in skirting_df.columns else None
    h_col = "height_mm" if "height_mm" in skirting_df.columns else None
    price_col = "price_per_lm" if "price_per_lm" in skirting_df.columns else ("price" if "price" in skirting_df.columns else None)

    if not (sid_col and price_col):
        st.error("Skirting sheet needs columns: id, price_per_lm (and optional height_mm).")
    else:
        skirting_df["_sid"] = skirting_df[sid_col].astype(str)
        options = skirting_df["_sid"].tolist()

        def _sk_fmt(sid: str) -> str:
            row = skirting_df[skirting_df["_sid"] == str(sid)]
            if row.empty:
                return str(sid)
            r = row.iloc[0]
            if h_col:
                return f"{int(safe_float(r.get(h_col, 0), 0))}mm"
            return str(sid)

        st.session_state.setdefault("skirting_id", options[0] if options else "")
        st.selectbox("Skirting height", options=options, format_func=_sk_fmt, key="skirting_id")

        row = skirting_df[skirting_df["_sid"] == str(st.session_state.get("skirting_id", ""))]
        if not row.empty:
            r = row.iloc[0]
            price = safe_float(r.get(price_col, 0.0), 0.0)
            label = f"Skirting — {_sk_fmt(st.session_state['skirting_id'])}"
            subtotal += addon_row(
                key=f"sk_{st.session_state['skirting_id']}",
                label=label,
                unit="lm",
                qty_default=0.0,
                price_default=float(price),
            )


# ---------- Totals ----------
st.divider()
gst = subtotal * GST_RATE
total_inc = subtotal + gst
t1, t2, t3 = st.columns(3)
t1.metric("Subtotal (ex GST)", money0(subtotal))
t2.metric("GST", money0(gst))
t3.metric("Total (inc GST)", money0(total_inc))


# ---------- Client details at end ----------
st.divider()
st.subheader("Client Details (fill at end)")
c1, c2 = st.columns(2)
with c1:
    st.text_input("Client name", key="client_name")
    st.text_input("Client phone (keep 0)", key="client_phone")
with c2:
    st.text_input("Client email", key="client_email")
    st.text_input("Site address", key="site_address")


# ---------- Terms ----------
st.divider()
st.subheader("Terms")
terms_default = [
    "Quote valid for 30 days.",
    "A 10% deposit is required to secure stock and confirm installation date.",
    "Balance due immediately upon completion.",
]
terms_text = st.text_area("Terms (one per line)", "\n".join(terms_default), height=140)
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
    "client_phone": (st.session_state.get("client_phone", "") or "").strip(),  # KEEP typed phone
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

st.session_state.setdefault("quote_saved", False)

def handle_save():
    if not st.session_state.get("quote_saved", False):
        qid = save_quote_to_sheet(payload)
        st.session_state["quote_saved"] = True
        st.session_state["last_quote_id"] = qid
        st.success(f"Quote saved: {qid}")

# ---------- Output ----------
st.divider()
st.subheader("Save & Generate")

col1, col2 = st.columns(2)
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

st.divider()
st.subheader("Mobile-friendly quote (copy/paste) (ex GST)")
mobile_text = build_mobile_quote_text(payload)
st.text_area("Copy/paste", value=mobile_text, height=260)
