"use client";

import { useEffect, useMemo, useState } from "react";

type Market = "JRA" | "NAR";
type ViewTab = "predict" | "calendar" | "results";
type TabIconId = "today" | "calendar" | "results";
type AppIconId = "waliwali" | "keisya" | "hikaku" | "portfolio";
type RunnerSortKey = "prediction" | "number" | "odds" | "result";
type BettingHeatTone = "hot" | "standard" | "safe" | "pass";

type Runner = {
  number: number;
  gate?: number;
  name: string;
  jockey: string;
  odds: number;
  placeOdds?: number;
  baseWin: number;
  drift: number;
  form: number;
  carriedWeight?: number;
  horseWeight?: number;
  horseWeightDiff?: number;
  age?: number;
  sex?: string;
  trainer?: string;
  runningStyle?: string;
  recentRecord?: string;
  daysSinceLastRun?: number;
  avgLast3Speed?: number;
  bestTime?: number;
  last600m?: number;
  jockeyWinRate?: number;
  trainerWinRate?: number;
  horseRecentWinRate?: number;
  horseRecentPlaceRate?: number;
  horseDistancePlaceRate?: number;
  horseSurfacePlaceRate?: number;
  trainingScore?: number;
  bloodlineScore?: number;
  paddockScore?: number;
  oddsDelta?: number;
  oddsDelta5m?: number;
  oddsDelta15m?: number;
  oddsVolatility?: number;
  ticketPoolShare?: number;
  lap3f?: number;
  lap4f?: number;
  bodyWeightAnnouncedAt?: string;
  payoutWin?: number;
  payoutPlace?: number;
  payoutQuinella?: number;
  payoutWide?: number;
  payoutExacta?: number;
  payoutTrio?: number;
  payoutTrifecta?: number;
  drawBias?: number;
  sireId?: string;
  sire?: string;
  damSireId?: string;
  damSire?: string;
  tags?: string[];
};

type Race = {
  id: string;
  date: string;
  day: string;
  start: string;
  venue: string;
  title: string;
  course: string;
  grade: string;
  market: Market;
  status: "card" | "odds" | "watch" | "finished" | "schedule";
  officialNote?: string;
  source?: string;
  sourceUrl?: string;
  sourceCheckedAt?: string;
  verificationStatus?: "verified" | "stale" | "unverified";
  payouts?: RacePayout[];
  runners: Runner[];
};

type RacePayout = {
  betType: string;
  selection: string;
  payoutYen: number;
  popularity?: number;
};

type TicketLeg = {
  label: string;
  numbers: number[];
};

type TicketTemplate = {
  type: string;
  selection: (top: RunnerProjection[]) => string;
  legs: (top: RunnerProjection[]) => TicketLeg[];
  method: string;
  tickets: (top: RunnerProjection[]) => number;
  risk: number;
  probability: number;
  odds: number;
  model: string;
};

type RunnerProjection = Runner & {
  winProbability: number;
  top2Probability?: number;
  placeProbability: number;
  secondProbability?: number;
  thirdProbability?: number;
  outProbability?: number;
  fairOdds: number;
  edge: number;
  score: number;
};

type TicketProjection = Omit<TicketTemplate, "selection" | "tickets" | "legs"> & {
  selection: string;
  legs: TicketLeg[];
  tickets: number;
  unitStake: number;
  edge: number;
  stake: number;
  expectedReturn: number;
};

type PublicHistorySummary = {
  total: number;
  hits: number;
  stake: number;
  payout: number;
  roi: number;
  hitRate: number;
};

type CalendarDay = {
  date: string;
  label: string;
  day: string;
};

type MonthCell = CalendarDay & {
  inMonth: boolean;
  raceCount: number;
  jraCount: number;
  narCount: number;
  plannedCount: number;
  historyCount: number;
  hitCount: number;
  isToday: boolean;
};

type VenueOption = {
  venue: string;
  count: number;
};

type HistoricalPrediction = {
  id: string;
  date: string;
  start: string;
  venue: string;
  title: string;
  course: string;
  market: Market;
  topTicket: string;
  result: string;
  roi: number;
  hitRate: number;
  stake: number;
  payout: number;
  settled: boolean;
  hit: boolean;
  hitCount: number;
  betCount: number;
  prediction?: ApiRacePrediction;
  resultOrder?: number[];
  recommendationResults?: RecommendationResult[];
  predictionKind?: string;
  officialPrediction?: boolean;
  generatedAfterResult?: boolean;
};

type RecommendationResult = {
  betType: string;
  strategy: string;
  selection: string;
  hit: boolean;
  selectionMatched?: boolean;
  stake: number;
  odds: number;
  payout: number;
  officialPayoutYen?: number;
  payoutSource?: string;
  winningTickets?: number;
};

type ApiState = "loading" | "ready" | "empty" | "fallback";
type DataPhase = "initial" | "today" | "range" | "ready";

type ApiRunnerPrediction = {
  id: string;
  gate: number;
  number: number;
  name: string;
  win_probability: number;
  top2_probability?: number | null;
  place_probability: number;
  second_probability?: number | null;
  third_probability?: number | null;
  out_probability?: number | null;
  fair_odds: number;
  market_odds: number;
  edge: number;
  score: number;
};

type ApiBetRecommendation = {
  selection: string;
  note: string;
  bet_type: string;
  strategy: string;
  tickets: number;
  unit_stake: number;
  covered_selections: string[];
  legs: TicketLeg[];
  probability: number;
  odds: number;
  edge: number;
  stake: number;
};

type ApiRacePrediction = {
  race_id: string;
  runners: ApiRunnerPrediction[];
  recommendations: ApiBetRecommendation[];
  total_stake: number;
  expected_return: number;
  expected_roi: number;
  warning: string;
};

type BettingHeat = {
  tone: BettingHeatTone;
  label: string;
  action: string;
  score: number;
  profile: string;
  volatilityLabel: string;
  volatilityScore: number;
  dataDepth: number;
  reasons: string[];
};

const races: Race[] = [
  {
    id: "tokyo-20260506-11",
    date: "2026-05-06",
    day: "水",
    start: "15:45",
    venue: "東京",
    title: "サンプル 東京11R",
    course: "芝1600m / 良想定",
    grade: "JRA",
    market: "JRA",
    status: "odds",
    runners: [
      { number: 3, name: "アオバブレイク", jockey: "戸崎", odds: 4.8, baseWin: 0.165, drift: -8.4, form: 84 },
      { number: 7, name: "レイライン", jockey: "川田", odds: 3.7, baseWin: 0.188, drift: 3.1, form: 88 },
      { number: 10, name: "ミナトクラウン", jockey: "坂井", odds: 8.6, baseWin: 0.104, drift: -13.2, form: 79 },
      { number: 1, name: "セイランコード", jockey: "横山武", odds: 12.4, baseWin: 0.076, drift: 6.6, form: 74 },
      { number: 12, name: "クオンタムベル", jockey: "ルメール", odds: 5.9, baseWin: 0.142, drift: -2.5, form: 82 },
    ],
  },
  {
    id: "sonoda-20260506-10",
    date: "2026-05-06",
    day: "水",
    start: "16:20",
    venue: "園田",
    title: "サンプル 園田10R",
    course: "ダ1400m / 稍重想定",
    grade: "NAR",
    market: "NAR",
    status: "card",
    runners: [
      { number: 2, name: "ハルノテンカ", jockey: "下原", odds: 4.1, baseWin: 0.176, drift: -4.2, form: 81 },
      { number: 5, name: "コウベライト", jockey: "吉村", odds: 2.9, baseWin: 0.214, drift: 9.4, form: 86 },
      { number: 8, name: "サザンミスト", jockey: "廣瀬", odds: 11.7, baseWin: 0.083, drift: -10.6, form: 76 },
      { number: 9, name: "トウカイリズム", jockey: "田中", odds: 7.3, baseWin: 0.118, drift: -1.8, form: 78 },
    ],
  },
  {
    id: "kyoto-20260507-11",
    date: "2026-05-07",
    day: "木",
    start: "15:35",
    venue: "京都",
    title: "京都11R 直前監視",
    course: "ダ1800m / 馬場確認中",
    grade: "JRA",
    market: "JRA",
    status: "watch",
    runners: [
      { number: 4, name: "キタヤマフォース", jockey: "武豊", odds: 6.4, baseWin: 0.136, drift: -6.2, form: 80 },
      { number: 6, name: "ネオグランツ", jockey: "松山", odds: 4.4, baseWin: 0.171, drift: 2.8, form: 83 },
      { number: 11, name: "ロードソリッド", jockey: "岩田望", odds: 9.9, baseWin: 0.091, drift: -15.1, form: 75 },
      { number: 13, name: "ブルーヴェイル", jockey: "西村淳", odds: 15.8, baseWin: 0.061, drift: -4.9, form: 72 },
    ],
  },
];

const predictionHistory: HistoricalPrediction[] = [];

function runnerNumbers(top: RunnerProjection[], start = 0, end = top.length) {
  return top.slice(start, end).map((runner) => runner.number).join("-");
}

function runnerNumberList(top: RunnerProjection[], start = 0, end = top.length) {
  return top.slice(start, end).map((runner) => runner.number);
}

function combinationCount(n: number, r: number) {
  if (r < 0 || n < r) {
    return 0;
  }
  let result = 1;
  for (let index = 1; index <= r; index += 1) {
    result = (result * (n - r + index)) / index;
  }
  return Math.round(result);
}

function permutationCount(n: number, r: number) {
  if (r < 0 || n < r) {
    return 0;
  }
  let result = 1;
  for (let index = 0; index < r; index += 1) {
    result *= n - index;
  }
  return result;
}

const ticketTemplates: TicketTemplate[] = [
  {
    type: "単勝",
    selection: (top) => `${top[0].number}`,
    legs: (top) => [{ label: "単勝", numbers: [top[0].number] }],
    method: "1頭指定",
    tickets: () => 1,
    risk: 42,
    probability: 0.18,
    odds: 4.2,
    model: "勝ち切り評価",
  },
  {
    type: "枠連",
    selection: (top) => {
      const firstGate = top[0].gate ?? Math.ceil(top[0].number / 2);
      const secondGate = top[1]?.gate ?? Math.ceil((top[1]?.number ?? top[0].number) / 2);
      return `${firstGate}-${secondGate}`;
    },
    legs: (top) => {
      const firstGate = top[0].gate ?? Math.ceil(top[0].number / 2);
      const secondGate = top[1]?.gate ?? Math.ceil((top[1]?.number ?? top[0].number) / 2);
      return [{ label: "枠", numbers: [firstGate, secondGate] }];
    },
    method: "枠指定",
    tickets: () => 1,
    risk: 34,
    probability: 0.13,
    odds: 6.8,
    model: "枠順評価",
  },
  {
    type: "ワイド",
    selection: (top) => runnerNumbers(top, 0, 2),
    legs: (top) => [{ label: "組み合わせ", numbers: runnerNumberList(top, 0, 2) }],
    method: "2頭指定",
    tickets: () => 1,
    risk: 36,
    probability: 0.22,
    odds: 4.8,
    model: "相手評価",
  },
  {
    type: "馬連",
    selection: (top) => runnerNumbers(top, 0, 2),
    legs: (top) => [{ label: "組み合わせ", numbers: runnerNumberList(top, 0, 2) }],
    method: "2頭指定",
    tickets: () => 1,
    risk: 58,
    probability: 0.11,
    odds: 8.6,
    model: "相手評価",
  },
  {
    type: "馬単",
    selection: (top) => runnerNumbers(top, 0, 2),
    legs: (top) => [
      { label: "1着", numbers: runnerNumberList(top, 0, 1) },
      { label: "2着", numbers: runnerNumberList(top, 1, 2) },
    ],
    method: "1着固定",
    tickets: () => 1,
    risk: 68,
    probability: 0.07,
    odds: 12.4,
    model: "相手評価",
  },
  {
    type: "3連複",
    selection: (top) => `軸 ${top[0].number} / 相手 ${runnerNumbers(top, 1, 6)}`,
    legs: (top) => [
      { label: "軸", numbers: [top[0].number] },
      { label: "相手", numbers: runnerNumberList(top, 1, 6) },
    ],
    method: "1頭軸流し",
    tickets: (top) => combinationCount(Math.max(top.length - 1, 0), 2),
    risk: 74,
    probability: 0.12,
    odds: 8.4,
    model: "期待値評価",
  },
  {
    type: "3連複",
    selection: (top) => `軸 ${runnerNumbers(top, 0, 2)} / 相手 ${runnerNumbers(top, 2, 7)}`,
    legs: (top) => [
      { label: "軸1", numbers: runnerNumberList(top, 0, 1) },
      { label: "軸2", numbers: runnerNumberList(top, 1, 2) },
      { label: "相手", numbers: runnerNumberList(top, 2, 7) },
    ],
    method: "2頭軸流し",
    tickets: (top) => Math.max(top.length - 2, 0),
    risk: 78,
    probability: 0.085,
    odds: 12.2,
    model: "期待値評価",
  },
  {
    type: "3連複",
    selection: (top) => `BOX ${runnerNumbers(top, 0, 5)}`,
    legs: (top) => [{ label: "BOX", numbers: runnerNumberList(top, 0, 5) }],
    method: "5頭BOX",
    tickets: (top) => combinationCount(Math.min(top.length, 5), 3),
    risk: 82,
    probability: 0.17,
    odds: 6.4,
    model: "期待値評価",
  },
  {
    type: "3連単",
    selection: (top) => `1着 ${top[0].number} / 2-3着 ${runnerNumbers(top, 1, 6)}`,
    legs: (top) => [
      { label: "1着", numbers: [top[0].number] },
      { label: "2着", numbers: runnerNumberList(top, 1, 6) },
      { label: "3着", numbers: runnerNumberList(top, 1, 6) },
    ],
    method: "1着軸流し",
    tickets: (top) => permutationCount(Math.max(top.length - 1, 0), 2),
    risk: 86,
    probability: 0.055,
    odds: 18.8,
    model: "着順評価",
  },
  {
    type: "3連単",
    selection: (top) => `軸 ${top[0].number} / 相手 ${runnerNumbers(top, 1, 5)}`,
    legs: (top) => [
      { label: "軸", numbers: [top[0].number] },
      { label: "相手", numbers: runnerNumberList(top, 1, 5) },
    ],
    method: "1頭軸マルチ",
    tickets: (top) => combinationCount(Math.max(top.length - 1, 0), 2) * 6,
    risk: 92,
    probability: 0.074,
    odds: 13.6,
    model: "着順評価",
  },
  {
    type: "3連単",
    selection: (top) => `1着 ${runnerNumbers(top, 0, 2)} / 2着 ${runnerNumbers(top, 0, 4)} / 3着 ${runnerNumbers(top, 0, 6)}`,
    legs: (top) => [
      { label: "1着", numbers: runnerNumberList(top, 0, 2) },
      { label: "2着", numbers: runnerNumberList(top, 0, 4) },
      { label: "3着", numbers: runnerNumberList(top, 0, 6) },
    ],
    method: "フォーメーション",
    tickets: (top) => permutationCount(Math.min(top.length, 4), 3),
    risk: 96,
    probability: 0.081,
    odds: 11.9,
    model: "着順評価",
  },
  {
    type: "3連単",
    selection: (top) => `BOX ${runnerNumbers(top, 0, 4)}`,
    legs: (top) => [{ label: "BOX", numbers: runnerNumberList(top, 0, 4) }],
    method: "4頭BOX",
    tickets: (top) => permutationCount(Math.min(top.length, 4), 3),
    risk: 95,
    probability: 0.062,
    odds: 15.2,
    model: "着順評価",
  },
];

const tabs: { id: ViewTab; label: string; icon: TabIconId }[] = [
  { id: "predict", label: "本日", icon: "today" },
  { id: "calendar", label: "日程", icon: "calendar" },
  { id: "results", label: "成績", icon: "results" },
];

const PORTFOLIO_RISK_LEVEL = 72;
const PUBLIC_BET_TYPE_GUIDES = [
  { id: "win", label: "単勝", summary: "1着を当てる", method: "1頭指定" },
  { id: "bracket_quinella", label: "枠連", summary: "1・2着の枠", method: "枠指定 / 流し" },
  { id: "quinella", label: "馬連", summary: "1・2着を順不同", method: "流し / BOX" },
  { id: "wide", label: "ワイド", summary: "2頭が3着以内", method: "流し / BOX" },
  { id: "exacta", label: "馬単", summary: "1・2着順通り", method: "軸流し / BOX" },
  { id: "trio", label: "3連複", summary: "3頭が3着以内", method: "1頭軸 / 2頭軸 / BOX / フォーメーション" },
  { id: "trifecta", label: "3連単", summary: "1・2・3着順通り", method: "軸流し / マルチ / BOX / フォーメーション" },
];

const appLinks = [
  { name: "WaliWali", label: "割り勘", href: "https://waliwali-app.vercel.app/", icon: "waliwali" as const },
  { name: "Keisya", label: "傾斜会計", href: "https://keisya-app.vercel.app/", icon: "keisya" as const },
  { name: "HikakU", label: "比較", href: "https://hikak-u.vercel.app/", icon: "hikaku" as const },
  { name: "アプリ一覧", label: "agoringang", href: "https://agoringang.com/#apps", icon: "portfolio" as const },
];

