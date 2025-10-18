# corte_streamlit_app_v2.py
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from fpdf import FPDF
import io
import tempfile
import os
import math
import random

# -------------------------
# UTILIDADES
# -------------------------
def fmt_m(x):
    """Formatea metros con 3 decimales."""
    return f"{x:.3f}"

# -------------------------
# MAXRECTS BIN (BSSF heuristic)
# -------------------------
class FreeRect:
    def __init__(self, x, y, w, h):
        self.x = x; self.y = y; self.w = w; self.h = h

class Placement:
    def __init__(self, sheet, x, y, w, h, rid, rotated):
        self.sheet = sheet
        self.x = x; self.y = y; self.w = w; self.h = h
        self.rid = rid
        self.rotated = rotated

class MaxRectsBin:
    def __init__(self, width, height, kerf=0.0):
        self.width = width
        self.height = height
        self.kerf = kerf
        self.free_rects = [FreeRect(0.0, 0.0, width, height)]
        self.placements = []

    def _score_bssf(self, free, rw, rh):
        leftover_h = abs(free.h - rh)
        leftover_w = abs(free.w - rw)
        short_side = min(leftover_h, leftover_w)
        long_side = max(leftover_h, leftover_w)
        return (short_side, long_side)

    def _split_free(self, free, used):
        out = []
        # no intersection
        if used.x >= free.x + free.w - 1e-12 or used.x + used.w <= free.x + 1e-12 or used.y >= free.y + free.h - 1e-12 or used.y + used.h <= free.y + 1e-12:
            return [free]
        # left
        if used.x > free.x + 1e-12:
            out.append(FreeRect(free.x, free.y, used.x - free.x, free.h))
        # right
        if used.x + used.w < free.x + free.w - 1e-12:
            out.append(FreeRect(used.x + used.w, free.y, free.x + free.w - (used.x + used.w), free.h))
        # top
        if used.y > free.y + 1e-12:
            out.append(FreeRect(free.x, free.y, free.w, used.y - free.y))
        # bottom
        if used.y + used.h < free.y + free.h - 1e-12:
            out.append(FreeRect(free.x, used.y + used.h, free.w, free.y + free.h - (used.y + used.h)))
        return out

    def _prune_free(self):
        pruned = []
        for i, a in enumerate(self.free_rects):
            contained = False
            for j, b in enumerate(self.free_rects):
                if i != j:
                    if a.x >= b.x - 1e-12 and a.y >= b.y - 1e-12 and a.x + a.w <= b.x + b.w + 1e-12 and a.y + a.h <= b.y + b.h + 1e-12:
                        contained = True
                        break
            if not contained:
                pruned.append(a)
        self.free_rects = pruned

    def insert(self, w, h, rid, allow_rotate=True, sheet_index=1):
        # find best position
        best = None
        best_free = None
        best_rot = False
        for fr in self.free_rects:
            for rot in ([False, True] if allow_rotate else [False]):
                rw = w if not rot else h
                rh = h if not rot else w
                # compute occupied size including kerf only if piece would not reach sheet edge
                # Candidate position is at fr.x, fr.y
                kerf_x = self.kerf if (fr.x + rw) < self.width - 1e-12 else 0.0
                kerf_y = self.kerf if (fr.y + rh) < self.height - 1e-12 else 0.0
                occ_w = round((rw + kerf_x) / 0.001) * 0.001
                occ_h = round((rh + kerf_y) / 0.001) * 0.001
                # check fit
                if occ_w <= fr.w + 1e-12 and occ_h <= fr.h + 1e-12:
                    score = self._score_bssf(fr, occ_w, occ_h)
                    if best is None or score < best:
                        best = score
                        best_free = fr
                        best_rot = rot
        if best_free is None:
            return None
        # place at best_free.x, best_free.y with actual piece dims (without kerf) for record
        rw = w if not best_rot else h
        rh = h if not best_rot else w
        placed_x = best_free.x
        placed_y = best_free.y
        # occupied rect includes kerf if not touching edge
        kerf_x = self.kerf if (placed_x + rw) < self.width - 1e-12 else 0.0
        kerf_y = self.kerf if (placed_y + rh) < self.height - 1e-12 else 0.0
        occ_w = round((rw + kerf_x) / 0.001) * 0.001
        occ_h = round((rh + kerf_y) / 0.001) * 0.001
        used = FreeRect(placed_x, placed_y, occ_w, occ_h)
        # update free rects
        new_free = []
        for fr in self.free_rects:
            new_free.extend(self._split_free(fr, used))
        self.free_rects = new_free
        self._prune_free()
        # store placement with actual piece size (rw,rh) and rotation flag
        placement = Placement(sheet_index, placed_x, placed_y, rw, rh, rid, best_rot)
        self.placements.append(placement)
        return placement

