import io
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


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
    {"id": "r1", "name": "Carpet", "remove_per_m2": 12.0},
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
# PDF GENERATION (simple & professional enough for prototype)
# =========================
def _money(x: float) -> str:
    return f"${x:,.2f}"


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

    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Client: {payload['client_name']}")
    y -= 14
    c.drawString(left, y, f"Phone: {payload['client_phone']}    Email: {payload['client_email']}")
    y -= 14
    c.drawString(left, y, f"Site: {payload['site_address']}")
    y -= 14
    c.drawString(left, y, f"Mode: {payload['job_mode']}")
    y -= 18

    # Rooms table
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

    # Scope / line items
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
        c.drawRightString(right - 55, y, _money(li["total"]))
        y -= 12
        if y < 120:
            c.showPage()
            y = height - 48
            c.setFont("Helvetica", 9)

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Subtotal (ex GST)")
    c.drawRightString(right - 55, y, _money(payload["subtotal_ex_gst"]))
    y -= 14

    c.setFont("Helvetica", 10)
    c.drawString(left, y, "GST")
    c.drawRightString(right - 55, y, _money(payload["gst"]))
    y -= 14

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left, y, "Total (inc GST)")
    c.drawRightString(right - 55, y, _money(payload["total_inc_gst"]))
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
# HELPERS
# =========================
def find_by_id(items: List[dict], item_id: str) -> dict:
    for it in items:
        if it["id"] == item_id:
            return it
    raise KeyError(item_id)


def line_item(label: str, qty_str: str, total: float) -> dict:
    return {"label": label, "qty_str": qty_str, "total": float(total)}


def init_rooms_df():
    return pd.DataFrame([{"Room": "Living", "Length_m": 3.0, "Width_m": 4.0}])


# =========================
# UI
# =========================
st.set_page_config(page_title="Flooring Quote Prototype", layout="centered")
st.title("📱 Flooring Quote Prototype (V1)")

# Session init
if "step" not in st.session_state:
    st.session_state.step = 1
if "rooms_df" not in st.session_state:
    st.session_state.rooms_df = init_rooms_df()

# ---------- STEP 1: JOB SETUP ----------
if st.session_state.step == 1:
    st.subheader("Step 1 — Job Setup")

    col1, col2 = st.columns(2)
    with col1:
        client_name = st.text_input("Client name", key="client_name")
        client_phone = st.text_input("Client phone", key="client_phone")
    with col2:
        client_email = st.text_input("Client email", key="client_email")
        site_address = st.text_input("Site address", key="site_address")

    job_mode = st.radio(
        "Work type",
        ["Supply & Install", "Installation Only"],
        horizontal=True,
        key="job_mode",
    )

    quote_type = st.selectbox("Quote type (for your own tracking)", ["Retail", "Builder"], key="quote_type")

    st.divider()
    st.subheader("Step 2 — Select Scope")
    c_removal = st.checkbox("Include floor removal & disposal", key="scope_removal")
    c_furniture = st.checkbox("Include furniture handling", key="scope_furniture")
    c_skirting = st.checkbox("Include skirting", key="scope_skirting")

    st.divider()

    # Validation for next step
    ok = True
    if job_mode == "Supply & Install":
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

    # Scope sub-options captured now (so quote page only shows selected)
    if c_removal:
        st.session_state.removal_selected = st.multiselect(
            "Existing floor type(s) to remove",
            options=[r["id"] for r in REMOVAL_TYPES],
            format_func=lambda rid: find_by_id(REMOVAL_TYPES, rid)["name"],
            default=[REMOVAL_TYPES[0]["id"]],
            key="removal_selected_ui",
        )
    else:
        st.session_state.removal_selected = []

    if c_furniture:
        st.session_state.furniture_rate = st.number_input(
            "Furniture handling rate ($ per room)",
            min_value=0.0,
            value=float(DEFAULT_FURNITURE_PER_ROOM),
            step=5.0,
            key="furniture_rate_ui",
        )
    else:
        st.session_state.furniture_rate = float(DEFAULT_FURNITURE_PER_ROOM)

    if c_skirting:
        st.session_state.skirting_id = st.selectbox(
            "Skirting height",
            options=[s["id"] for s in SKIRTING],
            format_func=lambda sid: f"{find_by_id(SKIRTING, sid)['height_mm']}mm",
            key="skirting_id_ui",
        )
    else:
        st.session_state.skirting_id = None

    # Next
    if st.button("Next → Measurements & Quote"):
        st.session_state.step = 2
        st.rerun()


# ---------- STEP 2: QUOTE BUILDER ----------
if st.session_state.step == 2:
    st.subheader("Step 3 — Measurements")

    rooms_df = st.data_editor(
        st.session_state.rooms_df,
        num_rows="dynamic",
        use_container_width=True,
        key="rooms_editor",
    )
    rooms_df = rooms_df.copy()
    if len(rooms_df) == 0:
        st.warning("Add at least one room.")
        st.stop()

    # Compute areas
    rooms_df["Area_m2"] = rooms_df["Length_m"].astype(float) * rooms_df["Width_m"].astype(float)
    total_area = float(rooms_df["Area_m2"].sum())
    wastage_pct = float(st.session_state.get("wastage_pct", DEFAULT_WASTAGE_PCT))
    chargeable_area = total_area * (1.0 + wastage_pct / 100.0)

    st.session_state.rooms_df = rooms_df.drop(columns=["Area_m2"], errors="ignore")

    colA, colB, colC = st.columns(3)
    colA.metric("Total area (m²)", f"{total_area:.2f}")
    colB.metric("Wastage (%)", f"{wastage_pct:.1f}")
    colC.metric("Chargeable area (m²)", f"{chargeable_area:.2f}")

    st.divider()
    st.subheader("Step 4 — Quote Items (selected scope only)")

    line_items: List[dict] = []
    subtotal = 0.0

    # 1) Core job mode item(s)
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

    # 3) Furniture handling
    if st.session_state.get("scope_furniture", False):
        st.markdown("#### Furniture Handling")
        rate = float(st.session_state.get("furniture_rate", DEFAULT_FURNITURE_PER_ROOM))

        # Choose rooms by checkbox (mobile-friendly enough for V1)
        room_names = [str(x) for x in rooms_df["Room"].tolist()]
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
                value=float(rate),
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

    colT1, colT2, colT3 = st.columns(3)
    colT1.metric("Subtotal (ex GST)", f"${subtotal:,.0f}")
    colT2.metric("GST", f"${gst:,.0f}")
    colT3.metric("Total (inc GST)", f"${total_inc:,.0f}")

    st.divider()
    st.subheader("Step 5 — Generate Quote PDF")

    terms_default = [
        "Quote valid for 7 days.",
        "Variations may apply if site conditions differ from inspection.",
        "Progress payments may apply for larger jobs.",
    ]
    terms_text = st.text_area("Terms (one per line)", "\n".join(terms_default), height=120)
    terms = [t.strip() for t in terms_text.splitlines() if t.strip()]

    # Build payload
    rooms_out = []
    for _, row in rooms_df.iterrows():
        rooms_out.append({
            "name": str(row["Room"]),
            "length": float(row["Length_m"]),
            "width": float(row["Width_m"]),
            "area": float(row["Area_m2"]),
        })

    payload = {
        "client_name": st.session_state.get("client_name", "—") or "—",
        "client_phone": st.session_state.get("client_phone", "—") or "—",
        "client_email": st.session_state.get("client_email", "—") or "—",
        "site_address": st.session_state.get("site_address", "—") or "—",
        "job_mode": st.session_state.get("job_mode", "—"),
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