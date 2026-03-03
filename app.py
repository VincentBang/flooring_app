import io
import re
import uuid
import datetime
import json
import html
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
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

    # filter active rows if column exists (case-insensitive)
    cols_norm = {str(c).strip().lower(): c for c in df.columns}
    if "active" in cols_norm:
        active_col = cols_norm["active"]
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

def parse_dims(text: str) -> Tuple[Optional[float], Optional[float]]:
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

def colpick(df: pd.DataFrame, *names: str) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None

def norm_colname(c: str) -> str:
    return str(c or "").strip().lower().replace(" ", "").replace("_", "")

def _ensure_dict(x):
    """payload_json may be dict OR JSON string OR None"""
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        try:
            obj = json.loads(x)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}

def _ensure_list_of_line_items(x) -> List[dict]:
    """
    line_items may come back as:
      - list[dict] (best)
      - dict with numeric keys { "0": {...}, "1": {...} }
      - JSON string of either of the above
      - None
    """
    if x is None:
        return []
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except Exception:
            return []

    if isinstance(x, list):
        return [it for it in x if isinstance(it, dict)]

    if isinstance(x, dict):
        numeric_keys = []
        for k in x.keys():
            try:
                numeric_keys.append(int(k))
            except Exception:
                pass
        if numeric_keys:
            items = []
            for i in sorted(numeric_keys):
                it = x.get(str(i), None)
                if isinstance(it, dict):
                    items.append(it)
            return items

    return []

def _extract_loaded_items_from_search_row(r: dict) -> List[dict]:
    """
    SINGLE SOURCE OF TRUTH:
      Prefer payload_json.line_items (because that's what you saved).
      Fall back to r.line_items if Apps Script returns it.
    """
    payload = _ensure_dict(r.get("payload_json"))
    items = _ensure_list_of_line_items(payload.get("line_items"))
    if items:
        return items

    items2 = _ensure_list_of_line_items(r.get("line_items"))
    if items2:
        return items2

    items3 = _ensure_list_of_line_items(r.get("line_items_json"))
    if items3:
        return items3

    return []

def clear_search_state():
    ss = st.session_state
    # clear search inputs
    for k in ("search_phone", "search_address", "search_name"):
        if k in ss:
            ss[k] = ""
    # clear persisted results + label
    ss["search_results"] = []
    ss["search_last_query"] = ""

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
        "client_phone": payload.get("client_phone", ""),           # keep leading 0 (as typed)
        "client_phone_norm": payload.get("client_phone_norm", ""), # normalized digits for search
        "client_email": payload.get("client_email", ""),
        "site_address": payload.get("site_address", ""),
        "total_area": payload.get("total_area", 0),
        "chargeable_area": payload.get("chargeable_area", 0),
        "wastage_pct": payload.get("wastage_pct", 0),
        "subtotal_ex_gst": payload.get("subtotal_ex_gst", 0),
        "gst": payload.get("gst", 0),
        "total_inc_gst": payload.get("total_inc_gst", 0),

        # compatibility
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


