export type RaceStatus = "prediction-ready" | "card-ready" | "racecard-available" | "schedule-only" | "finished";

export type Runner = {
  number: number;
  gate: number;
  name: string;
  jockey: string;
  weight: string;
  rating: number;
  odds: number;
  tags: string[];
};

export type Race = {
  id: string;
  date: string;
  day: string;
  venue: string;
  meeting: string;
  raceNo: string;
  start: string;
  title: string;
  grade: string;
  course: string;
  status: RaceStatus;
  officialNote: string;
  source: string;
  runners: Runner[];
};

export type PricedRunner = Runner & {
  winProbability: number;
  placeProbability: number;
  fairOdds: number;
  edge: number;
};

export type Bet = {
  type: "単勝" | "複勝" | "枠連" | "馬連" | "馬単" | "ワイド" | "3連複" | "3連単";
  selection: string;
  probability: number;
  odds: number;
  edge: number;
  stake: number;
  strategy?: string;
  tickets?: number;
  unitStake?: number;
  note: string;
  isHit?: boolean;
};

export type OddsMove = {
  number: number;
  name: string;
  previousOdds: number;
  currentOdds: number;
  direction: "up" | "down" | "flat";
  reason: string;
};

export type Scratch = {
  number: number;
  name: string;
  reason: string;
  announcedAt: string;
};

export type LiveResult = {

  status: "pending" | "hit" | "miss" | "refund" | "official";

  message: string;

  payout?: number;

  winningSelection?: string;

  order?: number[];

};



export type LiveSnapshot = {

  racecardStatus: "waiting" | "available" | "parsed";

  oddsStatus: "waiting" | "monitoring" | "closed";

  resultStatus: "waiting" | "official";

  nextPollSeconds: number;

  updatedAt: string;

  oddsMoves: OddsMove[];

  scratches: Scratch[];

  result: LiveResult;

  alerts: string[];

};



export type RaceOverride = Partial<Pick<Race, "title" | "grade" | "course" | "status" | "officialNote">> & {

  runners?: Runner[];

};



export type MeetingProgram = {

  key: string;

  date: string;

  day: string;

  venue: string;

  meeting: string;

  times: string[];

};



export type BackendStatus = {

  mode: string;

  provider: string;

  data_window: string;

  active_model: string;

  stages: {

    id: string;

    label: string;

    status: "idle" | "running" | "ready" | "blocked" | "partial";

    detail: string;

    records: number;

    latency_ms: number | null;

  }[];

  artifacts: {

    name: string;

    version: string;

    target: string;

    metric: string;

    path: string;

  }[];

  feature_coverage: {

    group: string;

    status: string;

    fields: string[];

    source: string;

    detail: string;

  }[];

  backtest: {

    status: string;

    window: string;

    races: number;

    bets: number;

    total_stake: number;

    total_payout: number;

    roi: number;

    hit_rate: number;

    max_drawdown: number;

    note: string;

  };

  runtime_notes: string[];

};

export type ApiRunnerPrediction = {
  id: string;
  gate: number;
  number: number;
  name: string;
  win_probability: number;
  place_probability: number;
  fair_odds: number;
  market_odds: number;
  edge: number;
  score: number;
};

export type ApiBetRecommendation = {
  selection: string;
  note: string;
  bet_type:
    | "win"
    | "place"
    | "support"
    | "bracket_quinella"
    | "quinella"
    | "wide"
    | "exacta"
    | "trio"
    | "trifecta"
    | "win5";
  strategy?: string;
  tickets?: number;
  unit_stake?: number;
  covered_selections?: string[];
  probability: number;
  odds: number;
  edge: number;
  kelly_fraction: number;
  stake: number;
};

export type ApiRacePrediction = {
  race_id: string;
  model_mode: "ensemble" | "deep" | "value";
  runners: ApiRunnerPrediction[];
  recommendations: ApiBetRecommendation[];
  total_stake: number;
  expected_return: number;
  expected_roi: number;
  warning: string;
};

export type PredictionProofEntry = {
  raceId: string;
  title: string;
  date: string;
  venue: string;
  predictedTop: number;
  actualTop: number;
  topHit: boolean;
  predictedTop3: number[];
  actualTop3: number[];
  top3HitCount: number;
};

export type PredictionProofSummary = {
  checkedRaces: number;
  topHitRate: number;
  avgTop3HitCount: number;
};