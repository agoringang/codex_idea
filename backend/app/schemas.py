from typing import Literal

from pydantic import BaseModel, Field


# Frontend-compatible types
class Runner(BaseModel):
    number: int
    gate: int
    name: str
    jockey: str
    weight: str | None = None # Added to match frontend
    rating: int
    odds: float
    tags: list[str]


class Race(BaseModel):
    id: str
    date: str
    day: str
    venue: str
    meeting: str
    raceNo: str
    start: str
    title: str
    grade: str | None = None
    course: str
    status: str
    officialNote: str
    source: str | None = None # Added to match frontend
    runners: list[Runner]


ModelMode = Literal["ensemble", "deep", "value"]
BetType = Literal[
    "win",
    "place",
    "support",
    "bracket_quinella",
    "quinella",
    "wide",
    "exacta",
    "trio",
    "trifecta",
    "win5",
]

DEFAULT_BET_TYPES: list[BetType] = [
    "win",
    "place",
    "support",
    "bracket_quinella",
    "quinella",
    "wide",
    "exacta",
    "trio",
    "trifecta",
]


class RunnerInput(BaseModel):
    id: str
    gate: int = Field(default=1, ge=1, le=8)
    number: int = Field(ge=1)
    name: str
    market_odds: float = Field(gt=1)
    place_odds: float = Field(gt=1)
    speed: float = Field(ge=0, le=100)
    stamina: float = Field(ge=0, le=100)
    pace: float = Field(ge=0, le=100)
    condition: float = Field(ge=0, le=100)
    base_win: float = Field(gt=0, lt=1)
    carried_weight: float | None = Field(default=None, ge=0)
    horse_weight: float | None = Field(default=None, ge=0)
    horse_weight_diff: float | None = None
    distance: int | None = Field(default=None, ge=0)
    age: int | None = Field(default=None, ge=0)
    sex: str | None = None
    venue: str | None = None
    surface: str | None = None
    going: str | None = None
    weather: str | None = None
    running_style: str | None = None
    jockey: str | None = None
    trainer: str | None = None
    owner: str | None = None
    breeder: str | None = None
    sire: str | None = None
    dam_sire: str | None = None
    days_since_last_run: int | None = Field(default=None, ge=0)
    avg_last3_speed: float | None = Field(default=None, ge=0)
    best_time: float | None = Field(default=None, ge=0)
    last600m: float | None = Field(default=None, ge=0)
    jockey_win_rate: float | None = Field(default=None, ge=0, le=1)
    trainer_win_rate: float | None = Field(default=None, ge=0, le=1)
    horse_recent_win_rate: float | None = Field(default=None, ge=0, le=1)
    horse_recent_place_rate: float | None = Field(default=None, ge=0, le=1)
    training_score: float | None = Field(default=None, ge=0, le=100)
    bloodline_score: float | None = Field(default=None, ge=0, le=100)
    odds_rank: int | None = Field(default=None, ge=1)
    odds_delta: float | None = None
    ticket_pool_share: float | None = Field(default=None, ge=0, le=1)
    draw_bias: float | None = Field(default=None, ge=-1, le=1)


class RaceRequest(BaseModel):
    race_id: str
    model_mode: ModelMode = "ensemble"
    risk_level: float = Field(default=48, ge=0, le=100)
    bankroll: float = Field(default=100_000, gt=0)
    min_edge: float = Field(default=0.08, ge=0, le=1)
    min_probability: float = Field(default=0.0, ge=0, le=1)
    max_candidate_odds: float = Field(default=999.0, gt=1)
    max_edge: float | None = Field(default=None, ge=0)
    min_portfolio_roi: float = Field(default=1.0, ge=0)
    max_exposure: float = Field(default=0.02, gt=0, le=0.1)
    enabled_bet_types: list[BetType] = Field(default_factory=lambda: DEFAULT_BET_TYPES.copy())
    runners: list[RunnerInput] = Field(min_length=2)


class RunnerPrediction(BaseModel):
    id: str
    gate: int
    number: int
    name: str
    win_probability: float
    top2_probability: float | None = None
    place_probability: float
    second_probability: float | None = None
    third_probability: float | None = None
    out_probability: float | None = None
    fair_odds: float
    market_odds: float
    edge: float
    score: float


