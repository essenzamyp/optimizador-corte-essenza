import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from fpdf import FPDF
import io

st.title("🪚 Optimizador de Corte Essenza")
st.write("Optimiza el aprovechamiento de láminas de mármol o cuarzo minimizando el desperdicio.")

# ------------------------------
# Parámetros de entrada
# ------------------------------
sheet_w = st.number_input("Ancho de la lámina (m)", value=1.60, step=0.01, format="%.3f")
sheet_h = st.number_input("Largo de la lámina (m)", value=2.40, step=0.01, format="%.3f")
kerf = st.number_input("Espesor del disco de corte (kerf, m)", value=0.003, step=0.001, format="%.3f")

st.subheader("Piezas (mesones) a cortar")
n = st.number_input("Número de piezas diferentes", min_value=1, value=1, step=1)

pieces = []
for i in range(int(n)):
    st.markdown(f"**Pieza {i+1}**")
    w = st.number_input(f"Ancho pieza {i+1} (m)", value=0.5, step=0.01, format="%.3f")
    h = st.number_input(f"Largo pieza {i+1} (m)", value=1.4, step=0.01, format="%.3f")
    qty = st.number_input(f"Cantidad", min_value=1, value=6, step=1)
    pieces.append({"width": w, "height": h, "qty": qty})

# ------------------------------
# Algoritmo de colocación simple (fila a fila)
# ------------------------------
placements = []
num_sheets = 1
x, y, max_row_h = 0, 0, 0

for piece in pieces:
    for _ in range(piece["qty"]):
        w, h = piece["width"], piece["height"]
        if w > sheet_w or h > sheet_h:
            st.warning(f"No cabe la pieza {w:.3f} x {h:.3f} m en la lámina.")
            continue
        if x + w > sheet_w:
            x = 0
            y += max_row_h + kerf
            max_row_h = 0
        if y + h > sheet_h:
            num_sheets += 1
            x, y, max_row_h = 0, 0, 0
        placements.append({"sheet": num_sheets, "x": x, "y": y, "w": w, "h": h})
        x += w + kerf
        max_row_h = max(max_row_h, h)

# ------------------------------
# Cálculo de aprovechamiento
# ------------------------------
total_area = sheet_w * sheet_h * num_sheets
used_area = sum(p["w"] * p["h"] for p in placements)
usage = (used_area / total_area * 100) if total_area > 0 else 0
waste = 100 - usage

st.write(f"**Aprovechamiento del material: {usage:.2f}%**")
st.write(f"**Desperdicio: {waste:.2f}%**")

# ------------------------------
# Gráficos
# ------------------------------
def plot_sheet(sheet_num):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_xlim(0, sheet_w)
    ax.set_ylim(0, sheet_h)
    ax.set_aspect("equal")
    ax.set_title(f"Lámina {sheet_num}")

    # Fondo gris claro = área total
    ax.add_patch(patches.Rectangle((0, 0), sheet_w, sheet_h, facecolor="#e0e0e0"))

    # Dibujar piezas
    for p in placements:
        if p["sheet"] == sheet_num:
            rect = patches.Rectangle((p["x"], p["y"]), p["w"], p["h"],
                                     linewidth=1, edgecolor='blue', facecolor='skyblue', alpha=0.8)
            ax.add_patch(rect)
            cx = p["x"] + p["w"]/2
            cy = p["y"] + p["h"]/2
            ax.text(cx, cy, f"{p['w']:.3f}×{p['h']:.3f}", ha='center', va='center', fontsize=8)

    # Texto de aprovechamiento y desperdicio
    ax.text(sheet_w * 0.98, sheet_h * 0.98,
            f"Aprovechamiento: {usage:.2f}%\nDesperdicio: {waste:.2f}%",
            ha='right', va='top', fontsize=10, color='black',
            bbox=dict(facecolor='white', alpha=0.7, edgecolor='gray'))

    ax.set_xlabel("m")
    ax.set_ylabel("m")
    st.pyplot(fig)
    return fig

for s in range(1, num_sheets + 1):
    plot_sheet(s)

# ------------------------------
# Generar PDF
# ------------------------------
def generate_pdf(sheet_w, sheet_h, placements, num_sheets, usage, waste):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    for s in range(1, num_sheets + 1):
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, f"Optimización de Corte - Lámina {s}", ln=True, align="C")
        pdf.set_font("Arial", size=11)
        pdf.cell(0, 10, f"Aprovechamiento: {usage:.2f}% | Desperdicio: {waste:.2f}%", ln=True)

        fig = plot_sheet(s)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        pdf.image(buf, x=15, w=180)

    return pdf.output(dest="S").encode("latin1")

# ------------------------------
# Botón de descarga PDF
# ------------------------------
if st.button("📄 Exportar reporte PDF"):
    pdf_bytes = generate_pdf(sheet_w, sheet_h, placements, num_sheets, usage, waste)
    st.download_button(
        label="Descargar reporte PDF",
        data=pdf_bytes,
        file_name="reporte_optimizacion_corte.pdf",
        mime="application/pdf"
    )
