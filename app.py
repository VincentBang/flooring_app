# app.py — paste this whole file
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
# PAGE CONFIG (MUST BE FIRST)
# =========================
st.set_page_config(page_title="Flooring Quote Prototype", layout="wide")


# =========================
# CONFIG
# =========================
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbz8dQm5wDnMgUejAt7knJW4lLJq8OyxmqjLCgULlT4Itq8KYiuu3cOCTsI8z44i9SzoFw/exec"
SHEET_ID = "10G98m8XHdySRTMWjbAUlQCZMH1NXCD6uca82xN0p4fY"

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

# Fallback data (only used if sheets are empty)
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
# SHEET LOADER
# =========================
@st.cache_data(ttl=300)
def load_sheet(tab_name: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={tab_name}"
    try:
        df = pd.read_csv(url)
    except Exception:
        return pd.DataFrame()

    # Be defensive: some tabs might not have active column while testing
    if "active" in df.columns:
        # Handle TRUE/true/1 etc.
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


def find_by_id(items: List[dict], item_id: str) -> dict:
    for it in items:
        if str(it.get("id")) == str(item_id):
            return it
    raise KeyError(item_id)


def line_item(label: str, qty_str: str, unit_price: float, total: float) -> dict:
    return {
        "label": str(label),
        "qty_str": str(qty_str),
        "unit_price": float(unit_price),
        "total": float(total),
    }


def money0(x: float) -> str:
    return f"${float(x):,.0f}"


def money2(x: float) -> str:
    return f"${float(x):,.2f}"


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
    """
    Parse '3.2x4', '3.2 x 4', '3.2*4', '3.2×4', '3.2,4'
    Returns (length, width) or (None, None) if invalid.
    """
    if not text:
        return None, None
    s = text.strip().lower()
    s = s.replace("×", "x").replace("*", "x").replace(" ", "")
    s = s.replace(",", "x")
    m = re.match(r"^(\d+(\.\d+)?)[x](\d+(\.\d+)?)$", s)
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(3))
    except Exception:
        return None, None


# =========================
# STATE (SINGLE INITIALISATION)
# =========================
def init_state():
    if st.session_state.get("__init_done__"):
        return

    st.session_state.step = 1

    # Job fields
    st.session_state.client_name = ""
    st.session_state.client_phone = ""
    st.session_state.client_email = ""
    st.session_state.site_address = ""
    st.session_state.job_mode = "Supply & Install"
    st.session_state.quote_type = "Retail"

    # Scope toggles
    st.session_state.scope_removal = False
    st.session_state.scope_furniture = False
    st.session_state.scope_skirting = False

    # Selections / rates
    st.session_state.wastage_pct = DEFAULT_WASTAGE_PCT
    st.session_state.removal_selected = []
    st.session_state.furniture_rate = DEFAULT_FURNITURE_PER_ROOM
    st.session_state.skirting_id = SKIRTING[0]["id"]

    # Measurement rooms (starts empty)
    st.session_state.rooms = [{"length": 0.0, "width": 0.0}]

    # Save guards
    st.session_state.quote_saved = False
    st.session_state.last_quote_id = ""

    st.session_state.__init_done__ = True


def reset_quote():
    # Clear only quote-specific things (keep cached sheets etc.)
    st.session_state.step = 1

    st.session_state.client_name = ""
    st.session_state.client_phone = ""
    st.session_state.client_email = ""
    st.session_state.site_address = ""
    st.session_state.job_mode = "Supply & Install"
    st.session_state.quote_type = "Retail"

    st.session_state.scope_removal = False
    st.session_state.scope_furniture = False
    st.session_state.scope_skirting = False

    st.session_state.wastage_pct = DEFAULT_WASTAGE_PCT
    st.session_state.removal_selected = []
    st.session_state.furniture_rate = DEFAULT_FURNITURE_PER_ROOM
    st.session_state.skirting_id = SKIRTING[0]["id"]

    st.session_state.rooms = [{"length": 0.0, "width": 0.0}]

    st.session_state.quote_saved = False
    st.session_state.last_quote_id = ""

    # Clear dynamic UI keys that can cause “hidden state” confusion
    for k in list(st.session_state.keys()):
        if str(k).startswith("dim_") or str(k).startswith("addon_") or str(k).startswith("addon_qty_") or str(k).startswith("addon_price_"):
            del st.session_state[k]


