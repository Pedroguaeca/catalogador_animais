# interface_v2.py
# SIAB - Sistema de Identificação de Animais BR
# Interface moderna estilo iOS minimalista

import os, glob, json
from typing import List, Dict
from datetime import datetime
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CONFIGURAÇÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FRAMES_DIR = "frames"
DATASET_DIR = "dataset"
IMAGES_TRAIN = os.path.join(DATASET_DIR, "images", "train")
LABELS_TRAIN = os.path.join(DATASET_DIR, "labels", "train")
CLASSES_FILE = os.path.join(DATASET_DIR, "classes.txt")
STATS_FILE = os.path.join(DATASET_DIR, "stats.json")
UPLOAD_DIR = "videos/uploaded"

for p in [IMAGES_TRAIN, LABELS_TRAIN, UPLOAD_DIR, "assets"]:
    os.makedirs(p, exist_ok=True)

st.set_page_config(
    page_title="SIAB - Sistema de Identificação de Animais BR",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CSS MINIMALISTA ESTILO iOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.markdown("""
<style>
    /* ===== Cores e Variáveis ===== */
    :root {
        --primary: #007AFF;
        --secondary: #5856D6;
        --success: #34C759;
        --warning: #FF9500;
        --danger: #FF3B30;
        --gray-1: #F2F2F7;
        --gray-2: #E5E5EA;
        --gray-3: #C7C7CC;
        --gray-4: #8E8E93;
        --text-primary: #000000;
        --text-secondary: #6C6C70;
        --radius-sm: 8px;
        --radius-md: 12px;
        --radius-lg: 16px;
        --shadow: 0 2px 8px rgba(0,0,0,0.08);
        --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    /* ===== Reset e Base ===== */
    .main .block-container {
        max-width: 1600px;
        padding: 1rem 2rem 2rem 2rem;
    }
    
    /* Remove elementos padrão do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* ===== Typography ===== */
    h1, h2, h3 {
        font-weight: 600 !important;
        color: var(--text-primary) !important;
        letter-spacing: -0.02em;
    }
    
    h1 { font-size: 2rem !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 1.5rem !important; margin-bottom: 0.75rem !important; }
    h3 { font-size: 1.125rem !important; margin-bottom: 0.5rem !important; }
    
    /* ===== Cards ===== */
    .card {
        background: white;
        border-radius: var(--radius-md);
        padding: 1.25rem;
        box-shadow: var(--shadow);
        border: 1px solid var(--gray-2);
        margin-bottom: 1rem;
    }
    
    .card-header {
        font-size: 0.875rem;
        font-weight: 600;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.75rem;
    }
    
    /* ===== Botões ===== */
    div.stButton > button {
        height: 44px;
        border-radius: var(--radius-md);
        border: none;
        font-weight: 500;
        font-size: 0.9375rem;
        transition: var(--transition);
        box-shadow: var(--shadow);
    }
    
    div.stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    }
    
    /* Botão primário */
    .btn-primary button {
        background: var(--primary) !important;
        color: white !important;
    }
    
    .btn-primary button:hover {
        background: #0051D5 !important;
    }
    
    /* Botão sucesso */
    .btn-success button {
        background: var(--success) !important;
        color: white !important;
    }
    
    /* Botão secundário */
    .btn-secondary button {
        background: var(--gray-1) !important;
        color: var(--text-primary) !important;
    }
    
    /* Botão perigo */
    .btn-danger button {
        background: var(--danger) !important;
        color: white !important;
    }
    
    /* ===== Inputs ===== */
    .stTextInput input, .stSelectbox select, .stNumberInput input {
        border-radius: var(--radius-md) !important;
        border: 1px solid var(--gray-2) !important;
        padding: 0.75rem !important;
        font-size: 0.9375rem !important;
        transition: var(--transition) !important;
    }
    
    .stTextInput input:focus, .stSelectbox select:focus {
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 3px rgba(0,122,255,0.1) !important;
    }
    
    /* ===== Imagem Principal ===== */
    .image-container {
        background: white;
        border-radius: var(--radius-lg);
        padding: 1rem;
        box-shadow: var(--shadow);
        border: 1px solid var(--gray-2);
        position: relative;
        overflow: hidden;
    }
    
    .image-container img {
        border-radius: var(--radius-md);
        width: 100%;
        height: auto;
        max-height: 70vh;
        object-fit: contain;
    }
    
    /* ===== Stats Cards ===== */
    .stat-card {
        background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
        color: white;
        padding: 1rem;
        border-radius: var(--radius-md);
        text-align: center;
        box-shadow: var(--shadow);
    }
    
    .stat-value {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    
    .stat-label {
        font-size: 0.75rem;
        opacity: 0.9;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* ===== Badges ===== */
    .badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    
    .badge-primary { background: var(--primary); color: white; }
    .badge-success { background: var(--success); color: white; }
    .badge-warning { background: var(--warning); color: white; }
    .badge-secondary { background: var(--gray-2); color: var(--text-primary); }
    
    /* ===== Sidebar ===== */
    [data-testid="stSidebar"] {
        background: var(--gray-1);
        padding: 1.5rem 1rem;
    }
    
    [data-testid="stSidebar"] .stButton button {
        width: 100%;
    }
    
    /* ===== Expander ===== */
    .streamlit-expanderHeader {
        background: var(--gray-1);
        border-radius: var(--radius-md);
        font-weight: 500;
    }
    
    /* ===== Slider ===== */
    .stSlider > div > div > div {
        background: var(--primary);
    }
    
    /* ===== Checkbox ===== */
    .stCheckbox {
        font-size: 0.9375rem;
    }
    
    /* ===== Divider ===== */
    hr {
        margin: 1.5rem 0;
        border: none;
        border-top: 1px solid var(--gray-2);
    }
    
    /* ===== Info boxes ===== */
    .stAlert {
        border-radius: var(--radius-md);
        border: none;
        box-shadow: var(--shadow);
    }
    
    /* ===== Progress bar ===== */
    .stProgress > div > div {
        background: var(--primary);
        border-radius: 8px;
    }
    
    /* ===== Miniatura preview ===== */
    .thumbnail {
        border-radius: var(--radius-sm);
        border: 2px solid transparent;
        transition: var(--transition);
        cursor: pointer;
    }
    
    .thumbnail:hover {
        border-color: var(--primary);
        transform: scale(1.05);
    }
    
    .thumbnail.active {
        border-color: var(--primary);
        box-shadow: 0 0 0 3px rgba(0,122,255,0.2);
    }
    
    /* ===== Keyboard hints ===== */
    .kbd {
        display: inline-block;
        padding: 0.2rem 0.5rem;
        background: var(--gray-1);
        border: 1px solid var(--gray-3);
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.75rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FUNÇÕES AUXILIARES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def list_images(frames_dir: str):
    """Lista todas as imagens nos formatos suportados"""
    imgs = sorted(glob.glob(os.path.join(frames_dir, "**", "*.jpg"), recursive=True))
    imgs += sorted(glob.glob(os.path.join(frames_dir, "**", "*.png"), recursive=True))
    imgs += sorted(glob.glob(os.path.join(frames_dir, "**", "*.jpeg"), recursive=True))
    return imgs

def base_prefix_for_frame(path: str) -> str:
    """Extrai o prefixo do vídeo do nome do arquivo"""
    base = os.path.splitext(os.path.basename(path))[0]
    parts = base.split("_frame_")
    return parts[0] if parts else base

def video_prefixes(image_paths):
    """Lista todos os prefixos únicos de vídeos"""
    return sorted({base_prefix_for_frame(p) for p in image_paths})

def read_classes(path: str):
    """Lê o arquivo de classes"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        classes = [ln.strip().lower() for ln in f if ln.strip()]
    return sorted(set(classes))

def write_classes(path: str, classes):
    """Escreve o arquivo de classes"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ordered = sorted(set([c.strip().lower() for c in classes if c.strip()]))
    with open(path, "w", encoding="utf-8") as f:
        for c in ordered:
            f.write(c + "\n")
    return ordered

def class_id_for(name: str, classes):
    """Retorna o ID numérico de uma classe"""
    ordered = sorted(set(classes + [name.strip().lower()]))
    return ordered.index(name.strip().lower())

def xyxy_to_yolo(x1, y1, x2, y2, w, h):
    """Converte coordenadas xyxy para formato YOLO"""
    bw = max(x2 - x1, 1e-6)
    bh = max(y2 - y1, 1e-6)
    cx = x1 + bw / 2.0
    cy = y1 + bh / 2.0
    return cx / w, cy / h, bw / w, bh / h

def draw_boxes(img_pil: Image.Image, dets: List[Dict], show_conf: bool = True) -> Image.Image:
    """Desenha bounding boxes na imagem"""
    img = img_pil.copy()
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("Arial.ttf", size=max(14, img.width // 50))
    except:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=max(14, img.width // 50))
        except:
            font = ImageFont.load_default()
    
    colors = {
        'default': '#34C759',
        'selected': '#007AFF',
        'disabled': '#8E8E93'
    }
    
    for d in dets:
        if not d.get("use", True):
            continue
            
        x1, y1, x2, y2 = d["xyxy"]
        label = d.get("classe", "obj")
        conf = d.get("conf", None)
        
        # Escolhe a cor
        color_hex = colors['selected'] if d.get('selected', False) else colors['default']
        color = tuple(int(color_hex[i:i+2], 16) for i in (1, 3, 5))
        
        # Label com confiança
        if conf is not None and show_conf:
            label = f"{label} {conf:.2f}"
        
        # Desenha o retângulo
        draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
        
        # Desenha o label
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Background do texto
        padding = 6
        label_bg = [
            x1,
            max(0, y1 - text_height - padding * 2),
            x1 + text_width + padding * 2,
            y1
        ]
        draw.rectangle(label_bg, fill=color)
        draw.text(
            (x1 + padding, y1 - text_height - padding),
            label,
            fill='white',
            font=font
        )
    
    return img

@st.cache_resource
def load_model_cached(model_path: str):
    """Carrega o modelo YOLO (com cache)"""
    return YOLO(model_path)

def infer_image(model: YOLO, img_path: str, conf: float, iou: float):
    """Realiza inferência em uma imagem"""
    res = model.predict(img_path, conf=conf, iou=iou, imgsz=960, verbose=False)
    dets = []
    
    if res and res[0].boxes is not None:
        r = res[0]
        names = r.names
        
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf_f = float(box.conf[0])
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            
            dets.append({
                "use": True,
                "classe": names[cls_id],
                "conf": conf_f,
                "xyxy": [x1, y1, x2, y2]
            })
    
    return dets

def save_annotation(img_path: str, detections: List[Dict]):
    """Salva a anotação no formato YOLO"""
    os.makedirs(IMAGES_TRAIN, exist_ok=True)
    os.makedirs(LABELS_TRAIN, exist_ok=True)
    
    base = os.path.splitext(os.path.basename(img_path))[0]
    dest_img_path = os.path.join(IMAGES_TRAIN, base + ".jpg")
    
    # Salva imagem
    Image.open(img_path).convert("RGB").save(dest_img_path, "JPEG", quality=95)
    
    # Prepara anotações
    W, H = Image.open(dest_img_path).size
    classes_current = read_classes(CLASSES_FILE)
    lines = []
    
    for d in detections:
        if not d.get("use"):
            continue
            
        cls_name = d["classe"].strip().lower()
        cls_id = class_id_for(cls_name, classes_current)
        x1, y1, x2, y2 = d["xyxy"]
        x_center, y_center, w_norm, h_norm = xyxy_to_yolo(x1, y1, x2, y2, W, H)
        lines.append(f"{cls_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")
    
    # Salva arquivo de label
    with open(os.path.join(LABELS_TRAIN, base + ".txt"), "w") as f:
        f.write("\n".join(lines))
    
    # Atualiza estatísticas
    update_stats(detections)
    
    return dest_img_path

def update_stats(detections: List[Dict]):
    """Atualiza estatísticas de anotação"""
    stats = load_stats()
    
    stats['total_annotations'] += 1
    stats['last_annotation'] = datetime.now().isoformat()
    
    for d in detections:
        if d.get("use"):
            cls = d["classe"]
            stats['class_counts'][cls] = stats['class_counts'].get(cls, 0) + 1
    
    save_stats(stats)

def load_stats():
    """Carrega estatísticas"""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    return {
        'total_annotations': 0,
        'class_counts': {},
        'last_annotation': None
    }

def save_stats(stats):
    """Salva estatísticas"""
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

def fake_fullbox_detection(img_path: str, classe: str):
    """Cria uma detecção com bounding box cobrindo toda a imagem"""
    img = Image.open(img_path)
    w, h = img.size
    return [{
        "use": True,
        "classe": classe,
        "conf": None,
        "xyxy": [0.0, 0.0, float(w), float(h)]
    }]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARREGAR DADOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

image_paths = list_images(FRAMES_DIR)

if not image_paths:
    st.title("🐾 SIAB - Sistema de Identificação de Animais BR")
    st.warning("⚠️ Nenhuma imagem encontrada em `frames/`. Faça upload de vídeos para começar.")
    
    with st.expander("📤 Upload de Vídeos", expanded=True):
        files = st.file_uploader(
            "Envie vídeos para processar",
            type=["mp4", "avi", "mov", "mkv"],
            accept_multiple_files=True
        )
        
        if files:
            for f in files:
                out = os.path.join(UPLOAD_DIR, f.name)
                with open(out, "wb") as w:
                    w.write(f.getbuffer())
            st.success(f"✅ {len(files)} vídeo(s) salvo(s) em `{UPLOAD_DIR}`")
            st.info("💡 Agora execute seu pipeline para gerar os frames.")
    
    st.stop()

prefixes = video_prefixes(image_paths)
stats = load_stats()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ESTADO DA SESSÃO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if "selected_prefix" not in st.session_state:
    st.session_state.selected_prefix = prefixes[0]

if "idx" not in st.session_state:
    firsts = [p for p in image_paths if base_prefix_for_frame(p) == st.session_state.selected_prefix]
    st.session_state.idx = image_paths.index(firsts[0])

if "selected_class" not in st.session_state:
    classes_init = read_classes(CLASSES_FILE)
    st.session_state.selected_class = classes_init[0] if classes_init else ""

if "show_detections" not in st.session_state:
    st.session_state.show_detections = True

if "zoom_level" not in st.session_state:
    st.session_state.zoom_level = 1.0

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIDEBAR - ESTATÍSTICAS E CONTROLES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with st.sidebar:
    st.title("🐾 SIAB")
    st.caption("Sistema de Identificação de Animais BR")
    
    st.divider()
    
    # Estatísticas
    st.markdown("### 📊 Estatísticas")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-value">{stats['total_annotations']}</div>
            <div class="stat-label">Anotações</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        classes_count = len(stats['class_counts'])
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #34C759 0%, #30D158 100%);">
            <div class="stat-value">{classes_count}</div>
            <div class="stat-label">Classes</div>
        </div>
        """, unsafe_allow_html=True)
    
    if stats['class_counts']:
        st.markdown("#### Top Classes")
        sorted_classes = sorted(stats['class_counts'].items(), key=lambda x: x[1], reverse=True)[:5]
        for cls, count in sorted_classes:
            st.markdown(f"**{cls}**: {count} anotações")
    
    st.divider()
    
    # Configurações de detecção
    st.markdown("### ⚙️ Detecção")
    
    conf_thres = st.slider(
        "Confiança mínima",
        0.0, 1.0, 0.25, 0.05,
        help="Threshold de confiança para detecções"
    )
    
    iou_thres = st.slider(
        "IoU (NMS)",
        0.1, 1.0, 0.7, 0.05,
        help="Threshold de IoU para Non-Maximum Suppression"
    )
    
    st.session_state.show_detections = st.checkbox(
        "Mostrar detecções",
        value=st.session_state.show_detections
    )
    
    st.divider()
    
    # Opções avançadas
    with st.expander("🔧 Opções Avançadas"):
        apply_all_frames = st.checkbox(
            "Aplicar a todos os frames do vídeo",
            value=False,
            help="Aplica a categoria selecionada a todos os frames do vídeo atual"
        )
        
        allow_force = st.checkbox(
            "Permitir salvar sem detecção",
            value=False,
            help="Cria uma bbox cobrindo toda a imagem quando não há detecções"
        )
    
    st.divider()
    
    # Atalhos
    st.markdown("### ⌨️ Atalhos")
    st.markdown("""
    <div style="font-size: 0.875rem; color: var(--text-secondary);">
        <span class="kbd">←</span> Voltar<br>
        <span class="kbd">→</span> Próximo frame<br>
        <span class="kbd">⏎</span> Salvar & próximo<br>
        <span class="kbd">Espaço</span> Pular vídeo
    </div>
    """, unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HEADER PRINCIPAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

col_logo, col_title = st.columns([1, 11])

with col_logo:
    for ext in ("png", "jpg", "jpeg"):
        logo_path = f"assets/logo.{ext}"
        if os.path.exists(logo_path):
            st.image(logo_path, width=60)
            break

with col_title:
    st.title("Sistema de Identificação de Animais BR")
    progress_text = f"Frame {st.session_state.idx + 1} de {len(image_paths)}"
    progress_pct = (st.session_state.idx + 1) / len(image_paths)
    st.progress(progress_pct, text=progress_text)

st.divider()

CSV_PATH = "resultados/catalogo_animais.csv"


def load_csv_detections(csv_path: str) -> dict:
    """Carrega o CSV do pipeline → {frame_abs: [{classe, det_conf, cls_conf, conf, xyxy, use}]}"""
    import csv as csv_mod
    result: dict = {}
    if not os.path.exists(csv_path):
        return result
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv_mod.DictReader(f):
            frame_rel = row.get("frame", "")
            if not frame_rel:
                continue
            frame_abs = os.path.join(FRAMES_DIR, frame_rel)
            if frame_abs not in result:
                result[frame_abs] = []
            try:
                x1, y1, x2, y2 = float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])
            except (KeyError, ValueError):
                x1 = y1 = x2 = y2 = 0.0
            cls_conf = float(row.get("cls_conf") or 0)
            result[frame_abs].append({
                "use": True,
                "classe": row.get("genero", "Unknown"),
                "det_conf": float(row.get("det_conf") or 0),
                "cls_conf": cls_conf,
                "conf": cls_conf,           # compatível com draw_boxes
                "xyxy": [x1, y1, x2, y2],
            })
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CARREGAR DETECÇÕES E FILTRAR CROPS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Exclui recortes (crops) da navegação — só frames completos
image_paths = [p for p in image_paths if "/crops/" not in p and "\\crops\\" not in p]
prefixes = video_prefixes(image_paths)

