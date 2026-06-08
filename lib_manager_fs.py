"""
File-system operations for the library/cell/view structure.
All other modules import from here to get/set library paths.
"""
import json
from datetime import datetime
from pathlib import Path


_PROJECT_ROOT = Path(__file__).parent
LIBRARY_ROOT = _PROJECT_ROOT / "libraries"


def ensure_library_root():
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)


def library_path(lib_name: str) -> Path:
    return LIBRARY_ROOT / lib_name


def cell_path(lib_name: str, cell_name: str) -> Path:
    return library_path(lib_name) / cell_name


def view_path(lib_name: str, cell_name: str, view: str) -> Path:
    """view: 'schematic', 'layout', 'symbol'"""
    return cell_path(lib_name, cell_name) / view


def view_file(lib_name: str, cell_name: str, view: str) -> Path:
    """Returns path to the JSON data file for a view."""
    return view_path(lib_name, cell_name, view) / f"{view}.json"


def create_library(lib_name: str, description: str = "") -> bool:
    """Create library folder and lib.json. Returns True if newly created."""
    ensure_library_root()
    path = library_path(lib_name)
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": lib_name,
        "description": description,
        "created_at": datetime.now().isoformat(),
    }
    (path / "lib.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return True


def delete_library(lib_name: str):
    """Remove library folder recursively."""
    import shutil

    path = library_path(lib_name)
    if path.exists():
        shutil.rmtree(path)


def list_libraries() -> list:
    """Return list of library names found on disk."""
    ensure_library_root()
    return [
        p.name
        for p in LIBRARY_ROOT.iterdir()
        if p.is_dir() and (p / "lib.json").exists()
    ]


def get_library_meta(lib_name: str) -> dict:
    meta_file = library_path(lib_name) / "lib.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text(encoding="utf-8"))
    return {"name": lib_name}


def create_cell(lib_name: str, cell_name: str) -> bool:
    """Create cell folder (with schematic/layout/symbol subfolders) and cell.json."""
    path = cell_path(lib_name, cell_name)
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    for view in ("schematic", "layout", "symbol"):
        (path / view).mkdir(exist_ok=True)
    meta = {
        "name": cell_name,
        "library": lib_name,
        "created_at": datetime.now().isoformat(),
        "views": [],
    }
    (path / "cell.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return True


def delete_cell(lib_name: str, cell_name: str):
    import shutil

    path = cell_path(lib_name, cell_name)
    if path.exists():
        shutil.rmtree(path)


def list_cells(lib_name: str) -> list:
    path = library_path(lib_name)
    if not path.exists():
        return []
    return [
        p.name
        for p in path.iterdir()
        if p.is_dir() and (p / "cell.json").exists()
    ]


def get_cell_meta(lib_name: str, cell_name: str) -> dict:
    meta_file = cell_path(lib_name, cell_name) / "cell.json"
    if meta_file.exists():
        return json.loads(meta_file.read_text(encoding="utf-8"))
    return {"name": cell_name, "library": lib_name, "views": []}


def cell_has_view(lib_name: str, cell_name: str, view: str) -> bool:
    return view_file(lib_name, cell_name, view).exists()


def save_view(lib_name: str, cell_name: str, view: str, data: dict):
    """Save view data dict to JSON file. Creates folders if needed."""
    create_library(lib_name)
    if not cell_path(lib_name, cell_name).exists():
        create_cell(lib_name, cell_name)
    vpath = view_path(lib_name, cell_name, view)
    vpath.mkdir(parents=True, exist_ok=True)
    vfile = vpath / f"{view}.json"
    vfile.write_text(json.dumps(data, indent=2), encoding="utf-8")

    meta = get_cell_meta(lib_name, cell_name)
    if view not in meta.get("views", []):
        meta.setdefault("views", []).append(view)
        (cell_path(lib_name, cell_name) / "cell.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )


def load_view(lib_name: str, cell_name: str, view: str) -> dict:
    """Load view data dict from JSON file. Returns {} if not found."""
    vfile = view_file(lib_name, cell_name, view)
    if vfile.exists():
        return json.loads(vfile.read_text(encoding="utf-8"))
    return {}


def get_views(lib_name: str, cell_name: str) -> list:
    """Return list of view names that have data files."""
    result = []
    for view in ("schematic", "layout", "symbol"):
        if cell_has_view(lib_name, cell_name, view):
            result.append(view)
    return result