init_state()


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
        "quote_type": st.session_state.get("quote_type", ""),
        "job_mode": payload.get("job_mode", ""),
        "client_name": payload.get("client_name", ""),
        "client_phone": payload.get("client_phone", ""),
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


def search_quotes(phone=None, address=None):
    params = {"sheet_id": SHEET_ID, "phone": phone or "", "address": address or ""}
    r = requests.get(APPS_SCRIPT_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def load_snapshot_into_state(snapshot: Dict[str, Any]):
    # Only restore known keys so we don’t overwrite state with unexpected shapes.
    st.session_state.client_name = str(snapshot.get("client_name", "") or "")
    st.session_state.client_phone = str(snapshot.get("client_phone", "") or "")
    st.session_state.client_email = str(snapshot.get("client_email", "") or "")
    st.session_state.site_address = str(snapshot.get("site_address", "") or "")
    st.session_state.job_mode = str(snapshot.get("job_mode", "") or st.session_state.job_mode)

    # rooms
    rooms = snapshot.get("rooms", [])
    restored_rooms = []
    if isinstance(rooms, list) and rooms:
        for r in rooms:
            try:
                restored_rooms.append(
                    {
                        "length": float(r.get("length", 0.0) or 0.0),
                        "width": float(r.get("width", 0.0) or 0.0),
                    }
                )
            except Exception:
                continue
    st.session_state.rooms = restored_rooms if restored_rooms else [{"length": 0.0, "width": 0.0}]

    # make sure save guard resets
    st.session_state.quote_saved = False
    st.session_state.last_quote_id = ""

    # clear dim keys so UI reflects restored rooms cleanly
    for k in list(st.session_state.keys()):
        if str(k).startswith("dim_"):
            del st.session_state[k]


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
            c.drawImage(
                logo,
                logo_x,
                logo_y,
                width=logo_w,
                height=logo_h,
                mask="auto",
                preserveAspectRatio=True,
            )
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

    def money_pdf(x: float) -> str:
        return f"${float(x):,.2f}"

    # Header
    y = draw_company_header()

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, "Quotation")
    y -= 10
    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 18

    # Client Details
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
    y -= 18

    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 18

    # Pricing Table
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

    # Totals box
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

    # Terms
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
removal_df = load_sheet("removal")
skirting_df = load_sheet("skirting")
addons_df = load_sheet("addons")

st.title("📱 Flooring Quote Prototype (V1)")
st.caption(f"{COMPANY['name']} • {COMPANY['abn']} • {COMPANY['phone']} • {COMPANY['email']}")

top_col1, top_col2 = st.columns([1, 1])
with top_col1:
    if st.button("🧼 New Quote (reset)", use_container_width=True):
        reset_quote()
        st.rerun()

with top_col2:
    st.write("")


# =========================
# RETRIEVE EXISTING QUOTE
# =========================
st.divider()
st.subheader("Retrieve Existing Quote")
search_phone = st.text_input("Search by phone", key="search_phone")
search_address = st.text_input("Search by address", key="search_address")

if st.button("Search Quotes"):
    try:
        results = search_quotes(search_phone, search_address)
    except Exception as e:
        st.error(f"Search failed: {e}")
        results = []

    if not results:
        st.warning("No matching quotes found.")
    else:
        for r in results:
            st.markdown(f"**{r.get('quote_id','')}** — {r.get('created_at','')}")
            if st.button(f"Load {r.get('quote_id','')}", key=f"load_{r.get('quote_id','')}"):
                snapshot = r.get("payload_json", {}) or {}
                load_snapshot_into_state(snapshot)
                st.success("Quote loaded successfully.")
                st.session_state.step = 2
                st.rerun()


