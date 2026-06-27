"""Testa a integridade do genus_map.json (mapeamento científico → PT/EN)."""
import pytest

# Gêneros que o AI4GAmazonRainforest v2 deve classificar — todos precisam ter tradução
EXPECTED_GENERA = [
    "Dasyprocta", "Crypturellus", "Aramides", "Pecari", "Tinamus",
    "Eira", "Unknown", "Tapirus", "Mazama", "Hydrochoerus",
    "Nasua", "Cuniculus", "Myrmecophaga", "Tamandua", "Leopardus",
]


def test_genus_map_existe(genus_map_path):
    """O arquivo genus_map.json deve existir na raiz do projeto."""
    import os
    assert os.path.exists(genus_map_path), (
        f"Arquivo não encontrado: {genus_map_path}\n"
        "Crie genus_map.json na raiz do projeto."
    )


def test_genus_map_nao_vazio(genus_map):
    """O mapa não pode estar vazio."""
    assert len(genus_map) > 0, "genus_map.json está vazio"


def test_todos_entries_tem_pt_e_en(genus_map):
    """Cada gênero deve ter os campos 'pt' (português) e 'en' (inglês)."""
    for genus, entry in genus_map.items():
        assert "pt" in entry, f"{genus}: campo 'pt' ausente"
        assert "en" in entry, f"{genus}: campo 'en' ausente"
        assert entry["pt"].strip(), f"{genus}: campo 'pt' está vazio"
        assert entry["en"].strip(), f"{genus}: campo 'en' está vazio"


def test_unknown_mapeado(genus_map):
    """'Unknown' deve ter tradução (ex: 'Desconhecido')."""
    assert "Unknown" in genus_map, "Unknown não está mapeado em genus_map.json"
    assert genus_map["Unknown"]["pt"], "Tradução PT de 'Unknown' está vazia"


@pytest.mark.parametrize("genus", EXPECTED_GENERA)
def test_genera_ai4g_mapeados(genus_map, genus):
    """Todos os gêneros detectáveis pelo AI4GAmazonRainforest devem estar mapeados."""
    assert genus in genus_map, (
        f"Gênero '{genus}' não encontrado em genus_map.json. "
        "Adicione a tradução PT e EN para esse gênero."
    )


def test_sem_espacos_extras_nos_nomes(genus_map):
    """Nomes PT e EN não devem ter espaços no início ou fim."""
    for genus, entry in genus_map.items():
        assert entry["pt"] == entry["pt"].strip(), (
            f"{genus}: campo 'pt' tem espaço extra: '{entry['pt']}'"
        )
        assert entry["en"] == entry["en"].strip(), (
            f"{genus}: campo 'en' tem espaço extra: '{entry['en']}'"
        )
