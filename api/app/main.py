from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.models.database import engine, Base, init_db
from app.routers import (
    analysis, evidence, reports, license as license_router, settings,
    ai_copilot, prediction,
    document_intelligence, benchmarking, compliance as compliance_router,
    consolidation, asia_markets, cloud_sync,
    time_series, financial_engineering, backtest,
    fuzzy_mcdm, factor_analysis, black_litterman, sentiment,
    stochastic_calculus, network_analysis, causal_inference,
    reinforcement_learning, fuzzy_neural, advanced_optimization,
    credit_exposure, margin_models, credit_rating, counterparty_monitor,
    risk_methodology, regional, public_filings,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    yield
    # Shutdown
    engine.dispose()


app = FastAPI(
    title="Sentinel Risk API",
    description=(
        "Backend API for the Sentinel Risk workbench: credit risk, risk methodology "
        "and credit exposure management, with market coverage for India, China, "
        "Japan and South Korea."
    ),
    version="0.6.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(evidence.router, prefix="/api/v1/evidence", tags=["Evidence Review"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(license_router.router, prefix="/api/v1/license", tags=["License"])
app.include_router(settings.router, prefix="/api/v1/settings", tags=["Settings"])
app.include_router(ai_copilot.router, prefix="/api/v1/ai", tags=["AI Copilot"])
app.include_router(prediction.router, prefix="/api/v1/prediction", tags=["Prediction"])
app.include_router(document_intelligence.router, prefix="/api/v1/document-intelligence", tags=["Document Intelligence"])
app.include_router(benchmarking.router, prefix="/api/v1/benchmarking", tags=["Benchmarking"])
app.include_router(compliance_router.router, prefix="/api/v1/compliance", tags=["Compliance"])
app.include_router(consolidation.router, prefix="/api/v1/consolidation", tags=["Consolidation"])
app.include_router(asia_markets.router, prefix="/api/v1/asia-markets", tags=["Asia Markets"])
app.include_router(cloud_sync.router, prefix="/api/v1/cloud-sync", tags=["Cloud Sync"])
app.include_router(time_series.router, prefix="/api/v1/time-series", tags=["Time Series"])
app.include_router(financial_engineering.router, prefix="/api/v1/financial-engineering", tags=["Financial Engineering"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["Backtesting"])
app.include_router(fuzzy_mcdm.router, prefix="/api/v1/fuzzy-mcdm", tags=["Fuzzy MCDM"])
app.include_router(factor_analysis.router, prefix="/api/v1/factor-analysis", tags=["Factor Analysis"])
app.include_router(black_litterman.router, prefix="/api/v1/black-litterman", tags=["Black-Litterman"])
app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["Sentiment Analysis"])
app.include_router(stochastic_calculus.router, prefix="/api/v1/stochastic-calculus", tags=["Stochastic Calculus"])
app.include_router(network_analysis.router, prefix="/api/v1/network-analysis", tags=["Network Analysis"])
app.include_router(causal_inference.router, prefix="/api/v1/causal-inference", tags=["Causal Inference"])
app.include_router(reinforcement_learning.router, prefix="/api/v1/reinforcement-learning", tags=["Reinforcement Learning"])
app.include_router(fuzzy_neural.router, prefix="/api/v1/fuzzy-neural", tags=["Fuzzy Neural"])
app.include_router(advanced_optimization.router, prefix="/api/v1/advanced-optimization", tags=["Advanced Optimization"])
app.include_router(credit_exposure.router, prefix="/api/v1/credit-exposure", tags=["Credit Exposure"])
app.include_router(margin_models.router, prefix="/api/v1/margin-models", tags=["Margin Models"])
app.include_router(credit_rating.router, prefix="/api/v1/credit-rating", tags=["Credit Rating"])
app.include_router(counterparty_monitor.router, prefix="/api/v1/counterparty-monitor", tags=["Counterparty Monitor"])
app.include_router(risk_methodology.router, prefix="/api/v1/risk-methodology", tags=["Risk Methodology"])
app.include_router(regional.router, prefix="/api/v1/regional", tags=["Regional Reference"])
app.include_router(public_filings.router, prefix="/api/v1/public-filings", tags=["Public Filings"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": "0.6.0"}