def load_snapshot_into_state(snapshot: Any, loaded_quote_id: str = ""):
    ss = st.session_state

    # --- normalize snapshot into a dict ---
    if snapshot is None:
        snap = {}
    elif isinstance(snapshot, dict):
        snap = snapshot
    elif isinstance(snapshot, str):
        try:
            snap = json.loads(snapshot)
            if not isinstance(snap, dict):
                snap = {}
        except Exception:
            snap = {}
    else:
        snap = {}

    # clear dynamic widget keys
    for k in list(ss.keys()):
        if str(k).startswith(("dim_", "addon_", "addon_qty_", "addon_price_", "rem_", "sk_", "core_")):
            del ss[k]

    # restore fields
    ss["client_name"] = str(snap.get("client_name", "") or "")
    ss["client_phone"] = str(snap.get("client_phone", "") or "")
    ss["client_email"] = str(snap.get("client_email", "") or "")
    ss["site_address"] = str(snap.get("site_address", "") or "")

    ss["job_mode"] = str(snap.get("job_mode", ss.get("job_mode", "Supply & Install")) or "Supply & Install")
    ss["quote_type"] = str(snap.get("quote_type", ss.get("quote_type", "Retail")) or "Retail")
    ss["wastage_pct"] = float(snap.get("wastage_pct", ss.get("wastage_pct", DEFAULT_WASTAGE_PCT)) or DEFAULT_WASTAGE_PCT)

    # restore rooms
    rooms = snap.get("rooms", [])
    restored = []
    if isinstance(rooms, list) and rooms:
        for r in rooms:
            try:
                restored.append({"length": float(r.get("length", 0.0) or 0.0), "width": float(r.get("width", 0.0) or 0.0)})
            except Exception:
                continue
    ss["rooms"] = restored if restored else [{"length": 0.0, "width": 0.0}]

    # force rebuild of measurement widgets
    ss["load_nonce"] = int(ss.get("load_nonce", 0)) + 1
    ss["last_loaded_quote_id"] = loaded_quote_id or ""
    ss["quote_saved"] = False
    ss["last_quote_id"] = ""

    # clear selector memory so defaults recalc cleanly
    for k in ("last_product_id", "last_install_id"):
        if k in ss:
            del ss[k]


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

    for li in items:
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
    ss = st.session_state
    ss.setdefault("loaded_quote_id", "")
    ss.setdefault("loaded_line_items", [])
    ss.setdefault("start_new_quote", False)

    ss.setdefault("load_nonce", 0)
    ss.setdefault("last_loaded_quote_id", "")
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

# Global "Start New Quote" (works anytime)
if st.button("Start New Quote", use_container_width=True):
    ss = st.session_state

    # clear loaded quote lock + items
    ss["loaded_quote_id"] = ""
    ss["loaded_line_items"] = []

    # clear builder inputs + client details
    ss["client_name"] = ""
    ss["client_phone"] = ""
    ss["client_email"] = ""
    ss["site_address"] = ""

    # reset quote settings
    ss["job_mode"] = "Supply & Install"
    ss["quote_type"] = "Retail"
    ss["product_id"] = ""
    ss["install_id"] = ""
    ss["wastage_pct"] = float(DEFAULT_WASTAGE_PCT)

    # reset rooms
    ss["rooms"] = [{"length": 0.0, "width": 0.0}]

    # clear dynamic widget keys (so checkboxes/qty/price don’t “stick”)
    for k in list(ss.keys()):
        if str(k).startswith(("dim_", "addon_", "addon_qty_", "addon_price_", "rem_", "sk_", "core_")):
            del ss[k]

    # clear search UI completely
    clear_search_state()

    # reset save flags
    ss["quote_saved"] = False
    ss["last_quote_id"] = ""

    # force widget rebuild
    ss["load_nonce"] = int(ss.get("load_nonce", 0)) + 1

    st.rerun()

# ---------- Retrieve quote ----------
st.divider()
st.subheader("Retrieve Existing Quote")

if st.session_state.get("loaded_quote_id"):
    if st.button("Edit loaded quote (switch to builder)", use_container_width=True):
        st.session_state["loaded_quote_id"] = ""
        st.rerun()

# keep results across reruns so Load buttons work
st.session_state.setdefault("search_results", [])
st.session_state.setdefault("search_last_query", "")