csv_dets = load_csv_detections(CSV_PATH)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SELEÇÃO DE VÍDEO E CLASSE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

sel_col1, sel_col2, sel_col3 = st.columns([3, 3, 2])

with sel_col1:
    new_prefix = st.selectbox(
        "Vídeo",
        prefixes,
        index=prefixes.index(st.session_state.selected_prefix)
        if st.session_state.selected_prefix in prefixes else 0,
        label_visibility="collapsed",
    )
    if new_prefix != st.session_state.selected_prefix:
        st.session_state.selected_prefix = new_prefix
        firsts = [p for p in image_paths if base_prefix_for_frame(p) == new_prefix]
        st.session_state.idx = image_paths.index(firsts[0]) if firsts else 0
        st.rerun()

with sel_col2:
    classes_list = read_classes(CLASSES_FILE)
    # Garante que gêneros do AI estejam disponíveis para anotação
    ai_genera = sorted({d["classe"] for dets in csv_dets.values() for d in dets if d["classe"] != "Unknown"})
    merged_classes = sorted(set(classes_list + ai_genera))
    if merged_classes != classes_list:
        write_classes(CLASSES_FILE, merged_classes)
        classes_list = merged_classes

    current_frame_dets = csv_dets.get(image_paths[st.session_state.idx], [])
    ai_suggestion = current_frame_dets[0]["classe"] if current_frame_dets else (classes_list[0] if classes_list else "")
    default_idx = classes_list.index(ai_suggestion) if ai_suggestion in classes_list else 0

    selected_class = st.selectbox(
        "Classe",
        classes_list if classes_list else ["(sem classes — adicione em dataset/classes.txt)"],
        index=default_idx,
        label_visibility="collapsed",
    )
    st.session_state.selected_class = selected_class

