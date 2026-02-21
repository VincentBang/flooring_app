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

st.caption(f"{COMPANY['name']} • {COMPANY['abn']} •{COMPANY['phone']} • {COMPANY['email']}")

# =========================
# DATA (V1: in-code; later load CSV/Google Sheet)
# =========================

# Supply & Install products (sell price preset)
PRODUCTS = [
    {"id": "p1", "brand": "BrandA", "name": "Engineered Oak 14mm", "type": "Engineered", "sell_per_m2": 120.0},
    {"id": "p2", "brand": "BrandB", "name": "Hybrid 6.5mm", "type": "Hybrid", "sell_per_m2": 75.0},
    {"id": "p3", "brand": "BrandC", "name": "Solid Timber 19mm", "type": "Solid", "sell_per_m2": 165.0},
]

# Installation-only types (preset install price)
INSTALL_ONLY = [
    {"id": "i1", "name": "Installation only – Engineered timber", "install_per_m2": 55.0},
    {"id": "i2", "name": "Installation only – Hybrid", "install_per_m2": 38.0},
    {"id": "i3", "name": "Installation only – Solid timber", "install_per_m2": 70.0},
]

# Removal types (preset $/m2)
REMOVAL_TYPES = [
    {"id": "r1", "name": "Carpet", "remove_per_m2": 6.0},
    {"id": "r2", "name": "Floating floor", "remove_per_m2": 18.0},
    {"id": "r3", "name": "Glued floor", "remove_per_m2": 28.0},
    {"id": "r4", "name": "Timber", "remove_per_m2": 35.0},
]

# Skirting options (preset $/lm)
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
    from reportlab.lib.utils import ImageReader
    from reportlab.lib import colors

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    left = 42
    right = width - 42

    # ===== Header bar =====
    header_h = 70
    c.setFillColorRGB(0.10, 0.10, 0.10)  # dark charcoal
    c.rect(0, height - header_h, width, header_h, stroke=0, fill=1)

    # Logo (optional)
    logo_w, logo_h = 120, 40
    logo_x = left
    logo_y = height - header_h + (header_h - logo_h) / 2

    try:
        logo = ImageReader(LOGO_PATH)
        c.drawImage(logo, logo_x, logo_y, width=logo_w, height=logo_h, mask="auto")
    except Exception:
        # If logo missing, just skip (no crash)
        pass

    # Company text (right)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(right, height - 22, COMPANY["name"])
    c.setFont("Helvetica", 9)
    c.drawRightString(right, height - 36, COMPANY["abn"])
    c.drawRightString(right, height - 48, COMPANY["phone"])
    c.drawRightString(right, height - 60, COMPANY["email"])

    # ===== Document title =====
    y = height - header_h - 25
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(left, y, "QUOTATION")
    y -= 18

    # ===== Client block =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Client details")
    y -= 12
    c.setFont("Helvetica", 10)

    client_lines = [
        ("Client", payload["client_name"]),
        ("Phone", payload["client_phone"]),
        ("Email", payload["client_email"]),
        ("Site", payload["site_address"]),
        ("Mode", payload["job_mode"]),
    ]

    label_x = left
    value_x = left + 70

    for k, v in client_lines:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(label_x, y, f"{k}:")
        c.setFont("Helvetica", 10)
        c.drawString(value_x, y, str(v))
        y -= 14

    y -= 8

    # ===== Measurements =====
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Measurements")
    y -= 14

    # table header
    c.setLineWidth(0.5)
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.line(left, y, right, y)
    y -= 14

    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Room")
    c.drawRightString(left + 250, y, "L (m)")
    c.drawRightString(left + 310, y, "W (m)")
    c.drawRightString(left + 380, y, "Area (m²)")
    y -= 10

    c.setFont("Helvetica", 9)
    for r in payload["rooms"]:
        c.drawString(left, y, r["name"])
        c.drawRightString(left + 250, y, f"{r['length']:.2f}")
        c.drawRightString(left + 310, y, f"{r['width']:.2f}")
        c.drawRightString(left + 380, y, f"{r['area']:.2f}")
        y -= 12
        if y < 180:
            c.showPage()
            y = height - 60
            c.setFont("Helvetica", 9)

    y -= 4
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Total area: {payload['total_area']:.2f} m²")
    y -= 14
    c.drawString(left, y, f"Wastage: {payload['wastage_pct']:.1f}%")
    y -= 14
    c.drawString(left, y, f"Chargeable area: {payload['chargeable_area']:.2f} m²")
    y -= 18

    # ===== Pricing =====
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Scope & Pricing (ex GST)")
    y -= 14

    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.line(left, y, right, y)
    y -= 14

    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Item")
    c.drawRightString(right - 120, y, "Qty")
    c.drawRightString(right, y, "Total")
    y -= 10

    c.setFont("Helvetica", 9)
    for li in payload["line_items"]:
        c.drawString(left, y, li["label"])
        c.drawRightString(right - 120, y, li["qty_str"])
        c.drawRightString(right, y, money(li["total"]))
        y -= 12
        if y < 140:
            c.showPage()
            y = height - 60
            c.setFont("Helvetica", 9)

    y -= 8
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Subtotal (ex GST)")
    c.drawRightString(right, y, money(payload["subtotal_ex_gst"]))
    y -= 14

    c.setFont("Helvetica", 10)
    c.drawString(left, y, "GST")
    c.drawRightString(right, y, money(payload["gst"]))
    y -= 16

    c.setFont("Helvetica-Bold", 12)
    c.drawString(left, y, "Total (inc GST)")
    c.drawRightString(right, y, money(payload["total_inc_gst"]))
    y -= 18

    # ===== Terms =====
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Terms")
    y -= 12
    c.setFont("Helvetica", 9)
    for t in payload["terms"]:
        c.drawString(left, y, f"• {t}")
        y -= 12
        if y < 70:
            c.showPage()
            y = height - 60
            c.setFont("Helvetica", 9)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()

