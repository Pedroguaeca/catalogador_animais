# siab_interface_v2.py — SIAB Human Review Interface
# Apple HIG · lê detecções do pipeline (MegaDetector + AI4GAmazonRainforest)

import os, csv as csv_mod, json
from datetime import datetime
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ════════════════════════════════════════════════════════════

FRAMES_DIR   = "frames"
DATASET_DIR  = "dataset"
IMAGES_TRAIN = os.path.join(DATASET_DIR, "images", "train")
LABELS_TRAIN = os.path.join(DATASET_DIR, "labels", "train")
CLASSES_FILE = os.path.join(DATASET_DIR, "classes.txt")
STATS_FILE   = os.path.join(DATASET_DIR, "stats.json")
CSV_PATH     = "resultados/catalogo_animais.csv"

for p in [IMAGES_TRAIN, LABELS_TRAIN, "assets"]:
    os.makedirs(p, exist_ok=True)

st.set_page_config(
    page_title="SIAB · Revisão",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ════════════════════════════════════════════════════════════
# TRADUÇÃO: gênero científico → nome popular em português
# ════════════════════════════════════════════════════════════

_GENUS_MAP_PATH = "genus_map.json"

def _load_genus_map() -> dict:
    if os.path.exists(_GENUS_MAP_PATH):
        with open(_GENUS_MAP_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    return {}

GENUS_MAP = _load_genus_map()


def to_pt(genus: str) -> str:
    return GENUS_MAP.get(genus, {}).get("pt", genus)


def to_en(genus: str) -> str:
    return GENUS_MAP.get(genus, {}).get("en", genus)


# ════════════════════════════════════════════════════════════
# CSS — APPLE HIG LIGHT · sem scroll
# ════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* --- Base --- */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif !important;
    background: #F5F5F7 !important;
    color: #1C1C1E !important;
}
#MainMenu, footer, header { visibility: hidden; }

.block-container {
    padding: 0.5rem 1.25rem 0.25rem !important;
    max-width: 100% !important;
}

/* Reduz espaço entre elementos */
div[data-testid="stVerticalBlock"] > div { margin-bottom: 0 !important; }
div.element-container { margin-bottom: 2px !important; }
div[data-testid="column"] { padding-left: 3px !important; padding-right: 3px !important; }

/* --- Botões base --- */
div.stButton > button {
    border-radius: 10px !important;
    font-weight: 500 !important;
    font-size: 0.8125rem !important;
    height: 34px !important;
    border: none !important;
    width: 100% !important;
    transition: opacity 0.12s !important;
    background: #EBEBF0 !important;
    color: #1C1C1E !important;
    line-height: 1.2 !important;
}
div.stButton > button:hover { opacity: 0.72 !important; }

/* Pill primária (sugestão AI) */
.pill-ai div.stButton > button {
    background: #007AFF !important;
    color: #fff !important;
    border-radius: 17px !important;
    height: 40px !important;
    font-size: 0.875rem !important;
    font-weight: 600 !important;
}

/* Pill secundária */
.pill-std div.stButton > button {
    background: #fff !important;
    color: #1C1C1E !important;
    border: 1.5px solid #D1D1D6 !important;
    border-radius: 17px !important;
    height: 32px !important;
    font-size: 0.8125rem !important;
}

/* Botão pular */
.btn-skip div.stButton > button {
    background: transparent !important;
    color: #8E8E93 !important;
    border: 1px solid #D1D1D6 !important;
    height: 28px !important;
    font-size: 0.75rem !important;
    border-radius: 8px !important;
}

/* Nav */
.nav-btn div.stButton > button {
    background: #fff !important;
    color: #1C1C1E !important;
    border: 1.5px solid #D1D1D6 !important;
    border-radius: 10px !important;
    height: 36px !important;
    font-size: 0.8125rem !important;
}
.nav-btn div.stButton > button:disabled { opacity: 0.3 !important; }

/* Zoom */
.btn-zoom div.stButton > button {
    background: rgba(255,255,255,0.9) !important;
    border: 1.5px solid #D1D1D6 !important;
    border-radius: 8px !important;
    height: 28px !important;
    font-size: 0.75rem !important;
}

/* Input */
.stTextInput input {
    border-radius: 8px !important;
    border: 1.5px solid #D1D1D6 !important;
    background: #fff !important;
    font-size: 0.8125rem !important;
    height: 32px !important;
    padding: 0 8px !important;
    color: #1C1C1E !important;
}

/* Imagem */
.stImage img { border-radius: 10px !important; }

/* Separador */
hr { border: none; border-top: 1px solid #E5E5EA; margin: 4px 0 !important; }

/* Badge AI */
.ai-badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 8px 3px 6px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 600; line-height: 1;
}
.ai-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }

