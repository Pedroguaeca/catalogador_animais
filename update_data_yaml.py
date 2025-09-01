# update_data_yaml.py
import yaml
import os

CLASSES_FILE = "dataset/classes.txt"
DATA_YAML = "data.yaml"

if not os.path.exists(CLASSES_FILE):
    raise FileNotFoundError(f"{CLASSES_FILE} não encontrado. Anote pelo menos uma imagem antes.")

with open(CLASSES_FILE, "r") as f:
    classes = [c.strip() for c in f if c.strip()]

data = {
    "train": "dataset/images/train",
    "val": "dataset/images/val",
    "nc": len(classes),
    "names": classes
}

with open(DATA_YAML, "w") as f:
    yaml.dump(data, f)

print(f"Arquivo {DATA_YAML} atualizado com {len(classes)} classes.")
