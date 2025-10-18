import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from fpdf import FPDF
import io

# ==============================
# Funciones de optimización
# ==============================
class Rectangle:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h

def pack_rectangles(sheet_w, sheet_h, pieces, kerf):
    placements = []
    free = [Rectangle(0, 0, sheet_w, sheet_h)]

    for pid, (pw, ph, qty) in enumerate(pieces, start=1):
        for _ in range(qty):
            placed = False
            for i, f in enumerate(free):
                if pw <= f.w and ph <= f.h:
                    placements.append((pid, f.x, f.y, pw, ph))
                    new_rects = [
                        Rectangle(f.x + pw + kerf, f.y, f.w - pw - kerf, ph),
                        Rectangle(f.x, f.y + ph + kerf, f.w, f.h - ph - kerf)
                    ]
                    free.pop(i)
                    for nr in new_rects:
                        if nr.w > 0.01 and nr.h > 0.01:
                            free.append(nr)
                    placed = True
                    break
                elif ph <= f.w and pw <= f.h:
                    placements.append((pid, f.x, f.y, ph, pw))
                    new_rects = [
                        Rectangle(f.x + ph + kerf, f.y, f.w - ph - kerf, pw),
                        Rectangle(f.x, f.y + pw + kerf, f.w, f.h - pw - kerf)
                    ]
                    free.pop(i)
                    for nr in new_rects:
                        if nr.w > 0.01 and nr.h > 0.01:
                            free.append(nr)
                    placed = True
                    break
            if not placed:
                return placements, False
    return placements, True

# ==============================
# PDF generator
# ==============================
def generate_pdf(sheet_w, sheet_h, placements, pieces, usage):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Optimizador de Corte Essenza", ln=True, align="C")

    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Lámina: {sheet_w:.3f} m x {sheet_h:.3f} m", ln=True)
    pdf.cell(0, 10, f"Aprovechamiento: {usage:.2f}%", ln=True)

    # Dibujo
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.add_patch(patches.Rectangle((0, 0), sheet_w, sheet_h, fill=None, edgecolor='black', lw=2))
    colors = plt.cm.tab10.colors
    for (pid, x, y, w, h) in placements:
        color = colors[(pid-1) % len(colors)]
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=color, alpha=0.6))
        ax.text(x + w/2, y + h/2, f"P{pid}", ha='center', va='center', fontsize=8)
    ax.set_xlim(0, sheet_w)
    ax.set_ylim(0, sheet_h)
    ax.set_aspect('equal')
    ax.set_xlabel("m")
    ax.set_ylabel("m")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    pdf.image(buf, x=15, y=None, w=180)

    # Tabla de piezas
    pdf.ln(10)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "Piezas cortadas:", ln=True)
    pdf.set_font("Arial", size=10)
    for (pid, (pw, ph, qty)) in enumerate(pieces, start=1):
        pdf.cell(0, 8, f"P{pid}: {qty} x {pw:.3f}m x {ph:.3f}m", ln=True)

    out = io.BytesIO()
    pdf.output(out)
    out.seek(0)
    return out

# ==============================
# Interfaz Streamlit
# ==============================
st.title("🪨 Optimizador de Corte Essenza")
st.write("Calcula y visualiza el mejor aprovechamiento de láminas de mármol o cuarzo.")

col1, col2 = st.columns(2)
sheet_w = col1.number_input("Ancho de la lámina (m)", value=2.50, step=0.01)
sheet_h = col2.number_input("Largo de la lámina (m)", value=3.00, step=0.01)
kerf = st.number_input("Pérdida por corte (kerf) [m]", value=0.003, step=0.001)

st.subheader("Medidas de los mesones a cortar:")
num_pieces = st.number_input("Número de tipos de piezas:", min_value=1, max_value=20, value=3)
pieces = []
for i in range(num_pieces):
    c1, c2, c3 = st.columns(3)
    w = c1.number_input(f"Ancho pieza {i+1} (m)", value=1.2, step=0.01)
    h = c2.number_input(f"Largo pieza {i+1} (m)", value=0.6, step=0.01)
    q = c3.number_input(f"Cantidad pieza {i+1}", value=1, step=1)
    pieces.append((w, h, q))

if st.button("Calcular distribución"):
    placements, success = pack_rectangles(sheet_w, sheet_h, pieces, kerf)
    if not success:
        st.warning("⚠️ No todas las piezas caben en una lámina.")
    used_area = sum(w*h for (_,_,_,w,h) in placements)
    usage = 100 * used_area / (sheet_w * sheet_h)

    # Dibujo
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.add_patch(patches.Rectangle((0, 0), sheet_w, sheet_h, fill=None, edgecolor='black', lw=2))
    colors = plt.cm.tab10.colors
    for (pid, x, y, w, h) in placements:
        color = colors[(pid-1) % len(colors)]
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=color, alpha=0.5))
        ax.text(x + w/2, y + h/2, f"P{pid}", ha='center', va='center', fontsize=9)
    ax.set_xlim(0, sheet_w)
    ax.set_ylim(0, sheet_h)
    ax.set_aspect('equal')
    st.pyplot(fig)

    pdf_bytes = generate_pdf(sheet_w, sheet_h, placements, pieces, usage)
    st.download_button("📥 Descargar reporte en PDF", data=pdf_bytes, file_name="reporte_corte.pdf", mime="application/pdf")