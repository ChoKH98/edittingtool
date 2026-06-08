import json, pathlib

def load_pdk(path):
    data = json.loads(pathlib.Path(path).read_text())
    return data["name"], {
        entry["name"]: (entry["layer"], entry["datatype"], entry["color"])
        for entry in data["layers"]
    }

def default_pdk_path():
    return pathlib.Path(__file__).parent / "pdk" / "ihp_sg13g2.json"