with st.form("quote_search_form", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("Search by phone (any format)", key="search_phone")
    with c2:
        st.text_input("Search by address", key="search_address")
    with c3:
        st.text_input("Search by name", key="search_name")

    submitted = st.form_submit_button("Search", use_container_width=True)

if submitted:
    phone_norm = norm_phone(st.session_state.get("search_phone", ""))
    addr = (st.session_state.get("search_address", "") or "").strip()
    name = (st.session_state.get("search_name", "") or "").strip()

    if phone_norm:
        results = search_quotes(phone=phone_norm)
        st.session_state["search_last_query"] = f"phone={phone_norm}"
    elif addr:
        results = search_quotes(address=addr)
        st.session_state["search_last_query"] = f"address={addr}"
    elif name:
        results = search_quotes(name=name)
        st.session_state["search_last_query"] = f"name={name}"
    else:
        results = []
        st.warning("Enter phone, address, or name.")
        st.session_state["search_last_query"] = ""

    st.session_state["search_results"] = results or []

results = st.session_state.get("search_results", []) or []

if results:
    st.caption(f"Results ({len(results)}) — {st.session_state.get('search_last_query','')}")
    for r in results:
        qid = str(r.get("quote_id", "")).strip()
        created = str(r.get("created_at", "")).strip()

        cols = st.columns([3, 1])
        with cols[0]:
            st.markdown(f"**{qid}** — {created}")

        with cols[1]:
            if st.button("Load", key=f"load_{qid}", use_container_width=True):
                snapshot = _ensure_dict(r.get("payload_json", {}))
                load_snapshot_into_state(snapshot, loaded_quote_id=qid)

                loaded_items = _extract_loaded_items_from_search_row(r)
                if not loaded_items:
                    loaded_items = _ensure_list_of_line_items(snapshot.get("line_items"))

                st.session_state["loaded_line_items"] = loaded_items
                st.session_state["loaded_quote_id"] = qid  # lock into loaded view

                st.success(f"Loaded: {qid}")
                st.rerun()
else:
    if st.session_state.get("search_last_query"):
        st.warning("No matching quotes found.")


# ---------- Measurements ----------
st.divider()
st.subheader("Measurements")
st.caption("Type dimensions like 3.2x4 (metres). Used for pricing only; not shown in the PDF.")

def add_room():
    st.session_state["rooms"].append({"length": 0.0, "width": 0.0})

def remove_room(idx: int):
    if len(st.session_state["rooms"]) > 1:
        st.session_state["rooms"].pop(idx)
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
            if st.button("✕", key=f"remove_{st.session_state['load_nonce']}_{i}"):
                remove_room(i)

    updated_rooms.append(new_room)

st.session_state["rooms"] = updated_rooms
st.button("➕ Add Room", on_click=add_room)

total_area = sum(float(r["length"]) * float(r["width"]) for r in st.session_state["rooms"])

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


# =========================
# QUOTE BUILDING
# =========================
is_loaded_view = bool(st.session_state.get("loaded_quote_id"))
st.divider()
st.subheader("Work type & Product")

# Always define these so later code never crashes
line_items: List[dict] = []
subtotal: float = 0.0

if not is_loaded_view:
    def on_job_mode_change():
        if st.session_state.get("job_mode") == "Supply & Install":
            st.session_state["install_id"] = ""
            for k in ("core_price_install", "last_install_id"):
                if k in st.session_state:
                    del st.session_state[k]
        else:
            st.session_state["product_id"] = ""
            for k in ("core_price_supply", "last_product_id"):
                if k in st.session_state:
                    del st.session_state[k]

    st.radio(
        "Work type",
        ["Supply & Install", "Installation Only"],
        horizontal=True,
        key="job_mode",
        on_change=on_job_mode_change,
    )

    product_label = ""
    install_label = ""
    unit_price_default = 0.0

    if st.session_state.get("job_mode") == "Supply & Install":
        if products_df.empty or "id" not in products_df.columns:
            st.error("products sheet must have column: id")
            st.stop()

        brand_col = colpick(products_df, "brand")
        name_col = colpick(products_df, "name", "label")
        price_col = colpick(products_df, "sell_price", "sell_per_m2", "price")

        if not price_col:
            st.error("products sheet needs one of: sell_price / sell_per_m2 / price")
            st.stop()

        ids = products_df["id"].astype(str).tolist()
        if not ids:
            st.error("products sheet has no active rows.")
            st.stop()

        current = st.session_state.get("product_id", "")
        if current not in ids:
            current = ids[0]
            st.session_state["product_id"] = current

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

        row = products_df.loc[products_df["id"].astype(str) == str(st.session_state["product_id"])].iloc[0]
        b = str(row.get(brand_col, "")).strip() if brand_col else ""
        n = str(row.get(name_col, "")).strip() if name_col else ""
        product_label = f"Supply & install — {b} {n}".strip()
        unit_price_default = safe_float(row.get(price_col, 0.0), 0.0)

        last_pid = st.session_state.get("last_product_id", "")
        if last_pid != st.session_state["product_id"]:
            st.session_state["core_price_supply"] = float(unit_price_default)
            st.session_state["last_product_id"] = st.session_state["product_id"]

    else:
        if install_df.empty or "id" not in install_df.columns:
            st.error("install_only sheet must have column: id")
            st.stop()

        name_col = colpick(install_df, "name", "label")
        price_col = colpick(install_df, "install_price", "install_per_m2", "price", "install")

        if not price_col:
            st.error("install_only sheet needs one of: install_price / install_per_m2 / price / install")
            st.stop()

        ids = install_df["id"].astype(str).tolist()
        if not ids:
            st.error("install_only sheet has no active rows.")
            st.stop()

        current = st.session_state.get("install_id", "")
        if current not in ids:
            current = ids[0]
            st.session_state["install_id"] = current

        def _fmt_install(iid: str) -> str:
            row = install_df.loc[install_df["id"].astype(str) == str(iid)].iloc[0]
            return str(row.get(name_col, iid)).strip() if name_col else str(iid)

        st.selectbox(
            "Select installation type",
            options=ids,
            key="install_id",
            format_func=_fmt_install,
        )

        row = install_df.loc[install_df["id"].astype(str) == str(st.session_state["install_id"])].iloc[0]
        install_label = str(row.get(name_col, "Installation")).strip() if name_col else "Installation"
        unit_price_default = safe_float(row.get(price_col, 0.0), 0.0)

        last_iid = st.session_state.get("last_install_id", "")
        if last_iid != st.session_state["install_id"]:
            st.session_state["core_price_install"] = float(unit_price_default)
            st.session_state["last_install_id"] = st.session_state["install_id"]

    st.selectbox("Quote type", ["Retail", "Builder"], key="quote_type")

    st.divider()
    st.subheader("Quote Items")

    # If you loaded line items earlier but you're in builder mode, show them
    loaded_items = st.session_state.get("loaded_line_items")
    if isinstance(loaded_items, list) and len(loaded_items) > 0:
        line_items = loaded_items
        subtotal = sum(float(li.get("total", 0) or 0) for li in line_items)
        st.dataframe(pd.DataFrame(line_items), use_container_width=True, hide_index=True)
    else:
        if st.session_state["job_mode"] == "Supply & Install":
            unit_price = st.number_input(
                "Supply & Install price ($/m²) (default from sheet)",
                min_value=0.0,
                value=float(st.session_state.get("core_price_supply", unit_price_default)),
                step=1.0,
                key="core_price_supply",
            )
            total = chargeable_area * unit_price
            line_items.append(line_item(product_label, f"{chargeable_area:.2f} m²", unit_price, total))
            subtotal += total
        else:
            unit_price = st.number_input(
                "Installation price ($/m²) (default from sheet)",
                min_value=0.0,
                value=float(st.session_state.get("core_price_install", unit_price_default)),
                step=1.0,
                key="core_price_install",
            )
            total = total_area * unit_price
            line_items.append(line_item(install_label, f"{total_area:.2f} m²", unit_price, total))
            subtotal += total

    st.divider()

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
        elif unit_norm in ("lm", "linemeter", "linearmeter", "linearmetre", "linemetre"):
            step_qty = 0.5
            unit_display = "lm"
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

    st.markdown("### Removal & Disposal")
    if removal_df.empty:
        st.caption("No rows in sheet tab 'removal'.")
    else:
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
                    label=f"{nm}",
                    unit="m²",
                    qty_default=float(total_area),
                    price_default=float(pr),
                )

    if addons_df.empty:
        st.caption("No rows in sheet tab 'addons'.")
    else:
        colmap = {norm_colname(c): c for c in addons_df.columns}
        id_col = colmap.get("id")
        cat_col = colmap.get("category")
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

    st.markdown("### Skirting")
    if skirting_df.empty:
        st.caption("No rows in sheet tab 'skirting'.")
    else:
        sid_col = colpick(skirting_df, "id")
        h_col = colpick(skirting_df, "height_mm", "height")
        price_col = colpick(skirting_df, "price_per_lm", "price")

        if not (sid_col and price_col):
            st.error("Skirting sheet needs columns: id, price_per_lm (or price).")
        else:
            skirting_df["_sid"] = skirting_df[sid_col].astype(str)
            options = skirting_df["_sid"].tolist()

            def _sk_fmt(sid: str) -> str:
                row = skirting_df[skirting_df["_sid"] == str(sid)]
                if row.empty:
                    return str(sid)
                rr = row.iloc[0]
                if h_col:
                    return f"{int(safe_float(rr.get(h_col, 0), 0))}mm"
                return str(sid)

            st.session_state.setdefault("skirting_id", options[0] if options else "")
            if options:
                st.selectbox("Skirting height", options=options, format_func=_sk_fmt, key="skirting_id")

                row = skirting_df[skirting_df["_sid"] == str(st.session_state.get("skirting_id", ""))]
                if not row.empty:
                    rr = row.iloc[0]
                    price = safe_float(rr.get(price_col, 0.0), 0.0)
                    label = f"Skirting — {_sk_fmt(st.session_state['skirting_id'])}"
                    default_lm = max(0.0, float(chargeable_area))

                    subtotal += addon_row(
                        key=f"sk_{st.session_state['skirting_id']}",
                        label=label,
                        unit="lm",
                        qty_default=default_lm,
                        price_default=float(price),
                    )
