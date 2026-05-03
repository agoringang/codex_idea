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