const yenFormatter = new Intl.NumberFormat("ja-JP", {
  style: "currency",
  currency: "JPY",
  maximumFractionDigits: 0,
});

const numberFormatter = new Intl.NumberFormat("ja-JP");
const weekdayFormatter = new Intl.DateTimeFormat("ja-JP", { weekday: "short" });
const INITIAL_CALENDAR_DATE = "2026-05-07";
const JRA_FUTURE_SCHEDULE: Record<string, { venues: string[]; gradeRaces?: string[] }> = {
  "2026-05-09": { venues: ["東京", "京都", "新潟"], gradeRaces: ["エプソムC", "京都新聞杯"] },
  "2026-05-10": { venues: ["東京", "京都", "新潟"], gradeRaces: ["NHKマイルC"] },
  "2026-05-16": { venues: ["東京", "京都", "新潟"], gradeRaces: ["京都ハイジャンプ", "新潟大賞典"] },
  "2026-05-17": { venues: ["東京", "京都", "新潟"], gradeRaces: ["ヴィクトリアマイル"] },
  "2026-05-23": { venues: ["東京", "京都", "新潟"], gradeRaces: ["平安S"] },
  "2026-05-24": { venues: ["東京", "京都", "新潟"], gradeRaces: ["オークス"] },
  "2026-05-30": { venues: ["東京", "京都"], gradeRaces: ["葵S"] },
  "2026-05-31": { venues: ["東京", "京都"], gradeRaces: ["日本ダービー", "目黒記念"] },
  "2026-06-06": { venues: ["東京", "阪神"] },
  "2026-06-07": { venues: ["東京", "阪神"], gradeRaces: ["安田記念"] },
  "2026-06-13": { venues: ["東京", "阪神", "函館"], gradeRaces: ["東京ジャンプS", "函館スプリントS"] },
  "2026-06-14": { venues: ["東京", "阪神", "函館"], gradeRaces: ["宝塚記念"] },
  "2026-06-20": { venues: ["東京", "阪神", "函館"] },
  "2026-06-21": { venues: ["東京", "阪神", "函館"], gradeRaces: ["府中牝馬S", "しらさぎS"] },
  "2026-06-27": { venues: ["福島", "小倉", "函館"] },
  "2026-06-28": { venues: ["福島", "小倉", "函館"], gradeRaces: ["ラジオNIKKEI賞", "函館記念"] },
};

function formatPercent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatYen(value: number) {
  return yenFormatter.format(Math.round(value));
}

function formatSignedPercent(value: number, digits = 1) {
  return `${value >= 0 ? "+" : ""}${formatPercent(value, digits)}`;
}

function safeRatio(numerator: number, denominator: number) {
  return denominator > 0 ? numerator / denominator : 0;
}

function estimatedPlaceOdds(winOdds: number) {
  return Math.max(1.1, Math.min(8.0, 1.05 + Math.max(winOdds - 1, 0) * 0.09));
}

function apiBaseUrl() {
  const configured =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "/api";
  if (
    configured === "/api" &&
    typeof window !== "undefined" &&
    ["localhost", "127.0.0.1"].includes(window.location.hostname) &&
    window.location.port !== "8000"
  ) {
    return "http://127.0.0.1:8000";
  }
  return configured.replace(/\/$/, "");
}