else:
    st.info("Viewing a saved quote. Pricing inputs are disabled to prevent overwriting saved items.")
    line_items = st.session_state.get("loaded_line_items", []) or []
    subtotal = sum(float(li.get("total", 0) or 0) for li in line_items)


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
# CLIENT DETAILS
# =========================
st.divider()
st.subheader("Client Details")
c1, c2 = st.columns(2)
with c1:
    st.text_input("Client name", key="client_name")
    st.text_input("Client phone", key="client_phone")
with c2:
    st.text_input("Client email", key="client_email")
    st.text_input("Site address", key="site_address")


# =========================
# TERMS
# =========================
st.divider()
st.subheader("Terms")
terms_default = [
    "Quote valid for 30 days.",
    "A 10% deposit is required to secure materials and confirm the installation schedule.",
    "A further 50% payment is due upon delivery of materials and commencement of works.",
    "The remaining balance is payable in full immediately upon completion of the project.",
]
terms_text = st.text_area("Terms (one per line)", "\n".join(terms_default), height=140)
terms = [t.strip() for t in terms_text.splitlines() if t.strip()]


# =========================
# PAYLOAD
# =========================
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

st.session_state.setdefault("quote_saved", False)

def handle_save():
    if not st.session_state.get("quote_saved", False):
        qid = save_quote_to_sheet(payload)
        st.session_state["quote_saved"] = True
        st.session_state["last_quote_id"] = qid
        st.success(f"Quote saved: {qid}")