# -------------------------
# Empaquetado multi-lámina
# -------------------------
def pack_maxrects_multi(sheet_w, sheet_h, pieces, kerf=0.003, allow_rotate=True):
    # pieces: list of (id, w, h, qty)
    items = []
    for pid, w, h, qty in pieces:
        for _ in range(qty):
            items.append((pid, w, h))
    # sort by area desc
    items.sort(key=lambda x: x[1]*x[2], reverse=True)
    placements = []
    sheet_index = 1
    while items:
        bin = MaxRectsBin(sheet_w, sheet_h, kerf=kerf)
        i = 0
        placed_any = False
        while i < len(items):
            pid, w, h = items[i]
            res = bin.insert(w, h, pid, allow_rotate=allow_rotate, sheet_index=sheet_index)
            if res is None:
                i += 1
            else:
                placements.append(res)
                items.pop(i)
                placed_any = True
        # if nothing placed (item too big), raise
        if not placed_any:
            # item does not fit in empty sheet => error
            pid, w, h = items[0]
            raise ValueError(f"Pieza demasiado grande para la lámina: ID {pid} {w}x{h} m")
        sheet_index += 1
    # sheet_index was incremented after last used sheet, so num_sheets = sheet_index - 1
    num_sheets = max((p.sheet for p in placements), default=0)
    return placements, num_sheets

# -------------------------
# Dibujar hoja (matplotlib) con desperdicio y piezas
# -------------------------
def plot_sheet_matplotlib(sheet_w, sheet_h, placements, sheet_number, usage, waste):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_xlim(0, sheet_w)
    ax.set_ylim(0, sheet_h)
    ax.set_aspect('equal')
    ax.set_title(f"Lámina {sheet_number}")

    # fondo = área total (gris claro)
    ax.add_patch(patches.Rectangle((0,0), sheet_w, sheet_h, facecolor="#f0f0f0", edgecolor='none'))

    # Dibujar piezas
    for p in [pl for pl in placements if pl.sheet == sheet_number]:
        rect = patches.Rectangle((p.x, p.y), p.w, p.h, linewidth=1, edgecolor='black', facecolor='#5DADE2', alpha=0.9)
        ax.add_patch(rect)
        cx = p.x + p.w/2
        cy = p.y + p.h/2
        ax.text(cx, cy, f"ID{p.rid}\n{fmt_m(p.w)}×{fmt_m(p.h)}m\nR:{'Sí' if p.rotated else 'No'}", ha='center', va='center', fontsize=8)

    # Texto de aprovechamiento/desperdicio
    ax.text(sheet_w*0.98, sheet_h*0.98, f"Aprovechamiento: {usage:.2f}%\nDesperdicio: {waste:.2f}%", ha='right', va='top',
            fontsize=10, bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray'))

    ax.set_xlabel("m"); ax.set_ylabel("m")
    return fig

# -------------------------
# Generar PDF (usa archivo temporal para imagen)
# -------------------------
def generate_pdf(sheet_w, sheet_h, placements, num_sheets, usage, waste):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for s in range(1, num_sheets+1):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"Optimizador de Corte Essenza - Lámina {s}", ln=True, align="C")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, f"Lámina: {fmt_m(sheet_w)} m × {fmt_m(sheet_h)} m", ln=True)
        pdf.cell(0, 8, f"Aprovechamiento: {usage:.2f}%  |  Desperdicio: {waste:.2f}%", ln=True)
        pdf.ln(4)

        # crear figura para esta lámina
        fig = plot_sheet_matplotlib(sheet_w, sheet_h, placements, s, usage, waste)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=200, bbox_inches='tight')
        plt_close_safe(fig)
        buf.seek(0)

        # escribir a temp file con sufijo .png porque fpdf requiere nombre con extensión
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tf:
            tf.write(buf.getvalue())
            tmp_path = tf.name
        pdf.image(tmp_path, x=15, w=180)
        # eliminar archivo temporal
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    # obtener bytes en memoria (fpdf dest='S')
    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    return pdf_bytes

