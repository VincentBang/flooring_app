import io
from typing import List

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# =========================
# GOOGLE SHEET CONFIG
# =========================

SHEET_ID = "10G98m8XHdySRTMWjbAUlQCZMH1NXCD6uca82xN0p4fY"


@st.cache_data(ttl=300)
def load_sheet(tab_name: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={tab_name}"
    df = pd.read_csv(url)
    # Be defensive: some tabs might not have active column while testing
    if "active" in df.columns:
        df = df[df["active"] == True]
    return df


# =========================
# COMPANY DETAILS (edit these)
# =========================
COMPANY = {
    "name": "Oz Timber Floor Pty Ltd",
    "abn": "ABN: 84 168 475 358",
    "phone": "Phone: 0435 496 975",
    "email": "Email: info@oztimberfloor.com.au",
    "website": "Website: oztimberfloor.com.au",
    "address": "Address line (optional)",
}

# Put your logo file in the SAME folder as app.py (recommended)
LOGO_PATH = "logo.png"

# Brand colors (ReportLab wants 0-1 floats)
BRAND = {
    "header_rgb": (0.10, 0.10, 0.10),
    "accent_rgb": (0.18, 0.42, 0.78),
    "light_gray_rgb": (0.94, 0.94, 0.94),
    "mid_gray_rgb": (0.75, 0.75, 0.75),
}

st.caption(f"{COMPANY['name']} • {COMPANY['abn']} • {COMPANY['phone']} • {COMPANY['email']}")

# =========================
# FALLBACK DATA (kept for safety)
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

DEFAULT_WASTAGE_PCT = 10.0
DEFAULT_FURNITURE_PER_ROOM = 50.0
GST_RATE = 0.10


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
    """Line item structure used by UI and PDF."""
    return {
        "label": str(label),
        "qty_str": str(qty_str),
        "unit_price": float(unit_price),
        "total": float(total),
    }


def money(x: float) -> str:
    return f"${float(x):,.2f}"


def safe_pick_id(df: pd.DataFrame, current_id: str, id_col: str = "id") -> str:
    if df is None or df.empty or id_col not in df.columns:
        return str(current_id or "")
    ids = df[id_col].astype(str).tolist()
    if not ids:
        return ""
    return str(current_id) if str(current_id) in ids else ids[0]

# =========================
# Mobile GENERATION
# =========================

def build_mobile_quote_text(payload: dict) -> str:
    """
    Mobile-friendly quote format (ex GST only).
    PDF is unchanged.

    Output example:
    Supply & install — Hurfords Blackbutt 14mm
    46.2 m² x $125 = $5,775

    Total: $5,775
    """
    def money0(x: float) -> str:
        return f"${float(x):,.0f}"

    def qty_pretty(qty_str: str) -> tuple[str, str]:
        """
        Convert '46.20 m²' -> ('46.2', 'm²')
        Convert '2 room(s)' -> ('2', 'room(s)')
        Convert '1.00 each' -> ('1', 'each')
        If parsing fails, return raw string as qty with blank unit.
        """
        s = (qty_str or "").strip()
        if not s:
            return ("", "")
        parts = s.split()
        if len(parts) == 1:
            return (parts[0], "")
        qty_raw = parts[0]
        unit = " ".join(parts[1:])

        # Try format numeric quantity nicely
        try:
            q = float(qty_raw)
            # show 0 decimals if integer-like, else 1 decimal
            if abs(q - round(q)) < 1e-9:
                qty_fmt = f"{int(round(q))}"
            else:
                qty_fmt = f"{q:.1f}"
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
        lines.append("")  # blank line between items

    subtotal_ex_gst = float(payload.get("subtotal_ex_gst", 0.0))
    lines.append(f"Total: {money0(subtotal_ex_gst)}")

    return "\n".join(lines).strip()

# =========================
# PDF GENERATION
# =========================
def build_quote_pdf(payload: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    def _rgb(t):
        return colors.Color(t[0], t[1], t[2])

    def money_pdf(x: float) -> str:
        return f"${float(x):,.2f}"

    def safe_float_pdf(x, default=0.0) -> float:
        try:
            return float(x)
        except Exception:
            return float(default)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    left = 42
    right = width - 42
    table_w = right - left

    header_h = 18
    row_h = 16

    def draw_company_header() -> float:
        nonlocal c, width, height, left, right

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
        nonlocal c, width, height, left, right, table_w
        c.showPage()
        c.setPageSize(A4)
        width, height = A4
        left = 42
        right = width - 42
        table_w = right - left

    # =========================
    # HEADER
    # =========================
    y = draw_company_header()

    # =========================
    # TITLE
    # =========================
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, "Quotation")
    y -= 10
    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 18

    # =========================
    # CLIENT DETAILS
    # =========================
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Client Details")
    y -= 14

    c.setFont("Helvetica", 10)
    client_name = payload.get("client_name", "")
    client_phone = payload.get("client_phone", "")
    client_email = payload.get("client_email", "")
    site_address = payload.get("site_address", "")
    job_mode = payload.get("job_mode", "")
    

    c.drawString(left, y, f"Client: {client_name}")
    y -= 14
    c.drawString(left, y, f"Phone: {client_phone}")
    y -= 14
    c.drawString(left, y, f"Email: {client_email}")
    y -= 14
    c.drawString(left, y, f"Site: {site_address}")
    y -= 14
    c.drawString(left, y, f"Mode: {job_mode}")
    y -= 18

    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.6)
    c.line(left, y, right, y)
    y -= 18

    # ==========================================================
    # MEASUREMENTS REMOVED COMPLETELY (as requested)
    # ==========================================================

    # =========================
    # PRICING TABLE
    # =========================
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Scope & Pricing (ex GST)")
    y -= 14

    # Header background
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
    items = payload.get("line_items", [])

    for idx, li in enumerate(items):
        # Page break
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
        unit_price = safe_float_pdf(li.get("unit_price", 0.0), 0.0)
        total = safe_float_pdf(li.get("total", 0.0), 0.0)

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

    subtotal = safe_float_pdf(payload.get("subtotal_ex_gst", 0.0), 0.0)
    gst = safe_float_pdf(payload.get("gst", 0.0), 0.0)
    total_inc = safe_float_pdf(payload.get("total_inc_gst", 0.0), 0.0)

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

    for t in payload.get("terms", []):
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
# UI
# =========================
st.set_page_config(page_title="Flooring Quote Prototype", layout="wide")
st.title("📱 Flooring Quote Prototype (V1)")

