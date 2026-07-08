import core.doctor as doctor


def test_run_checks_returns_wellformed_list():
    checks = doctor.run_checks()
    assert isinstance(checks, list) and len(checks) >= 8
    for c in checks:
        assert set(c.keys()) == {"name", "ok", "detail"}
        assert isinstance(c["ok"], bool)
        assert isinstance(c["name"], str) and c["name"]


def test_print_report_returns_bool_and_never_raises(capsys):
    result = doctor.print_report()
    assert isinstance(result, bool)
    out = capsys.readouterr().out
    assert "PIORUN DOCTOR" in out


def test_individual_checks_have_names():
    assert doctor.check_ddgs()["name"] == "Wyszukiwarka (ddgs)"
    assert doctor.check_disk()["name"] == "Wolne miejsce (workdir)"
    # ddgs jest zainstalowany w tym srodowisku
    assert doctor.check_ddgs()["ok"] is True
