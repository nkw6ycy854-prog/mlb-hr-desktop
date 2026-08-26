from mlb_hr.services import bootstrap


def test_ai_review_disabled_by_default_even_with_configured_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("MLB_HR_DATA_DIR", str(tmp_path))

    _service, _paths, store = bootstrap.build_services()
    store.set_state("ollama_model", "llama3")

    service = bootstrap.build_services()[0]
    assert service.ai is None


def test_ai_review_enabled_builds_configured_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("MLB_HR_DATA_DIR", str(tmp_path))

    _service, _paths, store = bootstrap.build_services()
    store.set_state("ollama_model", "llama3")
    store.set_state("ai_review_enabled", True)

    service = bootstrap.build_services()[0]
    assert service.ai is not None
