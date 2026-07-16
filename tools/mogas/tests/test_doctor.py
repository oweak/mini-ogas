from tools.mogas.commands import doctor


def test_doctor_never_prints_secret_prefixes(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(doctor, "PROJ_ROOT", tmp_path)
    monkeypatch.setattr(doctor, "check", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(doctor, "_run_cmd", lambda *_args, **_kwargs: "test-version")
    monkeypatch.setenv("AI_DISPATCHER_TOKEN", "dispatcher-private-token")
    monkeypatch.setenv("API_ACCESS_TOKEN", "operator-token-private")

    doctor.run()

    output = capsys.readouterr().out
    assert "dispatcher-private" not in output
    assert "operator-t" not in output
    assert output.count("SET (redacted)") >= 2
