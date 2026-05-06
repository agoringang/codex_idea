"use client";

import { useEffect, useMemo, useState } from "react";

type Market = "JRA" | "NAR";
type ViewTab = "predict" | "calendar" | "results";
type AppIconId = "waliwali" | "keisya" | "hikaku" | "portfolio";

type Runner = {
  number: number;
  name: string;
  jockey: string;
  odds: number;
  baseWin: number;
  drift: number;
  form: number;
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
};

type ApiState = "loading" | "ready" | "fallback";

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
  { name: "HikakU", label: "比較", href: "https://agoringang.com/#detail-misekurabe", icon: "hikaku" as const },
  { name: "アプリ一覧", label: "agoringang", href: "https://agoringang.com/#apps", icon: "portfolio" as const },
];

const backtest = {
  races: 0,
  bets: 0,
  roi: 0,
  hitRate: 0,
  maxDrawdown: 0,
};

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

function normalizeApiRace(item: any): Race {
  const runners = Array.isArray(item.runners) ? item.runners : [];
  const normalizedRunners = runners.map((runner: any, index: number) => {
    const odds = Math.max(safeNumber(runner.odds ?? runner.market_odds, 1.1), 1.1);
    const rating = safeNumber(runner.rating, 64);
    return {
      number: safeNumber(runner.number, index + 1),
      name: String(runner.name ?? `${index + 1}番`),
      jockey: String(runner.jockey ?? "-"),
      odds,
      baseWin: Math.min(0.65, Math.max(0.004, 1 / odds)),
      drift: 0,
      form: Math.max(1, Math.min(100, rating)),
    };
  });
  const market = item.market === "NAR" || item.grade === "NAR" ? "NAR" : "JRA";
  const status = ["card", "odds", "watch", "finished"].includes(item.status)
    ? item.status
    : "card";

  return {
    id: String(item.id),
    date: String(item.date ?? "2026-05-06"),
    day: String(item.day ?? ""),
    start: String(item.start ?? "未取得"),
    venue: String(item.venue ?? "未設定"),
    title: String(item.title ?? item.raceNo ?? item.id),
    course: String(item.course ?? "条件未取得"),
    grade: String(item.grade ?? market),
    market,
    status,
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
      return {
        id: raceId,
        date,
        start: "確定",
        venue: String(entry.venue ?? raceId.split("-")[0] ?? "履歴"),
        title: String(entry.title ?? raceId),
        course: String(entry.course ?? "予測履歴"),
        market: "JRA" as Market,
        topTicket: String(prediction.top_ticket ?? prediction.warning ?? "AI予想"),
        result: String(result.message ?? "結果反映"),
        roi: stake > 0 ? payout / stake : safeNumber(prediction.expected_roi, 0),
        hitRate: safeNumber(prediction.hit_rate, 0),
        stake,
        payout,
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
        gate: Math.max(1, Math.min(8, Math.ceil(runner.number / 2))),
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
        venue: race.venue,
        surface,
        going,
        jockey: runner.jockey,
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

function calendarLabel(date: string) {
  const [, month, day] = date.split("-");
  return `${Number(month)}/${Number(day)}`;
}

function buildCalendarDays(items: { date: string }[]): CalendarDay[] {
  return Array.from(new Set(items.map((item) => item.date)))
    .sort()
    .map((date) => ({
      date,
      label: calendarLabel(date),
      day: weekdayFormatter.format(dateAtJst(date)).replace("曜日", ""),
    }));
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<ViewTab>("predict");
  const [selectedRaceId, setSelectedRaceId] = useState(races[0].id);
  const [selectedDate, setSelectedDate] = useState(races[0].date);
  const [riskLevel, setRiskLevel] = useState(48);
  const [bankroll, setBankroll] = useState(100000);
  const [apiRaces, setApiRaces] = useState<Race[]>([]);
  const [apiHistory, setApiHistory] = useState<HistoricalPrediction[]>([]);
  const [apiState, setApiState] = useState<ApiState>("loading");
  const [apiPrediction, setApiPrediction] = useState<ApiRacePrediction | null>(null);

  const availableRaces = apiRaces.length > 0 ? apiRaces : races;
  const availableHistory = apiHistory.length > 0 ? apiHistory : predictionHistory;
  const race = availableRaces.find((item) => item.id === selectedRaceId) ?? availableRaces[0];
  const selectedDateRaces = availableRaces.filter((item) => item.date === selectedDate);
  const selectedDateHistory = availableHistory.filter((item) => item.date === selectedDate);
  const calendarDays = useMemo(
    () => buildCalendarDays([...availableHistory, ...availableRaces]),
    [availableHistory, availableRaces],
  );
  const activeBankroll = Number.isFinite(bankroll) ? Math.max(bankroll, 1000) : 100000;
  const riskRatio = riskLevel / 100;

  useEffect(() => {
    let cancelled = false;
    async function loadInitialData() {
      try {
        const [raceResponse, historyResponse] = await Promise.all([
          fetch(`${apiBaseUrl()}/races`),
          fetch(`${apiBaseUrl()}/history`),
        ]);
        if (!raceResponse.ok) {
          throw new Error(`races ${raceResponse.status}`);
        }
        const racePayload = await raceResponse.json();
        const historyPayload = historyResponse.ok ? await historyResponse.json() : {};
        const nextRaces = Array.isArray(racePayload)
          ? racePayload.map(normalizeApiRace).filter((item) => item.runners.length > 0)
          : [];
        if (cancelled) {
          return;
        }
        if (nextRaces.length === 0) {
          setApiState("fallback");
          return;
        }
        setApiRaces(nextRaces);
        setApiHistory(normalizeApiHistory(historyPayload));
        setSelectedRaceId((current) =>
          nextRaces.some((item) => item.id === current) ? current : nextRaces[0].id,
        );
        setSelectedDate((current) =>
          nextRaces.some((item) => item.date === current) ? current : nextRaces[0].date,
        );
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

  const fallbackProjections = useMemo<RunnerProjection[]>(() => {
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
    () => mergeApiProjections(apiPrediction, race),
    [apiPrediction, race],
  );
  const projections = apiProjections ?? fallbackProjections;

  const fallbackTickets = useMemo<TicketProjection[]>(() => {
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
    if (!apiPrediction || apiPrediction.race_id !== race.id) {
      return [];
    }
    return apiPrediction.recommendations.map(apiRecommendationToTicket);
  }, [apiPrediction, race.id]);
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
    }
    setActiveTab(nextTab);
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
            <span>{race.date} {race.start}</span>
            <h1>{race.venue} {race.title}</h1>
            <p>{race.course}</p>
          </div>
          <div className="race-pills">
            <span>{race.market}</span>
            <span>{race.status}</span>
            <span>{apiPrediction?.race_id === race.id ? "実モデル" : apiState === "loading" ? "接続中" : "試算"}</span>
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

        {activeTab === "predict" && (
          <PredictPanel
            activeBankroll={activeBankroll}
            bankroll={bankroll}
            expectedRoi={expectedRoi}
            onBankrollChange={setBankroll}
            onRaceSelect={(raceId) => selectRace(raceId)}
            onRiskChange={setRiskLevel}
            apiState={apiPrediction?.race_id === race.id ? "ready" : apiState}
            projections={projections}
            race={race}
            races={availableRaces}
            riskLabel={riskLabel}
            riskLevel={riskLevel}
            tickets={tickets}
            totalStake={totalStake}
          />
        )}

        {activeTab === "calendar" && (
          <CalendarPanel
            calendarDays={calendarDays}
            history={availableHistory}
            onDateSelect={setSelectedDate}
            onRaceSelect={(raceId) => selectRace(raceId, "predict")}
            races={availableRaces}
            selectedDate={selectedDate}
            selectedDateHistory={selectedDateHistory}
            selectedDateRaces={selectedDateRaces}
            selectedRaceId={selectedRaceId}
          />
        )}

        {activeTab === "results" && (
          <ResultsPanel projections={projections} race={race} />
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

function PredictPanel({
  activeBankroll,
  apiState,
  bankroll,
  expectedRoi,
  onBankrollChange,
  onRaceSelect,
  onRiskChange,
  projections,
  race,
  races,
  riskLabel,
  riskLevel,
  tickets,
  totalStake,
}: {
  activeBankroll: number;
  apiState: ApiState;
  bankroll: number;
  expectedRoi: number;
  onBankrollChange: (value: number) => void;
  onRaceSelect: (raceId: string) => void;
  onRiskChange: (value: number) => void;
  projections: RunnerProjection[];
  race: Race;
  races: Race[];
  riskLabel: string;
  riskLevel: number;
  tickets: TicketProjection[];
  totalStake: number;
}) {
  return (
    <section className="tab-panel">
      <div className="control-strip">
        <div className="race-selector" aria-label="Race selector">
          {races.map((item) => (
            <button
              className={item.id === race.id ? "active" : ""}
              key={item.id}
              onClick={() => onRaceSelect(item.id)}
              type="button"
            >
              <span>{item.start}</span>
              <strong>{item.venue} {item.title}</strong>
              <em>{item.market}</em>
            </button>
          ))}
        </div>

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

function CalendarPanel({
  calendarDays,
  history,
  onDateSelect,
  onRaceSelect,
  races,
  selectedDate,
  selectedDateHistory,
  selectedDateRaces,
  selectedRaceId,
}: {
  calendarDays: CalendarDay[];
  history: HistoricalPrediction[];
  onDateSelect: (date: string) => void;
  onRaceSelect: (raceId: string) => void;
  races: Race[];
  selectedDate: string;
  selectedDateHistory: HistoricalPrediction[];
  selectedDateRaces: Race[];
  selectedRaceId: string;
}) {
  return (
    <section className="tab-panel">
      <div className="section-heading">
        <h2>カレンダー</h2>
        <span>{races.length}R</span>
      </div>

      <div className="date-rail">
        {calendarDays.map((day) => {
          const dayRaces = races.filter((race) => race.date === day.date);
          const dayHistory = history.filter((item) => item.date === day.date);
          return (
            <button
              className={selectedDate === day.date ? "active" : ""}
              key={day.date}
              onClick={() => onDateSelect(day.date)}
              type="button"
            >
              <span>{day.day}</span>
              <strong>{day.label}</strong>
              <em>{dayRaces.length + dayHistory.length}件</em>
            </button>
          );
        })}
      </div>

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
                <strong>{formatPercent(item.roi, 1)}</strong>
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

function ResultsPanel({ projections, race }: { projections: RunnerProjection[]; race: Race }) {
  return (
    <section className="tab-panel">
      <div className="section-heading">
        <h2>実績</h2>
        <span>未連携</span>
      </div>
      <div className="summary-strip">
        <Metric label="回収率" value={formatPercent(backtest.roi)} />
        <Metric label="的中率" value={formatPercent(backtest.hitRate)} />
        <Metric label="対象R" value={numberFormatter.format(backtest.races)} />
        <Metric label="最大DD" value={formatYen(backtest.maxDrawdown)} />
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
      {projections.map((runner, index) => (
        <article key={runner.number}>
          <span>{index + 1}</span>
          <strong>{runner.number}. {runner.name}</strong>
          <em>{runner.jockey}</em>
          <div className="runner-probs">
            <b>勝 {formatPercent(runner.winProbability)}</b>
            <b>2内 {formatPercent(runner.top2Probability ?? runner.winProbability)}</b>
            <b>3内 {formatPercent(runner.placeProbability)}</b>
          </div>
          <small className={runner.drift < 0 ? "positive" : "negative"}>
            {runner.drift > 0 ? "+" : ""}{runner.drift.toFixed(1)}%
          </small>
        </article>
      ))}
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
