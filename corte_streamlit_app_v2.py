# corte_streamlit_app_v3.py
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib import cm
from fpdf import FPDF
import io, os, tempfile, math, random

# -------------------------
# Utilidades
# -------------------------
def fmt_m(x):
    return f"{x:.3f}"

def plt_close_safe(fig):
    try:
        plt.close(fig)
    except Exception:
        pass

# -------------------------
# MaxRects (BSSF) implementation (same robust version)
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
        if used.x >= free.x + free.w - 1e-12 or used.x + used.w <= free.x + 1e-12 or used.y >= free.y + free.h - 1e-12 or used.y + used.h <= free.y + 1e-12:
            return [free]
        if used.x > free.x + 1e-12:
            out.append(FreeRect(free.x, free.y, used.x - free.x, free.h))
        if used.x + used.w < free.x + free.w - 1e-12:
            out.append(FreeRect(used.x + used.w, free.y, free.x + free.w - (used.x + used.w), free.h))
        if used.y > free.y + 1e-12:
            out.append(FreeRect(free.x, free.y, free.w, used.y - free.y))
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
        best = None
        best_free = None
        best_rot = False
        for fr in self.free_rects:
            for rot in ([False, True] if allow_rotate else [False]):
                rw = w if not rot else h
                rh = h if not rot else w
                kerf_x = self.kerf if (fr.x + rw) < self.width - 1e-12 else 0.0
                kerf_y = self.kerf if (fr.y + rh) < self.height - 1e-12 else 0.0
                occ_w = round((rw + kerf_x) / 0.001) * 0.001
                occ_h = round((rh + kerf_y) / 0.001) * 0.001
                if occ_w <= fr.w + 1e-12 and occ_h <= fr.h + 1e-12:
                    score = self._score_bssf(fr, occ_w, occ_h)
                    if best is None or score < best:
                        best = score
                        best_free = fr
                        best_rot = rot
        if best_free is None:
            return None
        rw = w if not best_rot else h
        rh = h if not best_rot else w
        placed_x = best_free.x
        placed_y = best_free.y
        kerf_x = self.kerf if (placed_x + rw) < self.width - 1e-12 else 0.0
        kerf_y = self.kerf if (placed_y + rh) < self.height - 1e-12 else 0.0
        occ_w = round((rw + kerf_x) / 0.001) * 0.001
        occ_h = round((rh + kerf_y) / 0.001) * 0.001
        used = FreeRect(placed_x, placed_y, occ_w, occ_h)
        new_free = []
        for fr in self.free_rects:
            new_free.extend(self._split_free(fr, used))
        self.free_rects = new_free
        self._prune_free()
        placement = Placement(sheet_index, placed_x, placed_y, rw, rh, rid, best_rot)
        self.placements.append(placement)
        return placement

def pack_maxrects_multi(sheet_w, sheet_h, pieces, kerf=0.003, allow_rotate=True):
    items = []
    for pid, w, h, qty in pieces:
        for _ in range(qty):
            items.append((pid, w, h))
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
        if not placed_any:
            pid, w, h = items[0]
            raise ValueError(f"Pieza demasiado grande para la lámina: ID {pid} {fmt_m(w)}x{fmt_m(h)} m")
        sheet_index += 1
    num_sheets = max((p.sheet for p in placements), default=0)
    return placements, num_sheets

