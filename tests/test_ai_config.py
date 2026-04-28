"""AI configuration persistence and privacy, using an isolated SQLite database."""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.models import SettingsModel
from app.routers import ai_copilot, settings


@pytest.fixture
def ai_app(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(ai_copilot.router, prefix="/ai")
    app.include_router(settings.router, prefix="/settings")

    def isolated_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    chat = AsyncMock(return_value={"response": "Computed explanation", "sources": []})
    monkeypatch.setattr(ai_copilot, "chat_with_ai", chat)
    with TestClient(app) as client:
        yield client, sessions, chat
    engine.dispose()


def config(**updates):
    return {
        "api_key": "test-private-key-not-a-real-secret",
        "api_endpoint": "https://provider.example/v1",
        "model": "configured-model-id",
        **updates,
    }


def test_empty_database_has_no_configured_model_or_endpoint(ai_app):
    client, _, chat = ai_app
    assert client.get("/ai/configure").json() == {
        "configured": False, "model": "", "endpoint": "",
    }
    assert client.post("/ai/chat", json={"message": "Explain the ratios"}).status_code == 200
    assert chat.await_args.kwargs["api_key"] is None
    assert chat.await_args.kwargs["model"] == ""


def test_configure_persists_on_empty_database_and_chat_uses_it(ai_app):
    client, sessions, chat = ai_app
    payload = config()
    response = client.post("/ai/configure", json=payload)
    assert response.status_code == 200
    assert payload["api_key"] not in response.text
    with sessions() as db:
        stored = db.get(SettingsModel, "ai_config")
        assert stored is not None
        assert json.loads(stored.value) == payload
    response = client.get("/ai/configure")
    assert response.json() == {
        "configured": True, "model": payload["model"], "endpoint": payload["api_endpoint"],
    }
    assert payload["api_key"] not in response.text
    assert client.post("/ai/chat", json={"message": "Explain the ratios"}).status_code == 200
    assert {name: chat.await_args.kwargs[name] for name in payload} == payload


def test_preferences_and_ai_settings_remain_independent_on_updates(ai_app):
    client, sessions, _ = ai_app
    prefs = {"default_language": "en", "chart_theme": "dark", "decimal_places": 4, "auto_save": False}
    assert client.put("/settings/preferences", json=prefs).status_code == 200
    assert client.post("/ai/configure", json=config()).status_code == 200
    replacement = config(api_key="replacement-test-key", model="another-model-id")
    assert client.post("/ai/configure", json=replacement).status_code == 200
    assert client.get("/settings/preferences").json() == prefs
    prefs["decimal_places"] = 3
    assert client.put("/settings/preferences", json=prefs).status_code == 200
    assert client.get("/ai/configure").json()["model"] == replacement["model"]
    with sessions() as db:
        assert db.query(SettingsModel).filter_by(key="ai_config").count() == 1
        assert json.loads(db.get(SettingsModel, "ai_config").value) == replacement


def test_legacy_config_is_preserved_until_explicitly_replaced(ai_app):
    client, sessions, chat = ai_app
    legacy = config(api_key="legacy-test-key", model="legacy-model-id")
    with sessions() as db:
        db.add(SettingsModel(key="auto_save", value="true"))
        db.add(SettingsModel(key="chart_theme", value='"light"', ai_config=json.dumps(legacy)))
        db.commit()
    assert client.get("/ai/configure").json() == {
        "configured": True, "model": legacy["model"], "endpoint": legacy["api_endpoint"],
    }
    assert client.post("/ai/chat", json={"message": "Explain"}).status_code == 200
    assert chat.await_args.kwargs["api_key"] == legacy["api_key"]
    assert chat.await_args.kwargs["model"] == legacy["model"]
    replacement = config(model="replacement-model-id")
    assert client.post("/ai/configure", json=replacement).status_code == 200
    assert client.post("/ai/chat", json={"message": "Explain"}).status_code == 200
    assert chat.await_args.kwargs["api_key"] == replacement["api_key"]
    assert client.get("/ai/configure").json()["model"] == replacement["model"]
    with sessions() as db:
        assert json.loads(db.get(SettingsModel, "chart_theme").ai_config) == legacy


@pytest.mark.parametrize("model", [None, "", "   "])
def test_model_is_required_and_validation_does_not_echo_key(ai_app, model):
    client, _, _ = ai_app
    payload = config()
    if model is None:
        payload.pop("model")
    else:
        payload["model"] = model
    response = client.post("/ai/configure", json=payload)
    assert response.status_code == 422
    assert payload["api_key"] not in response.text


@pytest.mark.parametrize("endpoint", [
    "", "provider.example/v1", "ftp://provider.example/v1", "https://",
    "https://host name/v1", "https://provider.example:bad/v1",
    "https://user:password@provider.example/v1", "https://provider.example/v1?key=secret",
    "https://provider.example/v1#secret",
])
def test_endpoint_requires_http_url_without_embedded_credentials(ai_app, endpoint):
    client, _, _ = ai_app
    payload = config(api_endpoint=endpoint)
    response = client.post("/ai/configure", json=payload)
    assert response.status_code == 422
    assert payload["api_key"] not in response.text
    assert endpoint not in response.text if endpoint else True


def test_config_values_are_trimmed_and_local_http_is_supported(ai_app):
    client, sessions, _ = ai_app
    response = client.post("/ai/configure", json=config(
        api_key="  test-key  ", model="  custom-model  ",
        api_endpoint="  http://127.0.0.1:1234/v1/  ",
    ))
    assert response.status_code == 200
    assert response.json()["model"] == "custom-model"
    assert response.json()["endpoint"] == "http://127.0.0.1:1234/v1"
    with sessions() as db:
        assert json.loads(db.get(SettingsModel, "ai_config").value)["api_key"] == "test-key"


def test_storage_error_is_generic_and_previous_config_survives(ai_app, monkeypatch):
    client, sessions, _ = ai_app
    assert client.post("/ai/configure", json=config()).status_code == 200
    payload = config(api_key="new-private-test-key")
    def fail_commit(_self):
        raise RuntimeError(f"SQL failed with parameters {payload['api_key']}")
    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post("/ai/configure", json=payload)
    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to save AI configuration."}
    assert payload["api_key"] not in response.text
    with sessions() as db:
        assert json.loads(db.get(SettingsModel, "ai_config").value) == config()


def test_provider_errors_cannot_echo_configured_key(ai_app):
    client, _, chat = ai_app
    payload = config()
    assert client.post("/ai/configure", json=payload).status_code == 200
    chat.return_value = {
        "response": f"Provider rejected {payload['api_key']}",
        "error": payload["api_key"], "sources": [],
    }
    response = client.post("/ai/chat", json={"message": "Explain"})
    assert response.status_code == 200
    assert payload["api_key"] not in response.text
    chat.side_effect = RuntimeError(f"Connection failed: {payload['api_key']}")
    response = client.post("/ai/chat", json={"message": "Explain"})
    assert response.status_code == 502
    assert payload["api_key"] not in response.text
