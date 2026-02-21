import io
from typing import List

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

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
# Example: flooring_app/logo.png
LOGO_PATH = "logo.png"

# Brand colors
BRAND = {
    "header_rgb": (0.10, 0.10, 0.10),   # dark charcoal
    "accent_rgb": (0.18, 0.42, 0.78),   # blue accent
    "light_gray_rgb": (0.94, 0.94, 0.94),
    "mid_gray_rgb": (0.75, 0.75, 0.75),
}

st.caption(f"{COMPANY['name']} • {COMPANY['abn']} •{COMPANY['phone']} • {COMPANY['email']}")

# =========================
# DATA (V1: in-code; later load CSV/Google Sheet)
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
def find_by_id(items: List[dict], item_id: str) -> dict:
    for it in items:
        if it["id"] == item_id:
            return it
    raise KeyError(item_id)


def line_item(label: str, qty_str: str, total: float) -> dict:
    return {"label": label, "qty_str": qty_str, "total": float(total)}


def money(x: float) -> str:
    return f"${x:,.2f}"


# =========================
# PDF GENERATION
# =========================
def build_quote_pdf(payload: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader

    def _rgb(t):
        return colors.Color(t[0], t[1], t[2])

    def _draw_kv(c, x_label, x_value, y, k, v):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_label, y, f"{k}:")
        c.setFont("Helvetica", 10)
        c.drawString(x_value, y, v if v else "")
        return y - 14

    def _hr(c, x1, x2, y, rgb):
        c.setStrokeColor(_rgb(rgb))
        c.setLineWidth(1)
        c.line(x1, y, x2, y)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    left = 42
    right = width - 42
    content_top = height - 42
    y = content_top

    # ===== Header Bar =====
    y = height - 48
    
    # Company Name
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.white)
    c.drawString(left, y, COMPANY["name"])
    y -= 16
    
    # Company Details (black text)
    c.setFont("Helvetica", 9)
    c.drawString(left, y, COMPANY["abn"])
    y -= 12
    c.drawString(left, y, f"{COMPANY['phone']}  |  {COMPANY['email']}")
    y -= 12
    c.drawString(left, y, COMPANY.get("website", ""))
    y -= 18
    
    # Thin separator line
    c.setStrokeColor(_rgb(BRAND["mid_gray_rgb"]))
    c.setLineWidth(0.8)
    c.line(left, y, right, y)
    y -= 22

    # Logo (optional)
    logo_w, logo_h = 120, 42
    logo_x = left
    logo_y = height - 42 - logo_h  # top margin = 42
    
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
    except Exception:
        pass

    # Company details (right side, white)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(right, height - 22, COMPANY["name"])
    c.setFont("Helvetica", 9)
    c.drawRightString(right, height - 38, COMPANY["abn"])
    c.drawRightString(right, height - 52, f"{COMPANY['phone']}  |  {COMPANY['email']}")
    c.drawRightString(right, height - 66, COMPANY.get("website", ""))

    # ===== Title =====
    y = height - header_h - 26
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, "Quotation")
    y -= 8
    _hr(c, left, right, y, BRAND["mid_gray_rgb"])
    y -= 18

    # ===== Client Block =====
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Client Details")
    y -= 14

    x_label = left
    x_value = left + 78

    y = _draw_kv(c, x_label, x_value, y, "Client", payload.get("client_name", ""))
    y = _draw_kv(c, x_label, x_value, y, "Phone", payload.get("client_phone", ""))
    y = _draw_kv(c, x_label, x_value, y, "Email", payload.get("client_email", ""))
    y = _draw_kv(c, x_label, x_value, y, "Site", payload.get("site_address", ""))
    y = _draw_kv(c, x_label, x_value, y, "Mode", payload.get("job_mode", ""))

    y -= 6
    _hr(c, left, right, y, BRAND["mid_gray_rgb"])
    y -= 18

    # ===== Measurements Table =====
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Measurements")
    y -= 12

    # Table header background
    table_w = right - left
    header_row_h = 18
    row_h = 16

    c.setFillColor(_rgb(BRAND["light_gray_rgb"]))
    c.rect(left, y - header_row_h + 4, table_w, header_row_h, stroke=0, fill=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)

    col_room = left + 6
    col_l = left + 250
    col_w = left + 315
    col_a = left + 390

    c.drawString(col_room, y, "Room")
    c.drawRightString(col_l, y, "L (m)")
    c.drawRightString(col_w, y, "W (m)")
    c.drawRightString(col_a, y, "Area (m²)")
    y -= row_h

    c.setFont("Helvetica", 9)
    rooms = payload.get("rooms", [])
    for idx, r in enumerate(rooms):
        # alternate row shading
        if idx % 2 == 0:
            c.setFillColor(colors.white)
        else:
            c.setFillColor(_rgb((0.98, 0.98, 0.98)))
        c.rect(left, y - 12, table_w, row_h, stroke=0, fill=1)

        c.setFillColor(colors.black)
        c.drawString(col_room, y, str(r.get("name", "")))
        c.drawRightString(col_l, y, f"{float(r.get('length', 0.0)):.2f}")
        c.drawRightString(col_w, y, f"{float(r.get('width', 0.0)):.2f}")
        c.drawRightString(col_a, y, f"{float(r.get('area', 0.0)):.2f}")
        y -= row_h

        if y < 210:
            c.showPage()
            y = height - 60

    y -= 6
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Total area: {payload.get('total_area', 0.0):.2f} m²")
    y -= 14
    c.drawString(left, y, f"Wastage: {payload.get('wastage_pct', 0.0):.1f}%")
    y -= 14
    c.drawString(left, y, f"Chargeable area: {payload.get('chargeable_area', 0.0):.2f} m²")
    y -= 16

    _hr(c, left, right, y, BRAND["mid_gray_rgb"])
    y -= 18

    # ===== Pricing Table =====
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Scope & Pricing (ex GST)")
    y -= 12

    c.setFillColor(_rgb(BRAND["light_gray_rgb"]))
    c.rect(left, y - header_row_h + 4, table_w, header_row_h, stroke=0, fill=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)

    col_item = left + 6
    col_qty = right - 150
    col_total = right - 6

    c.drawString(col_item, y, "Item")
    c.drawRightString(col_qty, y, "Qty")
    c.drawRightString(col_total, y, "Total")
    y -= row_h

    c.setFont("Helvetica", 9)
    items = payload.get("line_items", [])
    for idx, li in enumerate(items):
        if idx % 2 == 0:
            c.setFillColor(colors.white)
        else:
            c.setFillColor(_rgb((0.98, 0.98, 0.98)))
        c.rect(left, y - 12, table_w, row_h, stroke=0, fill=1)

        c.setFillColor(colors.black)
        label = str(li.get("label", ""))
        qty_str = str(li.get("qty_str", ""))
        total_val = float(li.get("total", 0.0))

        # simple wrap for long item names (single wrap line)
        if len(label) > 60:
            label = label[:57] + "..."

        c.drawString(col_item, y, label)
        c.drawRightString(col_qty, y, qty_str)
        c.drawRightString(col_total, y, money(total_val))
        y -= row_h

        if y < 180:
            c.showPage()
            y = height - 60

    y -= 10

    # ===== Totals box (right aligned) =====
    box_w = 220
    box_h = 70
    box_x = right - box_w
    box_y = y - box_h + 10

    c.setFillColor(_rgb((0.97, 0.97, 0.97)))
    c.rect(box_x, box_y, box_w, box_h, stroke=1, fill=1)

    subtotal = float(payload.get("subtotal_ex_gst", 0.0))
    gst = float(payload.get("gst", 0.0))
    total_inc = float(payload.get("total_inc_gst", 0.0))

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(box_x + 10, box_y + 48, "Subtotal (ex GST)")
    c.drawRightString(box_x + box_w - 10, box_y + 48, money(subtotal))

    c.drawString(box_x + 10, box_y + 30, "GST")
    c.drawRightString(box_x + box_w - 10, box_y + 30, money(gst))

    c.setFont("Helvetica-Bold", 11)
    c.drawString(box_x + 10, box_y + 12, "Total (inc GST)")
    c.drawRightString(box_x + box_w - 10, box_y + 12, money(total_inc))

    y = box_y - 18
    _hr(c, left, right, y, BRAND["mid_gray_rgb"])
    y -= 16

    # ===== Terms =====
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Terms")
    y -= 14

    c.setFont("Helvetica", 9)
    for t in payload.get("terms", []):
        c.drawString(left, y, f"• {t}")
        y -= 12
        if y < 60:
            c.showPage()
            y = height - 60

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()

