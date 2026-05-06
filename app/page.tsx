"use client";

import { useEffect, useMemo, useState } from "react";

type Market = "JRA" | "NAR";
type ViewTab = "predict" | "calendar" | "results";
type AppIconId = "waliwali" | "keisya" | "hikaku" | "portfolio";

type Runner = {
  number: number;
  gate?: number;
  name: string;
  jockey: string;
  odds: number;
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
  sire?: string;
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
  status: "card" | "odds" | "watch" | "finished";
  officialNote?: string;
  source?: string;
  sourceUrl?: string;
  sourceCheckedAt?: string;
  verificationStatus?: "verified" | "stale" | "unverified";
  runners: Runner[];
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

type CalendarDay = {
  date: string;
  label: string;
  day: string;
};

type MonthCell = CalendarDay & {
  inMonth: boolean;
  raceCount: number;
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
};

type ApiState = "loading" | "ready" | "empty" | "fallback";

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

const races: Race[] = [
  {
    id: "tokyo-20260506-11",
    date: "2026-05-06",
    day: "水",
    start: "15:45",
    venue: "東京",
    title: "東京11R AI予測対象",
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
    title: "園田10R 地方拡張テスト",
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

const predictionHistory: HistoricalPrediction[] = [
  {
    id: "tokyo-finished-1",
    date: "2026-05-04",
    start: "確定",
    venue: "東京",
    title: "東京 過去予想",
    course: "芝 / 結果反映済み",
    market: "JRA",
    topTicket: "単勝・複勝ポートフォリオ",
    result: "的中あり",
    roi: 1.18,
    hitRate: 0.5,
    stake: 10000,
    payout: 11800,
    settled: true,
    hit: true,
    hitCount: 2,
    betCount: 4,
  },
  {
    id: "kyoto-finished-1",
    date: "2026-05-03",
    start: "確定",
    venue: "京都",
    title: "京都 過去予想",
    course: "ダート / 結果反映済み",
    market: "JRA",
    topTicket: "ワイド1頭軸流し",
    result: "回収率100%超",
    roi: 1.07,
    hitRate: 0.4,
    stake: 7500,
    payout: 8025,
    settled: true,
    hit: true,
    hitCount: 1,
    betCount: 3,
  },
];

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
    type: "複勝",
    selection: (top) => `${top[0].number}`,
    legs: (top) => [{ label: "馬番", numbers: [top[0].number] }],
    method: "単票",
    tickets: () => 1,
    risk: 16,
    probability: 0.62,
    odds: 1.9,
    model: "Place",
  },
  {
    type: "ワイド",
    selection: (top) => `軸 ${top[0].number} / 相手 ${runnerNumbers(top, 1, 5)}`,
    legs: (top) => [
      { label: "軸", numbers: [top[0].number] },
      { label: "相手", numbers: runnerNumberList(top, 1, 5) },
    ],
    method: "1頭軸流し",
    tickets: (top) => Math.max(top.length - 1, 0),
    risk: 30,
    probability: 0.43,
    odds: 2.6,
    model: "Pair",
  },
  {
    type: "単勝",
    selection: (top) => `${top[0].number}`,
    legs: (top) => [{ label: "馬番", numbers: [top[0].number] }],
    method: "単票",
    tickets: () => 1,
    risk: 46,
    probability: 0.19,
    odds: 5.6,
    model: "Win",
  },
  {
    type: "馬連",
    selection: (top) => `軸 ${top[0].number} / 相手 ${runnerNumbers(top, 1, 5)}`,
    legs: (top) => [
      { label: "軸", numbers: [top[0].number] },
      { label: "相手", numbers: runnerNumberList(top, 1, 5) },
    ],
    method: "1頭軸流し",
    tickets: (top) => Math.max(top.length - 1, 0),
    risk: 56,
    probability: 0.24,
    odds: 3.8,
    model: "Pair",
  },
  {
    type: "馬単",
    selection: (top) => `1着 ${top[0].number} / 2着 ${runnerNumbers(top, 1, 5)}`,
    legs: (top) => [
      { label: "1着", numbers: [top[0].number] },
      { label: "2着", numbers: runnerNumberList(top, 1, 5) },
    ],
    method: "1着軸流し",
    tickets: (top) => Math.max(top.length - 1, 0),
    risk: 66,
    probability: 0.16,
    odds: 6.8,
    model: "Order",
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
    model: "EV",
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
    model: "EV",
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
    model: "EV",
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
    model: "EV",
  },
];

const tabs: { id: ViewTab; label: string; icon: string }[] = [
  { id: "predict", label: "予想", icon: "◎" },
  { id: "calendar", label: "日程", icon: "□" },
  { id: "results", label: "実績", icon: "◇" },
];

const modelStack = [
  ["Win", "単勝"],
  ["Place", "複勝"],
  ["Pair", "馬連/ワイド"],
  ["EV", "3連系"],
  ["Odds", "直前"],
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

function formatPercent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatYen(value: number) {
  return yenFormatter.format(Math.round(value));
}

function apiBaseUrl() {
  const configured =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "/api";
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
  const text = String(value ?? "").trim();
  return text.length > 0 ? text : undefined;
}

const jraVenues = new Set(["札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉"]);

function normalizeApiRace(item: any): Race {
  const runners = Array.isArray(item.runners) ? item.runners : [];
  const normalizedRunners = runners.map((runner: any, index: number) => {
    const odds = Math.max(safeNumber(runner.odds ?? runner.market_odds, 1.1), 1.1);
    const rating = safeNumber(runner.rating, 64);
    const number = safeNumber(runner.number, index + 1);
    return {
      number,
      gate: optionalNumber(runner.gate),
      name: String(runner.name ?? `${index + 1}番`),
      jockey: String(runner.jockey ?? "-"),
      odds,
      baseWin: Math.min(0.65, Math.max(0.004, 1 / odds)),
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
      sire: optionalText(runner.sire),
      damSire: optionalText(runner.damSire ?? runner.dam_sire),
      tags: Array.isArray(runner.tags) ? runner.tags.map(String) : undefined,
    };
  });
  const venue = String(item.venue ?? "未設定");
  const market =
    item.market === "NAR" || item.grade === "NAR" || !jraVenues.has(venue) ? "NAR" : "JRA";
  const status = ["card", "odds", "watch", "finished"].includes(item.status)
    ? item.status
    : "card";

  return {
    id: String(item.id),
    date: String(item.date ?? "2026-05-06"),
    day: String(item.day ?? ""),
    start: String(item.start ?? "未取得"),
    venue,
    title: String(item.title ?? item.raceNo ?? item.id),
    course: String(item.course ?? "条件未取得"),
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
      const raceId = String(entry.race_id ?? `${date}-${index}`);
      const stake = safeNumber(prediction.total_stake, 0);
      const payout = safeNumber(result.payout, safeNumber(prediction.expected_return, 0));
      const settled = Boolean(result.settled);
      const hit = Boolean(result.hit);
      const hitCount = safeNumber(result.hit_count, hit ? 1 : 0);
      const betCount = safeNumber(result.bet_count, Array.isArray(prediction.recommendations) ? prediction.recommendations.length : 0);
      return {
        id: raceId,
        date: String(entry.race_date ?? date),
        start: settled ? "確定" : "保存",
        venue: String(entry.venue ?? raceId.split("-")[0] ?? "履歴"),
        title: String(entry.title ?? raceId),
        course: String(entry.course ?? "予測履歴"),
        market: entry.market === "NAR" ? "NAR" as Market : "JRA" as Market,
        topTicket: String(
          prediction.recommendations?.[0]?.selection ??
            prediction.top_ticket ??
            prediction.warning ??
            "AI予想",
        ),
        result: String(result.message ?? (settled ? "結果反映" : "結果待ち")),
        roi: stake > 0 ? payout / stake : safeNumber(prediction.expected_roi, 0),
        hitRate: betCount > 0 ? hitCount / betCount : safeNumber(prediction.hit_rate, 0),
        stake,
        payout,
        settled,
        hit,
        hitCount,
        betCount,
      };
    });
  });
}

