# interface_v1.py
# Versão estável — layout horizontal simples e funcional

import os, glob
from typing import List, Dict
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

# --------- PATHS ---------
FRAMES_DIR = "frames"
DATASET_DIR = "dataset"
IMAGES_TRAIN = os.path.join(DATASET_DIR, "images", "train")
LABELS_TRAIN = os.path.join(DATASET_DIR, "labels", "train")
CLASSES_FILE = os.path.join(DATASET_DIR, "classes.txt")
UPLOAD_DIR = "videos/uploaded"
MODEL_PATH = "yolov8n.pt"  # troque pelo seu modelo treinado quando tiver

for p in [IMAGES_TRAIN, LABELS_TRAIN, UPLOAD_DIR, "assets"]:
    os.makedirs(p, exist_ok=True)

st.set_page_config(page_title="Sistema de identificação de animais BR", layout="wide")

# --------- CSS ENXUTO (layout horizontal, logo pequeno, botões em linha) ---------
st.markdown("""
<style>
  .main .block-container { max-width: 1400px; padding-top: .6rem; }
  .logo-box img { max-width: 48px; width: 100%; height: auto; border-radius: 8px; }

  /* garantir colunas lado a lado */
  [data-testid="stHorizontalBlock"] { gap: 1rem !important; flex-wrap: nowrap !important; align-items: flex-start !important; }
  /* imagem ~1/3 | comandos ~2/3 */
  [data-testid="stHorizontalBlock"] > div:first-child { flex: 0 0 33% !important; min-width: 320px !important; max-width: 33% !important; }
  [data-testid="stHorizontalBlock"] > div:nth-child(2) { flex: 1 0 0 !important; }

  /* imagem um pouco mais alta para equilibrar */
  .img-fixed img {
    width: 100% !important; height: auto !important;
    max-height: 78vh !important; object-fit: contain !important;
    border-radius: 10px; border: 1px solid #e5e7eb;
  }

  /* painel direito com scroll sutil */
  .right-pane { max-height: 78vh; overflow: auto; padding-right: .5rem; }

  /* botões menores, em linha */
  div.stButton > button {
    height: 2.0rem; padding: 0 .6rem; border-radius: 10px; white-space: nowrap; font-size: 0.9rem;
  }
</style>
""", unsafe_allow_html=True)

# --------- HELPERS ---------
def list_images(frames_dir: str):
    imgs = sorted(glob.glob(os.path.join(frames_dir, "**", "*.jpg"), recursive=True))
    imgs += sorted(glob.glob(os.path.join(frames_dir, "**", "*.png"), recursive=True))
    return imgs

