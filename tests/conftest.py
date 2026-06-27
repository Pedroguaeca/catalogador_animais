"""Fixtures compartilhadas entre todos os testes do SIAB."""
import os
import csv
import json
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session")
def project_root():
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def csv_path():
    return os.path.join(PROJECT_ROOT, "resultados", "catalogo_animais.csv")


@pytest.fixture(scope="session")
def frames_dir():
    return os.path.join(PROJECT_ROOT, "frames")


@pytest.fixture(scope="session")
def genus_map_path():
    return os.path.join(PROJECT_ROOT, "genus_map.json")


@pytest.fixture(scope="session")
def genus_map(genus_map_path):
    assert os.path.exists(genus_map_path), "genus_map.json não encontrado"
    with open(genus_map_path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


@pytest.fixture(scope="session")
def csv_rows(csv_path):
    if not os.path.exists(csv_path):
        pytest.skip("CSV não encontrado — execute 'python main.py' primeiro")
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
