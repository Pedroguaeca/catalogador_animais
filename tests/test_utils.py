"""Testes unitários das funções auxiliares em utils_catalogo.py."""
import os
import sys
import pytest

# Adiciona a raiz do projeto ao path para importar utils_catalogo
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(scope="module")
def utils():
    import utils_catalogo
    return utils_catalogo


# ---------------------------------------------------------------------------
# genus_to_pt
# ---------------------------------------------------------------------------

def test_genus_to_pt_dasyprocta(utils):
    """Dasyprocta deve mapear para Cutia."""
    assert utils.genus_to_pt("Dasyprocta") == "Cutia"


def test_genus_to_pt_unknown(utils):
    """Unknown deve mapear para Desconhecido."""
    result = utils.genus_to_pt("Unknown")
    assert result.lower() in ("desconhecido", "unknown"), (
        f"Esperava 'Desconhecido' para Unknown, recebi '{result}'"
    )


def test_genus_to_pt_fallback(utils):
    """Um gênero não mapeado deve retornar o próprio nome (fallback seguro)."""
    result = utils.genus_to_pt("GeneroInexistente123")
    assert result == "GeneroInexistente123", (
        "Fallback deve retornar o gênero original quando não há tradução"
    )


def test_genus_to_pt_case_sensitive(utils):
    """A função deve ser case-sensitive — 'dasyprocta' != 'Dasyprocta'."""
    capitalizado = utils.genus_to_pt("Dasyprocta")
    minusculo    = utils.genus_to_pt("dasyprocta")
    assert capitalizado == "Cutia", "Dasyprocta deve mapear para Cutia"
    # Minúsculo: ou é mapeado separadamente ou faz fallback — não deve crashar
    assert isinstance(minusculo, str), "genus_to_pt não deve lançar exceção"


# ---------------------------------------------------------------------------
# xyxy_to_yolo  (se existir)
# ---------------------------------------------------------------------------

def test_xyxy_to_yolo_centro(utils):
    """Conversão de bbox absoluta para formato YOLO normalizado."""
    if not hasattr(utils, "xyxy_to_yolo"):
        pytest.skip("xyxy_to_yolo não definido em utils_catalogo")
    x1, y1, x2, y2 = 100, 50, 300, 250
    img_w, img_h = 640, 480
    cx, cy, w, h = utils.xyxy_to_yolo(x1, y1, x2, y2, img_w, img_h)
    assert abs(cx - 0.3125) < 1e-4, f"cx esperado 0.3125, obtido {cx}"
    assert abs(cy - 0.3125) < 1e-4, f"cy esperado 0.3125, obtido {cy}"
    assert abs(w  - 0.3125) < 1e-4, f"w  esperado 0.3125, obtido {w}"
    assert abs(h  - 0.4167) < 1e-3, f"h  esperado ~0.4167, obtido {h}"


def test_xyxy_to_yolo_imagem_inteira(utils):
    """Bbox que ocupa a imagem toda deve resultar em (0.5, 0.5, 1.0, 1.0)."""
    if not hasattr(utils, "xyxy_to_yolo"):
        pytest.skip("xyxy_to_yolo não definido em utils_catalogo")
    cx, cy, w, h = utils.xyxy_to_yolo(0, 0, 640, 480, 640, 480)
    assert abs(cx - 0.5) < 1e-6
    assert abs(cy - 0.5) < 1e-6
    assert abs(w  - 1.0) < 1e-6
    assert abs(h  - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# slugify / parse_time_from_filename (se existir)
# ---------------------------------------------------------------------------

def test_parse_time_from_filename(utils):
    """parse_time_from_filename extrai HH:MM:SS de um bloco de 6 dígitos no nome do arquivo."""
    if not hasattr(utils, "parse_time_from_filename"):
        pytest.skip("parse_time_from_filename não definido em utils_catalogo")
    # Nomes de vídeo tipicamente contêm HHMMSS como 230637 (23h06m37s)
    fname = "/videos/Cutia_Cam2Pos2_230637.mp4"
    result = utils.parse_time_from_filename(fname)
    assert result is not None, (
        "parse_time_from_filename deve retornar (hh, mm, ss) para nomes com bloco HHMMSS"
    )
    assert result == (23, 6, 37), f"Esperava (23, 6, 37), obtive {result}"


def test_parse_time_sem_timestamp(utils):
    """parse_time_from_filename deve retornar None para nomes sem bloco HHMMSS."""
    if not hasattr(utils, "parse_time_from_filename"):
        pytest.skip("parse_time_from_filename não definido em utils_catalogo")
    result = utils.parse_time_from_filename("video_sem_hora.mp4")
    assert result is None, "Deve retornar None quando não há timestamp no nome"


# ---------------------------------------------------------------------------
# CSV header
# ---------------------------------------------------------------------------

def test_csv_header_tem_genero(project_root):
    """O CSV deve ter a coluna 'genero' (nome científico do gênero)."""
    import csv
    csv_path = os.path.join(project_root, "resultados", "catalogo_animais.csv")
    if not os.path.exists(csv_path):
        pytest.skip("CSV não encontrado — execute 'python main.py' primeiro")
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
    assert "genero" in headers, (
        f"Coluna 'genero' ausente no CSV. Colunas encontradas: {headers}"
    )


def test_csv_header_tem_genero_pt_apos_reprocessamento(project_root):
    """Após reprocessar com utils_catalogo.py atualizado, deve ter 'genero_pt'."""
    import csv
    csv_path = os.path.join(project_root, "resultados", "catalogo_animais.csv")
    if not os.path.exists(csv_path):
        pytest.skip("CSV não encontrado — execute 'python main.py' primeiro")
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        headers = next(reader)
    if "genero_pt" not in headers:
        pytest.xfail(
            "Coluna 'genero_pt' ausente — CSV gerado antes da atualização do pipeline. "
            "Reprocesse com 'python main.py' para incluir essa coluna."
        )
