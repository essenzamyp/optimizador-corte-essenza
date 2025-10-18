import streamlit as st
import matplotlib.pyplot as plt
from io import BytesIO
import tempfile
from fpdf import FPDF

# ==============================
# 🧩 ALGORITMO MAXRECTS (MEJORADO)
# ==============================
class MaxRectsBin:
    def __init__(self, width, height, kerf=0):
        self.width = width
        self.height = height
        self.kerf = kerf
        self.free_rects = [(0, 0, width, height)]
        self.placements = []

    def insert(self, w, h):
        """Inserta una pieza usando heurística Best Short Side Fit"""
        best_score = None
        best_rect = None
        best_index = -1

        for i, (fx, fy, fw, fh) in enumerate(self.free_rects):
            if w <= fw and h <= fh:
                score = min(fw - w, fh - h)
                if best_score is None or score < best_score:
                    best_score = score
                    best_rect = (fx, fy, w, h)
                    best_index = i

        if best_rect:
            fx, fy, w, h = best_rect
            self.place_rect(fx, fy, w, h, best_index)
            return True
        return False

    def place_rect(self, x, y, w, h, free_index):
        """Divide el área libre y actualiza cortes"""
        (fx, fy, fw, fh) = self.free_rects[free_index]
        del self.free_rects[free_index]

        kerf_x = self.kerf if x + w < self.width else 0
        kerf_y = self.kerf if y + h < self.height else 0

        if fw - w - kerf_x > 0:
            self.free_rects.append((x + w + kerf_x, fy, fw - w - kerf_x, h))
        if fh - h - kerf_y > 0:
            self.free_rects.append((fx, fy + h + kerf_y, fw, fh - h - kerf_y))

        self.placements.append((x, y, w, h, free_index))


# ==============================
# 📄 FUNCIÓN PDF
# ==============================
def generate_pdf(sheet_w, sheet_h, placements, pieces, usage):
    """Genera un PDF con plano y tabla de cortes"""
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_xlim(0, sheet_w)
    ax.set_ylim(0, sheet_h)
    ax.set_aspect('equal')
    ax.set_title('Plano de Corte', fontsize=14)
    ax.add_patch(plt.Rectangle((0, 0), sheet_w, sheet_h, fill=None, edgecolor='black', lw=2))

    for (x, y, w, h, _) in placements:
        ax.add_patch(plt.Rectangle((x, y), w, h, fill=True, alpha=0.4, color='skyblue', edgecolor='black'))
        ax.text(x + w / 2, y + h / 2, f"{int(w)}x{int(h)}", ha='center', va='center', fontsize=8)

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=200, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    # Crear PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "OPTIMIZADOR DE CORTE ESSENZA", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 10, f"Tamaño de lámina: {sheet_w} x {sheet_h} mm", ln=True)
    pdf.cell(0, 10, f"Aprovechamiento del material: {usage:.2f}%", ln=True)
    pdf.ln(10)

    # Guardar imagen temporalmente
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        tmp_file.write(buf.getvalue())
        tmp_path = tmp_file.name

    pdf.image(tmp_path, x=15, w=180)
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Detalle de piezas cortadas:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(40, 8, "Ancho (mm)", 1, 0, "C", fill=True)
    pdf.cell(40, 8, "Largo (mm)", 1, 0, "C", fill=True)
    pdf.cell(40, 8, "Área (mm²)", 1, 1, "C", fill=True)

    for _, _, w, h, _ in placements:
        pdf.cell(40, 8, str(int(w)), 1, 0, "C")
        pdf.cell(40, 8, str(int(h)), 1, 0, "C")
        pdf.cell(40, 8, f"{int(w*h)}", 1, 1, "C")

    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    return pdf_bytes


# ==============================
# 🎨 INTERFAZ STREAMLIT
# ==============================
st.set_page_config(page_title="Optimizador de Corte Essenza", layout="wide")
st.title("🪚 Optimizador de Corte Essenza")
st.markdown("Optimiza el aprovechamiento de láminas de mármol o cuarzo minimizando el desperdicio.")

col1, col2 = st.columns(2)
with col1:
    sheet_w = st.number_input("Ancho de la lámina (mm)", value=1600)
    sheet_h = st.number_input("Largo de la lámina (mm)", value=2400)
    kerf = st.number_input("Espesor del disco de corte (kerf, mm)", value=3.0)

with col2:
    st.markdown("### Piezas (mesones) a cortar")
    pieces = []
    n = st.number_input("Número de piezas diferentes", min_value=1, value=1, step=1)
    for i in range(int(n)):
        c1, c2, c3 = st.columns(3)
        with c1:
            w = st.number_input(f"Ancho pieza {i+1} (mm)", min_value=1.0, value=500.0, key=f"w{i}")
        with c2:
            h = st.number_input(f"Largo pieza {i+1} (mm)", min_value=1.0, value=1400.0, key=f"h{i}")
        with c3:
            qty = st.number_input(f"Cantidad", min_value=1, value=6, key=f"q{i}")
        for _ in range(qty):
            pieces.append((w, h))

if st.button("Calcular corte óptimo"):
    bin = MaxRectsBin(sheet_w, sheet_h, kerf)
    placements = []
    for w, h in pieces:
        if not bin.insert(w, h):
            if not bin.insert(h, w):  # intenta rotar
                st.warning(f"No cabe la pieza {w}x{h} mm en la lámina.")
    placements = bin.placements

    used_area = sum(w * h for _, _, w, h, _ in placements)
    total_area = sheet_w * sheet_h
    usage = (used_area / total_area) * 100

    st.success(f"Aprovechamiento del material: **{usage:.2f}%**")

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.set_xlim(0, sheet_w)
    ax.set_ylim(0, sheet_h)
    ax.set_aspect('equal')
    ax.add_patch(plt.Rectangle((0, 0), sheet_w, sheet_h, fill=None, edgecolor='black', lw=2))
    for (x, y, w, h, _) in placements:
        ax.add_patch(plt.Rectangle((x, y), w, h, fill=True, alpha=0.4, color='skyblue', edgecolor='black'))
        ax.text(x + w/2, y + h/2, f"{int(w)}x{int(h)}", ha='center', va='center', fontsize=8)

    st.pyplot(fig)

    pdf_bytes = generate_pdf(sheet_w, sheet_h, placements, pieces, usage)
    st.download_button(
        label="📄 Descargar reporte PDF",
        data=pdf_bytes,
        file_name="reporte_corte_essenza.pdf",
        mime="application/pdf"
    )
