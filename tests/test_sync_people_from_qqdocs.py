import importlib.util
import sqlite3
import tempfile
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_people_from_qqdocs.py"


def load_sync_module():
    spec = importlib.util.spec_from_file_location("sync_people_from_qqdocs_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_cookie_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("create table moz_cookies (host text, name text, value text)")
        con.executemany("insert into moz_cookies values (?, ?, ?)", rows)
        con.commit()
    finally:
        con.close()


def test_file_id_from_doc_url_decodes_markdown_token():
    sync = load_sync_module()

    assert sync.file_id_from_doc_url("https://docs.qq.com/markdown/DV2JWUGFEbUZKaVVD?") == "300000000$WbVPaDmFJiUC"
    assert sync.file_id_from_doc_url("https://docs.qq.com/markdown/DV3ZkWmV3bFRidnhj?") == "300000000$WvdZewlTbvxc"


def test_file_id_from_doc_url_rejects_non_markdown_url():
    sync = load_sync_module()

    with pytest.raises(ValueError):
        sync.file_id_from_doc_url("https://docs.qq.com/doc/not-markdown")


def test_load_cookie_header_uses_private_temp_copy_and_cleans_up(tmp_path, monkeypatch):
    sync = load_sync_module()
    cookie_db = tmp_path / "firefox-cookies.sqlite"
    make_cookie_db(
        cookie_db,
        [
            ("docs.qq.com", "doc_sid", "abc"),
            (".qq.com", "qq_token", "def"),
            ("example.com", "ignored", "bad"),
        ],
    )
    created_tempdirs = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def tracked_temporary_directory(*args, **kwargs):
        kwargs.setdefault("dir", tmp_path)
        td = real_temporary_directory(*args, **kwargs)
        created_tempdirs.append(Path(td.name))
        return td

    monkeypatch.setattr(sync, "FIREFOX_COOKIES", cookie_db)
    monkeypatch.setattr(sync.tempfile, "TemporaryDirectory", tracked_temporary_directory)

    header = sync.load_cookie_header()

    assert "doc_sid=abc" in header
    assert "qq_token=def" in header
    assert "ignored=bad" not in header
    assert created_tempdirs
    assert all(not path.exists() for path in created_tempdirs)


def test_load_cookie_header_cleans_temp_copy_on_sqlite_error(tmp_path, monkeypatch):
    sync = load_sync_module()
    cookie_db = tmp_path / "firefox-cookies.sqlite"
    cookie_db.write_bytes(b"not sqlite")
    created_tempdirs = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def tracked_temporary_directory(*args, **kwargs):
        kwargs.setdefault("dir", tmp_path)
        td = real_temporary_directory(*args, **kwargs)
        created_tempdirs.append(Path(td.name))
        return td

    monkeypatch.setattr(sync, "FIREFOX_COOKIES", cookie_db)
    monkeypatch.setattr(sync.tempfile, "TemporaryDirectory", tracked_temporary_directory)

    with pytest.raises(SystemExit):
        sync.load_cookie_header()

    assert created_tempdirs
    assert all(not path.exists() for path in created_tempdirs)


def test_load_cookie_header_fails_when_no_docs_or_qq_cookies(tmp_path, monkeypatch):
    sync = load_sync_module()
    cookie_db = tmp_path / "firefox-cookies.sqlite"
    make_cookie_db(cookie_db, [("example.com", "ignored", "bad")])
    monkeypatch.setattr(sync, "FIREFOX_COOKIES", cookie_db)

    with pytest.raises(SystemExit):
        sync.load_cookie_header()