# =========================
# UI
# =========================
st.set_page_config(page_title="Flooring Quote Prototype", layout="centered")
st.title("📱 Flooring Quote Prototype (V1)")

# ---- Session defaults (THIS fixes your blank PDF issue) ----
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

    # IMPORTANT: DO NOT assign st.session_state.job_mode manually
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

    # ✅ Next button is ALWAYS enabled (no required fields)
    if st.button("Next → Measurements & Quote"):
        st.session_state.step = 2
        st.rerun()


# ---------- STEP 2 ----------
if st.session_state.step == 2:
    st.subheader("Step 3 — Measurements (mobile friendly)")

    # Optional: edit client details here too (prevents blank PDFs after refresh)
    with st.expander("Client details (optional)", expanded=False):
        st.text_input("Client name", key="client_name")
        st.text_input("Client phone", key="client_phone")
        st.text_input("Client email", key="client_email")
        st.text_input("Site address", key="site_address")

    def add_room():
        st.session_state.rooms.append({"length": 0.0, "width": 0.0})

    def remove_room(idx: int):
        if len(st.session_state.rooms) > 1:
            st.session_state.rooms.pop(idx)

    for i, room in enumerate(st.session_state.rooms):
        st.markdown(f"### Room {i+1}")
        col1, col2, col3 = st.columns([1, 1, 1])

        with col1:
            room["length"] = st.number_input(
                "Length (m)", min_value=0.0, value=float(room.get("length", 0.0)), step=0.1, key=f"len_{i}"
            )
        with col2:
            room["width"] = st.number_input(
                "Width (m)", min_value=0.0, value=float(room.get("width", 0.0)), step=0.1, key=f"wid_{i}"
            )
        with col3:
            st.metric("Area (m²)", f"{float(room['length']) * float(room['width']):.2f}")

        if len(st.session_state.rooms) > 1:
            if st.button("Remove", key=f"remove_room_{i}"):
                remove_room(i)
                st.rerun()

    st.button("➕ Add Room", on_click=add_room)

    total_area = sum(float(r["length"]) * float(r["width"]) for r in st.session_state.rooms)
    wastage_pct = float(st.session_state.wastage_pct)
    chargeable_area = total_area * (1.0 + wastage_pct / 100.0)

    st.markdown("---")
    a, b, c = st.columns(3)
    a.metric("Total area (m²)", f"{total_area:.2f}")
    b.metric("Wastage (%)", f"{wastage_pct:.1f}")
    c.metric("Chargeable area (m²)", f"{chargeable_area:.2f}")

    st.divider()
    st.subheader("Step 4 — Quote Items (selected scope only)")

    line_items: List[dict] = []
    subtotal = 0.0

    # Core mode
    if st.session_state.job_mode == "Supply & Install":
        p = find_by_id(PRODUCTS, st.session_state.product_id)
        st.markdown("#### Supply & Install")
        unit_price = st.number_input(
            "Supply & Install price ($/m²)",
            min_value=0.0,
            value=float(p["sell_per_m2"]),
            step=1.0,
            key="supply_install_price_override",
        )
        total = chargeable_area * unit_price
        line_items.append(line_item(f"Supply & install — {p['brand']} {p['name']}", f"{chargeable_area:.2f} m²", total))
        subtotal += total
    else:
        ins = find_by_id(INSTALL_ONLY, st.session_state.install_id)
        st.markdown("#### Installation Only")
        unit_price = st.number_input(
            "Installation price ($/m²)",
            min_value=0.0,
            value=float(ins["install_per_m2"]),
            step=1.0,
            key="install_only_price_override",
        )
        total = total_area * unit_price
        line_items.append(line_item(ins["name"], f"{total_area:.2f} m²", total))
        subtotal += total

    # Removal
    if st.session_state.scope_removal:
        st.markdown("#### Floor Removal & Disposal")
        for rid in st.session_state.removal_selected:
            r = find_by_id(REMOVAL_TYPES, rid)
            rate = st.number_input(
                f"{r['name']} removal ($/m²)",
                min_value=0.0,
                value=float(r["remove_per_m2"]),
                step=1.0,
                key=f"removal_rate_{rid}",
            )
            total = total_area * rate
            line_items.append(line_item(f"Removal & disposal — {r['name']}", f"{total_area:.2f} m²", total))
            subtotal += total

    # Furniture
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
        rate = st.number_input(
            "Furniture handling rate ($ per room)",
            min_value=0.0,
            value=float(st.session_state.furniture_rate),
            step=5.0,
            key="furniture_rate_override",
        )
        total = rooms_count * rate
        line_items.append(line_item("Furniture handling", f"{rooms_count} room(s)", total))
        subtotal += total

    # Skirting
    if st.session_state.scope_skirting:
        st.markdown("#### Skirting")
        sk = find_by_id(SKIRTING, st.session_state.skirting_id)
        price_lm = st.number_input(
            "Skirting price ($/lm)",
            min_value=0.0,
            value=float(sk["price_per_lm"]),
            step=1.0,
            key="skirting_price_override",
        )
        lm = st.number_input("Total skirting length (lm)", min_value=0.0, value=0.0, step=1.0, key="skirting_lm")
        total = lm * price_lm
        line_items.append(line_item(f"Skirting — {sk['height_mm']}mm", f"{lm:.1f} lm", total))
        subtotal += total

    st.divider()
    gst = subtotal * GST_RATE
    total_inc = subtotal + gst
    t1, t2, t3 = st.columns(3)
    t1.metric("Subtotal (ex GST)", f"${subtotal:,.0f}")
    t2.metric("GST", f"${gst:,.0f}")
    t3.metric("Total (inc GST)", f"${total_inc:,.0f}")

    st.divider()
    st.subheader("Step 5 — Generate Quote PDF")

    terms_default = [
        "Quote valid for 7 days.",
        "Variations may apply if site conditions differ from inspection.",
        "Progress payments may apply for larger jobs.",
    ]
    terms_text = st.text_area("Terms (one per line)", "\n".join(terms_default), height=120)
    terms = [t.strip() for t in terms_text.splitlines() if t.strip()]

    rooms_out = []
    for i, r in enumerate(st.session_state.rooms):
        rooms_out.append(
            {"name": f"Room {i+1}", "length": float(r["length"]), "width": float(r["width"]), "area": float(r["length"]) * float(r["width"])}
        )

    payload = {
        # NO "—" fallbacks. Blank is allowed.
        "client_name": (st.session_state.client_name or "").strip(),
        "client_phone": (st.session_state.client_phone or "").strip(),
        "client_email": (st.session_state.client_email or "").strip(),
        "site_address": (st.session_state.site_address or "").strip(),
        "job_mode": st.session_state.job_mode,
        "rooms": rooms_out,
        "total_area": total_area,
        "wastage_pct": wastage_pct,
        "chargeable_area": chargeable_area,
        "line_items": line_items,
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
        if st.button("Generate PDF"):
            pdf_bytes = build_quote_pdf(payload)
            st.success("PDF generated.")
            st.download_button(
                "Download Quote.pdf",
                data=pdf_bytes,
                file_name="Quote.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
