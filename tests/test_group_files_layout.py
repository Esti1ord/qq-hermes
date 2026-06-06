import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module():
    spec = importlib.util.spec_from_file_location("bridge_under_test_group_files_layout", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_group_persona_prefers_group_folder(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    bridge.PERSONA_FILE = tmp_path / "persona.md"
    bridge.PERSONA_FILE.write_text("根目录旧人格", encoding="utf-8")
    (bridge.GROUP_CONFIG_DIR / "975805598").mkdir(parents=True)
    (bridge.GROUP_CONFIG_DIR / "975805598" / "persona.md").write_text("旧群组内人格", encoding="utf-8")

    assert bridge.persona_file_for_group(975805598) == bridge.GROUP_CONFIG_DIR / "975805598" / "persona.md"


def test_default_group_people_prefers_group_folder(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PEOPLE_FILE.write_text("根目录旧people", encoding="utf-8")
    (bridge.GROUP_CONFIG_DIR / "975805598").mkdir(parents=True)
    (bridge.GROUP_CONFIG_DIR / "975805598" / "people.md").write_text("旧群组内people", encoding="utf-8")

    assert bridge.group_people_file_for_group(975805598) == bridge.GROUP_CONFIG_DIR / "975805598" / "people.md"


def test_new_group_without_people_still_has_no_people_file(tmp_path):
    bridge = load_bridge_module()
    bridge.GROUP_CONFIG_DIR = tmp_path / "groups"
    bridge.PEOPLE_FILE = tmp_path / "people.md"
    bridge.PEOPLE_FILE.write_text("根目录旧people", encoding="utf-8")
    (bridge.GROUP_CONFIG_DIR / "781423661").mkdir(parents=True)

    assert bridge.group_people_file_for_group(781423661) is None