# =========================
# UI
# =========================
st.set_page_config(page_title="Flooring Quote Prototype", layout="centered")
st.title("📱 Flooring Quote Prototype (V1)")

# -------------------------
# Session defaults (critical)
# -------------------------
DEFAULTS = {
    "step": 1,
    "client_name": "",
    "client_phone": "",
    "client_email": "",
    "site_address": "",
    "job_mode": "Supply & Install",   # ensures Mode is never missing
    "quote_type": "Retail",
    "wastage_pct": DEFAULT_WASTAGE_PCT,
    "product_id": PRODUCTS[0]["id"],
    "install_id": INSTALL_ONLY[0]["id"],
    "removal_selected": [],
    "furniture_rate": DEFAULT_FURNITURE_PER_ROOM,
    "skirting_id": SKIRTING[0]["id"],
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Rooms list default
if "rooms" not in st.session_state or not st.session_state.rooms:
    st.session_state.rooms = [{"length": 3.0, "width": 4.0}]

# Session init
if "step" not in st.session_state:
    st.session_state.step = 1

# IMPORTANT: keep rooms in session state (mobile-friendly)
if "rooms" not in st.session_state:
    st.session_state.rooms = [{"length": 3.0, "width": 4.0}]


# ---------- STEP 1: JOB SETUP ----------
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
        st.session_state.product_id = st.selectbox(
            "Select timber product (Supply & Install)",
            options=[p["id"] for p in PRODUCTS],
            format_func=lambda pid: f"{find_by_id(PRODUCTS, pid)['brand']} — {find_by_id(PRODUCTS, pid)['name']}",
            key="product_id_ui",
        )
    else:
        st.session_state.install_id = st.selectbox(
            "Select installation type (Installation Only)",
            options=[i["id"] for i in INSTALL_ONLY],
            format_func=lambda iid: find_by_id(INSTALL_ONLY, iid)["name"],
            key="install_id_ui",
        )

    st.session_state.wastage_pct = st.number_input(
        "Wastage (%)",
        min_value=0.0,
        max_value=25.0,
        value=float(DEFAULT_WASTAGE_PCT),
        step=0.5,
        key="wastage_pct_ui",
    )

    # Scope sub-options
    if st.session_state.get("scope_removal", False):
        st.session_state.removal_selected = st.multiselect(
            "Existing floor type(s) to remove",
            options=[r["id"] for r in REMOVAL_TYPES],
            format_func=lambda rid: find_by_id(REMOVAL_TYPES, rid)["name"],
            default=[REMOVAL_TYPES[0]["id"]],
            key="removal_selected_ui",
        )
    else:
        st.session_state.removal_selected = []

    if st.session_state.get("scope_furniture", False):
        st.session_state.furniture_rate = st.number_input(
            "Furniture handling rate ($ per room)",
            min_value=0.0,
            value=float(DEFAULT_FURNITURE_PER_ROOM),
            step=5.0,
            key="furniture_rate_ui",
        )
    else:
        st.session_state.furniture_rate = float(DEFAULT_FURNITURE_PER_ROOM)

    if st.session_state.get("scope_skirting", False):
        st.session_state.skirting_id = st.selectbox(
            "Skirting height",
            options=[s["id"] for s in SKIRTING],
            format_func=lambda sid: f"{find_by_id(SKIRTING, sid)['height_mm']}mm",
            key="skirting_id_ui",
        )
    else:
        st.session_state.skirting_id = None

    client_name = (st.session_state.get("client_name") or "").strip()
    site_address = (st.session_state.get("site_address") or "").strip()
    
    missing = []
    if not client_name:
        missing.append("Client name")
    if not site_address:
        missing.append("Site address")
    
    if missing:
        st.warning("Please fill: " + ", ".join(missing))
        can_next = False
    else:
        can_next = True

    if st.button("Next → Measurements & Quote", disabled=not can_next):
        st.session_state.step = 2
        st.rerun()


# ---------- STEP 2: QUOTE BUILDER ----------
if st.session_state.step == 2:
    with st.expander("Client details (optional)", expanded=False):
        st.text_input("Client name", key="client_name")
        st.text_input("Client phone", key="client_phone")
        st.text_input("Client email", key="client_email")
        st.text_input("Site address", key="site_address")
        st.subheader("Step 3 — Measurements (mobile friendly)")

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
            area = float(room["length"]) * float(room["width"])
            st.metric("Area (m²)", f"{area:.2f}")

        if len(st.session_state.rooms) > 1:
            if st.button("Remove", key=f"remove_room_{i}"):
                remove_room(i)
                st.rerun()

    st.button("➕ Add Room", on_click=add_room)

    total_area = sum(float(r["length"]) * float(r["width"]) for r in st.session_state.rooms)
    wastage_pct = float(st.session_state.get("wastage_pct", DEFAULT_WASTAGE_PCT))
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

    # 1) Core job mode
    job_mode = st.session_state.get("job_mode", "Supply & Install")

    if job_mode == "Supply & Install":
        p = find_by_id(PRODUCTS, st.session_state.get("product_id"))
        st.markdown("#### Supply & Install")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"Product: {p['brand']} — {p['name']}")
            unit_price = st.number_input(
                "Supply & Install price ($/m²)",
                min_value=0.0,
                value=float(p["sell_per_m2"]),
                step=1.0,
                key="supply_install_price_override",
            )
        with col2:
            st.write("Quantity basis: chargeable area (includes wastage)")
            st.write(f"Chargeable area: {chargeable_area:.2f} m²")

        total = chargeable_area * unit_price
        line_items.append(line_item(f"Supply & install — {p['brand']} {p['name']}", f"{chargeable_area:.2f} m²", total))
        subtotal += total

    else:
        ins = find_by_id(INSTALL_ONLY, st.session_state.get("install_id"))
        st.markdown("#### Installation Only")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"Type: {ins['name']}")
            unit_price = st.number_input(
                "Installation price ($/m²)",
                min_value=0.0,
                value=float(ins["install_per_m2"]),
                step=1.0,
                key="install_only_price_override",
            )
        with col2:
            st.write("Quantity basis: total area")
            st.write(f"Total area: {total_area:.2f} m²")

        total = total_area * unit_price
        line_items.append(line_item(ins["name"], f"{total_area:.2f} m²", total))
        subtotal += total

    # 2) Removal
    if st.session_state.get("scope_removal", False):
        st.markdown("#### Floor Removal & Disposal")
        selected = st.session_state.get("removal_selected", [])
        if not selected:
            st.warning("Removal selected, but no floor types chosen. Go back and select at least one.")
        else:
            for rid in selected:
                r = find_by_id(REMOVAL_TYPES, rid)
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"Remove & dispose: {r['name']}")
                    rate = st.number_input(
                        f"{r['name']} removal ($/m²)",
                        min_value=0.0,
                        value=float(r["remove_per_m2"]),
                        step=1.0,
                        key=f"removal_rate_{rid}",
                    )
                with col2:
                    st.write("Quantity basis: total area")
                    st.write(f"{total_area:.2f} m²")

                total = total_area * rate
                line_items.append(line_item(f"Removal & disposal — {r['name']}", f"{total_area:.2f} m²", total))
                subtotal += total

    # 3) Furniture handling (NO rooms_df anywhere)
    if st.session_state.get("scope_furniture", False):
        st.markdown("#### Furniture Handling")
        base_rate = float(st.session_state.get("furniture_rate", DEFAULT_FURNITURE_PER_ROOM))

        room_names = [f"Room {i+1}" for i in range(len(st.session_state.rooms))]
        selected_rooms = st.multiselect(
            "Select rooms requiring furniture handling",
            options=room_names,
            default=room_names,
            key="furniture_rooms_selected",
        )
        rooms_count = len(selected_rooms)

        col1, col2 = st.columns(2)
        with col1:
            rate_override = st.number_input(
                "Furniture handling rate ($ per room)",
                min_value=0.0,
                value=float(base_rate),
                step=5.0,
                key="furniture_rate_override",
            )
        with col2:
            st.write(f"Rooms selected: {rooms_count}")

        total = rooms_count * rate_override
        line_items.append(line_item("Furniture handling", f"{rooms_count} room(s)", total))
        subtotal += total

    # 4) Skirting
    if st.session_state.get("scope_skirting", False):
        st.markdown("#### Skirting")
        sid = st.session_state.get("skirting_id")
        if not sid:
            st.warning("Skirting selected but no height chosen. Go back and choose a height.")
        else:
            sk = find_by_id(SKIRTING, sid)
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"Skirting height: {sk['height_mm']}mm")
                price_lm = st.number_input(
                    "Skirting price ($/lm)",
                    min_value=0.0,
                    value=float(sk["price_per_lm"]),
                    step=1.0,
                    key="skirting_price_override",
                )
            with col2:
                lm = st.number_input(
                    "Total skirting length (lm)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key="skirting_lm",
                )

            total = lm * price_lm
            line_items.append(line_item(f"Skirting — {sk['height_mm']}mm", f"{lm:.1f} lm", total))
            subtotal += total

    # Totals
    st.divider()
    st.subheader("Totals")

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

    # Build payload rooms
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
        "client_name": (st.session_state.get("client_name") or "").strip(),
        "client_phone": (st.session_state.get("client_phone") or "").strip(),
        "client_email": (st.session_state.get("client_email") or "").strip(),
        "site_address": (st.session_state.get("site_address") or "").strip(),
        "job_mode": st.session_state.get("job_mode", "Supply & Install"),
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

    st.caption("V1 prototype: PDF download only. Email/SMS sending can be added in V1.1.")
