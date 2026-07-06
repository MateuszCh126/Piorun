import os

from core.config import _bool_from_env, _int_from_env, _parse_env_file


def test_int_from_env(monkeypatch):
    monkeypatch.setenv("PIORUN_TEST_INT", "42")
    assert _int_from_env("PIORUN_TEST_INT", 7) == 42
    monkeypatch.setenv("PIORUN_TEST_INT", "nie-liczba")
    assert _int_from_env("PIORUN_TEST_INT", 7) == 7
    monkeypatch.delenv("PIORUN_TEST_INT", raising=False)
    assert _int_from_env("PIORUN_TEST_INT", 7) == 7


def test_bool_from_env(monkeypatch):
    for truthy in ("1", "true", "YES", "on", "y"):
        monkeypatch.setenv("PIORUN_TEST_BOOL", truthy)
        assert _bool_from_env("PIORUN_TEST_BOOL", False) is True
    monkeypatch.setenv("PIORUN_TEST_BOOL", "false")
    assert _bool_from_env("PIORUN_TEST_BOOL", True) is False


def test_parse_env_file_respects_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / "test.env"
    env_file.write_text(
        "# komentarz\n"
        "PIORUN_TEST_A=abc\n"
        'PIORUN_TEST_B="w cudzyslowie"\n'
        "linia bez znaku rownosci\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PIORUN_TEST_A", raising=False)
    monkeypatch.setenv("PIORUN_TEST_B", "juz-ustawione")
    _parse_env_file(env_file)
    assert os.environ["PIORUN_TEST_A"] == "abc"
    # setdefault: jawna zmienna srodowiskowa wygrywa z plikiem .env
    assert os.environ["PIORUN_TEST_B"] == "juz-ustawione"
    monkeypatch.delenv("PIORUN_TEST_A", raising=False)