class BetLeg(BaseModel):
    label: str
    numbers: list[int]


class BetRecommendation(BaseModel):
    selection: str
    note: str
    bet_type: BetType
    strategy: str = "single"
    tickets: int = Field(default=1, ge=1)
    unit_stake: float = Field(default=100, ge=0)
    covered_selections: list[str] = Field(default_factory=list)
    legs: list[BetLeg] = Field(default_factory=list)
    probability: float
    odds: float
    edge: float
    kelly_fraction: float
    stake: float


class RacePrediction(BaseModel):
    race_id: str
    model_mode: ModelMode
    runners: list[RunnerPrediction]
    recommendations: list[BetRecommendation]
    total_stake: float
    expected_return: float
    expected_roi: float
    warning: str


class SyncJobRequest(BaseModel):
    provider: Literal["jravan", "csv", "netkeiba_csv"] = "jravan"
    years: int = Field(default=20, ge=1, le=30)
    include_realtime: bool = True
    raw_path: str | None = None


class SyncJobResponse(BaseModel):
    provider: str
    years: int
    status: Literal["planned", "queued"]
    next_steps: list[str]


class TrainingJobRequest(BaseModel):
    start_year: int = Field(ge=1986)
    end_year: int = Field(ge=1986)
    target: Literal["win", "place", "rank", "multiclass"] = "rank"
    include_odds_snapshots: bool = True


class TrainingJobResponse(BaseModel):
    status: Literal["planned", "queued"]
    dataset: str
    targets: list[str]
    next_steps: list[str]


class BackendStage(BaseModel):
    id: str
    label: str
    status: Literal["idle", "running", "ready", "blocked", "partial"]
    detail: str
    records: int
    latency_ms: int | None = None


class ModelArtifact(BaseModel):
    name: str
    version: str
    target: str
    metric: str
    path: str


class FeatureCoverage(BaseModel):
    group: str
    status: str # Literal["ready", "partial", "missing"]
    fields: list[str]
    source: str
    detail: str


class BacktestSummary(BaseModel):
    status: str # Literal["not_started", "sample", "ready"]
    window: str
    races: int
    bets: int
    total_stake: float
    total_payout: float
    roi: float
    hit_rate: float
    max_drawdown: float
    note: str


class BackendStatus(BaseModel):
    mode: str # Literal["simulation", "live", "local-trained"]
    provider: str # Literal["jravan", "csv", "netkeiba_csv"]
    data_window: str
    active_model: str
    stages: list[BackendStage]
    artifacts: list[ModelArtifact]
    feature_coverage: list[FeatureCoverage]
    backtest: BacktestSummary
    runtime_notes: list[str]


class LiveOddsMove(BaseModel):
    number: int
    name: str
    previous_odds: float
    current_odds: float
    direction: Literal["up", "down", "flat"]
    reason: str


class LiveScratch(BaseModel):
    number: int
    name: str
    reason: str
    announced_at: str


class LiveResult(BaseModel):
    status: Literal["pending", "hit", "miss", "refund", "official"]
    payout: float = 0
    message: str
    winning_selection: str | None = None
    order: list[int] | None = None


class LiveSnapshot(BaseModel):
    racecard_status: Literal["waiting", "available", "parsed"]
    odds_status: Literal["waiting", "monitoring", "closed"]
    result_status: Literal["waiting", "official"]
    updated_at: str
    next_poll_seconds: int
    odds_moves: list[LiveOddsMove]
    scratches: list[LiveScratch]
    result: LiveResult
    alerts: list[str]


class LivePollingJobRequest(BaseModel):
    provider: Literal["jravan", "accessd", "simulation", "netkeiba_csv"] = "simulation"
    interval_seconds: int = Field(default=60, ge=10, le=600)
    race_ids: list[str] = Field(default_factory=list)


class LivePollingJobResponse(BaseModel):
    status: Literal["planned", "queued"]
    provider: str
    interval_seconds: int
    watched_races: int
    next_steps: list[str]