# =========================
# SAVE & GENERATE
# =========================
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


# =========================
# MOBILE FRIENDLY TEXT
# =========================
import html  # add at top of file

# ...

st.subheader("Mobile-friendly quote (ex GST)")
mobile_text = build_mobile_quote_text(payload)
st.text_area("", value=mobile_text, height=260)

safe_text = html.escape(mobile_text)

components.html(
    f"""
    <div style="display:flex; gap:12px; align-items:center; font-family: sans-serif;">
      <button id="copyBtn"
              style="padding:10px 14px;border-radius:10px;border:1px solid #ddd;background:#fff;cursor:pointer;font-weight:600;">
        📋 Copy
      </button>
      <span id="copyStatus" style="font-size: 14px; color: #444;"></span>
    </div>

    <textarea id="quoteText" style="position:absolute; left:-9999px; top:-9999px;">{safe_text}</textarea>

    <script>
      const btn = document.getElementById("copyBtn");
      const status = document.getElementById("copyStatus");
      const ta = document.getElementById("quoteText");

      async function doCopy() {{
        const text = ta.value;

        try {{
          await navigator.clipboard.writeText(text);
          status.textContent = "Copied ✅";
          setTimeout(() => status.textContent = "", 1200);
          return;
        }} catch (e) {{}}

        try {{
          ta.focus();
          ta.select();
          const ok = document.execCommand("copy");
          status.textContent = ok ? "Copied ✅" : "Copy blocked (select + Cmd/Ctrl+C)";
          setTimeout(() => status.textContent = "", 1800);
        }} catch (e) {{
          status.textContent = "Copy blocked (select + Cmd/Ctrl+C)";
          setTimeout(() => status.textContent = "", 1800);
        }}
      }}

      btn.addEventListener("click", doCopy);
    </script>
    """,
    height=60,
)
