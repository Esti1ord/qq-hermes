import importlib.util
from pathlib import Path

BRIDGE_PATH = Path(__file__).resolve().parents[1] / "bridge.py"


def load_bridge_module(monkeypatch, group_file: Path):
    monkeypatch.setenv("GROUP_LIST_FILE", str(group_file))
    monkeypatch.delenv("GROUP_IDS", raising=False)
    monkeypatch.delenv("ALLOWED_GROUP_IDS", raising=False)
    spec = importlib.util.spec_from_file_location("bridge_group_config_under_test", BRIDGE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_group_ids_can_be_loaded_from_config_file(tmp_path, monkeypatch):
    group_file = tmp_path / "groups.txt"
    group_file.write_text("# comments ok\n975805598\n781423661 # 宁群\n123456789\n\n", encoding="utf-8")

    bridge = load_bridge_module(monkeypatch, group_file)

    assert {975805598, 781423661, 123456789}.issubset(bridge.ALLOWED_GROUP_IDS)
    assert bridge.is_allowed_group({"group_id": 123456789}) is True
    assert bridge.is_allowed_group({"group_id": 111111111}) is False


def test_add_group_script_creates_full_group_layout_and_preserves_files(tmp_path):
    # Validate script behavior in a copied mini project to avoid mutating real groups.
    import shutil
    import subprocess

    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    (project / "groups").mkdir()
    script_src = Path(__file__).resolve().parents[1] / "scripts" / "add_group.sh"
    script_dst = project / "scripts" / "add_group.sh"
    shutil.copy(script_src, script_dst)
    script_dst.chmod(0o755)

    subprocess.run([str(script_dst), "123456789", "测试群提示"], cwd=project, check=True)
    people_file = project / "groups" / "123456789" / "people.md"
    knowledge_file = project / "groups" / "123456789" / "knowledge.md"
    people_file.write_text("自定义群友资料\n", encoding="utf-8")
    knowledge_file.write_text("自定义知识库\n", encoding="utf-8")

    subprocess.run([str(script_dst), "123456789", "不应覆盖"], cwd=project, check=True)

    assert (project / "groups" / "123456789" / "persona.md").read_text(encoding="utf-8").strip() == "测试群提示"
    assert people_file.read_text(encoding="utf-8") == "自定义群友资料\n"
    assert knowledge_file.read_text(encoding="utf-8") == "自定义知识库\n"
    lines = [x.strip() for x in (project / "groups" / "groups.txt").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert lines == ["123456789"]


def test_add_group_script_default_files_describe_expected_formats(tmp_path):
    import shutil
    import subprocess

    project = tmp_path / "project"
    (project / "scripts").mkdir(parents=True)
    (project / "groups").mkdir()
    script_src = Path(__file__).resolve().parents[1] / "scripts" / "add_group.sh"
    script_dst = project / "scripts" / "add_group.sh"
    shutil.copy(script_src, script_dst)
    script_dst.chmod(0o755)

    subprocess.run([str(script_dst), "123456789"], cwd=project, check=True)

    persona = (project / "groups" / "123456789" / "persona.md").read_text(encoding="utf-8")
    people = (project / "groups" / "123456789" / "people.md").read_text(encoding="utf-8")
    knowledge = (project / "groups" / "123456789" / "knowledge.md").read_text(encoding="utf-8")
    assert "群 123456789 提示词" in persona
    assert "## QQ号或主要昵称" in people
    assert "昵称" in people and "标签" in people
    assert "/search" in knowledge and "/deepseek" in knowledge