function buildRaceRequest(race: Race, riskLevel: number, bankroll: number) {
  const oddsRank = new Map(
    [...race.runners]
      .sort((a, b) => a.odds - b.odds)
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
    min_edge: riskLevel < 34 ? 0.02 : riskLevel < 67 ? 0.06 : 0.1,
    min_probability: riskLevel < 34 ? 0.08 : riskLevel < 67 ? 0.04 : 0.015,
    max_candidate_odds: riskLevel < 34 ? 18 : riskLevel < 67 ? 45 : 120,
    max_edge: 1.4,
    max_exposure: riskLevel < 34 ? 0.012 : riskLevel < 67 ? 0.02 : 0.035,
    runners: race.runners.map((runner) => {
      const odds = Math.max(runner.odds, 1.1);
      const form = Math.max(1, Math.min(100, runner.form));
      return {
        id: `${race.id}-${runner.number}`,
        gate: Math.max(1, Math.min(8, Math.round(runner.gate ?? Math.ceil(runner.number / 2)))),
        number: runner.number,
        name: runner.name,
        market_odds: odds,
        place_odds: Math.max(1.1, odds * 0.32),
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
        sire: runner.sire,
        dam_sire: runner.damSire,
        odds_rank: oddsRank.get(runner.number),
        odds_delta: runner.drift / 100,
      };
    }),
  };
}

const betTypeLabels: Record<string, string> = {
  win: "単勝",
  place: "複勝",
  support: "見送り",
  bracket_quinella: "枠連",
  quinella: "馬連",
  wide: "ワイド",
  exacta: "馬単",
  trio: "3連複",
  trifecta: "3連単",
  win5: "WIN5",
};