/* Label de seção */
.sec-label {
    font-size: 0.6875rem; font-weight: 700; color: #8E8E93;
    text-transform: uppercase; letter-spacing: 0.06em;
    display: block; margin-bottom: 3px; margin-top: 4px;
}

/* Selectbox */
div[data-testid="stSelectbox"] > div > div {
    border-radius: 8px !important; border: 1.5px solid #D1D1D6 !important;
    background: #fff !important; font-size: 0.875rem !important; min-height: 34px !important;
}

/* Expander */
details summary { font-size: 0.75rem !important; color: #8E8E93 !important; }
details { border: none !important; background: transparent !important; }
div[data-testid="stExpander"] { border: none !important; background: transparent !important; }

/* Metadados do header */
.siab-title { font-size: 1rem; font-weight: 700; color: #1C1C1E; letter-spacing: -0.02em; }
.siab-meta { font-size: 0.75rem; color: #8E8E93; text-align: right; padding-top: 8px; }
.siab-meta b { color: #1C1C1E; }
.green { color: #34C759 !important; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# FUNÇÕES AUXILIARES
# ════════════════════════════════════════════════════════════

def frames_from_csv(csv_path: str, frames_dir: str):
    seen, paths, prefix_map = set(), [], {}
    if not os.path.exists(csv_path):
        return [], {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv_mod.DictReader(f):
            rel = row.get("frame", "")
            if not rel:
                continue
            p = os.path.normpath(os.path.join(frames_dir, rel))
            if p not in seen:
                seen.add(p)
                paths.append(p)
            prefix_map[p] = row.get("video", "")
    return paths, prefix_map


def load_csv_detections(csv_path: str, frames_dir: str) -> dict:
    result = {}
    if not os.path.exists(csv_path):
        return result
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv_mod.DictReader(f):
            rel = row.get("frame", "")
            if not rel:
                continue
            p = os.path.normpath(os.path.join(frames_dir, rel))
            if p not in result:
                result[p] = []
            try:
                x1, y1 = float(row.get("x1") or 0), float(row.get("y1") or 0)
                x2, y2 = float(row.get("x2") or 0), float(row.get("y2") or 0)
            except ValueError:
                x1 = y1 = x2 = y2 = 0.0
            cls_conf = float(row.get("cls_conf") or 0)
            genus = row.get("genero", "Unknown")
            result[p].append({
                "use": True,
                "genus": genus,
                "classe": to_pt(genus),
                "conf": cls_conf,
                "det_conf": float(row.get("det_conf") or 0),
                "cls_conf": cls_conf,
                "xyxy": [x1, y1, x2, y2],
            })
    return result


def read_classes() -> list:
    if not os.path.exists(CLASSES_FILE):
        return []
    with open(CLASSES_FILE, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def write_classes(classes: list) -> list:
    os.makedirs(os.path.dirname(CLASSES_FILE), exist_ok=True)
    ordered = sorted(set(c.strip() for c in classes if c.strip()))
    with open(CLASSES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ordered) + "\n")
    return ordered


def xyxy_to_yolo(x1, y1, x2, y2, W, H):
    bw, bh = max(x2 - x1, 1e-6), max(y2 - y1, 1e-6)
    return (x1 + bw / 2) / W, (y1 + bh / 2) / H, bw / W, bh / H


def draw_boxes(img: Image.Image, dets: list) -> Image.Image:
    img = img.copy()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(14, img.width // 60))
    except Exception:
        font = ImageFont.load_default()
    for d in dets:
        if not d.get("use"):
            continue
        x1, y1, x2, y2 = d["xyxy"]
        if x2 <= x1 or y2 <= y1:
            continue
        c = d.get("cls_conf", 0)
        color = (52, 199, 89) if c >= 0.5 else (255, 149, 0) if c >= 0.3 else (142, 142, 147)
        pt_name = d.get("classe", "")
        genus   = d.get("genus", "")
        label   = f"{pt_name} {c:.0%}" if pt_name == genus else f"{pt_name} ({genus}) {c:.0%}"
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        try:
            bb = draw.textbbox((0, 0), label, font=font)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            pad = 5
            draw.rectangle([x1, max(0, y1 - th - pad * 2), x1 + tw + pad * 2, y1], fill=color)
            draw.text((x1 + pad, y1 - th - pad), label, fill="white", font=font)
        except Exception:
            pass
    return img


def zoom_to_det(img: Image.Image, dets: list, factor: float = 2.2) -> Image.Image:
    if not dets:
        return img
    x1, y1, x2, y2 = dets[0]["xyxy"]
    W, H = img.size
    px = max((x2 - x1) * 0.35, 50)
    py = max((y2 - y1) * 0.35, 50)
    box = (max(0, x1 - px), max(0, y1 - py), min(W, x2 + px), min(H, y2 + py))
    crop = img.crop(box)
    return crop.resize((int(crop.width * factor), int(crop.height * factor)), Image.LANCZOS)


def save_annotation(img_path: str, detections: list, classe_override: str = None):
    os.makedirs(IMAGES_TRAIN, exist_ok=True)
    os.makedirs(LABELS_TRAIN, exist_ok=True)
    base = os.path.splitext(os.path.basename(img_path))[0]
    dest = os.path.join(IMAGES_TRAIN, base + ".jpg")
    pil = Image.open(img_path).convert("RGB")
    pil.save(dest, "JPEG", quality=95)
    W, H = pil.size
    classes = read_classes()
    lines = []
    for d in detections:
        if not d.get("use"):
            continue
        cls_name = (classe_override or d.get("classe", "Desconhecido")).strip()
        if cls_name not in classes:
            classes = write_classes(classes + [cls_name])
        cls_id = classes.index(cls_name)
        x1, y1, x2, y2 = d["xyxy"]
        if x2 <= x1 or y2 <= y1:
            x1, y1, x2, y2 = 0.0, 0.0, float(W), float(H)
        xc, yc, bw, bh = xyxy_to_yolo(x1, y1, x2, y2, W, H)
        lines.append(f"{cls_id} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    with open(os.path.join(LABELS_TRAIN, base + ".txt"), "w") as f:
        f.write("\n".join(lines))
    _update_stats(detections, classe_override)


def _update_stats(detections: list, override: str = None):
    s = _load_stats()
    s["total_annotations"] += 1
    s["last_annotation"] = datetime.now().isoformat()
    for d in detections:
        if d.get("use"):
            cls = override or d.get("classe", "Desconhecido")
            s["class_counts"][cls] = s["class_counts"].get(cls, 0) + 1
    with open(STATS_FILE, "w") as f:
        json.dump(s, f, indent=2)


def _load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE) as f:
            return json.load(f)
    return {"total_annotations": 0, "class_counts": {}, "last_annotation": None}


# ════════════════════════════════════════════════════════════
# CARREGAR DADOS
# ════════════════════════════════════════════════════════════

image_paths, prefix_map = frames_from_csv(CSV_PATH, FRAMES_DIR)

if not image_paths:
    st.title("SIAB · Revisão")
    st.warning("Nenhum frame encontrado. Execute o pipeline primeiro.")
    st.code("conda activate catalogo && python main.py", language="bash")
    st.stop()

csv_dets = load_csv_detections(CSV_PATH, FRAMES_DIR)

_seen_pref: set = set()
prefixes: list = []
for _p in image_paths:
    _pref = prefix_map.get(_p, "")
    if _pref and _pref not in _seen_pref:
        _seen_pref.add(_pref)
        prefixes.append(_pref)

stats = _load_stats()

# ════════════════════════════════════════════════════════════
# ESTADO
# ════════════════════════════════════════════════════════════

for k, v in [("idx", 0), ("selected_prefix", prefixes[0]), ("zoom", False), ("cls_search", "")]:
    if k not in st.session_state:
        st.session_state[k] = v

# ════════════════════════════════════════════════════════════
# HELPERS DE NAVEGAÇÃO
# ════════════════════════════════════════════════════════════

current_prefix = st.session_state.selected_prefix
if current_prefix not in prefixes:
    current_prefix = prefixes[0]
    st.session_state.selected_prefix = current_prefix

prefix_frames = [p for p in image_paths if prefix_map.get(p) == current_prefix]
prefix_idx    = prefixes.index(current_prefix)

current_img_path = image_paths[min(st.session_state.idx, len(image_paths) - 1)]
if prefix_map.get(current_img_path) != current_prefix:
    current_img_path = prefix_frames[0]
    st.session_state.idx = image_paths.index(current_img_path)

local_idx = prefix_frames.index(current_img_path)


def _go(path: str):
    st.session_state.idx = image_paths.index(path)


def go_prev_frame():
    if local_idx > 0:
        _go(prefix_frames[local_idx - 1])


def go_next_frame():
    if local_idx < len(prefix_frames) - 1:
        _go(prefix_frames[local_idx + 1])


def go_prev_video():
    if prefix_idx > 0:
        pref = prefixes[prefix_idx - 1]
        st.session_state.selected_prefix = pref
        _go([p for p in image_paths if prefix_map.get(p) == pref][0])


def go_next_video():
    if prefix_idx < len(prefixes) - 1:
        pref = prefixes[prefix_idx + 1]
        st.session_state.selected_prefix = pref
        _go([p for p in image_paths if prefix_map.get(p) == pref][0])


def save_and_advance(classe: str):
    dets = [d.copy() for d in csv_dets.get(current_img_path, [])]
    if not dets:
        W, H = Image.open(current_img_path).size
        dets = [{"use": True, "genus": classe, "classe": classe,
                 "conf": None, "det_conf": None, "cls_conf": None,
                 "xyxy": [0.0, 0.0, float(W), float(H)]}]
    save_annotation(current_img_path, dets, classe_override=classe)
    go_next_frame()


# ════════════════════════════════════════════════════════════
# HEADER COMPACTO
# ════════════════════════════════════════════════════════════

hc1, hc2, hc3 = st.columns([3, 4, 3])

with hc1:
    st.markdown("<span class='siab-title'>SIAB · Revisão</span>", unsafe_allow_html=True)

with hc2:
    new_pref = st.selectbox("v", prefixes, index=prefix_idx, label_visibility="collapsed")
    if new_pref != current_prefix:
        st.session_state.selected_prefix = new_pref
        _go([p for p in image_paths if prefix_map.get(p) == new_pref][0])
        st.rerun()

with hc3:
    annotated = stats["total_annotations"]
    st.markdown(
        f"<div class='siab-meta'>"
        f"Frame <b>{local_idx + 1}</b>/{len(prefix_frames)}&ensp;"
        f"Vídeo <b>{prefix_idx + 1}</b>/{len(prefixes)}&ensp;"
        f"<span class='green'>{annotated}&nbsp;anotados</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ════════════════════════════════════════════════════════════
# LAYOUT PRINCIPAL
# ════════════════════════════════════════════════════════════

frame_dets = csv_dets.get(current_img_path, [])
col_img, col_ctrl = st.columns([3, 1], gap="small")

# ── Imagem ──────────────────────────────────────────────────
with col_img:
    img_pil = Image.open(current_img_path).convert("RGB")

    if frame_dets:
        img_display = draw_boxes(img_pil, frame_dets)
        if st.session_state.zoom:
            img_display = zoom_to_det(img_display, frame_dets)
    else:
        img_display = img_pil

    st.image(img_display, use_container_width=True)

    info_col, zoom_col = st.columns([10, 1])
    with info_col:
        if frame_dets:
            parts = []
            for d in frame_dets:
                c   = d["cls_conf"]
                hex_c = "#34C759" if c >= 0.5 else "#FF9500" if c >= 0.3 else "#8E8E93"
                sci = d["genus"]
                pt  = d["classe"]
                lbl = f"{pt} ({sci})" if pt != sci else pt
                parts.append(
                    f'<span class="ai-badge" style="background:{hex_c}18;border:1px solid {hex_c}40;">'
                    f'<span class="ai-dot" style="background:{hex_c};"></span>'
                    f'AI · {lbl} · {c:.0%}'
                    f'<span style="color:#8E8E93;font-weight:400;margin-left:4px;">det {d["det_conf"]:.2f}</span>'
                    f'</span>'
                )
            st.markdown("&ensp;".join(parts), unsafe_allow_html=True)
        else:
            st.caption("Nenhuma detecção neste frame.")

    with zoom_col:
        st.markdown('<div class="btn-zoom">', unsafe_allow_html=True)
        if st.button("✕" if st.session_state.zoom else "🔍", key="btn_zoom"):
            st.session_state.zoom = not st.session_state.zoom
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# ── Controles ───────────────────────────────────────────────
with col_ctrl:
    classes = read_classes()
    ai_pt_classes = sorted({to_pt(d["genus"]) for d in frame_dets if d["genus"]})
    all_classes = sorted(set(classes + ai_pt_classes))
    if set(all_classes) != set(classes):
        all_classes = write_classes(all_classes)

    ai_suggestion_pt = to_pt(frame_dets[0]["genus"]) if frame_dets else None

    st.markdown("<span class='sec-label'>Confirmar como</span>", unsafe_allow_html=True)

    search = st.text_input(
        "s", value=st.session_state.cls_search,
        placeholder="🔍  filtrar...",
        label_visibility="collapsed", key="cls_search_input",
    )
    st.session_state.cls_search = search

    filtered = [c for c in all_classes if search.lower() in c.lower()] if search else all_classes

    # Pill primária — linha inteira
    if ai_suggestion_pt and ai_suggestion_pt in filtered:
        genus_hint = frame_dets[0]["genus"] if frame_dets else ""
        suffix = f" ({genus_hint})" if genus_hint != ai_suggestion_pt else ""
        st.markdown('<div class="pill-ai">', unsafe_allow_html=True)
        if st.button(f"✓  {ai_suggestion_pt}{suffix}", key="pill_ai_primary"):
            save_and_advance(ai_suggestion_pt)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    # Restante em grid 2 colunas
    others = [c for c in filtered if c != ai_suggestion_pt]
    cols2 = st.columns(2)
    for i, cls in enumerate(others):
        with cols2[i % 2]:
            st.markdown('<div class="pill-std">', unsafe_allow_html=True)
            if st.button(cls, key=f"pill_{cls}_{i}"):
                save_and_advance(cls)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    # Nova categoria em expander
    with st.expander("＋  Nova categoria"):
        new_cls = st.text_input(
            "Nome", placeholder="ex: Veado", label_visibility="collapsed", key="new_cls_input"
        )
        if st.button("Adicionar", key="btn_add_cls") and new_cls.strip():
            write_classes(all_classes + [new_cls.strip()])
            st.session_state.cls_search = ""
            st.rerun()

    st.markdown('<div class="btn-skip">', unsafe_allow_html=True)
    if st.button("Pular frame →", key="btn_skip"):
        go_next_frame()
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# BARRA DE NAVEGAÇÃO
# ════════════════════════════════════════════════════════════

st.markdown("<hr>", unsafe_allow_html=True)
n1, n2, n3, n4 = st.columns(4)

for col, label, fn, disabled, key in [
    (n1, "◀◀  Vídeo anterior",  go_prev_video, prefix_idx == 0,                     "nav_pv"),
    (n2, "◀  Frame anterior",   go_prev_frame, local_idx == 0,                      "nav_pf"),
    (n3, "Frame seguinte  ▶",   go_next_frame, local_idx == len(prefix_frames) - 1, "nav_nf"),
    (n4, "Vídeo seguinte  ▶▶",  go_next_video, prefix_idx == len(prefixes) - 1,     "nav_nv"),
]:
    with col:
        st.markdown('<div class="nav-btn">', unsafe_allow_html=True)
        if st.button(label, key=key, disabled=disabled):
            fn()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