# -------------------------
# Dibujo & resumen por lámina (pantalla y PDF)
# -------------------------
def plot_sheet_matplotlib(sheet_w, sheet_h, placements, sheet_number, id_color_map):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_xlim(0, sheet_w)
    ax.set_ylim(0, sheet_h)
    ax.set_aspect('equal')
    ax.set_title(f"Lámina {sheet_number}")

    # fondo = área total (gris claro)
    ax.add_patch(patches.Rectangle((0,0), sheet_w, sheet_h, facecolor="#f0f0f0", edgecolor='none'))

    # dibujar piezas coloreadas por id
    for p in [pl for pl in placements if pl.sheet == sheet_number]:
        color = id_color_map.get(p.rid, (0.36, 0.67, 0.94))
        rect = patches.Rectangle((p.x, p.y), p.w, p.h, linewidth=1, edgecolor='black', facecolor=color, alpha=0.9)
        ax.add_patch(rect)
        cx = p.x + p.w/2
        cy = p.y + p.h/2
        ax.text(cx, cy, f"ID{p.rid}\n{fmt_m(p.w)}×{fmt_m(p.h)}m\nR:{'Sí' if p.rotated else 'No'}",
                ha='center', va='center', fontsize=8, color='black')

    ax.set_xlabel("m"); ax.set_ylabel("m")
    return fig

def summary_per_sheet(placements, sheet_number):
    # returns list of dicts: {id, count, total_area, w,h sample}
    by_id = {}
    for p in placements:
        if p.sheet != sheet_number: continue
        by_id.setdefault(p.rid, {'count':0, 'area':0.0, 'w':p.w, 'h':p.h})
        by_id[p.rid]['count'] += 1
        by_id[p.rid]['area'] += p.w * p.h
    rows = []
    for rid, v in by_id.items():
        rows.append({'id': rid, 'count': v['count'], 'area_m2': v['area'], 'w': v['w'], 'h': v['h']})
    rows.sort(key=lambda r: r['id'])
    return rows

# -------------------------
# PDF generation (temp images)
# -------------------------
def generate_pdf_report(sheet_w, sheet_h, placements, num_sheets, usage, waste, id_color_map):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    for s in range(1, num_sheets+1):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"Optimizador de Corte Essenza - Lámina {s}", ln=True, align="C")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, f"Lámina: {fmt_m(sheet_w)} m × {fmt_m(sheet_h)} m", ln=True)
        pdf.cell(0, 8, f"Aprovechamiento: {usage:.2f}%  |  Desperdicio: {waste:.2f}%", ln=True)
        pdf.ln(4)

        # figura
        fig = plot_sheet_matplotlib(sheet_w, sheet_h, placements, s, id_color_map)
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=200, bbox_inches='tight')
        plt_close_safe(fig)
        buf.seek(0)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tf:
            tf.write(buf.getvalue()); tmp_path = tf.name
        pdf.image(tmp_path, x=15, w=180)
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        pdf.ln(6)
        # resumen por id
        rows = summary_per_sheet(placements, s)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(40, 8, "ID", 1, 0, "C")
        pdf.cell(50, 8, "Medidas (m)", 1, 0, "C")
        pdf.cell(40, 8, "Cantidad", 1, 0, "C")
        pdf.cell(50, 8, "Área (m²)", 1, 1, "C")
        pdf.set_font("Helvetica", "", 10)
        for r in rows:
            pdf.cell(40, 8, str(r['id']), 1, 0, "C")
            pdf.cell(50, 8, f"{fmt_m(r['w'])}×{fmt_m(r['h'])}", 1, 0, "C")
            pdf.cell(40, 8, str(r['count']), 1, 0, "C")
            pdf.cell(50, 8, f"{r['area_m2']:.3f}", 1, 1, "C")

    return pdf.output(dest='S').encode('latin-1')

# -------------------------
# STREAMLIT UI
# -------------------------
st.set_page_config(page_title="Optimizador de Corte Essenza", layout="wide")
st.title("🪚 Optimizador de Corte Essenza")
st.markdown("Optimiza cortes en láminas (metros). Kerf se aplica solo entre cortes internos.")

col1, col2 = st.columns([1, 0.6])
with col1:
    sheet_w = st.number_input("Ancho de la lámina (m)", min_value=0.1, value=1.600, step=0.01, format="%.3f")
    sheet_h = st.number_input("Largo de la lámina (m)", min_value=0.1, value=2.400, step=0.01, format="%.3f")
    kerf_mm = st.number_input("Kerf (mm) - pérdida por corte", min_value=0.0, value=3.0, step=0.5)
    kerf = kerf_mm / 1000.0