def base_prefix_for_frame(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    parts = base.split("_frame_")
    return parts[0] if parts else base

def video_prefixes(image_paths): 
    return sorted({ base_prefix_for_frame(p) for p in image_paths })

def read_classes(path: str):
    if not os.path.exists(path): return []
    with open(path, "r") as f:
        classes = [ln.strip().lower() for ln in f if ln.strip()]
    return sorted(set(classes))

def write_classes(path: str, classes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ordered = sorted(set([c.strip().lower() for c in classes if c.strip()]))
    with open(path, "w") as f:
        for c in ordered: f.write(c + "\n")
    return ordered

def class_id_for(name: str, classes):
    ordered = sorted(set(classes + [name.strip().lower()]))
    return ordered.index(name.strip().lower())

def xyxy_to_yolo(x1, y1, x2, y2, w, h):
    bw = max(x2 - x1, 1e-6); bh = max(y2 - y1, 1e-6)
    cx = x1 + bw / 2.0; cy = y1 + bh / 2.0
    return cx / w, cy / h, bw / w, bh / h

def draw_boxes(img_pil: Image.Image, dets: List[Dict]) -> Image.Image:
    img = img_pil.copy()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("Helvetica.ttc", size=max(13, img.width // 60))
    except:
        font = ImageFont.load_default()
    for d in dets:
        if not d.get("use", True): continue
        x1, y1, x2, y2 = d["xyxy"]
        label = d.get("classe", "obj"); conf = d.get("conf", None)
        if conf is not None: label = f"{label} {conf:.2f}"
        draw.rectangle([x1, y1, x2, y2], outline=(0, 160, 80), width=3)
        tw = draw.textlength(label, font=font); th = font.size + 6; pad=4
        box = [x1, max(0, y1-th), x1 + tw + 2*pad, y1]
        draw.rectangle(box, fill=(0,160,80))
        draw.text((x1+pad, y1 - th + 3), label, fill=(0,0,0), font=font)
    return img

@st.cache_resource
def load_model_cached(model_path: str):
    return YOLO(model_path)

def infer_image(model: YOLO, img_path: str, conf: float, iou: float):
    res = model.predict(img_path, conf=conf, iou=iou, imgsz=960, verbose=False)
    dets = []
    if res and res[0].boxes is not None:
        r = res[0]; names = r.names
        for box in r.boxes:
            cls_id = int(box.cls[0]); conf_f = float(box.conf[0])
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            dets.append({"use": True, "classe": names[cls_id], "conf": conf_f, "xyxy": [x1, y1, x2, y2]})
    return dets

def save_annotation(img_path: str, detections: List[Dict], use_val: bool=False):
    dest_imgs = IMAGES_TRAIN
    dest_lbls = LABELS_TRAIN
    os.makedirs(dest_imgs, exist_ok=True); os.makedirs(dest_lbls, exist_ok=True)
    base = os.path.splitext(os.path.basename(img_path))[0]
    dest_img_path = os.path.join(dest_imgs, base + ".jpg")
    Image.open(img_path).convert("RGB").save(dest_img_path, "JPEG", quality=95)
    W, H = Image.open(dest_img_path).size
    classes_current = read_classes(CLASSES_FILE)
    lines = []
    for d in detections:
        if not d.get("use"): continue
        cls_name = d["classe"].strip().lower()
        cls_id = class_id_for(cls_name, classes_current)
        x1, y1, x2, y2 = d["xyxy"]
        x_center, y_center, w_norm, h_norm = xyxy_to_yolo(x1, y1, x2, y2, W, H)
        lines.append(f"{cls_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")
    with open(os.path.join(dest_lbls, base + ".txt"), "w") as f:
        f.write("\n".join(lines))
    return dest_img_path

def fake_fullbox_detection(img_path: str, classe: str):
    img = Image.open(img_path); w, h = img.size
    return [{ "use": True, "classe": classe, "conf": None, "xyxy": [0.0, 0.0, float(w), float(h)] }]

# --------- CARREGAR FRAMES ---------
image_paths = list_images(FRAMES_DIR)
if not image_paths:
    st.title("Sistema de identificação de animais BR")
    st.warning("Nenhuma imagem encontrada em `frames/`. Gere frames pelo pipeline ou mova imagens para lá.")
    with st.expander("📤 Upload de vídeos (teste rápido)"):
        files = st.file_uploader("Envie vídeos (mp4/avi/mov/mkv)", type=["mp4","avi","mov","mkv"], accept_multiple_files=True)
        if files:
            for f in files:
                out = os.path.join(UPLOAD_DIR, f.name)
                with open(out, "wb") as w: w.write(f.getbuffer())
            st.success(f"{len(files)} arquivo(s) salvo(s) em `{UPLOAD_DIR}`. Depois gere frames.")
    st.stop()

prefixes = video_prefixes(image_paths)

# --------- HEADER ---------
hl, hr = st.columns([1, 8], vertical_alignment="center")
with hl:
    for ext in ("png","jpg","jpeg"):
        lp = f"assets/logo.{ext}"
        if os.path.exists(lp):
            st.markdown('<div class="logo-box">', unsafe_allow_html=True)
            st.image(lp, caption="", use_container_width=False)
            st.markdown('</div>', unsafe_allow_html=True)
            break
with hr:
    st.title("Sistema de identificação de animais BR")

# --------- ESTADO INICIAL ---------
if "selected_prefix" not in st.session_state:
    st.session_state.selected_prefix = prefixes[0]
if "idx" not in st.session_state:
    firsts = [p for p in image_paths if base_prefix_for_frame(p) == st.session_state.selected_prefix]
    st.session_state.idx = image_paths.index(firsts[0])
if "selected_class" not in st.session_state:
    classes_init = read_classes(CLASSES_FILE)
    st.session_state.selected_class = classes_init[0] if classes_init else ""

# --------- LINHA 1: dois selects lado a lado ---------
top_l, top_r = st.columns([1,1], gap="large")
with top_l:
    st.markdown("ℹ️ **Escolha o vídeo (prefixo do frame)**")
    sel = st.selectbox(
        " ", prefixes,
        index=prefixes.index(st.session_state.selected_prefix),
        label_visibility="collapsed"
    )
    if sel != st.session_state.selected_prefix:
        st.session_state.selected_prefix = sel
        frames_this = [p for p in image_paths if base_prefix_for_frame(p) == sel]
        st.session_state.idx = image_paths.index(frames_this[0])

with top_r:
    st.markdown("ℹ️ **Categoria (ordem alfabética)**")
    classes_ui = read_classes(CLASSES_FILE)
    st.session_state.selected_class = st.selectbox(
        " ", classes_ui if classes_ui else ["(nenhuma cadastrada)"],
        index=0, label_visibility="collapsed"
    )

# --------- Upload simples ---------
with st.expander("📤 Upload de vídeos (teste rápido)", expanded=False):
    files = st.file_uploader("Envie novos vídeos (mp4/avi/mov/mkv)", type=["mp4","avi","mov","mkv"], accept_multiple_files=True)
    if files:
        saved = 0
        for f in files:
            out = os.path.join(UPLOAD_DIR, f.name)
            with open(out, "wb") as w: w.write(f.getbuffer()); saved += 1
        st.success(f"{saved} vídeo(s) salvo(s) em `{UPLOAD_DIR}`. Gere frames com seu pipeline.")

# --------- Opções de detecção ---------
with st.expander("⚙️ Opções de detecção / navegação", expanded=False):
    conf_thres = st.slider("Nível de confiança mínimo", 0.0, 1.0, 0.20, 0.01)
    iou_thres  = st.slider("Ajuste de supressão (IoU)", 0.10, 1.0, 0.70, 0.05)
    apply_all_frames = st.checkbox("Aplicar esta categoria a todos os frames deste vídeo (lento)", value=False)
    allow_force      = st.checkbox("Permitir salvar sem detecção (usar frame inteiro)", value=False)

# --------- Frame atual + inferência ---------
curr_idx = st.session_state.idx
curr_path = image_paths[curr_idx]
curr_prefix = base_prefix_for_frame(curr_path)

model = load_model_cached(MODEL_PATH)
detections = infer_image(model, curr_path, conf_thres, iou_thres)
img = Image.open(curr_path).convert("RGB")

# --------- LAYOUT: imagem (1/3) | comandos (2/3) ---------
left_col, right_col = st.columns([1, 2], gap="large")

with left_col:
    st.markdown("#### Frame atual")
    st.markdown('<div class="img-fixed">', unsafe_allow_html=True)
    st.image(draw_boxes(img, detections) if detections else img,
             use_container_width=True, caption=os.path.basename(curr_path))
    st.markdown('</div>', unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="right-pane">', unsafe_allow_html=True)
    st.markdown("#### Catalogação")

    # Criar nova categoria (input + botão lado a lado simples)
    c_nc1, c_nc2 = st.columns([3,1], gap="small")
    with c_nc1:
        new_class = st.text_input("Criar nova categoria", "", placeholder="ex.: cutia, onça-parda, macuco")
    with c_nc2:
        add_click = st.button("➕ Adicionar", use_container_width=True)
    if add_click:
        nc = new_class.strip().lower()
        if nc:
            updated = write_classes(CLASSES_FILE, classes_ui + [nc])
            st.session_state.selected_class = nc
            st.success(f"Categoria '{nc}' adicionada.")
        else:
            st.warning("Digite um nome antes de adicionar.")

    mode = st.radio(
        "Aplicação da categoria",
        ["Aplicar a todas as caixas deste frame", "Selecionar detecções manualmente"],
        index=0
    )

    edited = []
    if mode == "Aplicar a todas as caixas deste frame":
        for d in detections:
            d["use"] = True
            d["classe"] = st.session_state.selected_class
        edited = detections
    else:
        if not detections:
            st.info("Nenhuma detecção encontrada com as configurações atuais.")
        else:
            tmp=[]
            for i, d in enumerate(detections):
                with st.expander(f"Detecção #{i+1} — {d['classe']} ({d.get('conf',0):.2f})", expanded=True):
                    use = st.checkbox("Usar", value=True, key=f"use_{i}")
                    cls_opts = [st.session_state.selected_class] + [c for c in classes_ui if c != st.session_state.selected_class]
                    cls = st.selectbox("Categoria desta detecção", cls_opts, index=0, key=f"cls_{i}")
                    x1, y1, x2, y2 = d["xyxy"]
                    x1 = st.number_input("x1", value=float(x1), key=f"x1_{i}")
                    y1 = st.number_input("y1", value=float(y1), key=f"y1_{i}")
                    x2 = st.number_input("x2", value=float(x2), key=f"x2_{i}")
                    y2 = st.number_input("y2", value=float(y2), key=f"y2_{i}")
                    tmp.append({"use": use, "classe": cls, "xyxy": [x1,y1,x2,y2], "conf": d.get("conf",None)})
            edited = tmp

    st.divider()
    # Rodapé com 4 botões em UMA linha (voltar | pular frame | pular vídeo | salvar & próxima)
    bc1, bc2, bc3, bc4 = st.columns(4, gap="small")
    with bc1: back_clicked = st.button("↩️ Voltar", use_container_width=True)
    with bc2: skip_frame  = st.button("⏭️ Pular frame", use_container_width=True)
    with bc3: skip_video  = st.button("⏭️⏭️ Pular VÍDEO", use_container_width=True)
    with bc4: save_next_clicked = st.button("💾 Salvar & Próxima", use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)  # fecha right-pane

# --------- Navegação ---------
def jump_to_first_frame_of(prefix: str):
    frames_this = [p for p in image_paths if base_prefix_for_frame(p) == prefix]
    if frames_this:
        st.session_state.idx = image_paths.index(frames_this[0])

def jump_to_next_video():
    idx_prefix = prefixes.index(curr_prefix)
    if idx_prefix + 1 < len(prefixes):
        jump_to_first_frame_of(prefixes[idx_prefix + 1])
    else:
        st.balloons(); st.info("Chegamos ao fim das imagens.")

if back_clicked:
    st.session_state.idx = max(0, st.session_state.idx - 1)
    st.rerun()

if skip_frame:
    st.session_state.idx = min(len(image_paths) - 1, st.session_state.idx + 1)
    st.rerun()

if skip_video:
    jump_to_next_video()
    st.rerun()

# --------- Salvar ---------
if save_next_clicked:
    if (not edited) and st.session_state.selected_class and 'allow_force' in locals() and allow_force:
        edited = fake_fullbox_detection(curr_path, st.session_state.selected_class)

    if edited:
        save_annotation(curr_path, edited, use_val=False)
        if 'apply_all_frames' in locals() and apply_all_frames:
            same_video_idxs = [i for i,p in enumerate(image_paths) if base_prefix_for_frame(p) == curr_prefix]
            batch_paths = [image_paths[i] for i in same_video_idxs]
            st.info(f"Aplicando '{st.session_state.selected_class}' a {len(batch_paths)} frames deste vídeo…")
            prog = st.progress(0); mdl = load_model_cached(MODEL_PATH)
            for i, p in enumerate(batch_paths):
                dets = infer_image(mdl, p, conf_thres, iou_thres)
                if not dets and allow_force:
                    dets = fake_fullbox_detection(p, st.session_state.selected_class)
                for d in dets:
                    d["use"] = True; d["classe"] = st.session_state.selected_class
                if dets:
                    save_annotation(p, dets, use_val=False)
                prog.progress((i + 1) / max(1, len(batch_paths)))
            st.success("Propagação concluída."); jump_to_next_video(); st.rerun()
        else:
            st.session_state.idx = min(len(image_paths) - 1, st.session_state.idx + 1); st.rerun()
    else:
        st.info("Não houve detecções para salvar neste frame (tente reduzir confiança ou habilitar 'salvar sem detecção').")