# ---- Session defaults ----
DEFAULTS = {
    "step": 1,
    "client_name": "",
    "client_phone": "",
    "client_email": "",
    "site_address": "",
    "job_mode": "Supply & Install",
    "quote_type": "Retail",
    "wastage_pct": DEFAULT_WASTAGE_PCT,
    "product_id": PRODUCTS[0]["id"],
    "install_id": INSTALL_ONLY[0]["id"],
    "scope_removal": False,
    "scope_furniture": False,
    "scope_skirting": False,
    "removal_selected": [],
    "furniture_rate": DEFAULT_FURNITURE_PER_ROOM,
    "skirting_id": SKIRTING[0]["id"],
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

if "rooms" not in st.session_state or not st.session_state.rooms:
    st.session_state.rooms = [{"length": 3.0, "width": 4.0}]

# Load sheets
products_df = load_sheet("products")
install_df = load_sheet("install_only")
removal_df = load_sheet("removal")
skirting_df = load_sheet("skirting")
addons_df = load_sheet("addons")

# ---------- STEP 1 ----------
if st.session_state.step == 1:
    st.subheader("Step 1 — Job Setup")

    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Client name", key="client_name")
        st.text_input("Client phone", key="client_phone")
    with col2:
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

    # Core selection
    if st.session_state.job_mode == "Supply & Install":
        # Prefer Google Sheet products if available, else fallback to in-code list
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

    if st.button("Next → Measurements & Quote"):
        st.session_state.step = 2
        st.rerun()

# ---------- STEP 2 ----------
if st.session_state.step == 2:

    # ---------- Measurements UI (compact rows) ----------
    st.subheader("Measurements")
    st.caption("Used for pricing only. Measurements will NOT be shown in the PDF.")
    
    # Ensure at least 1 room exists (critical)
    if "rooms" not in st.session_state or not st.session_state.rooms:
        st.session_state.rooms = [{"length": 3.0, "width": 4.0}]
    
    def add_room():
        st.session_state.rooms.append({"length": 0.0, "width": 0.0})
    
    def remove_room(idx: int):
        if len(st.session_state.rooms) > 1:
            st.session_state.rooms.pop(idx)
    
    # Column headers (one heading for all rooms)
    h1, h2, h3, h4 = st.columns([1, 1, 1, 0.6])
    h1.markdown("**Length (m)**")
    h2.markdown("**Width (m)**")
    h3.markdown("**Area (m²)**")
    h4.markdown("")
    
    for i, room in enumerate(st.session_state.rooms):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 0.6])
    
        with c1:
            room["length"] = st.number_input(
                f"Length (m) {i}",
                min_value=0.0,
                value=float(room.get("length", 0.0)),
                step=0.1,
                key=f"len_{i}",
                label_visibility="collapsed",
            )
    
        with c2:
            room["width"] = st.number_input(
                f"Width (m) {i}",
                min_value=0.0,
                value=float(room.get("width", 0.0)),
                step=0.1,
                key=f"wid_{i}",
                label_visibility="collapsed",
            )
    
        with c3:
            area = float(room["length"]) * float(room["width"])
            st.write(f"{area:.2f}")  # more reliable than metric in tight rows
    
        with c4:
            if len(st.session_state.rooms) > 1:
                if st.button("✕", key=f"remove_{i}"):
                    remove_room(i)
                    st.rerun()
    
    # Add button OUTSIDE the loop so it always shows
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
    st.subheader("Step 4 — Quote Items (selected scope only)")

    line_items: List[dict] = []
    subtotal = 0.0

    # =========================
    # CORE MODE
    # =========================
    if st.session_state.job_mode == "Supply & Install":
        st.markdown("#### Supply & Install")

        # Prefer sheet-based product row if available
        unit_price_default = 0.0
        product_label = "Supply & install"

        if not products_df.empty and "id" in products_df.columns:
            pid = str(st.session_state.get("product_id", ""))
            match = products_df[products_df["id"].astype(str) == pid]
            product_row = match.iloc[0] if not match.empty else products_df.iloc[0]

            # Use sell_price column if present; else try sell_per_m2; else 0
            if "sell_price" in products_df.columns:
                unit_price_default = safe_float(product_row.get("sell_price", 0.0), 0.0)
            elif "sell_per_m2" in products_df.columns:
                unit_price_default = safe_float(product_row.get("sell_per_m2", 0.0), 0.0)

            brand = str(product_row.get("brand", "")).strip()
            name = str(product_row.get("name", "")).strip()
            product_label = f"Supply & install — {brand} {name}".strip()
        else:
            # fallback in-code list
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
        ins = find_by_id(INSTALL_ONLY, st.session_state.install_id)

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
    # REMOVAL
    # =========================
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

    # =========================
    # FURNITURE
    # =========================
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

    # =========================
    # SKIRTING
    # =========================
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

    # =========================
    # ADDITIONAL ITEMS (from Google Sheet)
    # =========================
    st.markdown("#### Additional Items")

    if addons_df is not None and not addons_df.empty:
        # expected columns: id, label, unit, price
        for _, row in addons_df.iterrows():
            addon_id = str(row.get("id", ""))
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

    st.divider()
    gst = subtotal * GST_RATE
    total_inc = subtotal + gst
    t1, t2, t3 = st.columns(3)
    t1.metric("Subtotal (ex GST)", f"${subtotal:,.0f}")
    t2.metric("GST", f"${gst:,.0f}")
    t3.metric("Total (inc GST)", f"${total_inc:,.0f}")

    st.divider()
    st.subheader("Step 5 — Generate Quote PDF")

    st.subheader("Payment & Terms")

    terms_default = [
        "Quote valid for 30 days.",
        "",
        "Payment Terms:",
        "• A 10% deposit is required to secure the stock and confirm the scheduled installation date.",
        "• 60% is payable upon delivery of materials and commencement of works on site.",
        "• The remaining 30% balance is due immediately upon completion of the installation.",
        "",
    ]
    
    terms_text = st.text_area(
        "Terms (one per line — editable)",
        "\n".join(terms_default),
        height=180,
    )
    
    terms = [t.strip() for t in terms_text.splitlines() if t.strip()]

    # Rooms kept for internal payload only (PDF will NOT display them)
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

    payload = {
        "client_name": (st.session_state.client_name or "").strip(),
        "client_phone": (st.session_state.client_phone or "").strip(),
        "client_email": (st.session_state.client_email or "").strip(),
        "site_address": (st.session_state.site_address or "").strip(),
        "job_mode": st.session_state.job_mode,
        "rooms": rooms_out,  # kept but not displayed in PDF
        "total_area": total_area,  # kept but not displayed in PDF
        "wastage_pct": wastage_pct,  # kept but not displayed in PDF
        "chargeable_area": chargeable_area,  # kept but not displayed in PDF
        "line_items": line_items,  # now includes unit_price
        "subtotal_ex_gst": subtotal,
        "gst": gst,
        "total_inc_gst": total_inc,
        "terms": terms,
    }

    
    colB1, colB2 = st.columns(2)

    with colB1:
        if st.button("← Back"):
            st.session_state.step = 1
            st.rerun()
    
    with colB2:
        pdf_bytes = build_quote_pdf(payload)
        st.download_button(
            "Download Quote.pdf",
            data=pdf_bytes,
            file_name="Quote.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    
    st.divider()
    st.subheader("Mobile-friendly quote (copy/paste)")
    
    mobile_text = build_mobile_quote_text(payload)
    st.text_area(
        "Copy this and paste into SMS/WhatsApp/email (ex GST)",
        value=mobile_text,
        height=260,
    )
    
    st.download_button(
        "Download Quote.txt",
        data=mobile_text.encode("utf-8"),
        file_name="Quote.txt",
        mime="text/plain",
        use_container_width=True,
    )