def plt_close_safe(fig):
    try:
        plt.close(fig)
    except Exception:
        pass

# -------------------------
# STREAMLIT UI
# -------------------------
st.set_page_config(page_title="Optimizador de Corte Essenza", layout="wide")
st.title("🪚 Optimizador de Corte Essenza")
st.markdown("Optimiza cortes en láminas (metros). Kerf se aplica solo entre cortes internos.")

col1, col2 = st.columns(2)
with col1:
    sheet_w = st.number_input("Ancho de la lámina (m)", min_value=0.1, value=1.600, step=0.01, format="%.3f")
    sheet_h = st.number_input("Largo de la lámina (m)", min_value=0.1, value=2.400, step=0.01, format="%.3f")
    kerf_mm = st.number_input("Kerf (mm) - pérdida por corte", min_value=0.0, value=3.0, step=0.5)
    kerf = kerf_mm / 1000.0
with col2:
    st.write("Opciones")
    allow_rotate = st.checkbox("Permitir rotación 90° en piezas", value=True)
    st.write("Ingresar tipos de mesones (id, ancho m, largo m, cantidad)")

# tabla simple de entrada
if "rows" not in st.session_state:
    st.session_state.rows = [{"id":1,"w":0.6,"h":1.4,"q":3}]

def add_row():
    cur = st.session_state.rows
    cur.append({"id": len(cur)+1, "w":0.5, "h":1.4, "q":1})
    st.session_state.rows = cur

st.button("Añadir tipo de pieza", on_click=add_row)

# formulario editable
rows = st.session_state.rows
new_rows = []
for i, r in enumerate(rows):
    c1, c2, c3, c4 = st.columns([1,1,1,0.5])
    idv = c1.number_input(f"ID {i+1}", value=r["id"], key=f"id_{i}")
    wv = c2.number_input(f"Ancho (m) {i+1}", value=float(r["w"]), format="%.3f", step=0.01, key=f"w_{i}")
    hv = c3.number_input(f"Largo (m) {i+1}", value=float(r["h"]), format="%.3f", step=0.01, key=f"h_{i}")
    qv = c4.number_input(f"Cantidad {i+1}", value=int(r["q"]), min_value=1, step=1, key=f"q_{i}")
    new_rows.append({"id":int(idv), "w":float(wv), "h":float(hv), "q":int(qv)})
st.session_state.rows = new_rows

# botón calcular
if st.button("Calcular corte (MaxRects)"):
    try:
        pieces = [(r["id"], r["w"], r["h"], r["q"]) for r in st.session_state.rows]
        placements, num_sheets = pack_maxrects_multi(sheet_w, sheet_h, pieces, kerf=kerf, allow_rotate=allow_rotate)
        used_area = sum(p.w * p.h for p in placements)
        total_area = sheet_w * sheet_h * max(1, num_sheets)
        usage = (used_area / total_area) * 100 if total_area > 0 else 0.0
        waste = 100.0 - usage

        st.success(f"Aprovechamiento total: {usage:.2f}%  —  Láminas usadas: {num_sheets}")

        # mostrar cada lámina
        for s in range(1, num_sheets+1):
            fig = plot_sheet_matplotlib(sheet_w, sheet_h, placements, s, usage, waste)
            st.pyplot(fig)
            plt_close_safe(fig)

        # generar PDF
        pdf_bytes = generate_pdf(sheet_w, sheet_h, placements, num_sheets, usage, waste)
        st.download_button("📄 Descargar reporte PDF", data=pdf_bytes, file_name="reporte_corte_essenza.pdf", mime="application/pdf")
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Ocurrió un error: {e}")