with col2:
    allow_rotate = st.checkbox("Permitir rotación 90° en piezas", value=True)
    st.markdown("**Ingresar tipos de mesones (id, ancho m, largo m, cantidad)**")

if "rows" not in st.session_state:
    st.session_state.rows = [{"id":1,"w":1.2,"h":0.6,"q":3}]

def add_row(): 
    cur = st.session_state.rows
    cur.append({"id": len(cur)+1, "w":0.5, "h":1.4, "q":1})
    st.session_state.rows = cur

st.button("Añadir tipo de pieza", on_click=add_row)

rows = st.session_state.rows
new_rows = []
for i, r in enumerate(rows):
    a,b,c,d = st.columns([0.9,1,1,0.6])
    idv = a.number_input(f"ID {i+1}", value=r["id"], key=f"id_{i}")
    wv = b.number_input(f"Ancho (m) {i+1}", value=float(r["w"]), format="%.3f", step=0.01, key=f"w_{i}")
    hv = c.number_input(f"Largo (m) {i+1}", value=float(r["h"]), format="%.3f", step=0.01, key=f"h_{i}")
    qv = d.number_input(f"Qty {i+1}", value=int(r["q"]), min_value=1, step=1, key=f"q_{i}")
    new_rows.append({"id":int(idv), "w":float(wv), "h":float(hv), "q":int(qv)})
st.session_state.rows = new_rows

# calcular
if st.button("Calcular corte (MaxRects)"):
    try:
        pieces = [(r["id"], r["w"], r["h"], r["q"]) for r in st.session_state.rows]
        # compute unique ids and color map
        unique_ids = sorted({r["id"] for r in st.session_state.rows})
        cmap = cm.get_cmap('tab20', max(3, len(unique_ids)))
        id_color_map = {}
        for idx, rid in enumerate(unique_ids):
            rgba = cmap(idx)  # returns rgba in 0..1
            id_color_map[rid] = (rgba[0], rgba[1], rgba[2])

        placements, num_sheets = pack_maxrects_multi(sheet_w, sheet_h, pieces, kerf=kerf, allow_rotate=allow_rotate)
        used_area = sum(p.w * p.h for p in placements)
        total_area = sheet_w * sheet_h * max(1, num_sheets)
        usage = (used_area / total_area) * 100 if total_area > 0 else 0.0
        waste = 100.0 - usage

        st.success(f"Aprovechamiento total: {usage:.2f}%  —  Láminas usadas: {num_sheets}")

        # Mostrar por lámina con resumen (tabla)
        for s in range(1, num_sheets+1):
            fig = plot_sheet_matplotlib(sheet_w, sheet_h, placements, s, id_color_map)
            st.pyplot(fig)
            plt_close_safe(fig)

            # resumen por lámina (tabla)
            rows_summary = summary_per_sheet(placements, s)
            if rows_summary:
                st.markdown(f"**Resumen - Lámina {s}**")
                st.table([{
                    "ID": r["id"],
                    "Medidas (m)": f"{fmt_m(r['w'])} × {fmt_m(r['h'])}",
                    "Cantidad en lámina": r["count"],
                    "Área total (m²)": f"{r['area_m2']:.3f}"
                } for r in rows_summary])
            else:
                st.info(f"Lámina {s} no tiene piezas asignadas.")

            # mostrar aprovechamiento/desperdicio fuera del gráfico
            st.write(f"**Aprovechamiento (lámina {s}):** {usage:.2f}%  —  **Desperdicio:** {waste:.2f}%")
            st.markdown("---")

        # PDF (una página por lámina con su resumen)
        pdf_bytes = generate_pdf_report(sheet_w, sheet_h, placements, num_sheets, usage, waste, id_color_map)
        st.download_button("📄 Descargar reporte PDF", data=pdf_bytes, file_name="reporte_corte_essenza.pdf", mime="application/pdf")

    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Ocurrió un error: {e}")