with sel_col3:
    new_class_input = st.text_input("Nova classe", placeholder="ex: veado", label_visibility="collapsed")
    if new_class_input.strip():
        classes_list = write_classes(CLASSES_FILE, classes_list + [new_class_input.strip()])
        st.rerun()

st.divider()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FRAME ATUAL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

current_prefix = st.session_state.selected_prefix
prefix_frames = [p for p in image_paths if base_prefix_for_frame(p) == current_prefix]

if not prefix_frames:
    st.warning("Nenhum frame para este vídeo.")
    st.stop()

# Garante que idx aponta para um frame deste vídeo
if image_paths[st.session_state.idx] not in prefix_frames:
    st.session_state.idx = image_paths.index(prefix_frames[0])

current_img_path = image_paths[st.session_state.idx]
local_idx = prefix_frames.index(current_img_path)

col_img, col_ctrl = st.columns([7, 3])

with col_img:
    img_pil = Image.open(current_img_path).convert("RGB")
    frame_dets = csv_dets.get(current_img_path, [])

    if st.session_state.show_detections and frame_dets:
        img_display = draw_boxes(img_pil, frame_dets, show_conf=True)
    else:
        img_display = img_pil

    st.image(img_display, use_container_width=True)

    # Info do AI sob a imagem
    if frame_dets:
        for i, d in enumerate(frame_dets):
            badge_color = "#34C759" if d["cls_conf"] >= 0.5 else "#FF9500" if d["cls_conf"] >= 0.3 else "#8E8E93"
            st.markdown(
                f'<span style="background:{badge_color};color:white;padding:3px 10px;'
                f'border-radius:12px;font-size:0.8rem;font-weight:600;margin-right:6px;">'
                f'AI: {d["classe"]}</span>'
                f'<span style="font-size:0.8rem;color:#6C6C70;">'
                f'det {d["det_conf"]:.2f} · cls {d["cls_conf"]:.2f}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("Nenhuma detecção do pipeline neste frame.")

with col_ctrl:
    st.markdown(f"**Frame {local_idx + 1} / {len(prefix_frames)}**")
    st.caption(os.path.basename(current_img_path))

    # Controles de detecção por frame
    if frame_dets:
        st.markdown("**Detecções:**")
        for i, d in enumerate(frame_dets):
            use = st.checkbox(
                f"{d['classe']} ({d['cls_conf']:.2f})",
                value=d["use"],
                key=f"use_{st.session_state.idx}_{i}",
            )
            frame_dets[i]["use"] = use
            # Override de classe por detecção
            override = st.selectbox(
                "Classe",
                classes_list,
                index=classes_list.index(d["classe"]) if d["classe"] in classes_list else 0,
                key=f"cls_{st.session_state.idx}_{i}",
                label_visibility="collapsed",
            )
            frame_dets[i]["classe"] = override

    st.divider()

    # Opção lote
    with st.expander("Opções avançadas"):
        apply_all_frames = st.checkbox(
            "Aplicar a todos os frames do vídeo",
            value=False,
            help="Aplica a classe selecionada a todos os frames deste vídeo"
        )
        allow_force = st.checkbox(
            "Salvar sem detecção (bbox = frame inteiro)",
            value=False,
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NAVEGAÇÃO E SAVE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.divider()
nav1, nav2, nav3, nav4 = st.columns(4)

def go_prev():
    if local_idx > 0:
        st.session_state.idx = image_paths.index(prefix_frames[local_idx - 1])

def go_next():
    if local_idx < len(prefix_frames) - 1:
        st.session_state.idx = image_paths.index(prefix_frames[local_idx + 1])

def skip_video():
    remaining = [p for p in image_paths if base_prefix_for_frame(p) not in
                 [current_prefix] + list({base_prefix_for_frame(q) for q in image_paths[:image_paths.index(current_img_path)]})]
    if remaining:
        next_prefix = base_prefix_for_frame(remaining[0])
        st.session_state.selected_prefix = next_prefix
        st.session_state.idx = image_paths.index(remaining[0])

def do_save():
    dets_to_save = frame_dets if frame_dets else (
        fake_fullbox_detection(current_img_path, st.session_state.selected_class) if allow_force else []
    )
    if not dets_to_save:
        st.warning("Nenhuma detecção para salvar. Ative 'Salvar sem detecção' se necessário.")
        return

    if apply_all_frames:
        for fp in prefix_frames:
            fd = csv_dets.get(fp, fake_fullbox_detection(fp, st.session_state.selected_class))
            for d in fd:
                d["classe"] = st.session_state.selected_class
            save_annotation(fp, fd)
        st.success(f"✅ {len(prefix_frames)} frames do vídeo anotados como {st.session_state.selected_class}.")
    else:
        save_annotation(current_img_path, dets_to_save)
        go_next()

with nav1:
    if st.button("← Voltar", use_container_width=True):
        go_prev()
        st.rerun()

with nav2:
    if st.button("Próximo →", use_container_width=True):
        go_next()
        st.rerun()

with nav3:
    if st.button("⏭ Pular vídeo", use_container_width=True):
        skip_video()
        st.rerun()

with nav4:
    if st.button("💾 Salvar & próximo", type="primary", use_container_width=True):
        do_save()
        st.rerun()