# =========================
# STEP 1 — JOB SETUP
# =========================
if st.session_state.step == 1:
    st.divider()
    st.subheader("Step 1 — Job Setup")

    c1, c2 = st.columns(2)
    with c1:
        st.text_input("Client name", key="client_name")
        st.text_input("Client phone", key="client_phone")
    with c2:
        st.text_input("Client email", key="client_email")
        st.text_input("Site address", key="site_address")

    st.radio(
        "Work type",
        ["Supply & Install", "Installation Only"],
        horizontal=True,
        key="job_mode",
    )

    st.selectbox("Quote type (for your own tracking)", ["Retail", "Builder"], key="quote_type")

    st.divider()
    st.subheader("Step 2 — Select Scope")
    st.checkbox("Include floor removal & disposal", key="scope_removal")
    st.checkbox("Include furniture handling", key="scope_furniture")
    st.checkbox("Include skirting", key="scope_skirting")

    st.divider()
    st.subheader("Core Selection")

    if st.session_state.job_mode == "Supply & Install":
        if not products_df.empty and "id" in products_df.columns:
            product_options = products_df["id"].astype(str).tolist()
            st.session_state.product_id = safe_pick_id(products_df, st.session_state.get("product_id", ""), "id")

            st.selectbox(
                "Select timber product (Supply & Install)",
                options=product_options,
                index=product_options.index(str(st.session_state.product_id)),
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

    st.number_input(
        "Wastage (%)",
        min_value=0.0,
        max_value=25.0,
        value=float(st.session_state.wastage_pct),
        step=0.5,
        key="wastage_pct",
    )

    if st.session_state.scope_removal:
        st.multiselect(
            "Existing floor type(s) to remove",
            options=[r["id"] for r in REMOVAL_TYPES],
            format_func=lambda rid: find_by_id(REMOVAL_TYPES, rid)["name"],
            key="removal_selected",
        )

    if st.session_state.scope_furniture:
        st.number_input(
            "Furniture handling rate ($ per room)",
            min_value=0.0,
            value=float(st.session_state.furniture_rate),
            step=5.0,
            key="furniture_rate",
        )

    if st.session_state.scope_skirting:
        st.selectbox(
            "Skirting height",
            options=[s["id"] for s in SKIRTING],
            format_func=lambda sid: f"{find_by_id(SKIRTING, sid)['height_mm']}mm",
            key="skirting_id",
        )

    st.divider()
    if st.button("Next → Measurements & Quote", use_container_width=True):
        st.session_state.step = 2
        st.rerun()


# =========================
# STEP 2 — MEASUREMENTS + QUOTE + OUTPUT
# =========================
if st.session_state.step == 2:
    st.divider()
    st.subheader("Measurements")
    st.caption("Type dimensions like 3.2x4 (metres). Used for pricing only; not shown in the PDF.")

    if "rooms" not in st.session_state or not st.session_state.rooms:
        st.session_state.rooms = [{"length": 0.0, "width": 0.0}]

    def add_room():
        st.session_state.rooms.append({"length": 0.0, "width": 0.0})

    def remove_room(idx: int):
        if len(st.session_state.rooms) > 1:
            st.session_state.rooms.pop(idx)
            # Clear dimension keys so inputs re-index cleanly
            for k in list(st.session_state.keys()):
                if str(k).startswith("dim_"):
                    del st.session_state[k]
            st.rerun()

    h1, h2, h3 = st.columns([2, 1, 0.6], gap="small")
    h1.markdown("**Length x Width (m)**")
    h2.markdown("**Area (m²)**")
    h3.markdown("")

    # IMPORTANT: write updates back to the list (avoid hidden mutation issues across reruns)
    updated_rooms = []
    for i, room in enumerate(st.session_state.rooms):
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
            st.markdown(
                f"<div style='padding-top:0.55rem;font-size:1rem;'>{area:.2f}</div>",
                unsafe_allow_html=True,
            )

        with c3:
            if len(st.session_state.rooms) > 1:
                if st.button("✕", key=f"remove_{i}"):
                    remove_room(i)

        updated_rooms.append(new_room)

    st.session_state.rooms = updated_rooms

    st.button("➕ Add Room", on_click=add_room)

    total_area = sum(float(r["length"]) * float(r["width"]) for r in st.session_state.rooms)
    wastage_pct = float(st.session_state.wastage_pct)
    chargeable_area = total_area * (1.0 + wastage_pct / 100.0)

    st.markdown("---")
    a, b, ccol = st.columns(3)
    a.metric("Total area (m²)", f"{total_area:.2f}")
    b.metric("Wastage (%)", f"{wastage_pct:.1f}")
    ccol.metric("Chargeable area (m²)", f"{chargeable_area:.2f}")

    st.divider()
    st.subheader("Quote Items (selected scope only)")

    line_items: List[dict] = []
    subtotal = 0.0

    # CORE MODE
    if st.session_state.job_mode == "Supply & Install":
        st.markdown("#### Supply & Install")

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
        st.markdown("#### Installation Only")
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

    # REMOVAL
    if st.session_state.scope_removal:
        st.markdown("#### Floor Removal & Disposal")
        for rid in st.session_state.removal_selected:
            r = find_by_id(REMOVAL_TYPES, rid)
            unit_price = st.number_input(
                f"{r['name']} removal ($/m²)",
                min_value=0.0,
                value=float(r["remove_per_m2"]),
                step=1.0,
                key=f"removal_rate_{rid}",
            )
            total = total_area * unit_price
            line_items.append(line_item(f"Removal & disposal — {r['name']}", f"{total_area:.2f} m²", unit_price, total))
            subtotal += total

    # FURNITURE
    if st.session_state.scope_furniture:
        st.markdown("#### Furniture Handling")
        room_names = [f"Room {i+1}" for i in range(len(st.session_state.rooms))]
        selected_rooms = st.multiselect(
            "Select rooms requiring furniture handling",
            options=room_names,
            default=room_names,
            key="furniture_rooms_selected",
        )
        rooms_count = len(selected_rooms)

        unit_price = st.number_input(
            "Furniture handling rate ($ per room)",
            min_value=0.0,
            value=float(st.session_state.furniture_rate),
            step=5.0,
            key="furniture_rate_override",
        )

        total = rooms_count * unit_price
        line_items.append(line_item("Furniture handling", f"{rooms_count} room(s)", unit_price, total))
        subtotal += total

    # SKIRTING
    if st.session_state.scope_skirting:
        st.markdown("#### Skirting")
        sk = find_by_id(SKIRTING, st.session_state.skirting_id)

        unit_price = st.number_input(
            "Skirting price ($/lm)",
            min_value=0.0,
            value=float(sk["price_per_lm"]),
            step=1.0,
            key="skirting_price_override",
        )

        lm = st.number_input("Total skirting length (lm)", min_value=0.0, value=0.0, step=1.0, key="skirting_lm")

        total = lm * unit_price
        line_items.append(line_item(f"Skirting — {sk['height_mm']}mm", f"{lm:.1f} lm", unit_price, total))
        subtotal += total

    # ADDONS
    st.markdown("#### Additional Items")
    if addons_df is not None and not addons_df.empty:
        for _, row in addons_df.iterrows():
            addon_id = str(row.get("id", "")).strip()
            label = str(row.get("label", "")).strip()
            unit = str(row.get("unit", "")).strip()
            default_price = safe_float(row.get("price", 0.0), 0.0)

            if not addon_id or not label:
                continue

            if st.checkbox(label, key=f"addon_{addon_id}"):
                col1, col2 = st.columns(2)
                with col1:
                    if unit == "m2":
                        qty_default = chargeable_area
                    elif unit == "room":
                        qty_default = len(st.session_state.rooms)
                    else:
                        qty_default = 1.0

                    qty = st.number_input(
                        f"Quantity ({unit})",
                        min_value=0.0,
                        value=float(qty_default),
                        step=1.0 if unit in ("room", "each") else 0.1,
                        key=f"addon_qty_{addon_id}",
                    )

                with col2:
                    unit_price = st.number_input(
                        f"Price per {unit}",
                        min_value=0.0,
                        value=float(default_price),
                        step=1.0,
                        key=f"addon_price_{addon_id}",
                    )

                total = qty * unit_price
                line_items.append(line_item(label, f"{qty:.2f} {unit}", unit_price, total))
                subtotal += total
    else:
        st.caption("No add-ons found in sheet tab 'addons' (or tab is empty).")

    gst = subtotal * GST_RATE
    total_inc = subtotal + gst

    st.divider()
    t1, t2, t3 = st.columns(3)
    t1.metric("Subtotal (ex GST)", money0(subtotal))
    t2.metric("GST", money0(gst))
    t3.metric("Total (inc GST)", money0(total_inc))

    st.divider()
    st.subheader("Save & Generate Quote")

    # Terms
    st.subheader("Payment & Terms")
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

    # Rooms output (for saving / reload)
    rooms_out = []
    for i, r in enumerate(st.session_state.rooms):
        rooms_out.append(
            {
                "name": f"Room {i+1}",
                "length": float(r["length"]),
                "width": float(r["width"]),
                "area": float(r["length"]) * float(r["width"]),
            }
        )

    # Payload (THIS is the single source used by PDF + save)
    payload = {
        "client_name": (st.session_state.get("client_name", "") or "").strip(),
        "client_phone": (st.session_state.get("client_phone", "") or "").strip(),
        "client_email": (st.session_state.get("client_email", "") or "").strip(),
        "site_address": (st.session_state.get("site_address", "") or "").strip(),
        "job_mode": st.session_state.get("job_mode", ""),
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

    # Safety: show a visible warning if client fields are empty at Step 2
    missing = []
    if not payload["client_name"]:
        missing.append("client name")
    if not payload["client_phone"]:
        missing.append("client phone")
    if not payload["site_address"]:
        missing.append("site address")
    if missing:
        st.warning("Missing: " + ", ".join(missing) + ". Click Back and fill them in (or load a saved quote).")

    def handle_save():
        if not st.session_state.quote_saved:
            quote_id = save_quote_to_sheet(payload)
            st.session_state.quote_saved = True
            st.session_state.last_quote_id = quote_id
            st.success(f"Quote saved: {quote_id}")

    st.divider()
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("← Back", use_container_width=True):
            st.session_state.step = 1
            st.rerun()

    with col2:
        if st.button("💾 Save Quote", use_container_width=True):
            try:
                handle_save()
            except Exception as e:
                st.error(f"Save failed: {e}")

    with col3:
        # Use download_button directly; it will render reliably
        try:
            # Save first if user clicks download
            if st.button("Generate PDF", use_container_width=True):
                handle_save()
            pdf_bytes = build_quote_pdf(payload)
            st.download_button(
                "Download Quote.pdf",
                data=pdf_bytes,
                file_name=f"{st.session_state.get('last_quote_id','Quote')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF generation failed: {e}")

    st.divider()
    st.subheader("Mobile-friendly quote (copy/paste)")
    mobile_text = build_mobile_quote_text(payload)
    st.text_area(
        "Copy this and paste into SMS/WhatsApp/email (ex GST)",
        value=mobile_text,
        height=260,
    )

    txt_col1, txt_col2 = st.columns([1, 2])
    with txt_col1:
        if st.button("Save (if not saved)", use_container_width=True):
            try:
                handle_save()
            except Exception as e:
                st.error(f"Save failed: {e}")

    with txt_col2:
        st.download_button(
            "Download Quote.txt",
            data=mobile_text.encode("utf-8"),
            file_name=f"{st.session_state.get('last_quote_id','Quote')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
