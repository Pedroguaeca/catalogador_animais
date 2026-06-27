"""Testa a estrutura de diretórios de frames gerados pelo pipeline."""
import os
import pytest

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def test_frames_dir_existe(frames_dir):
    """O diretório frames/ deve existir."""
    assert os.path.isdir(frames_dir), (
        f"Diretório não encontrado: {frames_dir}\n"
        "Execute 'python main.py' para gerar os frames."
    )


def test_frames_dir_nao_vazio(frames_dir):
    """O diretório frames/ deve conter subpastas de gênero."""
    if not os.path.isdir(frames_dir):
        pytest.skip("frames/ não existe")
    subdirs = [
        d for d in os.listdir(frames_dir)
        if os.path.isdir(os.path.join(frames_dir, d))
    ]
    assert subdirs, "frames/ está vazio — sem subpastas de gênero"


def test_sem_frames_na_raiz(frames_dir):
    """Não deve haver arquivos .jpg/.png diretamente na raiz de frames/."""
    if not os.path.isdir(frames_dir):
        pytest.skip("frames/ não existe")
    raiz_images = [
        f for f in os.listdir(frames_dir)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
    ]
    assert not raiz_images, (
        f"{len(raiz_images)} frame(s) antigo(s) na raiz de frames/ (sem subpasta):\n"
        + "\n".join(raiz_images[:10])
        + "\nDelete os frames legados do pipeline YOLO: "
        + "find frames -maxdepth 1 -name '*.jpg' -delete"
    )


def test_subpastas_sao_generos_validos(frames_dir):
    """Subpastas de frames/ devem corresponder a gêneros conhecidos (letras apenas, sem números)."""
    if not os.path.isdir(frames_dir):
        pytest.skip("frames/ não existe")
    import re
    subdirs = [
        d for d in os.listdir(frames_dir)
        if os.path.isdir(os.path.join(frames_dir, d))
    ]
    invalidos = [d for d in subdirs if not re.match(r"^[A-Za-z]+$", d)]
    assert not invalidos, (
        f"Subpastas com nome suspeito em frames/: {invalidos}\n"
        "As subpastas devem ter o nome do gênero (ex: Dasyprocta, Unknown)."
    )


def test_frames_sao_imagens(frames_dir):
    """Arquivos (não subpastas) dentro de frames/<genus>/ devem ser imagens."""
    if not os.path.isdir(frames_dir):
        pytest.skip("frames/ não existe")
    nao_imagens = []
    for subdir in os.listdir(frames_dir):
        subpath = os.path.join(frames_dir, subdir)
        if not os.path.isdir(subpath):
            continue
        for fname in os.listdir(subpath):
            fpath = os.path.join(subpath, fname)
            if os.path.isdir(fpath):
                continue  # subpastas como crops/ são ignoradas
            ext = os.path.splitext(fname)[1].lower()
            if ext not in IMAGE_EXTENSIONS:
                nao_imagens.append(os.path.join(subdir, fname))
    assert not nao_imagens, (
        f"Arquivos não-imagem em frames/: {nao_imagens[:10]}"
    )


def test_frames_nao_corrompidos(frames_dir, csv_rows):
    """Uma amostra dos frames do CSV deve abrir como imagem válida."""
    pytest.importorskip("PIL", reason="Pillow não instalado")
    from PIL import Image

    sample_paths = []
    seen = set()
    for row in csv_rows:
        rel = row["frame"]
        if rel not in seen:
            seen.add(rel)
            sample_paths.append(os.path.join(frames_dir, rel))
        if len(sample_paths) >= 10:
            break

    erros = []
    for p in sample_paths:
        if not os.path.exists(p):
            continue
        try:
            with Image.open(p) as img:
                img.verify()
        except Exception as e:
            erros.append(f"{p}: {e}")

    assert not erros, f"Frames corrompidos:\n" + "\n".join(erros)
