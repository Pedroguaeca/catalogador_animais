"""Testa a integridade do CSV gerado pelo pipeline (catalogo_animais.csv)."""
import os
import pytest

REQUIRED_COLUMNS = {
    "video", "frame", "genero",
    "det_conf", "cls_conf", "x1", "y1", "x2", "y2",
}

VALID_GENERA = {
    "Dasyprocta", "Crypturellus", "Aramides", "Pecari", "Tinamus",
    "Eira", "Unknown", "Tapirus", "Mazama", "Hydrochoerus",
    "Nasua", "Cuniculus", "Myrmecophaga", "Tamandua", "Leopardus",
    "Didelphis", "Dasypus", "Philander", "Sciurus", "Tayassu",
    "Caiman", "Chelonoidis", "Iguana", "Herpailurus", "Puma",
    "Panthera", "Cebus", "Alouatta", "Saimiri",
}


def test_csv_existe(csv_path):
    """O arquivo CSV deve existir após rodar o pipeline."""
    assert os.path.exists(csv_path), (
        f"CSV não encontrado: {csv_path}\n"
        "Execute 'python main.py' para gerar os resultados."
    )


def test_csv_tem_linhas(csv_rows):
    """O CSV não pode estar vazio (além do cabeçalho)."""
    assert len(csv_rows) > 0, "CSV não tem linhas de dados"


def test_colunas_obrigatorias_presentes(csv_rows):
    """Todas as colunas obrigatórias devem estar no CSV."""
    if not csv_rows:
        pytest.skip("CSV vazio")
    actual = set(csv_rows[0].keys())
    missing = REQUIRED_COLUMNS - actual
    assert not missing, f"Colunas ausentes no CSV: {missing}"


def test_confs_entre_0_e_1(csv_rows):
    """det_conf e cls_conf devem estar entre 0 e 1."""
    for i, row in enumerate(csv_rows):
        det = float(row["det_conf"])
        cls = float(row["cls_conf"])
        assert 0.0 <= det <= 1.0, f"Linha {i+2}: det_conf={det} fora do range [0,1]"
        assert 0.0 <= cls <= 1.0, f"Linha {i+2}: cls_conf={cls} fora do range [0,1]"


def test_bboxes_validas(csv_rows):
    """Bounding boxes devem ter x2>x1 e y2>y1 (coordenadas absolutas em pixels)."""
    for i, row in enumerate(csv_rows):
        x1, y1, x2, y2 = float(row["x1"]), float(row["y1"]), float(row["x2"]), float(row["y2"])
        assert x2 > x1, f"Linha {i+2}: x2={x2} deve ser maior que x1={x1}"
        assert y2 > y1, f"Linha {i+2}: y2={y2} deve ser maior que y1={y1}"
        assert x1 >= 0, f"Linha {i+2}: x1={x1} não pode ser negativo"
        assert y1 >= 0, f"Linha {i+2}: y1={y1} não pode ser negativo"


def test_genus_conhecidos(csv_rows):
    """Todos os gêneros no CSV devem estar na lista de gêneros conhecidos."""
    unknown_genera = set()
    for row in csv_rows:
        g = row["genero"]
        if g not in VALID_GENERA:
            unknown_genera.add(g)
    assert not unknown_genera, (
        f"Gêneros desconhecidos no CSV: {unknown_genera}\n"
        "Adicione ao genus_map.json se for um novo gênero válido."
    )


def test_genero_pt_presente_apos_reprocessamento(csv_rows):
    """genero_pt deve existir após reprocessar com a versão atualizada do pipeline.

    Se falhar: rode 'python main.py' depois de atualizar utils_catalogo.py.
    """
    if not csv_rows:
        pytest.skip("CSV vazio")
    if "genero_pt" not in csv_rows[0]:
        pytest.xfail(
            "Coluna 'genero_pt' ausente — CSV gerado antes da atualização de "
            "utils_catalogo.py. Reprocesse com 'python main.py' para gerar essa coluna."
        )
    empty = [
        f"Linha {i+2} (genero={row['genero']})"
        for i, row in enumerate(csv_rows)
        if not row.get("genero_pt", "").strip()
    ]
    assert not empty, (
        f"genero_pt vazio em {len(empty)} linha(s):\n" + "\n".join(empty[:10])
    )


def test_frames_existem_no_disco(csv_rows, frames_dir):
    """Cada frame referenciado no CSV deve existir em disco."""
    missing = []
    seen = set()
    for i, row in enumerate(csv_rows):
        rel = row["frame"]
        if rel in seen:
            continue
        seen.add(rel)
        full = os.path.join(frames_dir, rel)
        if not os.path.exists(full):
            missing.append(f"Linha {i+2}: {full}")
    assert not missing, (
        f"{len(missing)} frame(s) no CSV não existem em disco:\n"
        + "\n".join(missing[:10])
    )


def test_sem_duplicatas_exatas(csv_rows):
    """Não deve haver linhas completamente duplicadas no CSV."""
    tuples = [tuple(row.values()) for row in csv_rows]
    unique = set(tuples)
    assert len(tuples) == len(unique), (
        f"{len(tuples) - len(unique)} linha(s) duplicada(s) no CSV"
    )
