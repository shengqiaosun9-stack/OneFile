import ai_service


def test_deepseek_provider_uses_deepseek_env_without_hunyuan_extra_body(monkeypatch):
    monkeypatch.setenv("ONEPITCH_AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.delenv("HUNYUAN_API_KEY", raising=False)
    monkeypatch.delenv("HUNYUAN_MODEL", raising=False)
    monkeypatch.delenv("HUNYUAN_BASE_URL", raising=False)

    assert ai_service.get_ai_provider() == "deepseek"
    assert ai_service.get_model_name() == "deepseek-v4-flash"
    assert ai_service.get_base_url() == "https://api.deepseek.com"

    kwargs = ai_service.build_chat_completion_kwargs(
        temperature=0.2,
        messages=[{"role": "user", "content": "hello"}],
    )
    assert kwargs["model"] == "deepseek-v4-flash"
    assert "extra_body" not in kwargs


def test_hunyuan_provider_keeps_enhancement_extra_body(monkeypatch):
    monkeypatch.setenv("ONEPITCH_AI_PROVIDER", "hunyuan")
    monkeypatch.setenv("HUNYUAN_MODEL", "hunyuan-turbos-latest")

    kwargs = ai_service.build_chat_completion_kwargs(
        temperature=0.2,
        messages=[{"role": "user", "content": "hello"}],
    )

    assert kwargs["model"] == "hunyuan-turbos-latest"
    assert kwargs["extra_body"] == {"enable_enhancement": True}
