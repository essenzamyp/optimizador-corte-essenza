import io
import streamlit as st
from fpdf import FPDF
from PIL import Image, ImageDraw

# =========================================================
# 🧮 FUNCIONES DE OPTIMIZACIÓN
# =========================================================

def place_pieces(sheet_w, sheet_h, pieces, kerf):
    """
    Coloca las piezas dentro de la lámina usando un algoritmo simple de partición.
    El kerf solo se aplica entre cortes internos.
    """
    placements = []
    free_rects = [(0, 0, sheet_w, sheet_h)]

    for p in pieces:
        pw, ph, qty = p
        for _ in range(qty):
            placed = False
            for i, (x, y, w, h) in enumerate(free_rects):
                if pw <= w and ph <= h:
                    placements.append((x, y, pw, ph))
                    del free_rects[i]
                    free_rects += [
                        (x + pw + kerf, y, w - pw - kerf, ph),  # derecha
                        (x, y + ph + kerf, w, h - ph - kerf)   # abajo
                    ]
                    free_rects = [(fx, fy, fw, fh) for fx, fy, fw, fh in free_rects if fw > 0 and fh > 0]
                    placed = True
                    break
            if not placed:
                st.warning(f"No cabe la pieza {pw:.3f} x {ph:.3f} m en la lámina.")
    return placements

# =========================================================
# 📄 GENERAR PDF
# =========================================================
def generate_pdf(sheet_w, sheet_h, placements, pieces, usage):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(200, 10, txt="Optimizador de Corte Essenza", ln=True, align="C")

    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Lámina: {sheet_w:.3f} x {sheet_h:.3f} m", ln=True)
    pdf.cell(200, 10, txt=f"Aprovechamiento del material: {usage:.2f}%", ln=True)

    img_w, img_h = 800, int(800 * (sheet_h / sheet_w))
    img = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img)

    scale = img_w / sheet_w
    for (x, y, w, h) in placements:
        draw.rectangle(
            [(x * scale, y * scale), ((x + w) * scale, (y + h) * scale)],
            outline="black", width=2, fill="#A9CCE3"
        )
        draw.text((x * scale + 5, y * scale + 5), f"{w:.3f}x{h:.3f} m", fill="black")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    pdf.image(buf, x=15, y=None, w=180)

    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output

# =========================================================
# 🖥️ INTERFAZ STREAMLIT
# =========================================================
st.title("🪚 Optimizador de Corte Essenza")
st.write("Optimiza el aprovechamiento de láminas de mármol o cuarzo minimizando el desperdicio.")

sheet_w = st.number_input("Ancho de la lámina (m)", min_value=0.1, max_value=10.0, value=1.600, step=0.1)
sheet_h = st.number_input("Largo de la lámina (m)", min_value=0.1, max_value=10.0, value=2.400, step=0.1)
kerf = st.number_input("Espesor del disco de corte (kerf, mm)", min_value=0.0, max_value=10.0, value=3.0, step=0.1)
kerf_m = kerf / 1000.0  # convertir mm → m

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
    placements = place_pieces(sheet_w, sheet_h, pieces, kerf_m)
    used_area = sum(w * h for (_, _, w, h) in placements)
    total_area = sheet_w * sheet_h
    usage = (used_area / total_area) * 100 if total_area > 0 else 0

    st.success(f"Aprovechamiento del material: {usage:.2f}%")

    pdf_bytes = generate_pdf(sheet_w, sheet_h, placements, pieces, usage)

    st.download_button(
        label="📥 Descargar reporte en PDF",
        data=pdf_bytes,
        file_name="reporte_corte_essenza.pdf",
        mime="application/pdf"
    )