function safeNumber(value: unknown, fallback: number) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function optionalNumber(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function optionalText(value: unknown) {
  const text = String(value ?? "")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
  return text.length > 0 ? text : undefined;
}

function trustedPlaceOdds(winOdds: number, value: unknown) {
  const placeOdds = optionalNumber(value);
  if (!placeOdds || placeOdds <= 1 || winOdds <= 1 || placeOdds > winOdds) {
    return undefined;
  }
  const legacyEstimate = Math.round(Math.max(1.1, Math.min(winOdds, winOdds / 4)) * 100) / 100;
  const conservativeEstimate = Math.round(estimatedPlaceOdds(winOdds) * 100) / 100;
  const rounded = Math.round(placeOdds * 100) / 100;
  if (Math.abs(rounded - legacyEstimate) < 0.015) {
    return undefined;
  }
  if (Math.abs(rounded - conservativeEstimate) < 0.015) {
    return undefined;
  }
  return placeOdds;
}

function cleanCourseText(value: unknown) {
  return optionalText(value) ?? "条件未取得";
}

const jraVenues = new Set(["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]);

function marketClass(market: Market | undefined) {
  return market === "JRA" ? "market-jra" : "market-nar";
}

function venueMarket(venue: string): Market {
  return jraVenues.has(venue) ? "JRA" : "NAR";
}

function normalizedTopTicket(prediction: any) {
  const recommendations = Array.isArray(prediction.recommendations) ? prediction.recommendations : [];
  const recommendation = recommendations.find((item: any) => isPublicBetType(item?.bet_type)) ?? recommendations[0];
  if (recommendation?.selection) {
    const label = betTypeLabels[String(recommendation.bet_type ?? "")] ?? "買い目";
    return `${label} ${String(recommendation.selection)}`;
  }
  if (prediction.top_ticket) {
    return String(prediction.top_ticket);
  }
  const warning = String(prediction.warning ?? "");
  if (warning.startsWith("No model can guarantee")) {
    return "見送り";
  }
  return warning || "AI予想";
}

function isPublicBetType(value: string | undefined) {
  const normalized = normalizedBetType(value);
  return [
    "win",
    "tansho",
    "単勝",
    "bracket_quinella",
    "wakuren",
    "枠連",
    "枠連複",
    "quinella",
    "umaren",
    "馬連",
    "馬連複",
    "wide",
    "ワイド",
    "exacta",
    "umatan",
    "馬単",
    "馬連単",
    "trio",
    "fuku3",
    "3連複",
    "三連複",
    "trifecta",
    "tan3",
    "3連単",
    "三連単",
  ].includes(normalized);
}

function hasWinOddsValue(value: number | undefined | null) {
  return Number.isFinite(value) && Number(value) > 1.01;
}

function hasRunnerWinOdds(runner: Pick<Runner, "odds">) {
  return hasWinOddsValue(runner.odds);
}

function raceHasUsableWinOdds(race: Race) {
  const usable = race.runners.filter(hasRunnerWinOdds).length;
  return usable >= Math.max(2, Math.floor(race.runners.length * 0.7));
}

function normalizeApiRace(item: any): Race {
  const runners = Array.isArray(item.runners) ? item.runners : [];
  const normalizedRunners = runners.map((runner: any, index: number) => {
    const rawOdds = safeNumber(runner.odds ?? runner.market_odds, 0);
    const odds = rawOdds > 1.01 ? rawOdds : 0;
    const rating = safeNumber(runner.rating, 64);
    const number = safeNumber(runner.number, index + 1);
    return {
      number,
      gate: optionalNumber(runner.gate),
      name: optionalText(runner.name) ?? `${index + 1}番`,
      jockey: optionalText(runner.jockey) ?? "-",
      odds,
      placeOdds: trustedPlaceOdds(odds, runner.placeOdds ?? runner.place_odds),
      baseWin: hasWinOddsValue(odds)
        ? Math.min(0.65, Math.max(0.004, 1 / odds))
        : 1 / Math.max(runners.length, 1),
      drift: 0,
      form: Math.max(1, Math.min(100, rating)),
      carriedWeight: optionalNumber(runner.carriedWeight ?? runner.carried_weight),
      horseWeight: optionalNumber(runner.horseWeight ?? runner.horse_weight),
      horseWeightDiff: optionalNumber(runner.horseWeightDiff ?? runner.horse_weight_diff),
      age: optionalNumber(runner.age),
      sex: optionalText(runner.sex),
      trainer: optionalText(runner.trainer),
      runningStyle: optionalText(runner.runningStyle ?? runner.running_style),
      recentRecord: optionalText(runner.recentRecord ?? runner.recent_record),
      daysSinceLastRun: optionalNumber(runner.daysSinceLastRun ?? runner.days_since_last_run),
      avgLast3Speed: optionalNumber(runner.avgLast3Speed ?? runner.avg_last3_speed),
      bestTime: optionalNumber(runner.bestTime ?? runner.best_time),
      last600m: optionalNumber(runner.last600m ?? runner.last600m),
      jockeyWinRate: optionalNumber(runner.jockeyWinRate ?? runner.jockey_win_rate),
      trainerWinRate: optionalNumber(runner.trainerWinRate ?? runner.trainer_win_rate),
      horseRecentWinRate: optionalNumber(runner.horseRecentWinRate ?? runner.horse_recent_win_rate),
      horseRecentPlaceRate: optionalNumber(runner.horseRecentPlaceRate ?? runner.horse_recent_place_rate),
      horseDistancePlaceRate: optionalNumber(runner.horseDistancePlaceRate ?? runner.horse_distance_place_rate),
      horseSurfacePlaceRate: optionalNumber(runner.horseSurfacePlaceRate ?? runner.horse_surface_place_rate),
      trainingScore: optionalNumber(runner.trainingScore ?? runner.training_score),
      bloodlineScore: optionalNumber(runner.bloodlineScore ?? runner.bloodline_score),
      paddockScore: optionalNumber(runner.paddockScore ?? runner.paddock_score),
      oddsDelta: optionalNumber(runner.oddsDelta ?? runner.odds_delta),
      oddsDelta5m: optionalNumber(runner.oddsDelta5m ?? runner.odds_delta_5m),
      oddsDelta15m: optionalNumber(runner.oddsDelta15m ?? runner.odds_delta_15m),
      oddsVolatility: optionalNumber(runner.oddsVolatility ?? runner.odds_volatility),
      ticketPoolShare: optionalNumber(runner.ticketPoolShare ?? runner.ticket_pool_share),
      lap3f: optionalNumber(runner.lap3f ?? runner.lap_3f),
      lap4f: optionalNumber(runner.lap4f ?? runner.lap_4f),
      bodyWeightAnnouncedAt: optionalText(runner.bodyWeightAnnouncedAt ?? runner.body_weight_announced_at),
      payoutWin: optionalNumber(runner.payoutWin ?? runner.payout_win),
      payoutPlace: optionalNumber(runner.payoutPlace ?? runner.payout_place),
      payoutQuinella: optionalNumber(runner.payoutQuinella ?? runner.payout_quinella),
      payoutWide: optionalNumber(runner.payoutWide ?? runner.payout_wide),
      payoutExacta: optionalNumber(runner.payoutExacta ?? runner.payout_exacta),
      payoutTrio: optionalNumber(runner.payoutTrio ?? runner.payout_trio),
      payoutTrifecta: optionalNumber(runner.payoutTrifecta ?? runner.payout_trifecta),
      drawBias: optionalNumber(runner.drawBias ?? runner.draw_bias),
      sireId: optionalText(runner.sireId ?? runner.sire_id),
      sire: optionalText(runner.sire),
      damSireId: optionalText(runner.damSireId ?? runner.dam_sire_id),
      damSire: optionalText(runner.damSire ?? runner.dam_sire),
      tags: Array.isArray(runner.tags) ? runner.tags.map(String) : undefined,
    };
  });
  const venue = String(item.venue ?? "未設定");
  const market =
    item.market === "NAR" || item.grade === "NAR" || !jraVenues.has(venue) ? "NAR" : "JRA";
  const status = ["card", "odds", "watch", "finished", "schedule"].includes(item.status)
    ? item.status
    : "card";

  return {
    id: String(item.id),
    date: String(item.date ?? "2026-05-06"),
    day: String(item.day ?? ""),
    start: String(item.start ?? "未取得"),
    venue,
    title: String(item.title ?? item.raceNo ?? item.id),
    course: cleanCourseText(item.course ?? "条件未取得"),
    grade: String(item.grade ?? market),
    market,
    status,
    officialNote: optionalText(item.officialNote ?? item.official_note),
    source: optionalText(item.source),
    sourceUrl: optionalText(item.sourceUrl ?? item.source_url),
    sourceCheckedAt: optionalText(item.sourceCheckedAt ?? item.source_checked_at),
    verificationStatus: ["verified", "stale", "unverified"].includes(item.verificationStatus)
      ? item.verificationStatus
      : "unverified",
    payouts: Array.isArray(item.payouts)
      ? item.payouts.map((payout: any) => ({
          betType: String(payout.betType ?? payout.bet_type ?? ""),
          selection: String(payout.selection ?? ""),
          payoutYen: safeNumber(payout.payoutYen ?? payout.payout_yen, 0),
          popularity: optionalNumber(payout.popularity),
        })).filter((payout: RacePayout) => payout.betType && payout.selection && payout.payoutYen > 0)
      : [],
    runners: normalizedRunners,
  };
}

function normalizeApiHistory(payload: any): HistoricalPrediction[] {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return [];
  }

  return Object.entries(payload).flatMap(([date, entries]) => {
    if (!Array.isArray(entries)) {
      return [];
    }
    return entries.map((entry: any, index: number) => {
      const prediction = entry.prediction ?? {};
      const result = entry.result ?? {};
      const predictionRecommendations = Array.isArray(prediction.recommendations)
        ? prediction.recommendations.filter((item: any) => isPublicBetType(item?.bet_type))
        : [];
      const displayPrediction = { ...prediction, recommendations: predictionRecommendations };
      const raceId = String(entry.race_id ?? `${date}-${index}`);
      const stake = predictionRecommendations.length > 0
        ? predictionRecommendations.reduce((sum: number, item: any) => sum + safeNumber(item.stake, 0), 0)
        : safeNumber(prediction.total_stake, 0);
      const settled = Boolean(result.settled);
      const rawRecommendationResults: RecommendationResult[] = Array.isArray(result.recommendation_results)
        ? result.recommendation_results.map((item: any) => ({
            betType: String(item.bet_type ?? ""),
            strategy: String(item.strategy ?? ""),
            selection: String(item.selection ?? ""),
            hit: Boolean(item.hit),
            selectionMatched: Boolean(item.selection_matched),
            stake: safeNumber(item.stake, 0),
            odds: safeNumber(item.odds, 0),
            payout: safeNumber(item.payout, 0),
            officialPayoutYen: optionalNumber(item.official_payout_yen),
            payoutSource: String(item.payout_source ?? ""),
            winningTickets: optionalNumber(item.winning_tickets),
          }))
        : [];
      const recommendationResults = rawRecommendationResults.filter((item) => isPublicBetType(item.betType));
      const hasRecommendationBreakdown = recommendationResults.length > 0;
      const resultStake = settled && hasRecommendationBreakdown
        ? recommendationResults.reduce((sum, item) => sum + item.stake, 0)
        : safeNumber(result.stake, stake);
      const payout = settled && hasRecommendationBreakdown
        ? recommendationResults.reduce((sum, item) => sum + item.payout, 0)
        : settled
          ? safeNumber(result.payout, 0)
          : safeNumber(prediction.expected_return, 0);
      const hit = settled && hasRecommendationBreakdown
        ? recommendationResults.some((item) => item.hit)
        : Boolean(result.hit);
      const hitCount = settled && hasRecommendationBreakdown
        ? recommendationResults.filter((item) => item.hit).length
        : safeNumber(result.hit_count, hit ? 1 : 0);
      const betCount = settled && hasRecommendationBreakdown
        ? recommendationResults.length
        : predictionRecommendations.length || safeNumber(result.bet_count, 0);
      const resultOrder = Array.isArray(result.order)
        ? result.order.map((value: any) => Number(value)).filter((value: number) => Number.isFinite(value))
        : [];
      return {
        id: raceId,
        date: String(entry.race_date ?? date),
        start: settled ? "確定" : "保存",
        venue: String(entry.venue ?? raceId.split("-")[0] ?? "履歴"),
        title: String(entry.title ?? raceId),
        course: String(entry.course ?? "予測履歴"),
        market: entry.market === "NAR" ? "NAR" as Market : "JRA" as Market,
        topTicket: normalizedTopTicket(displayPrediction),
        result: String(result.message ?? (settled ? "結果反映" : "結果待ち")),
        roi: settled && resultStake > 0 ? payout / resultStake : safeNumber(prediction.expected_roi, 0),
        hitRate: betCount > 0 ? hitCount / betCount : safeNumber(prediction.hit_rate, 0),
        stake: settled ? resultStake : stake,
        payout,
        settled,
        hit,
        hitCount,
        betCount,
        prediction: displayPrediction && typeof displayPrediction === "object" ? displayPrediction as ApiRacePrediction : undefined,
        resultOrder,
        recommendationResults,
        predictionKind: String(entry.prediction_kind ?? ""),
        officialPrediction: entry.official_prediction !== false,
        generatedAfterResult: Boolean(entry.generated_after_result)
          || (settled && rawRecommendationResults.length > 0 && recommendationResults.length === 0),
      };
    });
  });
}

async function fetchRaceRangeFromApi(startDate: string, endDate: string) {
  const response = await fetch(`${apiBaseUrl()}/races?start_date=${startDate}&end_date=${endDate}`);
  if (!response.ok) {
    throw new Error(`races ${response.status}`);
  }
  const payload = await response.json();
  return Array.isArray(payload)
    ? compactRaceList(payload.map(normalizeApiRace).filter((item) => item.runners.length > 0))
    : [];
}

async function fetchHistoryRangeFromApi(startDate: string, endDate: string) {
  const response = await fetch(`${apiBaseUrl()}/history?start_date=${startDate}&end_date=${endDate}`);
  if (!response.ok) {
    return [];
  }
  return normalizeApiHistory(await response.json());
}

function buildRaceRequest(race: Race, riskLevel: number, bankroll: number) {
  const oddsRank = new Map(
    [...race.runners]
      .sort((a, b) => (hasRunnerWinOdds(a) ? a.odds : 9999) - (hasRunnerWinOdds(b) ? b.odds : 9999))
      .map((runner, index) => [runner.number, index + 1]),
  );
  const distance = Number(race.course.match(/(\d+)m/)?.[1] ?? undefined);
  const surface = race.course.includes("ダ") ? "ダ" : race.course.includes("芝") ? "芝" : undefined;
  const going = race.course.includes("不良")
    ? "不良"
    : race.course.includes("重")
      ? "重"
      : race.course.includes("稍")
        ? "稍重"
        : race.course.includes("良")
          ? "良"
          : undefined;

  return {
    race_id: race.id,
    race_date: race.date,
    venue: race.venue,
    title: race.title,
    race_no: `${raceNumberValue(race)}R`,
    course: race.course,
    market: race.market,
    model_version: "racequant-active",
    model_mode: "ensemble",
    risk_level: riskLevel,
    bankroll,
    min_edge: 0.0,
    min_probability: 0.0,
    max_candidate_odds: 999,
    max_edge: null,
    max_exposure: 0.1,
    recommendation_limit: 7,
    enabled_bet_types: [
      "win",
      "bracket_quinella",
      "quinella",
      "wide",
      "exacta",
      "trio",
      "trifecta",
    ],
    runners: race.runners.map((runner) => {
      const odds = Math.max(hasRunnerWinOdds(runner) ? runner.odds : 1.1, 1.1);
      const form = Math.max(1, Math.min(100, runner.form));
      return {
        id: `${race.id}-${runner.number}`,
        gate: Math.max(1, Math.min(8, Math.round(runner.gate ?? Math.ceil(runner.number / 2)))),
        number: runner.number,
        name: runner.name,
        market_odds: odds,
        place_odds: runner.placeOdds ?? 1.1,
        speed: form,
        stamina: Math.max(1, Math.min(100, form + (surface === "ダ" ? 2 : 0))),
        pace: Math.max(1, Math.min(100, form + (runner.drift < 0 ? 4 : -2))),
        condition: Math.max(1, Math.min(100, form + (runner.drift < 0 ? 3 : 0))),
        base_win: Math.min(0.8, Math.max(0.001, runner.baseWin)),
        distance: Number.isFinite(distance) ? distance : undefined,
        carried_weight: runner.carriedWeight,
        horse_weight: runner.horseWeight,
        horse_weight_diff: runner.horseWeightDiff,
        age: runner.age,
        sex: runner.sex,
        venue: race.venue,
        surface,
        going,
        jockey: runner.jockey,
        trainer: runner.trainer,
        running_style: runner.runningStyle,
        sire_id: runner.sireId,
        sire: runner.sire,
        dam_sire_id: runner.damSireId,
        dam_sire: runner.damSire,
        days_since_last_run: runner.daysSinceLastRun,
        avg_last3_speed: runner.avgLast3Speed,
        best_time: runner.bestTime,
        last600m: runner.last600m,
        jockey_win_rate: runner.jockeyWinRate,
        trainer_win_rate: runner.trainerWinRate,
        horse_recent_win_rate: runner.horseRecentWinRate,
        horse_recent_place_rate: runner.horseRecentPlaceRate,
        horse_distance_place_rate: runner.horseDistancePlaceRate,
        horse_surface_place_rate: runner.horseSurfacePlaceRate,
        training_score: runner.trainingScore,
        bloodline_score: runner.bloodlineScore,
        paddock_score: runner.paddockScore,
        lap_3f: runner.lap3f,
        lap_4f: runner.lap4f,
        draw_bias: runner.drawBias,
        odds_rank: oddsRank.get(runner.number),
        odds_delta: runner.oddsDelta ?? runner.drift / 100,
        odds_delta_5m: runner.oddsDelta5m,
        odds_delta_15m: runner.oddsDelta15m,
        odds_volatility: runner.oddsVolatility,
        ticket_pool_share: runner.ticketPoolShare,
      };
    }),
  };
}

const betTypeLabels: Record<string, string> = {
  win: "単勝",
  place: "複勝",
  support: "単複(旧)",
  bracket_quinella: "枠連",
  quinella: "馬連",
  wide: "ワイド",
  exacta: "馬単",
  trio: "3連複",
  trifecta: "3連単",
  win5: "WIN5",
};

function recommendationProfit(result: RecommendationResult) {
  return result.payout - result.stake;
}

function historyProfit(history: HistoricalPrediction) {
  return history.payout - history.stake;
}

function resultOutcomeText(history: HistoricalPrediction) {
  if (!history.settled) {
    return "結果待ち";
  }
  const profitRate = safeRatio(historyProfit(history), history.stake);
  const prefix = history.hit ? "🎯 的中" : "不的中";
  return `${prefix} / 損益率 ${formatSignedPercent(profitRate, 1)} / 回収率 ${formatPercent(history.roi, 1)}`;
}

function modelLabelForBetType(type: string) {
  if (type === "win") return "勝ち切り評価";
  if (type === "place") return "安定評価";
  if (["wide", "quinella", "exacta", "bracket_quinella"].includes(type)) return "相手評価";
  return "期待値評価";
}

function publicStrategyLabel(value: string | undefined) {
  const text = String(value ?? "").trim();
  const normalized = text.toLowerCase();
  if (!text || normalized === "ai") return "AI推奨";
  if (normalized === "single") return "単票";
  if (normalized.includes("formation")) return "フォーメーション";
  if (normalized.includes("box")) return "ボックス";
  if (normalized.includes("axis") || normalized.includes("nagashi")) return "軸流し";
  if (normalized.includes("ticket-ev") || normalized.includes("ev")) return "期待値重視";
  if (normalized.includes("rank-pair") || normalized.includes("pair")) return "相手関係重視";
  if (normalized.includes("win-ensemble") || normalized.includes("win")) return "勝ち切り重視";
  if (normalized.includes("place")) return "安定重視";
  if (normalized.includes("support")) return "旧データ";
  return text
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b[A-Z]{2,}\b/g, "")
    .trim() || "AI推奨";
}

function publicBetTypeLabel(value: string | undefined) {
  const text = String(value ?? "").trim();
  return betTypeLabels[text] ?? (text || "買い目");
}

function ticketCompactMethod(ticket: TicketProjection) {
  const legText = ticket.legs
    .map((leg) => `${leg.label}${leg.numbers.join(",")}`)
    .join(" / ");
  const target = legText || ticket.selection;
  return `${ticket.method} / ${target} / ${ticket.tickets}通り`;
}

function ticketExpectedProfitRate(ticket: TicketProjection) {
  return safeRatio(ticket.expectedReturn, ticket.stake) - 1;
}

function formatOdds(value: number) {
  if (!Number.isFinite(value) || value <= 0) {
    return "-";
  }
  const digits = value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)}倍`;
}

function ticketPayoutPer100(ticket: TicketProjection) {
  return formatYen(ticket.odds * 100);
}

function resultBetSummary(item: RecommendationResult) {
  return `${publicBetTypeLabel(item.betType)} ${officialSelectionText({ betType: item.betType, selection: item.selection })}`;
}

function resultPayoutPer100Label(item: RecommendationResult) {
  if (item.officialPayoutYen && item.officialPayoutYen > 0) {
    return formatYen(item.officialPayoutYen);
  }
  if (item.payoutSource === "missing_official_payout") {
    return "払戻未取得";
  }
  if (!item.hit) {
    return "払戻なし";
  }
  return formatYen(Math.max(0, item.odds) * 100);
}

function resultOddsLabel(item: RecommendationResult) {
  if (item.officialPayoutYen && item.officialPayoutYen > 0) {
    return `${(item.officialPayoutYen / 100).toFixed(item.officialPayoutYen >= 10000 ? 0 : 1)}倍`;
  }
  return formatOdds(item.odds);
}

const officialPayoutOrder = [
  "win",
  "単勝",
  "tansho",
  "place",
  "複勝",
  "fukusho",
  "bracket_quinella",
  "枠連",
  "枠連複",
  "wakuren",
  "quinella",
  "馬連",
  "馬連複",
  "umaren",
  "wide",
  "ワイド",
  "exacta",
  "馬単",
  "馬連単",
  "umatan",
  "trio",
  "3連複",
  "三連複",
  "fuku3",
  "trifecta",
  "3連単",
  "三連単",
  "tan3",
  "win5",
] as const;

function normalizedBetType(value: string | undefined) {
  return String(value ?? "").trim().toLowerCase().replaceAll("３", "3");
}

function officialPayoutRank(value: string | undefined) {
  const normalized = normalizedBetType(value);
  const index = officialPayoutOrder.findIndex((item) => normalizedBetType(item) === normalized);
  return index === -1 ? officialPayoutOrder.length : index;
}

function officialBetTypeLabel(value: string | undefined, market?: Market) {
  const text = String(value ?? "").trim();
  const normalized = normalizedBetType(text);
  if (["win", "tansho", "単勝"].includes(normalized)) return "単勝";
  if (["place", "fukusho", "複勝"].includes(normalized)) return "複勝";
  if (["bracket_quinella", "wakuren", "枠連", "枠連複"].includes(normalized)) return market === "NAR" ? "枠連複" : "枠連";
  if (["quinella", "umaren", "馬連", "馬連複"].includes(normalized)) return market === "NAR" ? "馬連複" : "馬連";
  if (["wide", "ワイド"].includes(normalized)) return "ワイド";
  if (["exacta", "umatan", "馬単", "馬連単"].includes(normalized)) return market === "NAR" ? "馬連単" : "馬単";
  if (["trio", "fuku3", "3連複", "三連複"].includes(normalized)) return market === "NAR" ? "三連複" : "3連複";
  if (["trifecta", "tan3", "3連単", "三連単"].includes(normalized)) return market === "NAR" ? "三連単" : "3連単";
  if (["win5"].includes(normalized)) return "WIN5";
  return publicBetTypeLabel(text);
}

function officialSelectionText(payout: Pick<RacePayout, "betType" | "selection">) {
  const type = officialBetTypeLabel(payout.betType);
  const separator = ["馬単", "馬連単", "3連単", "三連単"].includes(type) ? " → " : " - ";
  return String(payout.selection ?? "")
    .trim()
    .replace(/\s*(→|＞|>)\s*/g, " → ")
    .replace(/\s*[-－ー]\s*/g, separator);
}

function racePayoutRows(race: Race) {
  const direct = (race.payouts ?? []).filter((item) => item.payoutYen > 0);
  if (direct.length > 0) {
    return direct;
  }

  const rows: RacePayout[] = [];
  const resultOrder = raceResultOrder(race);
  const winner = resultOrder[0]?.runner;
  if (winner?.payoutWin) {
    rows.push({ betType: "win", selection: String(winner.number), payoutYen: winner.payoutWin });
  }
  resultOrder.slice(0, 3).forEach(({ runner }) => {
    if (runner.payoutPlace) {
      rows.push({ betType: "place", selection: String(runner.number), payoutYen: runner.payoutPlace });
    }
  });
  return rows;
}

function apiRecommendationToTicket(recommendation: ApiBetRecommendation): TicketProjection {
  const tickets = Math.max(safeNumber(recommendation.tickets, 1), 1);
  const stake = safeNumber(recommendation.stake, 0);
  const probability = safeNumber(recommendation.probability, 0);
  const odds = safeNumber(recommendation.odds, 1);
  const riskByType: Record<string, number> = {
    win: 42,
    place: 24,
    wide: 36,
    quinella: 58,
    exacta: 68,
    trio: 74,
    trifecta: 90,
  };
  return {
    type: betTypeLabels[recommendation.bet_type] ?? recommendation.bet_type,
    method: publicStrategyLabel(recommendation.strategy || recommendation.note),
    probability,
    odds,
    risk: riskByType[recommendation.bet_type] ?? 48,
    model: modelLabelForBetType(recommendation.bet_type),
    selection: recommendation.selection,
    legs: recommendation.legs ?? [],
    tickets,
    unitStake: safeNumber(recommendation.unit_stake, stake / tickets),
    edge: safeNumber(recommendation.edge, probability * odds - 1),
    stake,
    expectedReturn: stake * odds * probability,
  };
}

function mergeApiProjections(prediction: ApiRacePrediction | null, race: Race) {
  if (!prediction || prediction.race_id !== race.id) {
    return null;
  }
  const sourceByNumber = new Map(race.runners.map((runner) => [runner.number, runner]));
  const merged = prediction.runners
    .map((runner): RunnerProjection => {
      const source = sourceByNumber.get(runner.number);
      return {
        ...source,
        number: runner.number,
        name: runner.name,
        jockey: source?.jockey ?? "-",
        odds: source && hasRunnerWinOdds(source) && hasWinOddsValue(runner.market_odds)
          ? safeNumber(runner.market_odds, source?.odds ?? 0)
          : source?.odds ?? 0,
        baseWin: source?.baseWin ?? runner.win_probability,
        drift: source?.drift ?? 0,
        form: source?.form ?? Math.round(runner.score),
        winProbability: safeNumber(runner.win_probability, 0),
        top2Probability: runner.top2_probability ?? undefined,
        placeProbability: safeNumber(runner.place_probability, 0),
        secondProbability: runner.second_probability ?? undefined,
        thirdProbability: runner.third_probability ?? undefined,
        outProbability: runner.out_probability ?? undefined,
        fairOdds: safeNumber(runner.fair_odds, 0),
        edge: safeNumber(runner.edge, 0),
        score: safeNumber(runner.score, 0),
      };
    });
  return rankProjections(merged, race);
}

function roundStake(value: number) {
  return Math.max(100, Math.round(value / 100) * 100);
}

function frontendPortfolioProfile() {
  return {
    maxExposure: 0.08,
    limit: PUBLIC_BET_TYPE_GUIDES.length,
    allowedTypes: new Set(PUBLIC_BET_TYPE_GUIDES.map((item) => item.label)),
  };
}

function finishPosition(runner: Runner) {
  const finishTag = runner.tags?.find((tag) => /^\d+着$/.test(tag));
  return finishTag ? Number(finishTag.replace("着", "")) : undefined;
}

function taggedPopularity(runner: Runner) {
  const popularityTag = runner.tags?.find((tag) => /^\d+人気$/.test(tag));
  return popularityTag ? Number(popularityTag.replace("人気", "")) : undefined;
}

function oddsRankMap(race: Race) {
  return new Map(
    [...race.runners]
      .sort((a, b) => {
        const oddsA = hasRunnerWinOdds(a) ? a.odds : 9999;
        const oddsB = hasRunnerWinOdds(b) ? b.odds : 9999;
        return oddsA - oddsB || a.number - b.number;
      })
      .map((runner, index) => [runner.number, index + 1]),
  );
}

function runnerPopularity(runner: Runner, race: Race) {
  if (taggedPopularity(runner)) {
    return taggedPopularity(runner);
  }
  if (!raceHasUsableWinOdds(race) || !hasRunnerWinOdds(runner)) {
    return undefined;
  }
  return oddsRankMap(race).get(runner.number);
}

function runnerOddsMeta(runner: Runner, race: Race) {
  const popularity = runnerPopularity(runner, race);
  const popularityLabel = popularity ? `${popularity}人気` : "人気不明";
  const placeLabel = runner.placeOdds ? ` / 複${runner.placeOdds.toFixed(1)}倍` : "";
  const winLabel = hasRunnerWinOdds(runner) ? `単${runner.odds.toFixed(1)}倍` : "単勝未取得";
  return `${winLabel}${placeLabel} / ${popularityLabel}`;
}

function marketWinProbability(race: Race, runnerNumber: number) {
  const oddsReady = raceHasUsableWinOdds(race);
  if (!oddsReady) {
    return 1 / Math.max(race.runners.length, 1);
  }
  const implied = race.runners.filter(hasRunnerWinOdds).map((runner) => ({
    number: runner.number,
    value: 1 / Math.max(runner.odds, 1.01),
  }));
  const total = implied.reduce((sum, item) => sum + item.value, 0);
  const target = implied.find((item) => item.number === runnerNumber)?.value ?? 0;
  return total > 0 ? target / total : 1 / Math.max(race.runners.length, 1);
}

function nonMarketFeatureScore(runner: Runner) {
  return (
    (runner.jockeyWinRate ?? 0) * 8 +
    (runner.trainerWinRate ?? 0) * 7 +
    (runner.horseRecentWinRate ?? 0) * 8 +
    (runner.horseRecentPlaceRate ?? 0) * 6 +
    (runner.horseDistancePlaceRate ?? 0) * 4 +
    (runner.horseSurfacePlaceRate ?? 0) * 3 +
    (runner.drawBias ?? 0) * 3 +
    Math.max(0, (runner.avgLast3Speed ?? runner.form) - 65) / 12
  );
}

function predictionDisplayScore(runner: RunnerProjection, race: Race) {
  const marketProbability = marketWinProbability(race, runner.number);
  const marketGap = runner.winProbability - marketProbability;
  const placeMarket = Math.min(marketProbability * Math.min(race.runners.length, 3), 0.95);
  const placeGap = runner.placeProbability - placeMarket;
  const top2Probability = runner.top2Probability ?? Math.min(0.92, runner.winProbability + runner.placeProbability * 0.42);
  const baselineForm = hasRunnerWinOdds(runner)
    ? Math.max(18, 120 - Math.min(runner.odds, 80) * 3)
    : 64;
  const formSignal = Math.max(-12, Math.min(12, (runner.form - baselineForm) * 0.44));
  const weightSignal =
    runner.horseWeightDiff === undefined
      ? 0
      : Math.abs(runner.horseWeightDiff) >= 18
        ? -7
        : Math.abs(runner.horseWeightDiff) <= 4
          ? 3
          : 0;
  return (
    marketProbability * 54 +
    runner.winProbability * 70 +
    top2Probability * 36 +
    runner.placeProbability * 24 +
    runner.score * 0.18 +
    Math.max(-0.05, Math.min(marketGap, 0.055)) * 76 +
    Math.max(-0.08, Math.min(placeGap, 0.08)) * 24 +
    Math.max(-0.25, Math.min(hasRunnerWinOdds(runner) ? runner.edge : 0, 0.45)) * 4 +
    nonMarketFeatureScore(runner) * 0.88 +
    formSignal +
    weightSignal
  );
}

function rankProjections(projections: RunnerProjection[], race: Race) {
  return [...projections].sort(
    (a, b) =>
      predictionDisplayScore(b, race) - predictionDisplayScore(a, race) ||
      b.winProbability - a.winProbability ||
      (hasRunnerWinOdds(a) ? a.odds : 9999) - (hasRunnerWinOdds(b) ? b.odds : 9999) ||
      a.number - b.number,
  );
}

function buildRaceOnlyProjections(race: Race, riskRatio = 0.52) {
  const raw = race.runners.map((runner) => {
    const valueLift = hasRunnerWinOdds(runner) && runner.odds >= 8 ? riskRatio * 0.012 : 0;
    const oddsMoveLift = runner.drift < 0 ? Math.abs(runner.drift) * 0.00045 : -runner.drift * 0.0003;
    const featureLift = nonMarketFeatureScore(runner) / 140;
    const score = runner.baseWin * 1.08 + valueLift + oddsMoveLift + featureLift * 0.62 + runner.form / 3200;
    return { runner, score };
  });
  const total = raw.reduce((sum, item) => sum + item.score, 0);

  const projections = raw.map(({ runner, score }) => {
    const winProbability = total > 0 ? score / total : 1 / Math.max(race.runners.length, 1);
    const placeProbability = Math.min(0.86, winProbability * 2.55 + runner.form / 820);
    const fairOdds = 1 / Math.max(winProbability, 0.001);
    const edge = hasRunnerWinOdds(runner) ? winProbability * runner.odds - 1 : 0;
    return {
      ...runner,
      winProbability,
      placeProbability,
      fairOdds,
      edge,
      score: winProbability * 72 + placeProbability * 18 + Math.max(edge, -0.2) * 10,
    };
  });

  return rankProjections(projections, race);
}

function displayAiIndex(runner: RunnerProjection, race: Race) {
  const score = Math.max(1, Math.round(predictionDisplayScore(runner, race)));
  return raceHasUsableWinOdds(race) ? String(score) : `暫定${score}`;
}

function raceResultOrder(race: Race) {
  return race.runners
    .map((runner) => ({ runner, position: finishPosition(runner) }))
    .filter((item): item is { runner: Runner; position: number } => Number.isFinite(item.position))
    .sort((a, b) => a.position - b.position);
}

function dateAtJst(date: string) {
  return new Date(`${date}T00:00:00+09:00`);
}

function todayAtJst() {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function addDays(date: string, days: number) {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10);
}

function dateOrdinal(date: string) {
  const [year, month, day] = date.split("-").map(Number);
  return Date.UTC(year, month - 1, day) / 86_400_000;
}

function sortRaceCards(a: Race, b: Race) {
  return (
    a.date.localeCompare(b.date) ||
    a.venue.localeCompare(b.venue, "ja") ||
    raceNumberValue(a) - raceNumberValue(b) ||
    a.id.localeCompare(b.id)
  );
}

function raceNumberValue(race: Race) {
  return Number(race.title.match(/(\d+)R/)?.[1] ?? race.id.slice(-2)) || 999;
}

function raceDisplayKey(race: Race) {
  return `${race.date}|${race.venue}|${raceNumberValue(race)}`;
}

function raceFeatureCount(race: Race) {
  const keys: (keyof Runner)[] = [
    "horseWeight",
    "horseWeightDiff",
    "daysSinceLastRun",
    "avgLast3Speed",
    "last600m",
    "jockeyWinRate",
    "trainerWinRate",
    "horseRecentWinRate",
    "horseRecentPlaceRate",
    "horseDistancePlaceRate",
    "horseSurfacePlaceRate",
    "trainingScore",
    "bloodlineScore",
    "paddockScore",
    "oddsDelta",
    "ticketPoolShare",
    "drawBias",
    "sire",
    "damSire",
  ];
  return race.runners.reduce(
    (sum, runner) => sum + keys.filter((key) => runner[key] !== undefined && runner[key] !== null && runner[key] !== "").length,
    0,
  );
}

function raceQualityScore(race: Race) {
  const source = race.source ?? "";
  const sourceScore = source.includes("live scrape")
    ? 4
    : source.includes("netkeiba_2026")
      ? 3
      : source.includes("with_2026")
        ? 2
        : source.includes("normalized")
          ? 1
          : 0;
  const resultScore = race.status === "finished" ? 40 : 0;
  const startScore = /^\d{1,2}:\d{2}$/.test(race.start) ? 12 : race.start.startsWith("推定") ? 4 : 0;
  return sourceScore * 1000 + resultScore + startScore + race.runners.length + raceFeatureCount(race);
}

function compactRaceList(races: Race[]) {
  const merged = new Map<string, Race>();
  races.forEach((race) => {
    const key = raceNumberValue(race) === 999 ? race.id : raceDisplayKey(race);
    const current = merged.get(key);
    if (!current || raceQualityScore(race) >= raceQualityScore(current)) {
      merged.set(key, race);
    }
  });
  return Array.from(merged.values()).sort(sortRaceCards);
}

function pickDefaultRace(items: Race[], centerDate: string) {
  const center = dateOrdinal(centerDate);
  return [...items].sort((a, b) => {
    const aDistance = Math.abs(dateOrdinal(a.date) - center);
    const bDistance = Math.abs(dateOrdinal(b.date) - center);
    return aDistance - bDistance || b.date.localeCompare(a.date) || sortRaceCards(a, b);
  })[0];
}

function calendarLabel(date: string) {
  const [, month, day] = date.split("-");
  return `${Number(month)}/${Number(day)}`;
}

function monthStart(date: string) {
  return `${date.slice(0, 7)}-01`;
}

function addMonths(date: string, months: number) {
  const [year, month] = date.split("-").map(Number);
  const next = new Date(Date.UTC(year, month - 1 + months, 1));
  return next.toISOString().slice(0, 10);
}

function monthTitle(date: string) {
  const [year, month] = date.split("-").map(Number);
  return `${year}年${month}月`;
}

function buildMonthCells(
  monthAnchor: string,
  races: Race[],
  history: HistoricalPrediction[],
  today: string,
): MonthCell[] {
  const start = monthStart(monthAnchor);
  const [year, month] = start.split("-").map(Number);
  const first = new Date(Date.UTC(year, month - 1, 1));
  const firstWeekday = (first.getUTCDay() + 6) % 7;
  const gridStart = addDays(start, -firstWeekday);
  const raceIdsByDate = new Map<string, Set<string>>();
  const marketCountsByDate = new Map<string, { JRA: Set<string>; NAR: Set<string> }>();
  const historyCountByDate = new Map<string, number>();
  const historyIdsByDate = new Map<string, Set<string>>();
  const hitCountByDate = new Map<string, number>();

  races.forEach((race) => {
    const displayKey = raceDisplayKey(race);
    const ids = raceIdsByDate.get(race.date) ?? new Set<string>();
    ids.add(displayKey);
    raceIdsByDate.set(race.date, ids);
    const marketCounts = marketCountsByDate.get(race.date) ?? { JRA: new Set<string>(), NAR: new Set<string>() };
    marketCounts[race.market].add(displayKey);
    marketCountsByDate.set(race.date, marketCounts);
  });
  history.forEach((item) => {
    historyCountByDate.set(item.date, (historyCountByDate.get(item.date) ?? 0) + 1);
    const ids = historyIdsByDate.get(item.date) ?? new Set<string>();
    ids.add(item.id);
    historyIdsByDate.set(item.date, ids);
    if (item.hit) {
      hitCountByDate.set(item.date, (hitCountByDate.get(item.date) ?? 0) + 1);
    }
  });

  return Array.from({ length: 42 }, (_, index) => {
    const date = addDays(gridStart, index);
    const uniqueRaceIds = new Set([
      ...(raceIdsByDate.get(date) ?? []),
      ...(historyIdsByDate.get(date) ?? []),
    ]);
    const marketCounts = marketCountsByDate.get(date);
    return {
      date,
      label: calendarLabel(date),
      day: weekdayFormatter.format(dateAtJst(date)).replace("曜日", ""),
      inMonth: date.slice(0, 7) === start.slice(0, 7),
      raceCount: uniqueRaceIds.size,
      jraCount: marketCounts?.JRA.size ?? 0,
      narCount: marketCounts?.NAR.size ?? 0,
      plannedCount: JRA_FUTURE_SCHEDULE[date]?.venues.length ?? 0,
      historyCount: historyCountByDate.get(date) ?? 0,
      hitCount: hitCountByDate.get(date) ?? 0,
      isToday: date === today,
    };
  });
}

function mergeRaceLists(current: Race[], incoming: Race[]) {
  const merged = new Map(current.map((race) => [race.id, race]));
  incoming.forEach((race) => merged.set(race.id, race));
  return compactRaceList(Array.from(merged.values()));
}

function mergeHistoryLists(current: HistoricalPrediction[], incoming: HistoricalPrediction[]) {
  const merged = new Map(current.map((item) => [item.id, item]));
  incoming.forEach((item) => merged.set(item.id, item));
  return Array.from(merged.values());
}

function loadingText(phase: DataPhase, apiState: ApiState) {
  if (apiState === "fallback") return "レース情報の取得に失敗しました";
  if (apiState === "empty") return "";
  if (phase === "initial" || phase === "today") return "本日の出馬表と結果を照合中";
  if (phase === "range") return "月間カレンダーと過去成績を追加取得中";
  return "";
}

function verificationLabel(race: Race | null) {
  if (!race) return "未取得";
  if (race.verificationStatus === "verified") return "確認済み";
  if (race.verificationStatus === "stale") return "要更新";
  return "確認中";
}

function publicMarketLabel(market: Market | undefined) {
  if (market === "JRA") return "中央競馬";
  if (market === "NAR") return "地方競馬";
  return "競馬";
}

function publicMarketShortLabel(market: Market | undefined) {
  if (market === "JRA") return "中央";
  if (market === "NAR") return "地方";
  return "競馬";
}

function cleanRaceTitle(title: string) {
  return title
    .replace(/\s*実データ/g, "")
    .replace(/\s*AI予測対象/g, "")
    .replace(/\s*地方拡張テスト/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function displayRaceTitle(race: Race) {
  const title = cleanRaceTitle(race.title);
  return title.includes(race.venue) ? title : `${race.venue} ${title}`;
}

function displayHistoryTitle(history: HistoricalPrediction) {
  const title = cleanRaceTitle(history.title);
  return title.includes(history.venue) ? title : `${history.venue} ${title}`;
}

function raceStatusLead(race: Race) {
  const status = race.status === "finished" ? "結果確定" : "発走前";
  return `${race.course} / ${publicMarketLabel(race.market)} / ${status}`;
}

function raceStartLabel(race: Race) {
  const match = String(race.start || "").match(/\d{1,2}:\d{2}/);
  if (match) {
    const prefix = race.start.includes("推定") ? "推定 " : "";
    const suffix = race.status === "finished" ? " / 結果確定" : "";
    return `${prefix}${match[0]}発走${suffix}`;
  }
  if (race.status === "finished") {
    return "時刻未取得 / 結果確定";
  }
  return "発走時刻未取得";
}

function fieldSizeLabel(race: Race) {
  return `${race.runners.length}頭`;
}

function runnerWeightLabel(runner: Runner) {
  if (runner.horseWeight === undefined) {
    return "馬体重未取得";
  }
  const diff =
    runner.horseWeightDiff === undefined
      ? ""
      : ` ${runner.horseWeightDiff >= 0 ? "+" : ""}${runner.horseWeightDiff}`;
  return `${runner.horseWeight}kg${diff}`;
}

function runnerProfileLabel(runner: Runner) {
  return [
    runner.sex || runner.age ? `${runner.sex ?? ""}${runner.age ? `${runner.age}歳` : ""}` : undefined,
    runner.carriedWeight !== undefined ? `${runner.carriedWeight.toFixed(1)}kg` : undefined,
    runner.runningStyle,
  ]
    .filter(Boolean)
    .join(" / ") || "-";
}

function dataDepthScore(race: Race) {
  if (race.runners.length === 0) {
    return 0;
  }

  const fields: (keyof Runner)[] = [
    "carriedWeight",
    "horseWeight",
    "horseWeightDiff",
    "age",
    "sex",
    "trainer",
    "runningStyle",
    "recentRecord",
    "daysSinceLastRun",
    "avgLast3Speed",
    "last600m",
    "jockeyWinRate",
    "trainerWinRate",
    "horseRecentWinRate",
    "horseRecentPlaceRate",
    "horseDistancePlaceRate",
    "horseSurfacePlaceRate",
    "trainingScore",
    "bloodlineScore",
    "paddockScore",
    "oddsDelta",
    "ticketPoolShare",
    "lap3f",
    "lap4f",
    "sire",
    "damSire",
  ];

  const present = race.runners.reduce((sum, runner) => {
    return (
      sum +
      fields.filter((field) => {
        const value = runner[field];
        return value !== undefined && value !== null && value !== "";
      }).length
    );
  }, 0);

  return present / Math.max(race.runners.length * fields.length, 1);
}

function raceVolatilityProfile(race: Race, projections: RunnerProjection[]) {
  const top = projections[0];
  const second = projections[1];
  const favorite = [...race.runners]
    .filter(hasRunnerWinOdds)
    .sort((a, b) => a.odds - b.odds || a.number - b.number)[0];
  const favoriteMarketProbability = favorite ? marketWinProbability(race, favorite.number) : 0;
  const winGap = top && second ? top.winProbability - second.winProbability : 0;
  const contenderCount = top
    ? projections.filter((runner) => runner.winProbability >= Math.max(0.045, top.winProbability * 0.48)).length
    : 0;
  const valueCandidates = projections.filter((runner) => {
    const gap = runner.winProbability - marketWinProbability(race, runner.number);
    return hasRunnerWinOdds(runner) && runner.odds >= 4 && gap >= 0.012;
  }).length;
  const weightSwings = race.runners.filter((runner) => Math.abs(runner.horseWeightDiff ?? 0) >= 12).length;
  const oddsMoves = race.runners.filter((runner) => Math.abs(runner.oddsDelta ?? 0) >= 0.08).length;
  const paddockSignals = race.runners.filter((runner) => (runner.paddockScore ?? runner.trainingScore ?? 0) >= 76).length;
  const favoriteIsAiTop = Boolean(top && favorite && top.number === favorite.number);
  const topPopularity = top ? runnerPopularity(top, race) ?? 99 : 99;
  const depth = dataDepthScore(race);
  const score = Math.max(
    0,
    Math.min(
      100,
      36 +
        Math.max(0, race.runners.length - 8) * 3.2 +
        Math.max(0, 0.28 - favoriteMarketProbability) * 120 +
        Math.max(0, 0.14 - winGap) * 135 +
        Math.max(0, contenderCount - 2) * 7 +
        Math.min(valueCandidates, 3) * 8 +
        Math.min(weightSwings, 3) * 4 +
        Math.min(oddsMoves, 4) * 4 +
        Math.min(paddockSignals, 3) * 3 +
        (favoriteIsAiTop ? -10 : 12) +
        (topPopularity >= 4 ? 8 : 0) -
        (depth < 0.22 ? 10 : 0),
    ),
  );

  if (score >= 66) {
    return {
      label: "波乱大",
      score,
      reasons: [`拮抗 ${contenderCount}頭`, `本命支持 ${formatPercent(favoriteMarketProbability, 0)}`, `直前変動 ${oddsMoves}頭`],
    };
  }
  if (score <= 38) {
    return {
      label: "波乱小",
      score,
      reasons: [`勝率差 ${formatPercent(winGap, 1)}`, favoriteIsAiTop ? "AI1位=人気上位" : "人気とAIにズレ"],
    };
  }
  return {
    label: "波乱中",
    score,
    reasons: [`拮抗 ${contenderCount}頭`, `勝率差 ${formatPercent(winGap, 1)}`, `直前変動 ${oddsMoves}頭`],
  };
}

function summarizeHistory(items: HistoricalPrediction[]) {
  const settled = items.filter((item) => item.settled);
  const stake = settled.reduce((sum, item) => sum + item.stake, 0);
  const payout = settled.reduce((sum, item) => sum + item.payout, 0);
  const hits = settled.filter((item) => item.hit).length;
  return {
    total: settled.length,
    hits,
    stake,
    payout,
    roi: stake > 0 ? payout / stake : 0,
    hitRate: settled.length > 0 ? hits / settled.length : 0,
  };
}

function evaluateBettingHeat({
  activeBankroll,
  expectedRoi,
  projections,
  race,
  tickets,
  totalStake,
}: {
  activeBankroll: number;
  expectedRoi: number;
  projections: RunnerProjection[];
  race: Race;
  tickets: TicketProjection[];
  totalStake: number;
}) {
  const top = projections[0];
  const second = projections[1];
  if (!top) {
    return {
      tone: "pass" as const,
      label: "見送り",
      action: "予測対象なし",
      score: 0,
      profile: "判定不能",
      volatilityLabel: "不明",
      volatilityScore: 0,
      dataDepth: 0,
      reasons: ["出走馬または予測が不足"],
    };
  }

  if (!raceHasUsableWinOdds(race)) {
    const dataDepth = dataDepthScore(race);
    return {
      tone: "pass" as const,
      label: "オッズ待ち",
      action: "単勝オッズ公開後に7券種を固定予想",
      score: 0,
      profile: "買い目未生成",
      volatilityLabel: "未判定",
      volatilityScore: 0,
      dataDepth,
      reasons: ["単勝オッズ未取得", "AI評価未生成", "結果・オッズ更新待ち"],
    };
  }

  const volatility = raceVolatilityProfile(race, projections);
  const dataDepth = dataDepthScore(race);
  const winGap = top.winProbability - (second?.winProbability ?? 0);
  const marketGap = top.winProbability - marketWinProbability(race, top.number);
  const bestTicketEdge = tickets.length > 0 ? Math.max(...tickets.map((ticket) => ticket.edge)) : top.edge;
  const positiveTickets = tickets.filter((ticket) => ticket.edge > 0).length;
  const exposure = activeBankroll > 0 ? totalStake / activeBankroll : 0;
  const valueCandidates = projections.filter((runner) => {
    const gap = runner.winProbability - marketWinProbability(race, runner.number);
    return hasRunnerWinOdds(runner) && runner.odds >= 4 && gap >= 0.012;
  }).length;
  const informationPenalty = dataDepth < 0.22 ? 18 : dataDepth < 0.36 ? 8 : 0;
  const volatilityBonus = volatility.score >= 62 ? Math.min((volatility.score - 62) * 0.55, 14) : 0;
  const safeRacePenalty = volatility.score <= 36 ? 5 : 0;
  const score = Math.max(
    0,
    Math.min(
      100,
      34 +
        (expectedRoi - 1) * 95 +
        Math.max(0, bestTicketEdge) * 28 +
        Math.max(0, marketGap) * 150 +
        winGap * 42 +
        Math.min(valueCandidates, 3) * 8 +
        volatilityBonus -
        exposure * 180 -
        informationPenalty -
        safeRacePenalty,
    ),
  );

  const reasons = [
    `AI1位 ${top.number}. ${top.name}`,
    `荒れ度 ${Math.round(volatility.score)}`,
    `情報量 ${formatPercent(dataDepth, 0)}`,
    `勝率差 ${formatPercent(winGap, 1)}`,
    `市場差 ${marketGap >= 0 ? "+" : ""}${formatPercent(marketGap, 1)}`,
  ];

  if (dataDepth < 0.18 && tickets.length === 0) {
    return {
      tone: "pass" as const,
      label: "情報不足",
      action: "見送り優先",
      score,
      profile: "追加情報待ち",
      volatilityLabel: volatility.label,
      volatilityScore: volatility.score,
      dataDepth,
      reasons,
    };
  }

  if (tickets.length === 0 || positiveTickets === 0) {
    return {
      tone: "standard" as const,
      label: "予想確認",
      action: "7券種の候補を表示",
      score,
      profile: "券種別予想",
      volatilityLabel: volatility.label,
      volatilityScore: volatility.score,
      dataDepth,
      reasons,
    };
  }

  if (expectedRoi < 1.0 || marketGap < -0.045 || score < 30) {
    if (volatility.score >= 68 && dataDepth >= 0.22 && (valueCandidates >= 1 || marketGap > -0.02)) {
      return {
        tone: "standard" as const,
        label: "荒れ監視",
        action: "直前更新待ち",
        score: Math.max(score, 48),
        profile: "直前オッズ確認",
        volatilityLabel: volatility.label,
        volatilityScore: volatility.score,
        dataDepth,
        reasons,
      };
    }
    return {
      tone: "standard" as const,
      label: "低比率",
      action: "買うなら小さく",
      score: Math.max(score, 38),
      profile: "控えめ候補",
      volatilityLabel: volatility.label,
      volatilityScore: volatility.score,
      dataDepth,
      reasons,
    };
  }

  if (
    volatility.score >= 62 &&
    expectedRoi >= 1.03 &&
    bestTicketEdge >= 0.05 &&
    (valueCandidates >= 1 || marketGap >= 0.008) &&
    positiveTickets >= 2
  ) {
    return {
      tone: "hot" as const,
      label: "勝負",
      action: "買い候補あり",
      score,
      profile: "期待値重視",
      volatilityLabel: volatility.label,
      volatilityScore: volatility.score,
      dataDepth,
      reasons,
    };
  }

  if (
    volatility.score <= 34 &&
    top.placeProbability >= 0.62 &&
    winGap >= 0.12 &&
    expectedRoi >= 1.0 &&
    bestTicketEdge >= 0.02 &&
    score <= 58
  ) {
    return {
      tone: "safe" as const,
      label: "絞り込み",
      action: "点数を絞る",
      score,
      profile: "本線重視",
      volatilityLabel: volatility.label,
      volatilityScore: volatility.score,
      dataDepth,
      reasons,
    };
  }

  return {
    tone: "standard" as const,
    label: "通常監視",
    action: "券種別に比較",
    score,
    profile: "期待値比較",
    volatilityLabel: volatility.label,
    volatilityScore: volatility.score,
    dataDepth,
    reasons,
  };
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<ViewTab>("predict");
  const [selectedRaceId, setSelectedRaceId] = useState("");
  const [selectedDate, setSelectedDate] = useState(INITIAL_CALENDAR_DATE);
  const [selectedVenue, setSelectedVenue] = useState("");
  const [monthAnchor, setMonthAnchor] = useState(monthStart(INITIAL_CALENDAR_DATE));
  const [todayDate, setTodayDate] = useState(INITIAL_CALENDAR_DATE);
  const [bankroll, setBankroll] = useState(100000);
  const [apiRaces, setApiRaces] = useState<Race[]>([]);
  const [apiHistory, setApiHistory] = useState<HistoricalPrediction[]>([]);
  const [apiState, setApiState] = useState<ApiState>("loading");
  const [dataPhase, setDataPhase] = useState<DataPhase>("initial");
  const [apiPrediction, setApiPrediction] = useState<ApiRacePrediction | null>(null);

  const demoRacesEnabled = process.env.NEXT_PUBLIC_ENABLE_DEMO_RACES === "1";
  const rawAvailableRaces = apiRaces.length > 0 ? apiRaces : demoRacesEnabled ? races : [];
  const availableRaces = useMemo(() => compactRaceList(rawAvailableRaces), [rawAvailableRaces]);
  const availableHistory = apiHistory.length > 0 ? apiHistory : demoRacesEnabled ? predictionHistory : [];
  const sortedHistory = useMemo(
    () => [...availableHistory].sort((a, b) => b.date.localeCompare(a.date) || b.start.localeCompare(a.start) || b.id.localeCompare(a.id)),
    [availableHistory],
  );
  const historyByRaceId = useMemo(
    () => new Map(availableHistory.map((item) => [item.id, item])),
    [availableHistory],
  );
  const race = availableRaces.find((item) => item.id === selectedRaceId) ?? null;
  const todayRaces = useMemo(
    () => availableRaces.filter((item) => item.date === todayDate && item.runners.length > 0).sort(sortRaceCards),
    [availableRaces, todayDate],
  );
  const predictionRace = activeTab === "predict"
    ? todayRaces.find((item) => item.id === selectedRaceId) ?? pickDefaultRace(todayRaces, todayDate) ?? null
    : race;
  const visibleRace = activeTab === "predict" ? predictionRace : race;
  const selectedDateRaces = availableRaces.filter((item) => item.date === selectedDate);
  const venueOptions = useMemo<VenueOption[]>(() => {
    const counts = new Map<string, number>();
    selectedDateRaces.forEach((item) => counts.set(item.venue, (counts.get(item.venue) ?? 0) + 1));
    return Array.from(counts.entries())
      .map(([venue, count]) => ({ venue, count }))
      .sort((a, b) => a.venue.localeCompare(b.venue, "ja"));
  }, [selectedDateRaces]);
  const todayVenueOptions = useMemo<VenueOption[]>(() => {
    const counts = new Map<string, number>();
    todayRaces.forEach((item) => counts.set(item.venue, (counts.get(item.venue) ?? 0) + 1));
    return Array.from(counts.entries())
      .map(([venue, count]) => ({ venue, count }))
      .sort((a, b) => a.venue.localeCompare(b.venue, "ja"));
  }, [todayRaces]);
  const selectedVenueRaces = useMemo(() => {
    const venue = selectedVenue || venueOptions[0]?.venue;
    return selectedDateRaces.filter((item) => item.venue === venue).sort(sortRaceCards);
  }, [selectedDateRaces, selectedVenue, venueOptions]);
  const selectedTodayVenueRaces = useMemo(() => {
    const selectedVenueExists = todayRaces.some((item) => item.venue === selectedVenue);
    const venue = selectedVenueExists ? selectedVenue : predictionRace?.venue || todayVenueOptions[0]?.venue;
    return todayRaces.filter((item) => item.venue === venue).sort(sortRaceCards);
  }, [predictionRace?.venue, selectedVenue, todayRaces, todayVenueOptions]);
  const monthCells = useMemo(
    () => buildMonthCells(monthAnchor, availableRaces, availableHistory, todayDate),
    [availableHistory, availableRaces, monthAnchor, todayDate],
  );
  const historySummary = useMemo(
    () => summarizeHistory(availableHistory.filter((item) => !item.generatedAfterResult)),
    [availableHistory],
  );
  const activeBankroll = Number.isFinite(bankroll) ? Math.max(bankroll, 1000) : 100000;
  const riskLevel = PORTFOLIO_RISK_LEVEL;
  const riskRatio = riskLevel / 100;
  const modelingRace = activeTab === "predict" ? predictionRace : race;

  useEffect(() => {
    let cancelled = false;
    async function loadInitialData() {
      const centerDate = todayAtJst();
      setTodayDate(centerDate);
      setSelectedDate(centerDate);
      setMonthAnchor(monthStart(centerDate));
      setDataPhase("today");
      const historyStartDate = addDays(centerDate, -30);
      const nearFutureEndDate = addDays(centerDate, 3);
      try {
        const todayRacesPayload = await fetchRaceRangeFromApi(centerDate, centerDate);
        if (cancelled) {
          return;
        }
        setApiRaces(todayRacesPayload);
        const todayRace = pickDefaultRace(todayRacesPayload, centerDate);
        if (todayRace) {
          setSelectedRaceId(todayRace.id);
          setSelectedVenue(todayRace.venue);
          setApiState("ready");
        } else {
          setSelectedRaceId("");
          setSelectedVenue("");
          setApiState("empty");
        }

        setDataPhase("range");
        const rangeRaces = await fetchRaceRangeFromApi(centerDate, nearFutureEndDate);
        if (cancelled) {
          return;
        }
        setApiRaces((current) => mergeRaceLists(current, rangeRaces));
        const nextTodayRace = pickDefaultRace(
          rangeRaces.filter((item) => item.date === centerDate),
          centerDate,
        );
        if (nextTodayRace) {
          setSelectedRaceId((current) => current || nextTodayRace.id);
          setSelectedVenue((current) => current || nextTodayRace.venue);
        }
        setApiState(rangeRaces.length > 0 || todayRacesPayload.length > 0 ? "ready" : "empty");
        setDataPhase("ready");
        fetchHistoryRangeFromApi(historyStartDate, centerDate).then((rangeHistory) => {
          if (!cancelled) {
            setApiHistory(rangeHistory);
          }
        }).catch(() => undefined);
      } catch {
        if (!cancelled) {
          setApiState("fallback");
          setDataPhase("ready");
        }
      }
    }
    loadInitialData();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function refreshToday() {
      try {
        const [todayRacesPayload, todayHistoryPayload] = await Promise.all([
          fetchRaceRangeFromApi(todayDate, todayDate),
          fetchHistoryRangeFromApi(todayDate, todayDate),
        ]);
        if (cancelled) {
          return;
        }
        setApiRaces((current) => mergeRaceLists(current, todayRacesPayload));
        setApiHistory((current) => mergeHistoryLists(current, todayHistoryPayload));
        if (todayRacesPayload.length > 0) {
          setApiState("ready");
        }
      } catch {
        // Keep the last good data on screen; the next polling tick will retry.
      }
    }

    refreshToday();
    const timer = window.setInterval(refreshToday, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [todayDate]);

  useEffect(() => {
    let cancelled = false;
    async function loadPrediction() {
      if (activeTab !== "predict" || !modelingRace || modelingRace.runners.length < 2) {
        setApiPrediction(null);
        return;
      }
      if (modelingRace.date !== todayDate || modelingRace.status === "finished") {
        setApiPrediction(null);
        return;
      }
      try {
        const response = await fetch(`${apiBaseUrl()}/predict`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildRaceRequest(modelingRace, riskLevel, activeBankroll)),
        });
        if (!response.ok) {
          throw new Error(`predict ${response.status}`);
        }
        const prediction = (await response.json()) as ApiRacePrediction;
        if (!cancelled) {
          setApiPrediction(prediction);
          setApiState("ready");
        }
      } catch {
        if (!cancelled) {
          setApiPrediction(null);
          setApiState((current) => (current === "ready" ? "ready" : "fallback"));
        }
      }
    }
    loadPrediction();
    return () => {
      cancelled = true;
    };
  }, [activeBankroll, activeTab, modelingRace, riskLevel, todayDate]);

  useEffect(() => {
    if (selectedDateRaces.length === 0) {
      return;
    }
    const currentVenueExists = selectedDateRaces.some((item) => item.venue === selectedVenue);
    if (!currentVenueExists) {
      const nextRace = [...selectedDateRaces].sort(sortRaceCards)[0];
      setSelectedVenue(nextRace.venue);
      setSelectedRaceId((current) =>
        selectedDateRaces.some((item) => item.id === current) ? current : nextRace.id,
      );
    }
  }, [selectedDateRaces, selectedVenue]);

  const fallbackProjections = useMemo<RunnerProjection[]>(() => {
    if (!modelingRace) {
      return [];
    }
    return buildRaceOnlyProjections(modelingRace, riskRatio);
  }, [modelingRace, riskRatio]);

  const apiProjections = useMemo(
    () => (modelingRace ? mergeApiProjections(apiPrediction, modelingRace) : null),
    [apiPrediction, modelingRace],
  );
  const projections = apiProjections ?? fallbackProjections;

  const fallbackTickets = useMemo<TicketProjection[]>(() => {
    return [];
  }, []);

  const apiTickets = useMemo(() => {
    if (!modelingRace || !apiPrediction || apiPrediction.race_id !== modelingRace.id) {
      return [];
    }
    return apiPrediction.recommendations.map(apiRecommendationToTicket);
  }, [apiPrediction, modelingRace]);
  const tickets = apiTickets.length > 0 ? apiTickets : fallbackTickets;

  const totalStake = tickets.reduce((sum, ticket) => sum + ticket.stake, 0);
  const expectedReturn = tickets.reduce((sum, ticket) => sum + ticket.expectedReturn, 0);
  const expectedRoi = totalStake > 0 ? expectedReturn / totalStake : 0;
  function selectRace(raceId: string, nextTab: ViewTab = activeTab) {
    const nextRace = availableRaces.find((item) => item.id === raceId);
    setSelectedRaceId(raceId);
    if (nextRace) {
      setSelectedDate(nextRace.date);
      setSelectedVenue(nextRace.venue);
      setMonthAnchor(monthStart(nextRace.date));
    }
    setActiveTab(nextTab);
  }

  function selectTodayPrediction() {
    const todayRace = todayRaces.find((item) => item.id === selectedRaceId) ?? pickDefaultRace(todayRaces, todayDate);
    setSelectedDate(todayDate);
    setMonthAnchor(monthStart(todayDate));
    if (todayRace) {
      setSelectedRaceId(todayRace.id);
      setSelectedVenue(todayRace.venue);
    } else {
      setSelectedRaceId("");
      setSelectedVenue("");
    }
    setActiveTab("predict");
  }

  function selectDate(date: string) {
    setSelectedDate(date);
    setMonthAnchor(monthStart(date));
    const firstRace = availableRaces.filter((item) => item.date === date).sort(sortRaceCards)[0];
    if (firstRace) {
      setSelectedVenue(firstRace.venue);
      setSelectedRaceId(firstRace.id);
    } else {
      setSelectedVenue("");
      setSelectedRaceId("");
    }
  }

  return (
    <main className="umalab-shell">
      <div className="app-frame">
        <header className="top-bar">
          <div className="brand-row">
            <img src="/racequant-icon.svg" alt="" />
            <div>
              <strong>UMALAB</strong>
              <span>競馬AI予想</span>
            </div>
          </div>
          <a className="portfolio-link" href="https://agoringang.com/#apps">
            <span className="portfolio-grid" aria-hidden="true">
              <i />
              <i />
              <i />
              <i />
            </span>
            他のアプリを見る
          </a>
        </header>

        {loadingText(dataPhase, apiState) && (
          <LoadingBanner apiState={apiState} phase={dataPhase} />
        )}

        <section className={`race-status-card ${visibleRace ? marketClass(visibleRace.market) : ""}`}>
          <div className="race-status-main">
            <span>{visibleRace ? `${visibleRace.date} / ${raceStartLabel(visibleRace)}` : selectedDate}</span>
            <h1>{visibleRace ? displayRaceTitle(visibleRace) : "今日のAI競馬予想"}</h1>
            <p>{visibleRace ? raceStatusLead(visibleRace) : "単勝・枠連・馬連・ワイド・馬単・3連複・3連単の予想を固定表示します"}</p>
          </div>
          <div className="race-pills">
            <span>{publicMarketLabel(visibleRace?.market)}</span>
            <span className={visibleRace?.verificationStatus === "verified" ? "verified" : ""}>
              {visibleRace?.verificationStatus === "verified" ? "実データ" : "確認中"}
            </span>
            <span>{visibleRace?.status === "finished" ? "結果あり" : "予想対象"}</span>
          </div>
        </section>

        <div className="desktop-tabs" role="tablist" aria-label="UMALAB tabs">
          {tabs.map((tab) => (
            <button
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? "active" : ""}
              key={tab.id}
              onClick={() => (tab.id === "predict" ? selectTodayPrediction() : setActiveTab(tab.id))}
              role="tab"
              type="button"
            >
              <TabIcon icon={tab.icon} />
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "predict" && predictionRace && (
          <PredictPanel
            activeBankroll={activeBankroll}
            bankroll={bankroll}
            expectedRoi={expectedRoi}
            onBankrollChange={setBankroll}
            onRaceSelect={(raceId) => selectRace(raceId)}
            onVenueSelect={setSelectedVenue}
            projections={projections}
            race={predictionRace}
            historyByRaceId={historyByRaceId}
            raceHistory={predictionRace ? historyByRaceId.get(predictionRace.id) ?? null : null}
            selectedDate={todayDate}
            selectedVenue={selectedTodayVenueRaces[0]?.venue ?? selectedVenue}
            tickets={tickets}
            totalStake={totalStake}
            venueOptions={todayVenueOptions}
            venueRaces={selectedTodayVenueRaces}
          />
        )}
        {activeTab === "predict" && !predictionRace && (
          <VerifiedDataEmptyState apiState={apiState} selectedDate={todayDate} />
        )}

        {activeTab === "calendar" && (
          <CalendarPanel
            historyByRaceId={historyByRaceId}
            monthAnchor={monthAnchor}
            monthCells={monthCells}
            onDateSelect={selectDate}
            onMonthChange={setMonthAnchor}
            onRaceSelect={(raceId) => selectRace(raceId, selectedDate === todayDate ? "predict" : "calendar")}
            onVenueSelect={setSelectedVenue}
            selectedDate={selectedDate}
            selectedDateRaces={selectedDateRaces}
            selectedRaceId={selectedRaceId}
            selectedVenue={selectedVenue}
            venueOptions={venueOptions}
            venueRaces={selectedVenueRaces}
          />
        )}

        {activeTab === "results" && (
          <ResultsPanel
            history={sortedHistory}
            historySummary={historySummary}
            onRaceSelect={(raceId) => selectRace(raceId, "calendar")}
            todayDate={todayDate}
          />
        )}

        <BetTypeGuide />
        <OtherAppsPanel />
      </div>

      <nav className="bottom-tabs" aria-label="UMALAB navigation">
        {tabs.map((tab) => (
          <button
            className={activeTab === tab.id ? "active" : ""}
            key={tab.id}
            onClick={() => (tab.id === "predict" ? selectTodayPrediction() : setActiveTab(tab.id))}
            type="button"
          >
            <TabIcon icon={tab.icon} />
            {tab.label}
          </button>
        ))}
      </nav>
    </main>
  );
}

function VerifiedDataEmptyState({ apiState, selectedDate }: { apiState: ApiState; selectedDate: string }) {
  const label =
    apiState === "loading"
      ? "レース情報を確認中"
      : apiState === "fallback"
        ? "レース情報の取得に失敗"
        : "確認済みレースなし";

  return (
    <section className="tab-panel">
      <div className="empty-state verified-empty">
        <strong>{label}</strong>
        <span>{selectedDate} の開催データは未取得または開催なしです。日程タブから前後の開催日を確認できます。</span>
      </div>
    </section>
  );
}

function LoadingBanner({ apiState, phase }: { apiState: ApiState; phase: DataPhase }) {
  const text = loadingText(phase, apiState);
  return (
    <div className={apiState === "fallback" ? "loading-banner error" : "loading-banner"} role="status">
      <span className="loading-dot" aria-hidden="true" />
      <strong>{text}</strong>
      <em>{phase === "range" ? "本日分を先に表示し、過去成績と日程を更新しています" : "出馬表・オッズ・結果を確認しています"}</em>
    </div>
  );
}

function PredictPanel({
  activeBankroll,
  bankroll,
  expectedRoi,
  onBankrollChange,
  onRaceSelect,
  onVenueSelect,
  projections,
  race,
  historyByRaceId,
  raceHistory,
  selectedDate,
  selectedVenue,
  tickets,
  totalStake,
  venueOptions,
  venueRaces,
}: {
  activeBankroll: number;
  bankroll: number;
  expectedRoi: number;
  onBankrollChange: (value: number) => void;
  onRaceSelect: (raceId: string) => void;
  onVenueSelect: (venue: string) => void;
  projections: RunnerProjection[];
  race: Race;
  historyByRaceId: Map<string, HistoricalPrediction>;
  raceHistory: HistoricalPrediction | null;
  selectedDate: string;
  selectedVenue: string;
  tickets: TicketProjection[];
  totalStake: number;
  venueOptions: VenueOption[];
  venueRaces: Race[];
}) {
  const resultOrder = raceResultOrder(race);
  const isFinished = race.status === "finished";
  const primaryTicket = tickets[0];
  const oddsReady = raceHasUsableWinOdds(race);
  const bettingHeat = evaluateBettingHeat({
    activeBankroll,
    expectedRoi,
    projections,
    race,
    tickets,
    totalStake,
  });

  return (
    <section className={`tab-panel ${marketClass(race.market)}`}>
      {!isFinished && (
        <DecisionCard
          heat={bettingHeat}
          projections={projections}
          race={race}
          tickets={tickets}
        />
      )}

      <div className="control-strip">
        <RacePicker
          onRaceSelect={onRaceSelect}
          onVenueSelect={onVenueSelect}
          races={venueRaces}
          historyByRaceId={historyByRaceId}
          selectedDate={selectedDate}
          selectedRaceId={race.id}
          selectedVenue={selectedVenue || race.venue}
          venues={venueOptions}
        />

        {!isFinished && (
          <div className="settings-grid">
            <label className="field-card bankroll-card">
              <span>軍資金</span>
              <input
                min={1000}
                onChange={(event) => onBankrollChange(Number(event.target.value))}
                step={1000}
                type="number"
                value={bankroll}
              />
            </label>
          </div>
        )}
      </div>

      <RaceInfoChips race={race} />

      {!isFinished && (
        <PredictionOrderCard projections={projections} race={race} />
      )}
      {!isFinished && <BettingHeatCard heat={bettingHeat} />}

      {raceHistory && (
        <ResultStrip history={raceHistory} />
      )}
      {isFinished && (
        <RaceResultStrip race={race} resultOrder={resultOrder} raceHistory={raceHistory} />
      )}
      {isFinished && (
        <RacePayoutGrid race={race} />
      )}
      {isFinished && raceHistory && (
        <HitPayoutCard history={raceHistory} />
      )}
      {isFinished && (
        <PredictionResultDiff race={race} raceHistory={raceHistory} projections={projections} />
      )}

      {!isFinished && (
        <section className="bet-plan-card">
          <div className="section-heading">
            <h2>券種別予想</h2>
            <span>期待値で隠さず7券種を固定表示</span>
          </div>
          <div className="summary-strip compact">
            <Metric label="券種" value={`${PUBLIC_BET_TYPE_GUIDES.length}種`} />
            <Metric label="予想点数" value={`${tickets.reduce((sum, ticket) => sum + ticket.tickets, 0)}点`} />
            <Metric label="券オッズ" value={primaryTicket ? (oddsReady ? formatOdds(primaryTicket.odds) : "暫定") : "-"} />
            <Metric label="100円払戻" value={primaryTicket && oddsReady ? ticketPayoutPer100(primaryTicket) : "-"} />
            <Metric label="表示" value="券種別" />
          </div>
          <TicketList projections={projections} race={race} tickets={tickets} />
        </section>
      )}

      <section className="runner-table-card">
        <div className="section-heading compact">
          <h2>出走馬</h2>
          <span>{race.course}</span>
        </div>
        <RunnerTable projections={projections} race={race} />
      </section>
    </section>
  );
}

function RaceInfoChips({ race }: { race: Race }) {
  const depth = dataDepthScore(race);
  const chips = [
    { label: "発走", value: raceStartLabel(race) },
    { label: "頭数", value: fieldSizeLabel(race) },
    { label: "条件", value: race.course },
    { label: "区分", value: `${publicMarketLabel(race.market)} / 情報量${formatPercent(depth, 0)}` },
  ];

  return (
    <div className="race-info-chips" aria-label="レース情報">
      {chips.map((chip) => (
        <span key={chip.label}>
          <b>{chip.label}</b>
          {chip.value}
        </span>
      ))}
    </div>
  );
}

function BettingHeatCard({ heat }: { heat: BettingHeat }) {
  return (
    <section className={`heat-card ${heat.tone}`}>
      <div>
        <span>勝負度</span>
        <strong>{heat.label}</strong>
        <em>{heat.action}</em>
      </div>
      <div className="heat-meter" aria-label={`勝負度 ${Math.round(heat.score)}`}>
        <span style={{ width: `${Math.max(4, Math.min(100, heat.score))}%` }} />
      </div>
      <div className="heat-submetrics">
        <span>荒れ度 <b>{heat.volatilityLabel}</b></span>
        <span>情報量 <b>{formatPercent(heat.dataDepth, 0)}</b></span>
      </div>
      <div className="heat-reasons">
        <b>{heat.profile}</b>
        {heat.reasons.slice(0, 4).map((reason) => (
          <span key={reason}>{reason}</span>
        ))}
      </div>
    </section>
  );
}

function DecisionCard({
  heat,
  projections,
  race,
  tickets,
}: {
  heat: BettingHeat;
  projections: RunnerProjection[];
  race: Race;
  tickets: TicketProjection[];
}) {
  const topTicket = tickets[0];
  const oddsReady = raceHasUsableWinOdds(race);
  const shouldPass = !topTicket;
  const isPendingOdds = !oddsReady && !topTicket;
  const isTentative = !oddsReady && !!topTicket;
  const topRunner = projections[0];
  const confidence = Math.max(0, Math.min(100, Math.round(heat.score)));
  const displayRunners = isPendingOdds
    ? [...projections].sort((a, b) => a.number - b.number).slice(0, 3)
    : projections.slice(0, 3);

  return (
    <section className={`decision-card ${shouldPass ? "pass" : heat.tone} ${marketClass(race.market)}`}>
      <div className="decision-main">
        <span>{isPendingOdds ? "オッズ公開待ち" : isTentative ? "オッズ未取得の暫定予想" : shouldPass ? "予想準備中" : "今日の券種別予想"}</span>
        <h2>{isPendingOdds ? "AI評価は取得待ち" : shouldPass ? "予想生成待ち" : `${topTicket.type} ${topTicket.selection}`}</h2>
        <p>
          {isPendingOdds
            ? "出馬表は取得済み。単勝オッズ公開後に7券種の予想を自動生成します。"
            : shouldPass
            ? heat.action
            : `${ticketCompactMethod(topTicket)}。${isTentative ? "オッズ未取得のため払戻は未確定です。" : "各券種の予想を下に固定表示します。"}`}
        </p>
      </div>

      <div className="decision-metrics">
        <Value
          label={shouldPass ? "判断" : "推奨度"}
          value={shouldPass ? "見送り" : `${confidence}/100`}
          tone={shouldPass ? "negative" : confidence >= 62 ? "positive" : confidence < 38 ? "negative" : undefined}
        />
        <Value label="予想点数" value={shouldPass ? "-" : `${tickets.reduce((sum, ticket) => sum + ticket.tickets, 0)}点`} />
        <Value label="券オッズ" value={shouldPass || !topTicket ? "-" : isTentative ? "暫定" : formatOdds(topTicket.odds)} />
        <Value label="券種" value={isPendingOdds ? "オッズ待ち" : shouldPass ? "生成待ち" : `${tickets.length}種`} />
      </div>

      <div className="decision-examples">
        {!shouldPass && topTicket ? (
          <>
            <span>100円あたり払戻 {isTentative ? "未確定" : ticketPayoutPer100(topTicket)}</span>
            <span>的中率 {formatPercent(topTicket.probability)} / {topTicket.tickets}通り</span>
          </>
        ) : (
          <>
            <span>予想生成待ち</span>
            <span>{isPendingOdds ? "オッズ未取得 / AI評価未生成" : heat.reasons.slice(0, 2).join(" / ")}</span>
          </>
        )}
      </div>

      <div className="confidence-list">
        <span>{isPendingOdds ? "出馬表" : "自信度ランキング"}</span>
        {displayRunners.map((runner, index) => (
          <b key={runner.number}>
            {index + 1}. {runner.number} {runner.name}
            <em>{isPendingOdds ? "評価待ち" : `AI ${displayAiIndex(runner, race)}`}</em>
          </b>
        ))}
        {oddsReady && topRunner && <small>AI1位と人気の差 {formatPercent(topRunner.winProbability - marketWinProbability(race, topRunner.number), 1)}</small>}
      </div>
    </section>
  );
}

function PredictionOrderCard({ projections, race }: { projections: RunnerProjection[]; race: Race }) {
  const chartRows = projections.slice(0, 7);
  const volatility = raceVolatilityProfile(race, projections);
  const depth = dataDepthScore(race);
  return (
    <section className="prediction-order-card">
      <div className="section-heading">
        <h2>AI評価順</h2>
        <span>{publicMarketLabel(race.market)} / {volatility.label} / 情報量{formatPercent(depth, 0)}</span>
      </div>
      <div className="order-grid">
        {projections.slice(0, 5).map((runner, index) => (
          <article key={runner.number} className={index === 0 ? "lead" : ""}>
            <div className="order-rank">{index + 1}</div>
            <div>
              <strong>{runner.number}. {runner.name}</strong>
              <span>{runner.jockey} / {runnerOddsMeta(runner, race)}</span>
            </div>
            <div className="order-probs">
              <b>AI {displayAiIndex(runner, race)}</b>
              <em>勝 {formatPercent(runner.winProbability)} / 3内 {formatPercent(runner.placeProbability)}</em>
            </div>
          </article>
        ))}
      </div>
      <div className="probability-chart" aria-label="着順予想確率">
        {chartRows.map((runner, index) => {
          const marketProbability = marketWinProbability(race, runner.number);
          const gap = runner.winProbability - marketProbability;
          return (
            <article key={`chart-${runner.number}`}>
              <div className="chart-label">
                <strong>{index + 1}. {runner.number} {runner.name}</strong>
                <span>{gap >= 0 ? "+" : ""}{formatPercent(gap, 1)} vs 人気</span>
              </div>
              <div className="chart-bars">
                <span style={{ width: `${Math.min(runner.winProbability * 100, 100)}%` }} />
                <em style={{ width: `${Math.min(runner.placeProbability * 100, 100)}%` }} />
              </div>
              <div className="chart-values">
                <b>AI {displayAiIndex(runner, race)}</b>
                <b>勝 {formatPercent(runner.winProbability)}</b>
                <b>3内 {formatPercent(runner.placeProbability)}</b>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function MarketPendingCard({ race }: { race: Race }) {
  return (
    <section className={`prediction-order-card pending ${marketClass(race.market)}`}>
      <div className="section-heading">
        <h2>AI評価は取得待ち</h2>
        <span>{publicMarketLabel(race.market)} / {raceStartLabel(race)}</span>
      </div>
      <div className="pending-market-grid">
        <span>出馬表</span>
        <strong>{race.runners.length}頭取得済み</strong>
        <span>単勝オッズ</span>
        <strong>未取得</strong>
        <span>買い候補</span>
        <strong>オッズ公開後に券種別生成</strong>
      </div>
    </section>
  );
}

function ticketAnchorRunner(ticket: TicketProjection, projections: RunnerProjection[]) {
  const anchorNumber = ticket.legs[0]?.numbers[0] ?? Number(ticket.selection.match(/\d+/)?.[0]);
  return projections.find((runner) => runner.number === anchorNumber) ?? projections[0];
}

function ticketReasonRows(ticket: TicketProjection, race: Race, projections: RunnerProjection[]) {
  const anchor = ticketAnchorRunner(ticket, projections);
  const oddsReady = raceHasUsableWinOdds(race);
  if (!anchor) {
    return [
      { label: "AI評価", value: "出走馬情報不足" },
      { label: "買わない理由", value: "予測対象が足りない" },
    ];
  }
  const popularity = runnerPopularity(anchor, race);
  const marketGap = anchor.winProbability - marketWinProbability(race, anchor.number);
  const weightConcern =
    Math.abs(anchor.horseWeightDiff ?? 0) >= 16
      ? `馬体重変動 ${anchor.horseWeightDiff! > 0 ? "+" : ""}${anchor.horseWeightDiff}kg`
      : "";
  const oddsConcern =
    Math.abs(anchor.oddsDelta ?? 0) >= 0.12
      ? `直前オッズ変動 ${anchor.oddsDelta! > 0 ? "+" : ""}${formatPercent(anchor.oddsDelta!, 0)}`
      : "";
  const concern = weightConcern || oddsConcern || (ticket.edge < 0 ? "オッズ妙味は低め" : "大きな不安なし");
  const recommendation =
    ticket.edge >= 0.12 && anchor.placeProbability >= 0.45
      ? "強め"
      : ticket.edge >= 0.04
        ? "候補"
        : ticket.probability >= 0.5
          ? "保険寄り"
          : "控えめ";
  return [
    { label: "予想形", value: ticketCompactMethod(ticket) },
    { label: "AI評価", value: `${anchor.number} ${anchor.name} / AI指数 ${displayAiIndex(anchor, race)}` },
    { label: "券オッズ", value: oddsReady ? formatOdds(ticket.odds) : "暫定" },
    { label: "中心馬オッズ", value: `${anchor.number} ${formatOdds(anchor.odds)}` },
    { label: "AI平均との差", value: `${marketGap >= 0 ? "+" : ""}${formatPercent(marketGap, 1)}` },
    { label: "人気との差", value: popularity ? `${popularity}人気をAI上位評価` : "人気不明" },
    { label: "不安要素", value: concern },
    { label: "推奨度", value: recommendation },
  ];
}

function TicketList({
  projections,
  race,
  tickets,
}: {
  projections: RunnerProjection[];
  race: Race;
  tickets: TicketProjection[];
}) {
  const ticketByType = new Map<string, TicketProjection>();
  tickets.forEach((ticket) => {
    if (!ticketByType.has(ticket.type)) {
      ticketByType.set(ticket.type, ticket);
    }
  });

  return (
    <div className="ticket-list">
      {PUBLIC_BET_TYPE_GUIDES.map((guide) => {
        const ticket = ticketByType.get(guide.label);
        if (!ticket) {
          const oddsReady = raceHasUsableWinOdds(race);
          return (
            <article className="disabled" key={guide.id}>
              <div className="ticket-name">
                <span>{guide.summary}</span>
                <strong>{guide.label}</strong>
                <small>予想待ち</small>
              </div>
              <div className="ticket-body">
                <div className="ticket-meta">
                  <span>{guide.method}</span>
                  <strong>{oddsReady ? "予想生成待ち" : "オッズ未取得"}</strong>
                </div>
                <div className="ticket-data">
                  <Value label="券オッズ" value="-" />
                  <Value label="100円払戻" value="-" />
                  <Value label="予想点数" value="-" />
                  <Value label="状態" value={oddsReady ? "生成待ち" : "取得待ち"} />
                </div>
              </div>
            </article>
          );
        }
        const reasons = ticketReasonRows(ticket, race, projections);
        const oddsReady = raceHasUsableWinOdds(race);
        const oddsLabel = oddsReady ? formatOdds(ticket.odds) : "暫定";
        const payoutLabel = oddsReady ? ticketPayoutPer100(ticket) : "-";
        const isPrimary = tickets[0]?.type === ticket.type && tickets[0]?.selection === ticket.selection;
        return (
          <article className={isPrimary ? "primary" : ""} key={`${guide.id}-${ticket.selection}`}>
            <div className="ticket-name">
              <span>{isPrimary ? "最優先" : guide.summary}</span>
              <strong>{ticket.type}</strong>
              <small>{ticket.tickets}点予想</small>
            </div>
            <div className="ticket-body">
              <TicketLegs legs={ticket.legs} />
              <div className="ticket-meta">
                <span>{ticket.tickets}通り</span>
                <span>{oddsLabel}</span>
                <strong>100円払戻 {payoutLabel}</strong>
              </div>
              <div className="ticket-data">
                <Value label="的中率" value={formatPercent(ticket.probability)} />
                <Value label="券オッズ" value={oddsLabel} />
                <Value label="100円払戻" value={payoutLabel} />
                <Value label="予想点数" value={`${ticket.tickets}点`} />
              </div>
              <div className="ticket-reasons">
                {reasons.map((reason) => (
                  <span key={reason.label}>
                    <b>{reason.label}</b>
                    {reason.value}
                  </span>
                ))}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function RacePicker({
  onRaceSelect,
  onVenueSelect,
  races,
  historyByRaceId,
  selectedDate,
  selectedRaceId,
  selectedVenue,
  venues,
}: {
  onRaceSelect: (raceId: string) => void;
  onVenueSelect: (venue: string) => void;
  races: Race[];
  historyByRaceId: Map<string, HistoricalPrediction>;
  selectedDate: string;
  selectedRaceId: string;
  selectedVenue: string;
  venues: VenueOption[];
}) {
  const displayRaces = compactRaceList(races);
  const totalRaceCount = displayRaces.length || venues.reduce((sum, venue) => sum + venue.count, 0);
  return (
    <div className="race-picker">
      <div className="section-heading compact">
        <h2>{selectedDate}</h2>
        <span>{totalRaceCount}R</span>
      </div>
      <div className="venue-grid" aria-label="開催場">
        {venues.length > 0 ? (
          venues.map((venue) => {
            const market = venueMarket(venue.venue);
            return (
              <button
                className={[
                  selectedVenue === venue.venue ? "active" : "",
                  marketClass(market),
                ].filter(Boolean).join(" ")}
                key={venue.venue}
                onClick={() => onVenueSelect(venue.venue)}
                type="button"
              >
                <i>{publicMarketShortLabel(market)}</i>
                <strong>{venue.venue}</strong>
                <span>{venue.count}R</span>
              </button>
            );
          })
        ) : (
          <div className="empty-inline">開催なし</div>
        )}
      </div>
      <div className="race-number-grid" aria-label="レース番号">
        {displayRaces.map((item) => {
          const history = historyByRaceId.get(item.id);
          return (
            <button
              className={[
                item.id === selectedRaceId ? "active" : "",
                history?.hit ? "hit" : "",
                marketClass(item.market),
              ].filter(Boolean).join(" ")}
              key={item.id}
              onClick={() => onRaceSelect(item.id)}
              type="button"
            >
              {history?.hit && <em aria-label="的中">🎯</em>}
              <strong>{raceNumberValue(item)}R</strong>
              <span>{raceStartLabel(item)}</span>
              <i>{publicMarketShortLabel(item.market)}</i>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ResultStrip({ history }: { history: HistoricalPrediction }) {
  if (!history.settled) {
    return (
      <div className="result-strip pending">
        <strong>結果待ち</strong>
        <span>公式払戻取得後に回収率を表示</span>
        <span>投資比率 {formatPercent(safeRatio(history.stake, 100_000), 2)}</span>
        <em>{history.betCount}点</em>
      </div>
    );
  }

  const settledLabel = history.generatedAfterResult
    ? history.hit
      ? "🎯 参考的中"
      : "参考結果"
    : history.hit
      ? "🎯 的中"
      : history.settled
        ? "不的中"
        : "結果待ち";
  return (
    <div className={history.hit ? "result-strip hit" : "result-strip"}>
      <strong>{settledLabel}</strong>
      <span>{history.generatedAfterResult ? "参考回収率" : "回収率"} {formatPercent(history.roi, 1)}</span>
      <span className={historyProfit(history) >= 0 ? "positive" : "negative"}>
        損益率 {formatSignedPercent(safeRatio(historyProfit(history), history.stake), 1)}
      </span>
      <em>{history.hitCount}/{history.betCount} 点</em>
    </div>
  );
}

function HitPayoutCard({ history }: { history: HistoricalPrediction }) {
  const resultItems = [...(history.recommendationResults ?? [])].sort((a, b) => Number(b.hit) - Number(a.hit));
  const profit = historyProfit(history);
  const profitRate = safeRatio(profit, history.stake);
  const pending = !history.settled;

  return (
    <section className={`hit-payout-card ${history.hit ? "hit" : history.settled ? "miss" : "pending"}`}>
      <div className="hit-payout-main">
        <span>{history.hit ? "🎯 的中払戻" : history.settled ? "購入結果" : "結果待ち"}</span>
        <strong className={profit >= 0 ? "positive" : "negative"}>
          {pending ? "照合待ち" : formatSignedPercent(profitRate, 1)}
        </strong>
        <em>{pending ? "公式結果取得後に回収率を表示" : `回収率 ${formatPercent(history.roi, 1)} / 的中 ${history.hitCount}/${history.betCount}点`}</em>
      </div>
      <div className="hit-ticket-grid">
        {resultItems.length > 0 ? (
          resultItems.slice(0, 4).map((item, index) => {
            const stakeShare = safeRatio(item.stake, history.stake);
            return (
              <article className={item.hit ? "hit" : "miss"} key={`${item.betType}-${item.selection}-${index}`}>
                <span>
                  {item.hit ? "🎯 的中" : item.payoutSource === "missing_official_payout" ? "払戻未取得" : "不的中"} / {publicBetTypeLabel(item.betType)}
                </span>
                <strong>{resultBetSummary(item)}</strong>
                <em>投資比率 {formatPercent(stakeShare, 0)} / 100円払戻 {resultPayoutPer100Label(item)}</em>
                <b className={recommendationProfit(item) >= 0 ? "positive" : "negative"}>
                  {item.hit ? formatYen(item.payout) : "払戻なし"}
                </b>
                <small>{publicStrategyLabel(item.strategy) || "AI推奨"} / 購入オッズ {resultOddsLabel(item)}</small>
              </article>
            );
          })
        ) : (
          <article className="empty">
            <span>{history.settled ? "的中券なし" : "未確定"}</span>
            <strong>{history.settled ? "回収率 0.0%" : "結果取得後に自動照合"}</strong>
            <em>{history.hitCount}/{history.betCount}点</em>
          </article>
        )}
      </div>
    </section>
  );
}

function RaceResultStrip({
  race,
  raceHistory,
  resultOrder,
}: {
  race: Race;
  raceHistory: HistoricalPrediction | null;
  resultOrder: { runner: Runner; position: number }[];
}) {
  if (resultOrder.length === 0) {
    return null;
  }
  return (
    <div className={raceHistory?.hit ? "race-result-strip hit" : "race-result-strip"}>
      {resultOrder.slice(0, 3).map(({ runner, position }) => (
        <article key={runner.number}>
          <b>{position}着</b>
          <strong>{runner.number}. {runner.name}</strong>
          <span>{runnerOddsMeta(runner, race)}</span>
        </article>
      ))}
    </div>
  );
}

function RacePayoutGrid({ race }: { race: Race }) {
  const payouts = [...racePayoutRows(race)].sort((a, b) => {
    const typeRank = officialPayoutRank(a.betType) - officialPayoutRank(b.betType);
    if (typeRank !== 0) return typeRank;
    return officialSelectionText(a).localeCompare(officialSelectionText(b), "ja");
  });
  if (payouts.length === 0) {
    return (
      <section className="race-payout-grid empty">
        <div className="section-heading compact">
          <h2>払戻一覧</h2>
          <span>公式払戻未取得</span>
        </div>
        <div className="empty-inline">払戻データを再取得中</div>
      </section>
    );
  }

  return (
    <section className="race-payout-grid">
      <div className="section-heading compact">
        <h2>払戻一覧</h2>
        <span>100円あたり</span>
      </div>
      <div className="official-payout-table" role="table" aria-label="払戻一覧">
        <div className="official-payout-row header" role="row">
          <span role="columnheader">式別</span>
          <span role="columnheader">組番</span>
          <span role="columnheader">払戻金</span>
          <span role="columnheader">人気</span>
        </div>
        {payouts.map((payout, index) => {
          const currentType = officialBetTypeLabel(payout.betType, race.market);
          const previousType = index > 0 ? officialBetTypeLabel(payouts[index - 1].betType, race.market) : "";
          return (
            <div className="official-payout-row" key={`${payout.betType}-${payout.selection}-${index}`} role="row">
              <span role="cell">{currentType === previousType ? "" : currentType}</span>
              <strong role="cell">{officialSelectionText(payout)}</strong>
              <b role="cell">{numberFormatter.format(Math.round(payout.payoutYen))}円</b>
              <em role="cell">{payout.popularity ? `${payout.popularity}人気` : "-"}</em>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PredictionResultDiff({
  race,
  raceHistory,
  projections,
}: {
  race: Race;
  raceHistory: HistoricalPrediction | null;
  projections: RunnerProjection[];
}) {
  const actualOrder = raceResultOrder(race);
  const runnerByNumber = new Map(race.runners.map((runner) => [runner.number, runner]));
  const positionByNumber = new Map(actualOrder.map(({ runner, position }) => [runner.number, position]));
  const savedPredictionRunners = Array.isArray(raceHistory?.prediction?.runners)
    ? [...raceHistory.prediction.runners]
        .sort((a, b) => safeNumber(b.score, 0) - safeNumber(a.score, 0))
        .slice(0, 5)
        .map((runner) => ({
          number: runner.number,
          name: runner.name,
          winProbability: safeNumber(runner.win_probability, 0),
          placeProbability: safeNumber(runner.place_probability, 0),
          score: safeNumber(runner.score, 0),
        }))
    : [];
  const projectedRows = projections.slice(0, 5).map((runner) => ({
    number: runner.number,
    name: runner.name,
    winProbability: runner.winProbability,
    placeProbability: runner.placeProbability,
    score: runner.score,
  }));
  const predictedRows = projectedRows.length > 0 ? projectedRows : savedPredictionRunners;
  const statusLabel = raceHistory
    ? raceHistory.generatedAfterResult
      ? "参考照合"
      : raceHistory.settled
        ? "照合済み"
        : "結果待ち"
    : "履歴なし";

  return (
    <section className="prediction-diff">
      <div className="section-heading compact">
        <h2>予想と結果</h2>
        <span>{statusLabel}</span>
      </div>

      <div className="diff-grid">
        <div className="diff-lane">
          <span>AI上位</span>
          {predictedRows.slice(0, 3).map((runner, index) => {
            const actualPosition = positionByNumber.get(runner.number);
            const sourceRunner = runnerByNumber.get(runner.number);
            return (
              <article className={actualPosition && actualPosition <= 3 ? "matched" : ""} key={`${runner.number}-${index}`}>
                <strong>{index + 1}. {runner.number} {runner.name}</strong>
                <em>勝率 {formatPercent(runner.winProbability)} / 3着内 {formatPercent(runner.placeProbability)}</em>
                <small>
                  {actualPosition ? `${actualPosition}着` : race.status === "finished" ? "圏外/未完走" : "結果待ち"}
                  {sourceRunner ? ` / ${runnerOddsMeta(sourceRunner, race)}` : ""}
                </small>
              </article>
            );
          })}
        </div>

        <div className="diff-lane">
          <span>実着順</span>
          {actualOrder.slice(0, 3).map(({ runner, position }) => {
            const predictedIndex = predictedRows.findIndex((item) => item.number === runner.number);
            return (
              <article className={predictedIndex >= 0 && predictedIndex <= 2 ? "matched" : ""} key={runner.number}>
                <strong>{position}着 {runner.number} {runner.name}</strong>
                <em>{predictedIndex >= 0 ? `AI ${predictedIndex + 1}位` : "AI上位外"}</em>
                <small>{runnerOddsMeta(runner, race)}</small>
              </article>
            );
          })}
          {actualOrder.length === 0 && <div className="empty-inline">結果待ち</div>}
        </div>
      </div>
    </section>
  );
}

function CalendarPanel({
  historyByRaceId,
  monthAnchor,
  monthCells,
  onDateSelect,
  onMonthChange,
  onRaceSelect,
  onVenueSelect,
  selectedDate,
  selectedDateRaces,
  selectedRaceId,
  selectedVenue,
  venueOptions,
  venueRaces,
}: {
  historyByRaceId: Map<string, HistoricalPrediction>;
  monthAnchor: string;
  monthCells: MonthCell[];
  onDateSelect: (date: string) => void;
  onMonthChange: (date: string) => void;
  onRaceSelect: (raceId: string) => void;
  onVenueSelect: (venue: string) => void;
  selectedDate: string;
  selectedDateRaces: Race[];
  selectedRaceId: string;
  selectedVenue: string;
  venueOptions: VenueOption[];
  venueRaces: Race[];
}) {
  const selectedCalendarRace =
    selectedDateRaces.find((item) => item.id === selectedRaceId) ?? venueRaces[0] ?? selectedDateRaces[0] ?? null;
  const selectedCalendarHistory = selectedCalendarRace ? historyByRaceId.get(selectedCalendarRace.id) ?? null : null;
  function openCalendarRace(raceId: string) {
    onRaceSelect(raceId);
    window.requestAnimationFrame(() => {
      document.getElementById("calendar-race-detail")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  return (
    <section className="tab-panel">
      <div className="section-heading">
        <h2>カレンダー</h2>
        <span>{monthTitle(monthAnchor)}</span>
      </div>

      <div className="month-controls">
        <button onClick={() => onMonthChange(addMonths(monthAnchor, -1))} type="button">前月</button>
        <strong>{monthTitle(monthAnchor)}</strong>
        <button onClick={() => onMonthChange(addMonths(monthAnchor, 1))} type="button">翌月</button>
      </div>

      <div className="month-grid" aria-label="月間カレンダー">
        {["月", "火", "水", "木", "金", "土", "日"].map((day) => (
          <span className="month-weekday" key={day}>{day}</span>
        ))}
        {monthCells.map((day) => (
          <button
            className={[
              "month-cell",
              selectedDate === day.date ? "active" : "",
              day.inMonth ? "" : "muted",
              day.isToday ? "today" : "",
              day.jraCount > 0 ? "has-jra" : "",
              day.narCount > 0 ? "has-nar" : "",
            ].filter(Boolean).join(" ")}
            key={day.date}
            onClick={() => onDateSelect(day.date)}
            type="button"
          >
            <strong>{Number(day.date.slice(-2))}</strong>
            <span>{day.raceCount > 0 ? day.raceCount : day.plannedCount > 0 ? "予定" : 0}</span>
            {(day.jraCount > 0 || day.narCount > 0) && (
              <small>
                {day.jraCount > 0 ? `中央${day.jraCount}` : ""}
                {day.jraCount > 0 && day.narCount > 0 ? " / " : ""}
                {day.narCount > 0 ? `地方${day.narCount}` : ""}
              </small>
            )}
            {day.hitCount > 0 && <em>🎯</em>}
          </button>
        ))}
      </div>

      <RacePicker
        onRaceSelect={openCalendarRace}
        onVenueSelect={onVenueSelect}
        races={venueRaces}
        historyByRaceId={historyByRaceId}
        selectedDate={selectedDate}
        selectedRaceId={selectedRaceId}
        selectedVenue={selectedVenue}
        venues={venueOptions}
      />

      {selectedCalendarRace && (
        <CalendarRaceDetail race={selectedCalendarRace} raceHistory={selectedCalendarHistory} />
      )}

      {!selectedCalendarRace && (
        <div className="calendar-compact-note">
          {JRA_FUTURE_SCHEDULE[selectedDate] ? (
            <>
              <strong>中央開催予定</strong>
              <span>{JRA_FUTURE_SCHEDULE[selectedDate].venues.join("・")}</span>
              <em>{JRA_FUTURE_SCHEDULE[selectedDate].gradeRaces?.join(" / ") || "出馬表取得後に自動反映"}</em>
            </>
          ) : (
            <span>対象レースなし</span>
          )}
        </div>
      )}
    </section>
  );
}

function CalendarRaceDetail({
  race,
  raceHistory,
}: {
  race: Race;
  raceHistory: HistoricalPrediction | null;
}) {
  const projections = useMemo(() => {
    const merged = raceHistory?.prediction ? mergeApiProjections(raceHistory.prediction, race) : null;
    return merged ?? buildRaceOnlyProjections(race);
  }, [race, raceHistory]);
  const resultOrder = raceResultOrder(race);
  const isFinished = race.status === "finished";

  return (
    <section className={`calendar-race-detail ${marketClass(race.market)}`} id="calendar-race-detail">
      <div className="section-heading">
        <h2>{displayRaceTitle(race)}</h2>
        <span>{publicMarketLabel(race.market)} / {raceStartLabel(race)}</span>
      </div>
      <div className="calendar-detail-meta">
        <span>{race.date}</span>
        <strong>{race.course}</strong>
        <em>{verificationLabel(race)} / 実データ</em>
      </div>
      <RaceInfoChips race={race} />
      {isFinished ? (
        <>
          <RaceResultStrip race={race} resultOrder={resultOrder} raceHistory={raceHistory} />
          <RacePayoutGrid race={race} />
          {raceHistory && <HitPayoutCard history={raceHistory} />}
          <PredictionResultDiff race={race} raceHistory={raceHistory} projections={projections} />
        </>
      ) : (
        <>
          <PredictionOrderCard projections={projections} race={race} />
          <div className="result-strip">
            <strong>出馬表取得済み</strong>
            <span>発走前の自動予想対象</span>
            <span>{race.runners.length}頭</span>
          </div>
        </>
      )}
      <section className="runner-table-card">
        <div className="section-heading compact">
          <h2>出走馬</h2>
          <span>{race.course}</span>
        </div>
        <RunnerTable projections={projections} race={race} />
      </section>
    </section>
  );
}

function ResultsPanel({
  history,
  historySummary,
  onRaceSelect,
  todayDate,
}: {
  history: HistoricalPrediction[];
  historySummary: PublicHistorySummary;
  onRaceSelect: (raceId: string) => void;
  todayDate: string;
}) {
  const settledHistory = history.filter((item) => item.settled);
  const officialSettledHistory = settledHistory.filter((item) => !item.generatedAfterResult);
  const displayHistory = officialSettledHistory;
  const displayModeLabel = "実績";
  const todayAll = history.filter((item) => item.date === todayDate && !item.generatedAfterResult);
  const todayOfficialSettled = officialSettledHistory.filter((item) => item.date === todayDate);
  const todayDisplaySettled = todayOfficialSettled;
  const todaySummary = summarizeHistory(todayDisplaySettled);
  const waitingToday = todayAll.filter((item) => !item.settled).length;
  const daySummary = Array.from(
    displayHistory.reduce((map, item) => {
      const current = map.get(item.date) ?? { date: item.date, total: 0, hits: 0, stake: 0, payout: 0 };
      current.total += 1;
      current.hits += item.hit ? 1 : 0;
      current.stake += item.stake;
      current.payout += item.payout;
      map.set(item.date, current);
      return map;
    }, new Map<string, { date: string; total: number; hits: number; stake: number; payout: number }>()),
  )
    .map(([, item]) => ({ ...item, roi: item.stake > 0 ? item.payout / item.stake : 0 }))
    .sort((a, b) => b.date.localeCompare(a.date))
    .filter((item) => item.date !== todayDate)
    .slice(0, 5);
  const recentRaces = displayHistory
    .filter((item) => item.date !== todayDate)
    .sort((a, b) => b.date.localeCompare(a.date) || b.start.localeCompare(a.start))
    .slice(0, 6);
  const generatedAfterResultCount = settledHistory.filter((item) => item.generatedAfterResult).length;
  const officialCount = settledHistory.length - generatedAfterResultCount;
  return (
    <section className="tab-panel">
      <div className="section-heading">
        <h2>実績</h2>
        <span>直近1ヶ月 / {displayModeLabel}</span>
      </div>

      <section className="results-hero">
        <div>
          <span>本日の成績</span>
          <h2>{todayDate}</h2>
          <p>
            {todaySummary.total > 0
              ? `確定 ${todaySummary.hits}/${todaySummary.total}R`
              : waitingToday > 0
                ? `結果待ち ${waitingToday}R`
                : "本日の確定結果は未反映"}
          </p>
        </div>
        <strong>{todaySummary.total > 0 ? formatPercent(todaySummary.roi, 1) : "-"}</strong>
        <div className="results-hero-metrics">
          <span>回収率 {todaySummary.total > 0 ? formatPercent(todaySummary.roi, 1) : "-"}</span>
          <span className={todaySummary.payout - todaySummary.stake >= 0 ? "positive" : "negative"}>
            損益率 {todaySummary.total > 0 ? formatSignedPercent(safeRatio(todaySummary.payout - todaySummary.stake, todaySummary.stake), 1) : "-"}
          </span>
          <span>的中率 {todaySummary.total > 0 ? formatPercent(todaySummary.hitRate, 0) : "-"}</span>
          <span>対象 {todaySummary.total}R</span>
        </div>
      </section>

      {todayAll.length > 0 && (
        <div className="result-race-list compact">
          {todayAll.slice(0, 6).map((item) => (
            <button
              className={`${item.hit ? "hit" : ""} ${marketClass(item.market)}`}
              key={item.id}
              onClick={() => onRaceSelect(item.id)}
              type="button"
            >
              <span>{publicMarketLabel(item.market)} / {item.settled ? item.result : "結果待ち"}</span>
              <strong>{displayHistoryTitle(item)}</strong>
              <em>{item.settled ? resultOutcomeText(item) : item.topTicket}</em>
            </button>
          ))}
        </div>
      )}

      <div className="result-note-strip">
        <strong>集計ルール</strong>
        <span>実績 {numberFormatter.format(officialCount)}R / 累計 {historySummary.total > 0 ? formatPercent(historySummary.roi, 1) : "-"}</span>
        <span>参考データ {numberFormatter.format(generatedAfterResultCount)}Rは集計外</span>
      </div>

      <div className="result-day-grid">
        {daySummary.map((item) => (
          <article className={item.hits > 0 ? "hit" : ""} key={item.date}>
            <strong>{item.date.slice(5)}</strong>
            <span>{item.hits}/{item.total}R</span>
            <b>{formatPercent(item.roi, 0)}</b>
          </article>
        ))}
      </div>

      <div className="section-heading compact">
        <h2>直近レース</h2>
        <span>詳細へ移動</span>
      </div>
      <div className="result-race-list">
        {recentRaces.map((item) => (
          <button
            className={`${item.hit ? "hit" : ""} ${marketClass(item.market)}`}
            key={item.id}
            onClick={() => onRaceSelect(item.id)}
            type="button"
          >
            <span>{item.date.slice(5)} / {publicMarketLabel(item.market)} / {item.generatedAfterResult ? "参考" : "実績"}</span>
            <strong>{item.hit ? "🎯 " : ""}{displayHistoryTitle(item)}</strong>
            <em>{resultOutcomeText(item)}</em>
          </button>
        ))}
        {settledHistory.length === 0 && <div className="empty-state">保存済み予想はまだありません</div>}
      </div>
    </section>
  );
}

function OtherAppsPanel() {
  return (
    <section className="tab-panel other-apps-panel">
      <div className="section-heading">
        <h2>他のアプリを見る</h2>
        <a href="https://agoringang.com/#apps">一覧</a>
      </div>
      <div className="app-links">
        {appLinks.map((app) => (
          <a className="app-link" href={app.href} key={app.name}>
            <AppIcon icon={app.icon} />
            <div>
              <strong>{app.name}</strong>
              <small>{app.label}</small>
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

function BetTypeGuide() {
  return (
    <section className="tab-panel bet-guide-panel">
      <div className="section-heading compact">
        <h2>賭け方ガイド</h2>
        <span>券種と代表的な買い方</span>
      </div>
      <div className="bet-guide-grid">
        {PUBLIC_BET_TYPE_GUIDES.map((guide) => (
          <article key={guide.id}>
            <strong>{guide.label}</strong>
            <span>{guide.summary}</span>
            <em>{guide.method}</em>
          </article>
        ))}
      </div>
    </section>
  );
}

function AppIcon({ icon }: { icon: AppIconId }) {
  if (icon === "portfolio") {
    return (
      <span className="app-icon portfolio" aria-hidden="true">
        <span className="portfolio-grid-large">
          <i />
          <i />
          <i />
          <i />
        </span>
      </span>
    );
  }

  return (
    <span className={`app-icon ${icon}`} aria-hidden="true">
      <span className="icon-gloss" />
      <span className="icon-light" />
      {icon === "waliwali" && (
        <span className="waliwali-shape">
          <span className="wali-card first" />
          <span className="wali-card second" />
          <span className="wali-yen">¥</span>
        </span>
      )}
      {icon === "keisya" && (
        <span className="keisya-shape">
          <span className="bar low" />
          <span className="bar mid" />
          <span className="bar high" />
          <span className="ring" />
        </span>
      )}
      {icon === "hikaku" && (
        <span className="hikaku-shape">
          <span className="panel large" />
          <span className="panel side" />
          <span className="panel bottom" />
          <span className="line line-1" />
          <span className="line line-2" />
          <span className="line line-3" />
          <span className="line line-4" />
          <span className="line line-5" />
          <span className="line line-6" />
          <span className="line line-7" />
        </span>
      )}
    </span>
  );
}

function TabIcon({ icon }: { icon: TabIconId }) {
  const common = {
    width: 19,
    height: 19,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (icon === "today") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="7" />
        <circle cx="12" cy="12" r="2.4" />
        <path d="M12 3v3" />
        <path d="M12 18v3" />
        <path d="M3 12h3" />
        <path d="M18 12h3" />
      </svg>
    );
  }
  if (icon === "calendar") {
    return (
      <svg {...common}>
        <path d="M7 3v3" />
        <path d="M17 3v3" />
        <rect x="4" y="5" width="16" height="16" rx="4" />
        <path d="M4 10h16" />
        <path d="M8 14h.01" />
        <path d="M12 14h.01" />
        <path d="M16 14h.01" />
        <path d="M8 18h.01" />
        <path d="M12 18h.01" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M4 19V5" />
      <path d="M4 19h17" />
      <rect x="7" y="11" width="3" height="5" rx="1" />
      <rect x="12" y="7" width="3" height="9" rx="1" />
      <rect x="17" y="4" width="3" height="12" rx="1" />
    </svg>
  );
}

function TicketLegs({ legs }: { legs: TicketLeg[] }) {
  return (
    <div className="ticket-legs">
      {legs.map((leg) => (
        <div className="ticket-leg" key={leg.label}>
          <span>{leg.label}</span>
          <div>
            {leg.numbers.map((number) => (
              <b key={`${leg.label}-${number}`}>{number}</b>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function RunnerTable({ projections, race }: { projections: RunnerProjection[]; race: Race }) {
  const defaultSort: RunnerSortKey = race.status === "finished" ? "result" : "prediction";
  const oddsReady = raceHasUsableWinOdds(race);
  const [sortKey, setSortKey] = useState<RunnerSortKey>(defaultSort);
  useEffect(() => {
    setSortKey(defaultSort);
  }, [defaultSort, race.id]);
  const sortedProjections = useMemo(() => {
    return [...projections].sort((a, b) => {
      if (sortKey === "number") {
        return a.number - b.number;
      }
      if (sortKey === "odds") {
        const oddsA = hasRunnerWinOdds(a) ? a.odds : 9999;
        const oddsB = hasRunnerWinOdds(b) ? b.odds : 9999;
        return oddsA - oddsB || a.number - b.number;
      }
      if (sortKey === "result") {
        return (finishPosition(a) ?? 999) - (finishPosition(b) ?? 999) || a.number - b.number;
      }
      return (
        predictionDisplayScore(b, race) - predictionDisplayScore(a, race) ||
        b.winProbability - a.winProbability ||
        (hasRunnerWinOdds(a) ? a.odds : 9999) - (hasRunnerWinOdds(b) ? b.odds : 9999)
      );
    });
  }, [projections, race, sortKey]);

  return (
    <>
      <div className="runner-sort" role="group" aria-label="出走馬の並び替え">
        {[
          ["prediction", "AI評価順"],
          ["number", "馬番順"],
          ["odds", "オッズ順"],
          ["result", "着順"],
        ].map(([key, label]) => (
          <button
            className={sortKey === key ? "active" : ""}
            key={key}
            onClick={() => setSortKey(key as RunnerSortKey)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      <div className="runner-table-wrap">
        <table className="runner-table">
          <thead>
            <tr>
              <th>印</th>
              <th>馬</th>
              <th>オッズ</th>
              <th>AI評価</th>
              <th>状態</th>
            </tr>
          </thead>
          <tbody>
            {sortedProjections.map((runner, index) => {
            const horseWeight = runnerWeightLabel(runner);
            const profile = runnerProfileLabel(runner);
            const staff = [runner.jockey ? `騎 ${runner.jockey}` : undefined, runner.trainer ? `厩 ${runner.trainer}` : undefined]
              .filter(Boolean)
              .join(" / ");
            const result = finishPosition(runner);
            const popularity = runnerPopularity(runner, race);
            const predictionRank = projections.findIndex((item) => item.number === runner.number) + 1;

            return (
              <tr className={result && result <= 3 ? "placed" : ""} key={runner.number}>
                <td>
                  <b>{sortKey === "prediction" ? index + 1 : predictionRank || index + 1}</b>
                  {result && <em>{result}着</em>}
                </td>
                <td>
                  <strong>{runner.number}. {runner.name}</strong>
                  <span>{staff || runner.jockey}</span>
                  <span className="runner-condition-inline">{profile} / {horseWeight}</span>
                </td>
                <td>
                  <strong>{hasRunnerWinOdds(runner) ? `単 ${runner.odds.toFixed(1)}倍` : "単勝 未取得"}</strong>
                  <span>{runner.placeOdds ? `複 ${runner.placeOdds.toFixed(1)}倍` : "複 未取得"}</span>
                  <span>{popularity ? `${popularity}人気` : "人気不明"}</span>
                </td>
                <td>
                  {oddsReady ? (
                    <>
                      <strong>AI {displayAiIndex(runner, race)}</strong>
                      <span>勝 {formatPercent(runner.winProbability)} / 3内 {formatPercent(runner.placeProbability)}</span>
                    </>
                  ) : (
                    <>
                      <strong>評価待ち</strong>
                      <span>オッズ公開後に自動更新</span>
                    </>
                  )}
                </td>
                <td>
                  <strong>{profile}</strong>
                  <span>{horseWeight}</span>
                </td>
              </tr>
            );
          })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function Value({ label, value, tone }: { label: string; value: string; tone?: "positive" | "negative" }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}
