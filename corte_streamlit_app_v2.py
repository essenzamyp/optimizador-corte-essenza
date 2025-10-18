import io
import os
import tempfile
import streamlit as st
from fpdf import FPDF
from PIL import Image, ImageDraw

# =========================================================
# 🧮 FUNCIONES DE OPTIMIZACIÓN
# =========================================================

def place_pieces_in_sheets(sheet_w, sheet_h, pieces, kerf):
    """
    Coloca las piezas dentro de una o más láminas (en metros).
    El kerf solo se aplica entre cortes internos.
    """
    all_placements = []  # [(sheet_index, x, y, w, h)]
    current_sheet = 1
    free_rects = [(0, 0, sheet_w, sheet_h)]
    used_area = 0

    for p in pieces:
        pw, ph, qty = p
        for _ in range(qty):
            placed = False
            for i, (x, y, w, h) in enumerate(free_rects):
                if pw <= w and ph <= h:
                    all_placements.append((current_sheet, x, y, pw, ph))
                    used_area += pw * ph
                    del free_rects[i]
                    free_rects += [
                        (x + pw + kerf, y, w - pw - kerf, ph),
                        (x, y + ph + kerf, w, h - ph - kerf)
                    ]
                    free_rects = [(fx, fy, fw, fh) for fx, fy, fw, fh in free_rects if fw > 0 and fh > 0]
                    placed = True
                    break
            if not placed:
                # Inicia una nueva lámina
                current_sheet += 1
                free_rects = [(0, 0, sheet_w, sheet_h)]
                free_rects[0] = (0, 0, sheet_w, sheet_h)
                free_rects.pop(0)
                free_rects = [(0, 0, sheet_w, sheet_h)]
                free_rects_copy = free_rects.copy()
                free_rects = [(0, 0, sheet_w, sheet_h)]
                free_rects = [(0, 0, sheet_w, sheet_h)]
                all_placements.append((current_sheet, 0, 0, pw, ph))
                used_area += pw * ph
                free_rects = [(pw + kerf, 0, sheet_w - pw - kerf, ph),
                              (0, ph + kerf, sheet_w, sheet_h - ph - kerf)]
                placed = True
    return all_placements, used_area, current_sheet


# =========================================================
# 🖼️ GENERAR GRÁFICO DE CADA LÁMINA
# =========================================================

def draw_sheet(sheet_w, sheet_h, placements, sheet_number):
    img_w = 800
    img_h = int(800 * (sheet_h / sheet_w))
    img = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img)

    scale = img_w / sheet_w
    for (s, x, y, w, h) in placements:
        if s == sheet_number:
            draw.rectangle(
                [(x * scale, y * scale), ((x + w) * scale, (y + h) * scale)],
                outline="black", width=2, fill="#A9CCE3"
            )
            draw.text((x * scale + 5, y * scale + 5), f"{w:.3f}x{h:.3f} m", fill="black")

    return img


# =========================================================
# 📄 GENERAR PDF
# =========================================================

def generate_pdf(sheet_w, sheet_h, placements, num_sheets, usage):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    for s in range(1, num_sheets + 1):
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(200, 10, txt=f"Optimizador de Corte Essenza - Lámina {s}", ln=True, align="C")

        pdf.set_font("Arial", size=10)
        pdf.cell(200, 10, txt=f"Lámina: {sheet_w:.3f} x {sheet_h:.3f} m", ln=True)
        pdf.cell(200, 10, txt=f"Aprovechamiento total: {usage:.2f}%", ln=True)

        img = draw_sheet(sheet_w, sheet_h, placements, s)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        # Guardar imagen temporalmente
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            tmp_file.write(buf.getvalue())
            tmp_path = tmp_file.name

        pdf.image(tmp_path, x=15, y=None, w=180)
        os.remove(tmp_path)

    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output


# =========================================================
# 🖥️ INTERFAZ STREAMLIT
# =========================================================

st.title("🪚 Optimizador de Corte Essenza")
st.write("Optimiza el aprovechamiento de láminas de mármol o cuarzo minimizando el desperdicio (en metros).")

sheet_w = st.number_input("Ancho de la lámina (m)", min_value=0.1, max_value=10.0, value=1.600, step=0.1)
sheet_h = st.number_input("Largo de la lámina (m)", min_value=0.1, max_value=10.0, value=2.400, step=0.1)
kerf = st.number_input("Espesor del disco de corte (kerf, mm)", min_value=0.0, max_value=10.0, value=3.0, step=0.1)
kerf_m = kerf / 1000.0

st.subheader("Piezas (mesones) a cortar")
num_pieces = st.number_input("Número de piezas diferentes", min_value=1, max_value=20, value=1)

pieces = []
for i in range(num_pieces):
    col1, col2, col3 = st.columns(3)
    with col1:
        w = st.number_input(f"Ancho pieza {i+1} (m)", min_value=0.1, max_value=10.0, value=0.500, step=0.1, format="%.3f")
    with col2:
        h = st.number_input(f"Largo pieza {i+1} (m)", min_value=0.1, max_value=10.0, value=1.400, step=0.1, format="%.3f")
    with col3:
        qty = st.number_input(f"Cantidad", min_value=1, max_value=20, value=6)
    pieces.append((w, h, qty))

if st.button("🧠 Optimizar corte"):
    placements, used_area, num_sheets = place_pieces_in_sheets(sheet_w, sheet_h, pieces, kerf_m)
    total_area = sheet_w * sheet_h * num_sheets
    usage = (used_area / total_area) * 100 if total_area > 0 else 0

    st.success(f"✅ Aprovechamiento del material: {usage:.2f}% usando {num_sheets} lámina(s).")

    # Mostrar gráfico de cada lámina
    for s in range(1, num_sheets + 1):
        img = draw_sheet(sheet_w, sheet_h, placements, s)
        st.image(img, caption=f"Lámina {s}", use_container_width=True)

    pdf_bytes = generate_pdf(sheet_w, sheet_h, placements, num_sheets, usage)

    st.download_button(
        label="📥 Descargar reporte en PDF",
        data=pdf_bytes,
        file_name="reporte_corte_essenza.pdf",
        mime="application/pdf"
    )