function modelLabelForBetType(type: string) {
  if (type === "win") return "Win";
  if (type === "place") return "Place";
  if (["wide", "quinella", "exacta", "bracket_quinella"].includes(type)) return "Pair";
  return "EV";
}

function apiRecommendationToTicket(recommendation: ApiBetRecommendation): TicketProjection {
  const tickets = Math.max(safeNumber(recommendation.tickets, 1), 1);
  const stake = safeNumber(recommendation.stake, 0);
  const probability = safeNumber(recommendation.probability, 0);
  const odds = safeNumber(recommendation.odds, 1);
  return {
    type: betTypeLabels[recommendation.bet_type] ?? recommendation.bet_type,
    method: recommendation.strategy || recommendation.note || "AI",
    probability,
    odds,
    risk: recommendation.bet_type === "trifecta" ? 90 : recommendation.bet_type === "trio" ? 74 : 48,
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
  return prediction.runners
    .map((runner) => {
      const source = sourceByNumber.get(runner.number);
      return {
        ...source,
        number: runner.number,
        name: runner.name,
        jockey: source?.jockey ?? "-",
        odds: safeNumber(runner.market_odds, source?.odds ?? 1.1),
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
    })
    .sort((a, b) => b.score - a.score);
}

function roundStake(value: number) {
  return Math.max(100, Math.round(value / 100) * 100);
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
  const raceCountByDate = new Map<string, number>();
  const historyCountByDate = new Map<string, number>();
  const hitCountByDate = new Map<string, number>();

  races.forEach((race) => {
    raceCountByDate.set(race.date, (raceCountByDate.get(race.date) ?? 0) + 1);
  });
  history.forEach((item) => {
    historyCountByDate.set(item.date, (historyCountByDate.get(item.date) ?? 0) + 1);
    if (item.hit) {
      hitCountByDate.set(item.date, (hitCountByDate.get(item.date) ?? 0) + 1);
    }
  });

  return Array.from({ length: 42 }, (_, index) => {
    const date = addDays(gridStart, index);
    return {
      date,
      label: calendarLabel(date),
      day: weekdayFormatter.format(dateAtJst(date)).replace("曜日", ""),
      inMonth: date.slice(0, 7) === start.slice(0, 7),
      raceCount: raceCountByDate.get(date) ?? 0,
      historyCount: historyCountByDate.get(date) ?? 0,
      hitCount: hitCountByDate.get(date) ?? 0,
      isToday: date === today,
    };
  });
}

function verificationLabel(race: Race | null) {
  if (!race) return "未取得";
  if (race.verificationStatus === "verified") return "検証済み";
  if (race.verificationStatus === "stale") return "要更新";
  return "未検証";
}

function sourceLabel(race: Race | null) {
  if (!race) return "公式情報未接続";
  if (race.source) return race.source;
  return race.verificationStatus === "verified" ? "確認済みデータ" : "情報源未設定";
}

function displayRaceTitle(race: Race) {
  return race.title.includes(race.venue) ? race.title : `${race.venue} ${race.title}`;
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<ViewTab>("predict");
  const [selectedRaceId, setSelectedRaceId] = useState("");
  const [selectedDate, setSelectedDate] = useState(todayAtJst());
  const [selectedVenue, setSelectedVenue] = useState("");
  const [monthAnchor, setMonthAnchor] = useState(monthStart(todayAtJst()));
  const [riskLevel, setRiskLevel] = useState(48);
  const [bankroll, setBankroll] = useState(100000);
  const [apiRaces, setApiRaces] = useState<Race[]>([]);
  const [apiHistory, setApiHistory] = useState<HistoricalPrediction[]>([]);
  const [apiState, setApiState] = useState<ApiState>("loading");
  const [apiPrediction, setApiPrediction] = useState<ApiRacePrediction | null>(null);

  const demoRacesEnabled = process.env.NEXT_PUBLIC_ENABLE_DEMO_RACES === "1";
  const availableRaces = apiRaces.length > 0 ? apiRaces : demoRacesEnabled ? races : [];
  const availableHistory = apiHistory.length > 0 ? apiHistory : demoRacesEnabled ? predictionHistory : [];
  const race = availableRaces.find((item) => item.id === selectedRaceId) ?? availableRaces[0] ?? null;
  const selectedDateRaces = availableRaces.filter((item) => item.date === selectedDate);
  const selectedDateHistory = availableHistory.filter((item) => item.date === selectedDate);
  const venueOptions = useMemo<VenueOption[]>(() => {
    const counts = new Map<string, number>();
    selectedDateRaces.forEach((item) => counts.set(item.venue, (counts.get(item.venue) ?? 0) + 1));
    return Array.from(counts.entries())
      .map(([venue, count]) => ({ venue, count }))
      .sort((a, b) => a.venue.localeCompare(b.venue, "ja"));
  }, [selectedDateRaces]);
  const selectedVenueRaces = useMemo(() => {
    const venue = selectedVenue || venueOptions[0]?.venue;
    return selectedDateRaces.filter((item) => item.venue === venue).sort(sortRaceCards);
  }, [selectedDateRaces, selectedVenue, venueOptions]);
  const monthCells = useMemo(
    () => buildMonthCells(monthAnchor, availableRaces, availableHistory, todayAtJst()),
    [availableHistory, availableRaces, monthAnchor],
  );
  const raceHistory = race ? availableHistory.find((item) => item.id === race.id) ?? null : null;
  const historySummary = useMemo(() => {
    const settled = availableHistory.filter((item) => item.settled);
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
  }, [availableHistory]);
  const activeBankroll = Number.isFinite(bankroll) ? Math.max(bankroll, 1000) : 100000;
  const riskRatio = riskLevel / 100;

  useEffect(() => {
    let cancelled = false;
    async function loadInitialData() {
      const centerDate = todayAtJst();
      const startDate = addDays(centerDate, -30);
      const endDate = addDays(centerDate, 31);
      try {
        const [raceResponse, historyResponse] = await Promise.all([
          fetch(`${apiBaseUrl()}/races?start_date=${startDate}&end_date=${endDate}`),
          fetch(`${apiBaseUrl()}/history?start_date=${startDate}&end_date=${centerDate}`),
        ]);
        if (!raceResponse.ok) {
          throw new Error(`races ${raceResponse.status}`);
        }
        const racePayload = await raceResponse.json();
        const historyPayload = historyResponse.ok ? await historyResponse.json() : {};
        const nextRaces = Array.isArray(racePayload)
          ? racePayload.map(normalizeApiRace).filter((item) => item.runners.length > 0).sort(sortRaceCards)
          : [];
        if (cancelled) {
          return;
        }
        setApiHistory(normalizeApiHistory(historyPayload));
        if (nextRaces.length === 0) {
          setApiRaces([]);
          setSelectedRaceId("");
          setSelectedDate(centerDate);
          setApiState("empty");
          return;
        }
        setApiRaces(nextRaces);
        const defaultRace = pickDefaultRace(nextRaces, centerDate) ?? nextRaces[0];
        setSelectedRaceId((current) =>
          nextRaces.some((item) => item.id === current) ? current : defaultRace.id,
        );
        setSelectedDate((current) =>
          nextRaces.some((item) => item.date === current) ? current : defaultRace.date,
        );
        setSelectedVenue(defaultRace.venue);
        setMonthAnchor(monthStart(defaultRace.date));
        setApiState("ready");
      } catch {
        if (!cancelled) {
          setApiState("fallback");
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
    async function loadPrediction() {
      if (!race || race.runners.length < 2) {
        setApiPrediction(null);
        return;
      }
      try {
        const response = await fetch(`${apiBaseUrl()}/predict`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(buildRaceRequest(race, riskLevel, activeBankroll)),
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
  }, [activeBankroll, race, riskLevel]);

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
    if (!race) {
      return [];
    }
    const raw = race.runners.map((runner) => {
      const valueLift = runner.odds >= 8 ? riskRatio * 0.032 : 0;
      const oddsMoveLift = runner.drift < 0 ? Math.abs(runner.drift) * 0.0012 : -runner.drift * 0.0008;
      const score = runner.baseWin + valueLift + oddsMoveLift + runner.form / 2400;
      return { runner, score };
    });
    const total = raw.reduce((sum, item) => sum + item.score, 0);

    return raw
      .map(({ runner, score }) => {
        const winProbability = score / total;
        const placeProbability = Math.min(0.82, winProbability * 2.55 + runner.form / 820);
        const fairOdds = 1 / Math.max(winProbability, 0.001);
        const edge = winProbability * runner.odds - 1;
        return {
          ...runner,
          winProbability,
          placeProbability,
          fairOdds,
          edge,
          score: winProbability * 72 + placeProbability * 18 + Math.max(edge, -0.2) * 10,
        };
      })
      .sort((a, b) => b.score - a.score);
  }, [race, riskRatio]);

  const apiProjections = useMemo(
    () => (race ? mergeApiProjections(apiPrediction, race) : null),
    [apiPrediction, race],
  );
  const projections = apiProjections ?? fallbackProjections;

  const fallbackTickets = useMemo<TicketProjection[]>(() => {
    if (projections.length === 0) {
      return [];
    }
    const projected = ticketTemplates
      .filter((ticket) => Math.abs(ticket.risk - riskLevel) <= 40 || ticket.risk <= riskLevel + 12)
      .map((ticket) => {
        const top = projections.slice(0, 6);
        const edge = ticket.probability * ticket.odds - 1 + (riskRatio - 0.45) * 0.08;
        const exposure = 0.006 + riskRatio * 0.027;
        const tickets = Math.max(ticket.tickets(top), 1);
        const rawStake = activeBankroll * exposure * Math.max(0.35, 1 + edge) * (ticket.risk / 100);
        const unitStake = roundStake(rawStake / tickets);
        const stake = unitStake * tickets;
        return {
          ...ticket,
          selection: ticket.selection(top),
          legs: ticket.legs(top),
          tickets,
          unitStake,
          edge,
          stake,
          expectedReturn: stake * ticket.odds * ticket.probability,
        };
      })
      .filter((ticket) => ticket.expectedReturn / ticket.stake >= 1);

    const score = (ticket: TicketProjection) => {
      const riskFit = 1 - Math.abs(ticket.risk - riskLevel) / 100;
      const hitWeight = (1 - riskRatio) * ticket.probability * 1.2;
      const returnWeight = riskRatio * Math.min(ticket.odds / 20, 1.4) * 0.35;
      return ticket.edge * 1.4 + riskFit + hitWeight + returnWeight;
    };
    const sorted = projected.sort((a, b) => score(b) - score(a));
    const anchors = ["複勝", "単勝"]
      .map((type) => sorted.find((ticket) => ticket.type === type))
      .filter((ticket): ticket is TicketProjection => Boolean(ticket));
    const anchorKeys = new Set(anchors.map((ticket) => `${ticket.type}-${ticket.selection}`));
    return [...anchors, ...sorted.filter((ticket) => !anchorKeys.has(`${ticket.type}-${ticket.selection}`))]
      .slice(0, riskLevel < 34 ? 4 : 5);
  }, [activeBankroll, projections, riskLevel, riskRatio]);

  const apiTickets = useMemo(() => {
    if (!race || !apiPrediction || apiPrediction.race_id !== race.id) {
      return [];
    }
    return apiPrediction.recommendations.map(apiRecommendationToTicket);
  }, [apiPrediction, race]);
  const tickets = apiTickets.length > 0 ? apiTickets : fallbackTickets;

  const totalStake = tickets.reduce((sum, ticket) => sum + ticket.stake, 0);
  const expectedReturn = tickets.reduce((sum, ticket) => sum + ticket.expectedReturn, 0);
  const expectedRoi = totalStake > 0 ? expectedReturn / totalStake : 0;
  const riskLabel = riskLevel < 34 ? "堅実" : riskLevel < 67 ? "標準" : "攻め";

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

  function selectDate(date: string) {
    setSelectedDate(date);
    setMonthAnchor(monthStart(date));
    const firstRace = availableRaces.filter((item) => item.date === date).sort(sortRaceCards)[0];
    if (firstRace) {
      setSelectedVenue(firstRace.venue);
      setSelectedRaceId(firstRace.id);
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

        <section className="race-status-card">
          <div className="race-status-main">
            <span>{race ? `${race.date} ${race.start}` : selectedDate}</span>
            <h1>{race ? displayRaceTitle(race) : "検証済みレース未取得"}</h1>
            <p>{race ? race.course : "CSV、DB、または取得元で照合できたレースだけ表示します"}</p>
            {race?.officialNote && <small className="source-note">{race.officialNote}</small>}
          </div>
          <div className="race-pills">
            <span>{race?.market ?? "DATA"}</span>
            <span className={race?.verificationStatus === "verified" ? "verified" : ""}>{verificationLabel(race)}</span>
            <span>{sourceLabel(race)}</span>
            <span>{race && apiPrediction?.race_id === race.id ? "実モデル" : apiState === "loading" ? "接続中" : "待機"}</span>
          </div>
        </section>

        <div className="desktop-tabs" role="tablist" aria-label="UMALAB tabs">
          {tabs.map((tab) => (
            <button
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? "active" : ""}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              role="tab"
              type="button"
            >
              <span aria-hidden="true">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === "predict" && race && (
          <PredictPanel
            activeBankroll={activeBankroll}
            bankroll={bankroll}
            expectedRoi={expectedRoi}
            onBankrollChange={setBankroll}
            onRaceSelect={(raceId) => selectRace(raceId)}
            onVenueSelect={setSelectedVenue}
            onRiskChange={setRiskLevel}
            apiState={apiPrediction?.race_id === race.id ? "ready" : apiState}
            projections={projections}
            race={race}
            raceHistory={raceHistory}
            riskLabel={riskLabel}
            riskLevel={riskLevel}
            selectedDate={selectedDate}
            selectedVenue={selectedVenue}
            tickets={tickets}
            totalStake={totalStake}
            venueOptions={venueOptions}
            venueRaces={selectedVenueRaces}
          />
        )}
        {activeTab === "predict" && !race && (
          <VerifiedDataEmptyState apiState={apiState} selectedDate={selectedDate} />
        )}

        {activeTab === "calendar" && (
          <CalendarPanel
            history={availableHistory}
            monthAnchor={monthAnchor}
            monthCells={monthCells}
            onDateSelect={selectDate}
            onMonthChange={setMonthAnchor}
            onRaceSelect={(raceId) => selectRace(raceId, "predict")}
            onVenueSelect={setSelectedVenue}
            races={availableRaces}
            selectedDate={selectedDate}
            selectedDateHistory={selectedDateHistory}
            selectedDateRaces={selectedDateRaces}
            selectedRaceId={selectedRaceId}
            selectedVenue={selectedVenue}
            venueOptions={venueOptions}
            venueRaces={selectedVenueRaces}
          />
        )}

        {activeTab === "results" && race && (
          <ResultsPanel history={availableHistory} historySummary={historySummary} projections={projections} race={race} />
        )}
        {activeTab === "results" && !race && (
          <VerifiedDataEmptyState apiState={apiState} selectedDate={selectedDate} />
        )}

        <OtherAppsPanel />
      </div>

      <nav className="bottom-tabs" aria-label="UMALAB navigation">
        {tabs.map((tab) => (
          <button
            className={activeTab === tab.id ? "active" : ""}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            type="button"
          >
            <span aria-hidden="true">{tab.icon}</span>
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
        : "検証済みレースなし";

  return (
    <section className="tab-panel">
      <div className="empty-state verified-empty">
        <strong>{label}</strong>
        <span>{selectedDate} 周辺の出馬表、結果、オッズを確認できるデータがまだありません。</span>
      </div>
    </section>
  );
}

function PredictPanel({
  activeBankroll,
  apiState,
  bankroll,
  expectedRoi,
  onBankrollChange,
  onRaceSelect,
  onVenueSelect,
  onRiskChange,
  projections,
  race,
  raceHistory,
  riskLabel,
  riskLevel,
  selectedDate,
  selectedVenue,
  tickets,
  totalStake,
  venueOptions,
  venueRaces,
}: {
  activeBankroll: number;
  apiState: ApiState;
  bankroll: number;
  expectedRoi: number;
  onBankrollChange: (value: number) => void;
  onRaceSelect: (raceId: string) => void;
  onVenueSelect: (venue: string) => void;
  onRiskChange: (value: number) => void;
  projections: RunnerProjection[];
  race: Race;
  raceHistory: HistoricalPrediction | null;
  riskLabel: string;
  riskLevel: number;
  selectedDate: string;
  selectedVenue: string;
  tickets: TicketProjection[];
  totalStake: number;
  venueOptions: VenueOption[];
  venueRaces: Race[];
}) {
  return (
    <section className="tab-panel">
      <div className="control-strip">
        <RacePicker
          onRaceSelect={onRaceSelect}
          onVenueSelect={onVenueSelect}
          races={venueRaces}
          selectedDate={selectedDate}
          selectedRaceId={race.id}
          selectedVenue={selectedVenue || race.venue}
          venues={venueOptions}
        />

        <div className="settings-grid">
          <label className="field-card">
            <span>軍資金</span>
            <input
              min={1000}
              onChange={(event) => onBankrollChange(Number(event.target.value))}
              step={1000}
              type="number"
              value={bankroll}
            />
          </label>
          <div className="field-card risk-card">
            <span>リスク {riskLabel} / {riskLevel}</span>
            <input
              max={100}
              min={0}
              onChange={(event) => onRiskChange(Number(event.target.value))}
              type="range"
              value={riskLevel}
            />
            <div className="risk-presets">
              {[
                ["堅実", 24],
                ["標準", 52],
                ["攻め", 84],
              ].map(([label, value]) => (
                <button
                  className={Math.abs(riskLevel - Number(value)) <= 14 ? "active" : ""}
                  key={label}
                  onClick={() => onRiskChange(Number(value))}
                  type="button"
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="summary-strip">
        <Metric label="候補" value={`${tickets.length}件`} />
        <Metric label="投資" value={formatYen(totalStake)} />
        <Metric label="期待ROI" value={formatPercent(expectedRoi, 1)} />
        <Metric label="露出" value={formatPercent(totalStake / activeBankroll, 2)} />
        <Metric label="モデル" value={apiState === "ready" ? "実API" : apiState === "loading" ? "接続中" : "試算"} />
      </div>

      {raceHistory && (
        <ResultStrip history={raceHistory} />
      )}

      <div className="section-heading">
        <h2>買い目</h2>
        <span>{race.grade}</span>
      </div>
      <div className="ticket-list">
        {tickets.map((ticket) => (
          <article key={`${ticket.type}-${ticket.selection}`}>
            <div className="ticket-name">
              <span>{ticket.type}</span>
              <strong>{ticket.method}</strong>
              <small>{ticket.model}</small>
            </div>
            <div className="ticket-body">
              <TicketLegs legs={ticket.legs} />
              <div className="ticket-meta">
                <span>{ticket.tickets}通り</span>
                <span>各{formatYen(ticket.unitStake)}</span>
                <strong>合計 {formatYen(ticket.stake)}</strong>
              </div>
              <div className="ticket-data">
                <Value label="的中" value={formatPercent(ticket.probability)} />
                <Value label="想定" value={ticket.odds.toFixed(1)} />
                <Value label="Edge" value={formatPercent(ticket.edge)} tone={ticket.edge >= 0 ? "positive" : "negative"} />
                <Value label="期待" value={formatYen(ticket.expectedReturn)} />
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="two-column">
        <section className="mini-card">
          <div className="section-heading compact">
            <h2>直前オッズ</h2>
            <span>watch</span>
          </div>
          <div className="alert-list">
            {projections.slice(0, 3).map((runner) => (
              <article key={runner.number}>
                <strong>{runner.number}. {runner.name}</strong>
                <span className={runner.drift < 0 ? "positive" : "negative"}>
                  {runner.drift < 0 ? "妙味" : "過熱"} {Math.abs(runner.drift).toFixed(1)}%
                </span>
              </article>
            ))}
          </div>
        </section>

        <section className="mini-card">
          <div className="section-heading compact">
            <h2>出走馬</h2>
            <span>{race.course}</span>
          </div>
          <RunnerList projections={projections} />
        </section>
      </div>
    </section>
  );
}

function RacePicker({
  onRaceSelect,
  onVenueSelect,
  races,
  selectedDate,
  selectedRaceId,
  selectedVenue,
  venues,
}: {
  onRaceSelect: (raceId: string) => void;
  onVenueSelect: (venue: string) => void;
  races: Race[];
  selectedDate: string;
  selectedRaceId: string;
  selectedVenue: string;
  venues: VenueOption[];
}) {
  return (
    <div className="race-picker">
      <div className="section-heading compact">
        <h2>{selectedDate}</h2>
        <span>{venues.reduce((sum, venue) => sum + venue.count, 0)}R</span>
      </div>
      <div className="venue-grid" aria-label="開催場">
        {venues.length > 0 ? (
          venues.map((venue) => (
            <button
              className={selectedVenue === venue.venue ? "active" : ""}
              key={venue.venue}
              onClick={() => onVenueSelect(venue.venue)}
              type="button"
            >
              <strong>{venue.venue}</strong>
              <span>{venue.count}R</span>
            </button>
          ))
        ) : (
          <div className="empty-inline">開催なし</div>
        )}
      </div>
      <div className="race-number-grid" aria-label="レース番号">
        {races.map((item) => (
          <button
            className={item.id === selectedRaceId ? "active" : ""}
            key={item.id}
            onClick={() => onRaceSelect(item.id)}
            type="button"
          >
            <strong>{raceNumberValue(item)}R</strong>
            <span>{item.start}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ResultStrip({ history }: { history: HistoricalPrediction }) {
  return (
    <div className={history.hit ? "result-strip hit" : "result-strip"}>
      <strong>{history.hit ? "🎯 的中" : history.settled ? "不的中" : "結果待ち"}</strong>
      <span>ROI {formatPercent(history.roi, 1)}</span>
      <span>{formatYen(history.payout)} / {formatYen(history.stake)}</span>
      <em>{history.hitCount}/{history.betCount} 点</em>
    </div>
  );
}

function CalendarPanel({
  history,
  monthAnchor,
  monthCells,
  onDateSelect,
  onMonthChange,
  onRaceSelect,
  onVenueSelect,
  races,
  selectedDate,
  selectedDateHistory,
  selectedDateRaces,
  selectedRaceId,
  selectedVenue,
  venueOptions,
  venueRaces,
}: {
  history: HistoricalPrediction[];
  monthAnchor: string;
  monthCells: MonthCell[];
  onDateSelect: (date: string) => void;
  onMonthChange: (date: string) => void;
  onRaceSelect: (raceId: string) => void;
  onVenueSelect: (venue: string) => void;
  races: Race[];
  selectedDate: string;
  selectedDateHistory: HistoricalPrediction[];
  selectedDateRaces: Race[];
  selectedRaceId: string;
  selectedVenue: string;
  venueOptions: VenueOption[];
  venueRaces: Race[];
}) {
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
            ].filter(Boolean).join(" ")}
            key={day.date}
            onClick={() => onDateSelect(day.date)}
            type="button"
          >
            <strong>{Number(day.date.slice(-2))}</strong>
            <span>{day.raceCount + day.historyCount}</span>
            {day.hitCount > 0 && <em>🎯</em>}
          </button>
        ))}
      </div>

      <RacePicker
        onRaceSelect={onRaceSelect}
        onVenueSelect={onVenueSelect}
        races={venueRaces}
        selectedDate={selectedDate}
        selectedRaceId={selectedRaceId}
        selectedVenue={selectedVenue}
        venues={venueOptions}
      />

      <div className="calendar-list">
        {selectedDateRaces.length + selectedDateHistory.length > 0 ? (
          <>
          {selectedDateRaces.map((item) => (
            <article className={item.id === selectedRaceId ? "active" : ""} key={item.id}>
              <div>
                <span>{item.start} / {item.market}</span>
                <strong>{item.venue} {item.title}</strong>
                <em>{item.course}</em>
              </div>
              <button onClick={() => onRaceSelect(item.id)} type="button">予想へ</button>
            </article>
          ))}
          {selectedDateHistory.map((item) => (
            <article className="history" key={item.id}>
              <div>
                <span>{item.start} / {item.market} / 予想履歴</span>
                <strong>{item.venue} {item.title}</strong>
                <em>{item.course}</em>
              </div>
              <div className="history-result">
                <span>{item.topTicket}</span>
                <strong>{item.hit ? "🎯 " : ""}{formatPercent(item.roi, 1)}</strong>
                <em>{item.result} / 的中 {formatPercent(item.hitRate, 0)}</em>
              </div>
            </article>
          ))}
          </>
        ) : (
          <div className="empty-state">対象レースなし</div>
        )}
      </div>
    </section>
  );
}

function ResultsPanel({
  history,
  historySummary,
  projections,
  race,
}: {
  history: HistoricalPrediction[];
  historySummary: {
    total: number;
    hits: number;
    stake: number;
    payout: number;
    roi: number;
    hitRate: number;
  };
  projections: RunnerProjection[];
  race: Race;
}) {
  return (
    <section className="tab-panel">
      <div className="section-heading">
        <h2>実績</h2>
        <span>直近1ヶ月</span>
      </div>
      <div className="summary-strip">
        <Metric label="回収率" value={formatPercent(historySummary.roi)} />
        <Metric label="的中率" value={formatPercent(historySummary.hitRate)} />
        <Metric label="対象R" value={numberFormatter.format(historySummary.total)} />
        <Metric label="払戻" value={formatYen(historySummary.payout)} />
      </div>

      <div className="history-list">
        {history.slice(0, 20).map((item) => (
          <article className={item.hit ? "hit" : ""} key={`${item.date}-${item.id}`}>
            <div>
              <span>{item.date} / {item.venue} / {item.market}</span>
              <strong>{item.hit ? "🎯 " : ""}{item.title}</strong>
              <em>{item.topTicket}</em>
            </div>
            <div>
              <strong>{formatPercent(item.roi, 1)}</strong>
              <span>{formatYen(item.payout)} / {formatYen(item.stake)}</span>
              <em>{item.result}</em>
            </div>
          </article>
        ))}
        {history.length === 0 && <div className="empty-state">保存済み予想はまだありません</div>}
      </div>

      <div className="two-column">
        <section className="mini-card">
          <div className="section-heading compact">
            <h2>モデル</h2>
            <span>{modelStack.length}</span>
          </div>
          <div className="model-list">
            {modelStack.map(([name, detail]) => (
              <article key={name}>
                <strong>{name}</strong>
                <span>{detail}</span>
              </article>
            ))}
          </div>
        </section>

        <section className="mini-card">
          <div className="section-heading compact">
            <h2>現在の順位</h2>
            <span>{race.venue}</span>
          </div>
          <RunnerList projections={projections.slice(0, 4)} />
        </section>
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

function RunnerList({ projections }: { projections: RunnerProjection[] }) {
  return (
    <div className="runner-list">
      {projections.map((runner, index) => {
        const horseWeight =
          runner.horseWeight !== undefined
            ? `馬体 ${runner.horseWeight}kg${
                runner.horseWeightDiff !== undefined
                  ? ` ${runner.horseWeightDiff >= 0 ? "+" : ""}${runner.horseWeightDiff}`
                  : ""
              }`
            : undefined;
        const profile = [
          runner.sex || runner.age ? `${runner.sex ?? ""}${runner.age ? `${runner.age}歳` : ""}` : undefined,
          runner.carriedWeight !== undefined ? `斤量 ${runner.carriedWeight.toFixed(1)}` : undefined,
          horseWeight,
          runner.runningStyle ? `脚質 ${runner.runningStyle}` : undefined,
        ].filter(Boolean);
        const staff = [runner.jockey ? `騎 ${runner.jockey}` : undefined, runner.trainer ? `厩 ${runner.trainer}` : undefined]
          .filter(Boolean)
          .join(" / ");
        const bloodline = [runner.sire ? `父 ${runner.sire}` : undefined, runner.damSire ? `母父 ${runner.damSire}` : undefined]
          .filter(Boolean)
          .join(" / ");

        return (
          <article key={runner.number}>
            <span>{index + 1}</span>
            <div className="runner-main">
              <strong>{runner.number}. {runner.name}</strong>
              <em>{staff || runner.jockey}</em>
              {profile.length > 0 && <small>{profile.join(" / ")}</small>}
              {runner.recentRecord && <small>{runner.recentRecord}</small>}
              {bloodline && <small>{bloodline}</small>}
            </div>
            <div className="runner-probs">
              <b>勝 {formatPercent(runner.winProbability)}</b>
              <b>2内 {formatPercent(runner.top2Probability ?? runner.winProbability)}</b>
              <b>3内 {formatPercent(runner.placeProbability)}</b>
            </div>
            <small className={runner.drift < 0 ? "positive odds-move" : "negative odds-move"}>
              {runner.drift > 0 ? "+" : ""}{runner.drift.toFixed(1)}%
            </small>
          </article>
        );
      })}
    </div>
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
