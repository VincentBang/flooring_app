import io
from typing import List

import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


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
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    left = 42
    right = width - 42
    y = height - 48

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, "QUOTATION")
    y -= 22

    # Client block (blank is OK; we do NOT force)
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Client: {payload['client_name']}")
    y -= 14
    c.drawString(left, y, f"Phone: {payload['client_phone']}    Email: {payload['client_email']}")
    y -= 14
    c.drawString(left, y, f"Site: {payload['site_address']}")
    y -= 14
    c.drawString(left, y, f"Mode: {payload['job_mode']}")
    y -= 18

    # Measurements
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Measurements")
    y -= 14

    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Room")
    c.drawString(left + 210, y, "L (m)")
    c.drawString(left + 260, y, "W (m)")
    c.drawString(left + 310, y, "Area (m²)")
    y -= 10
    c.setFont("Helvetica", 9)

    for r in payload["rooms"]:
        c.drawString(left, y, r["name"])
        c.drawRightString(left + 245, y, f"{r['length']:.2f}")
        c.drawRightString(left + 295, y, f"{r['width']:.2f}")
        c.drawRightString(left + 370, y, f"{r['area']:.2f}")
        y -= 12
        if y < 160:
            c.showPage()
            y = height - 48
            c.setFont("Helvetica", 9)

    y -= 6
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Total area: {payload['total_area']:.2f} m²")
    y -= 14
    c.drawString(left, y, f"Wastage: {payload['wastage_pct']:.1f}%")
    y -= 14
    c.drawString(left, y, f"Chargeable area: {payload['chargeable_area']:.2f} m²")
    y -= 18

    # Scope / pricing
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Scope & Pricing (ex GST)")
    y -= 14

    c.setFont("Helvetica-Bold", 9)
    c.drawString(left, y, "Item")
    c.drawRightString(right - 120, y, "Qty")
    c.drawRightString(right - 55, y, "Total")
    y -= 10
    c.setFont("Helvetica", 9)

    for li in payload["line_items"]:
        c.drawString(left, y, li["label"])
        c.drawRightString(right - 120, y, li["qty_str"])
        c.drawRightString(right - 55, y, money(li["total"]))
        y -= 12
        if y < 120:
            c.showPage()
            y = height - 48
            c.setFont("Helvetica", 9)

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Subtotal (ex GST)")
    c.drawRightString(right - 55, y, money(payload["subtotal_ex_gst"]))
    y -= 14

    c.setFont("Helvetica", 10)
    c.drawString(left, y, "GST")
    c.drawRightString(right - 55, y, money(payload["gst"]))
    y -= 14

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Total (inc GST)")
    c.drawRightString(right - 55, y, money(payload["total_inc_gst"]))
    y -= 18

    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Terms")
    y -= 14
    c.setFont("Helvetica", 9)
    for t in payload["terms"]:
        c.drawString(left, y, f"• {t}")
        y -= 12
        if y < 60:
            c.showPage()
            y = height - 48
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
