import json
from typing import Any, List, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import AnalysisModel, RatioResultModel, SettingsModel
from app.services.ai_copilot import chat_with_ai


class PrivateValidationRoute(APIRoute):
    """Validation responses must not echo requests containing provider keys."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                return JSONResponse(status_code=422, content={
                    "detail": [
                        {name: item[name] for name in ("type", "loc", "msg")}
                        for item in error.errors()
                    ],
                })

        return private_handler


router = APIRouter(route_class=PrivateValidationRoute)
AI_CONFIG_KEY = "ai_config"


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    analysis_id: Optional[str] = None
    conversation_history: List[ChatMessage] = Field(default_factory=list)


class AIConfigRequest(BaseModel):
    api_key: SecretStr
    api_endpoint: str = "https://api.openai.com/v1"
    model: str = Field(..., min_length=1)

    @field_validator("api_key")
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value().strip()
        if not key:
            raise ValueError("API key must not be empty")
        return SecretStr(key)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("Model ID must not be empty")
        return model

    @field_validator("api_endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        endpoint = value.strip().rstrip("/")
        try:
            parsed = urlsplit(endpoint)
            valid = (
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and not parsed.username
                and not parsed.password
                and not parsed.query
                and not parsed.fragment
                and not any(char.isspace() or ord(char) < 32 for char in endpoint)
                and "\\" not in endpoint
            )
            # Accessing port checks for invalid or out-of-range port numbers.
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("Endpoint must be an HTTP(S) URL without credentials, query, or fragment")
        return endpoint


def _decode_config(raw: str | None) -> AIConfigRequest | None:
    if not raw:
        return None
    try:
        return AIConfigRequest.model_validate_json(raw)
    except (ValidationError, TypeError):
        return None


def _load_config(db: Session) -> AIConfigRequest | None:
    stored = db.get(SettingsModel, AI_CONFIG_KEY)
    if stored is not None:
        return _decode_config(stored.value)
    # Older versions attached config to an arbitrary preference row. Keep valid
    # legacy settings usable until the user explicitly saves a replacement.
    legacy_rows = db.query(SettingsModel).filter(
        SettingsModel.ai_config.is_not(None),
    ).order_by(SettingsModel.updated_at.desc(), SettingsModel.key).all()
    for row in legacy_rows:
        config = _decode_config(row.ai_config)
        if config is not None:
            return config
    return None


def _redact_key(value: Any, key: str | None) -> Any:
    if not key:
        return value
    if isinstance(value, str):
        return value.replace(key, "[redacted]")
    if isinstance(value, list):
        return [_redact_key(item, key) for item in value]
    if isinstance(value, dict):
        return {_redact_key(name, key): _redact_key(item, key) for name, item in value.items()}
    return value


@router.post("/chat")
async def copilot_chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Chat with the AI Financial Copilot."""
    analysis_data = None
    prediction_data = None
    if request.analysis_id:
        try:
            analysis = db.query(AnalysisModel).filter(
                AnalysisModel.id == request.analysis_id,
            ).first()
            if analysis:
                ratios = db.query(RatioResultModel).filter(
                    RatioResultModel.analysis_id == request.analysis_id,
                ).all()
                analysis_data = {
                    "company_name": analysis.company_name,
                    "period": analysis.period,
                    "ratios": [
                        {
                            "category": ratio.category,
                            "ratio_name": ratio.ratio_name,
                            "value": ratio.value,
                            "unit": ratio.unit,
                            "benchmark": ratio.benchmark,
                            "status": ratio.status,
                        }
                        for ratio in ratios
                    ],
                }
                try:
                    from app.services.predictor import predict_from_analysis
                    prediction_data = predict_from_analysis(analysis_data)
                except Exception:
                    pass  # Prediction is optional.
        except Exception:
            pass  # Continue without optional analysis context.

    try:
        config = _load_config(db)
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to load AI configuration.") from None
    api_key = config.api_key.get_secret_value() if config else None
    try:
        result = await chat_with_ai(
            message=request.message,
            analysis_data=analysis_data,
            prediction_data=prediction_data,
            conversation_history=[message.model_dump() for message in request.conversation_history],
            api_key=api_key,
            api_endpoint=config.api_endpoint if config else None,
            model=config.model if config else "",
        )
    except Exception:
        raise HTTPException(status_code=502, detail="Unable to contact the AI service.") from None
    return _redact_key(result, api_key)


@router.post("/configure")
async def configure_ai(config: AIConfigRequest, db: Session = Depends(get_db)):
    """Save provider settings in their own key/value record."""
    key = config.api_key.get_secret_value()
    try:
        value = json.dumps({
            "api_key": key, "api_endpoint": config.api_endpoint, "model": config.model,
        })
        stored = db.get(SettingsModel, AI_CONFIG_KEY)
        if stored is None:
            db.add(SettingsModel(key=AI_CONFIG_KEY, value=value))
        else:
            stored.value = value
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to save AI configuration.") from None
    return _redact_key({
        "status": "configured", "model": config.model, "endpoint": config.api_endpoint,
    }, key)


@router.get("/configure")
async def get_ai_config(db: Session = Depends(get_db)):
    """Return configuration status without the provider key."""
    try:
        config = _load_config(db)
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to load AI configuration.") from None
    if config is None:
        return {"configured": False, "model": "", "endpoint": ""}
    return _redact_key({
        "configured": True, "model": config.model, "endpoint": config.api_endpoint,
    }, config.api_key.get_secret_value())
