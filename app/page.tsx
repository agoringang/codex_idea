"use client";

import {
  Activity,
  AlertTriangle,
  BellRing,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  Database,
  ExternalLink,
  Gauge,
  Grid2X2,
  ListChecks,
  RefreshCcw,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingDown,
  Trophy,
  XCircle,
  WalletCards,
} from "lucide-react";
import { useMemo, useState } from "react";

type RaceStatus = "prediction-ready" | "card-ready" | "racecard-available" | "schedule-only";

type Runner = {
  number: number;
  gate: number;
  name: string;
  jockey: string;
  weight: string;
  rating: number;
  odds: number;
  tags: string[];
};

type Race = {
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

type PricedRunner = Runner & {
  winProbability: number;
  placeProbability: number;
  fairOdds: number;
  edge: number;
};

type Bet = {
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
};

type OddsMove = {
  number: number;
  name: string;
  previousOdds: number;
  currentOdds: number;
  direction: "up" | "down" | "flat";
  reason: string;
};

type Scratch = {
  number: number;
  name: string;
  reason: string;
  announcedAt: string;
};

type LiveResult = {
  status: "pending" | "hit" | "miss" | "refund";
  message: string;
  payout?: number;
  winningSelection?: string;
};

type LiveSnapshot = {
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

type RaceOverride = Partial<Pick<Race, "title" | "grade" | "course" | "status" | "officialNote">> & {
  runners?: Runner[];
};

type MeetingProgram = {
  key: string;
  date: string;
  day: string;
  venue: string;
  meeting: string;
  times: string[];
};

const meetingPrograms: MeetingProgram[] = [
  {
    key: "tokyo",
    date: "2026-05-02",
    day: "土曜",
    venue: "東京",
    meeting: "2回東京3日",
    times: ["10:05", "10:40", "11:10", "11:40", "12:30", "13:00", "13:30", "14:00", "14:30", "15:05", "15:45", "16:30"],
  },
  {
    key: "kyoto",
    date: "2026-05-02",
    day: "土曜",
    venue: "京都",
    meeting: "3回京都3日",
    times: ["10:00", "10:30", "11:00", "11:30", "12:20", "12:50", "13:20", "13:50", "14:20", "14:55", "15:30", "16:10"],
  },
  {
    key: "niigata",
    date: "2026-05-02",
    day: "土曜",
    venue: "新潟",
    meeting: "1回新潟1日",
    times: ["09:45", "10:20", "10:50", "11:20", "12:10", "12:40", "13:10", "13:40", "14:15", "14:50", "15:20", "16:00"],
  },
  {
    key: "tokyo",
    date: "2026-05-03",
    day: "日曜",
    venue: "東京",
    meeting: "2回東京4日",
    times: ["10:00", "10:30", "11:00", "11:30", "12:20", "12:50", "13:20", "13:50", "14:25", "15:00", "15:25", "16:10"],
  },
  {
    key: "kyoto",
    date: "2026-05-03",
    day: "日曜",
    venue: "京都",
    meeting: "3回京都4日",
    times: ["10:00", "10:30", "11:00", "11:30", "12:20", "12:50", "13:20", "13:50", "14:25", "15:00", "15:40", "16:25"],
  },
  {
    key: "niigata",
    date: "2026-05-03",
    day: "日曜",
    venue: "新潟",
    meeting: "1回新潟2日",
    times: ["09:50", "10:20", "10:50", "11:20", "12:10", "12:40", "13:10", "13:40", "14:15", "14:50", "15:15", "16:00"],
  },
];

const raceOverrides: Record<string, RaceOverride> = {
  "tokyo-20260502-10": {
    title: "スイートピーステークス",
    grade: "L",
    course: "芝1800m 左",
    officialNote: "JRA公式出馬表を確認。詳細データ接続待ち。",
  },
  "tokyo-20260502-11": {
    title: "京王杯スプリングカップ",
    grade: "GII",
    course: "芝1400m 左",
    status: "card-ready",
    officialNote: "JRA公式出馬表を一部反映。全頭データ接続待ち。",
    runners: [
      { number: 1, gate: 1, name: "レッドシュヴェルト", jockey: "横山和", weight: "57.0", rating: 78, odds: 9.2, tags: ["末脚", "東京巧者"] },
      { number: 2, gate: 2, name: "ダノンセンチュリー", jockey: "D.レーン", weight: "57.0", rating: 88, odds: 3.8, tags: ["安定", "騎手強化"] },
      { number: 3, gate: 3, name: "アサカラキング", jockey: "戸崎", weight: "57.0", rating: 83, odds: 6.7, tags: ["先行", "距離適性"] },
    ],
  },
  "kyoto-20260502-10": {
    title: "京極特別",
    grade: "2勝クラス",
    course: "ダート1200m 右",
    officialNote: "JRA公式出馬表を確認。詳細データ接続待ち。",
  },
  "kyoto-20260502-11": {
    title: "ユニコーンステークス",
    grade: "GIII",
    course: "ダート1900m 右",
    status: "card-ready",
    officialNote: "JRA公式出馬表を一部反映。3歳ダート戦。",
    runners: [
      { number: 1, gate: 1, name: "サイモンゼスト", jockey: "酒井", weight: "57.0", rating: 70, odds: 21.4, tags: ["逃げ", "巻返し"] },
      { number: 2, gate: 2, name: "ケイアイアギト", jockey: "鮫島克", weight: "57.0", rating: 84, odds: 5.6, tags: ["先行", "安定"] },
      { number: 3, gate: 3, name: "ヴィエントデコラ", jockey: "未定", weight: "57.0", rating: 80, odds: 7.9, tags: ["京都", "成長"] },
    ],
  },
  "kyoto-20260502-12": {
    title: "4歳以上1勝クラス",
    grade: "1勝クラス",
    course: "芝1600m 右外",
    officialNote: "JRA公式出馬表を確認。詳細データ接続待ち。",
  },
  "niigata-20260502-1": {
    title: "障害4歳以上未勝利",
    grade: "未勝利",
    course: "障害芝2890m",
    officialNote: "JRA公式出馬表を確認。詳細データ接続待ち。",
  },
  "niigata-20260502-11": {
    title: "三条ステークス",
    grade: "3勝クラス",
    course: "ダート1800m",
    officialNote: "JRA公式の今週の開催予定。詳細出馬表の接続待ち。",
  },
  "tokyo-20260503-11": {
    title: "プリンシパルステークス",
    grade: "L",
    course: "芝2000m 左",
    officialNote: "JRA公式出馬表を確認中。日本ダービーにつながる3歳戦。",
  },
  "kyoto-20260503-3": {
    title: "3歳未勝利",
    grade: "未勝利",
    course: "ダート1800m 右",
    officialNote: "JRA公式出馬表を確認。詳細データ接続待ち。",
  },
  "kyoto-20260503-6": {
    title: "3歳1勝クラス",
    grade: "1勝クラス",
    course: "ダート1400m 右",
    officialNote: "JRA公式出馬表を確認。詳細データ接続待ち。",
  },
  "kyoto-20260503-11": {
    title: "天皇賞（春）",
    grade: "GI",
    course: "芝3200m 右外",
    status: "prediction-ready",
    officialNote: "JRA公式出馬表を反映。現時点のメイン予想対象。",
    runners: [
      { number: 1, gate: 1, name: "ヴェルミセル", jockey: "鮫島克", weight: "56.0", rating: 74, odds: 35.0, tags: ["長距離", "牝馬"] },
      { number: 2, gate: 1, name: "サンライズソレイユ", jockey: "池添謙", weight: "58.0", rating: 79, odds: 18.5, tags: ["持久力", "内枠"] },
      { number: 3, gate: 2, name: "アドマイヤテラ", jockey: "武豊", weight: "58.0", rating: 89, odds: 7.2, tags: ["長距離適性", "騎手"] },
      { number: 4, gate: 2, name: "アクアヴァーナル", jockey: "松山弘", weight: "56.0", rating: 77, odds: 22.4, tags: ["軽量", "先行"] },
      { number: 5, gate: 3, name: "ケイアイサンデラ", jockey: "藤懸貴", weight: "58.0", rating: 73, odds: 41.0, tags: ["逃げ", "展開待ち"] },
      { number: 6, gate: 3, name: "エヒト", jockey: "川田将", weight: "58.0", rating: 82, odds: 14.6, tags: ["経験", "騎手"] },
      { number: 7, gate: 4, name: "クロワデュノール", jockey: "北村友", weight: "58.0", rating: 94, odds: 3.9, tags: ["能力上位", "安定"] },
      { number: 8, gate: 4, name: "シンエンペラー", jockey: "岩田望", weight: "58.0", rating: 91, odds: 5.8, tags: ["地力", "海外経験"] },
      { number: 9, gate: 5, name: "プレシャスデイ", jockey: "吉村誠", weight: "58.0", rating: 78, odds: 26.0, tags: ["成長", "穴"] },
      { number: 10, gate: 5, name: "マイネルカンパーナ", jockey: "津村明", weight: "58.0", rating: 75, odds: 38.0, tags: ["長距離", "持久力"] },
      { number: 11, gate: 6, name: "タガノデュード", jockey: "古川吉", weight: "58.0", rating: 76, odds: 30.5, tags: ["京都", "差し"] },
      { number: 12, gate: 6, name: "ヘデントール", jockey: "C.ルメ", weight: "58.0", rating: 96, odds: 3.2, tags: ["前年覇者", "本命級"] },
      { number: 13, gate: 7, name: "ミステリーウェイ", jockey: "松本大", weight: "58.0", rating: 72, odds: 55.0, tags: ["大穴", "展開待ち"] },
      { number: 14, gate: 7, name: "ホーエリート", jockey: "戸崎圭", weight: "56.0", rating: 83, odds: 12.8, tags: ["牝馬", "相手"] },
      { number: 15, gate: 8, name: "ヴェルテンベルク", jockey: "松若風", weight: "58.0", rating: 71, odds: 60.0, tags: ["外枠", "大穴"] },
    ],
  },
  "niigata-20260503-11": {
    title: "越後ステークス",
    grade: "OP",
    course: "ダート1200m",
    officialNote: "JRA公式の今週の開催予定。詳細出馬表の接続待ち。",
  },
};

function defaultTitle(raceNumber: number) {
  if (raceNumber <= 4) {
    return "未勝利・条件戦";
  }
  if (raceNumber <= 8) {
    return "平場戦";
  }
  if (raceNumber <= 10) {
    return "特別戦";
  }
  if (raceNumber === 11) {
    return "メインレース";
  }
  return "最終レース";
}

const races: Race[] = meetingPrograms.flatMap((program) =>
  program.times.map((start, index) => {
    const raceNumber = index + 1;
    const id = `${program.key}-${program.date.replaceAll("-", "")}-${raceNumber}`;
    const override = raceOverrides[id] ?? {};

    return {
      id,
      date: program.date,
      day: program.day,
      venue: program.venue,
      meeting: program.meeting,
      raceNo: `${raceNumber}R`,
      start,
      title: override.title ?? defaultTitle(raceNumber),
      grade: override.grade ?? "取得待ち",
      course: override.course ?? "出馬表取得待ち",
      status: override.status ?? "racecard-available",
      officialNote: override.officialNote ?? "JRA公式accessDの出馬表枠あり。馬名・オッズ解析後に予想へ切り替えます。",
      source: "JRA",
      runners: override.runners ?? [],
    };
  }),
);

const liveSnapshots: Record<string, LiveSnapshot> = {
  "kyoto-20260503-11": {
    racecardStatus: "parsed",
    oddsStatus: "monitoring",
    resultStatus: "waiting",
    nextPollSeconds: 60,
    updatedAt: "13:45",
    oddsMoves: [
      {
        number: 12,
        name: "ヘデントール",
        previousOdds: 3.5,
        currentOdds: 3.2,
        direction: "down",
        reason: "本命側に買いが入っています",
      },
      {
        number: 14,
        name: "ホーエリート",
        previousOdds: 15.1,
        currentOdds: 12.8,
        direction: "down",
        reason: "相手候補として評価上昇",
      },
    ],
    scratches: [],
    result: {
      status: "pending",
      message: "結果確定待ち。的中時はここが緑で強調されます。",
    },
    alerts: ["出馬表解析済み", "オッズ監視中", "取消発表があれば買い目を自動再計算"],
  },
  "tokyo-20260502-11": {
    racecardStatus: "parsed",
    oddsStatus: "monitoring",
    resultStatus: "waiting",
    nextPollSeconds: 60,
    updatedAt: "13:45",
    oddsMoves: [
      {
        number: 2,
        name: "ダノンセンチュリー",
        previousOdds: 4.4,
        currentOdds: 3.8,
        direction: "down",
        reason: "前日オッズで支持上昇",
      },
    ],
    scratches: [],
    result: {
      status: "pending",
      message: "結果確定待ち",
    },
    alerts: ["一部出馬表解析済み", "全頭データ接続待ち"],
  },
};

const backtestSummary = {
  status: "スモーク完了",
  window: "synthetic 1,200R",
  races: 1200,
  bets: 14243,
  totalStake: 14268700,
  totalPayout: 18451016,
  roi: 1.2931,
  hitRate: 0.04,
  maxDrawdown: 2329887,
  note: "合成データでの動作確認。実レースの回収率ではなく、実データ投入後に再計算します。",
};

const dataCoverage = [
  { group: "レース条件", state: "未接続", fields: "開催日 / 場 / 距離 / 馬場 / 天候 / クラス / 枠順" },
  { group: "出走馬", state: "未接続", fields: "馬齢 / 性別 / 斤量 / 馬体重 / 近走 / 走破タイム / 上がり" },
  { group: "人・血統", state: "未接続", fields: "騎手 / 調教師 / 馬主 / 生産者 / 父 / 母父 / 勝率" },
  { group: "市場", state: "未接続", fields: "全券種オッズ / 時系列オッズ / 票数 / オッズ変動" },
  { group: "結果", state: "未接続", fields: "着順 / 払戻 / 返還 / 取消 / 騎手変更" },
];

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatYen(value: number) {
  return new Intl.NumberFormat("ja-JP", {
    style: "currency",
    currency: "JPY",
    maximumFractionDigits: 0,
  }).format(value);
}

function estimate(race: Race): PricedRunner[] {
  if (race.runners.length === 0) {
    return [];
  }

  const raw = race.runners.map((runner) => {
    const oddsValue = clamp(18 / runner.odds, 0.75, 1.28);
    const distanceBias = race.course.includes("3200") && runner.tags.some((tag) => tag.includes("長距離")) ? 1.07 : 1;
    const formBias = runner.tags.some((tag) => tag.includes("前年") || tag.includes("能力")) ? 1.08 : 1;

    return Math.exp((runner.rating - 78) / 15) * oddsValue * distanceBias * formBias;
  });
  const total = raw.reduce((sum, value) => sum + value, 0);

  return race.runners
    .map((runner, index) => {
      const winProbability = raw[index] / total;
      const placeProbability = clamp(winProbability * 2.55 + runner.rating / 650, 0.08, 0.72);
      const fairOdds = 1 / winProbability;
      const edge = winProbability * runner.odds - 1;

      return {
        ...runner,
        winProbability,
        placeProbability,
        fairOdds,
        edge,
      };
    })
    .sort((a, b) => b.winProbability - a.winProbability);
}

function riskMode(risk: number) {
  if (risk < 34) {
    return "guard" as const;
  }
  if (risk < 67) {
    return "balanced" as const;
  }
  return "attack" as const;
}

function riskLabel(risk: number) {
  const mode = riskMode(risk);
  if (mode === "guard") {
    return "守り / 的中率重視";
  }
  if (mode === "balanced") {
    return "標準 / 期待値重視";
  }
  return "攻め / 回収率重視";
}

function riskDescription(risk: number) {
  const mode = riskMode(risk);
  if (mode === "guard") {
    return "複勝・ワイド中心。高配当より外しにくさを優先。";
  }
  if (mode === "balanced") {
    return "単勝・ワイド・馬連・馬単を混ぜ、的中率と回収率の中間を狙う。";
  }
  return "3連単フォーメーション・マルチで点数を広げつつ、高回収を狙う。";
}

function formationTicketCount(firsts: PricedRunner[], seconds: PricedRunner[], thirds: PricedRunner[]) {
  let count = 0;
  firsts.forEach((first) => {
    seconds.forEach((second) => {
      thirds.forEach((third) => {
        if (new Set([first.number, second.number, third.number]).size === 3) {
          count += 1;
        }
      });
    });
  });
  return count;
}

function buildBets(runners: PricedRunner[], bankroll: number, risk: number): Bet[] {
  if (runners.length < 2) {
    return [];
  }

  const mode = riskMode(risk);
  const stake = (ratio: number) => {
    if (bankroll <= 0) {
      return 0;
    }
    return Math.max(100, Math.round((bankroll * ratio) / 100) * 100);
  };
  const multiStake = (tickets: number, ratio: number) => {
    if (bankroll <= 0 || tickets <= 0) {
      return { stake: 0, unitStake: 0 };
    }
    const unitStake = Math.max(100, Math.round(stake(ratio) / tickets / 100) * 100);
    return { stake: unitStake * tickets, unitStake };
  };
  const [first, second, third, fourth] = runners;
  const topFive = runners.slice(0, 5);
  const topSix = runners.slice(0, 6);
  const wideProbability = clamp(first.placeProbability * second.placeProbability * 0.95, 0.02, 0.52);
  const quinellaProbability = clamp(first.winProbability * second.winProbability * 2.2, 0.01, 0.34);
  const frameProbability = clamp(quinellaProbability * 1.1, 0.01, 0.38);
  const exactaProbability = clamp(first.winProbability * second.winProbability * 1.35, 0.006, 0.26);
  const trioProbability = third ? clamp(first.winProbability * second.winProbability * third.winProbability * 7.2, 0.004, 0.2) : 0;
  const trifectaProbability = third
    ? clamp(first.winProbability * second.winProbability * third.winProbability * 2.1, 0.001, 0.09)
    : 0;
  const darkHorse = runners.find((runner) => runner.edge > 0.12) ?? fourth ?? runners[0];
  const attackWideProbability = clamp(first.placeProbability * darkHorse.placeProbability * 0.88, 0.02, 0.52);

  const placeOdds = (runner: PricedRunner) => clamp(runner.odds / 4, 1.2, 9.5);
  const wideOdds = clamp(1 / wideProbability * 0.82, 2.0, 18.0);
  const frameOdds = clamp(1 / frameProbability * 0.76, 1.8, 45.0);
  const quinellaOdds = clamp(1 / quinellaProbability * 0.78, 3.0, 80.0);
  const exactaOdds = clamp(1 / exactaProbability * 0.74, 4.0, 140.0);
  const trioOdds = third ? clamp(1 / trioProbability * 0.72, 8.0, 220.0) : 0;
  const trifectaOdds = third ? clamp(1 / trifectaProbability * 0.7, 20.0, 999.0) : 0;
  const attackWideOdds = clamp((1 / attackWideProbability) * 0.86, 2.0, 22.0);
  const formationTickets = topSix.length >= 6 ? formationTicketCount(topSix.slice(0, 2), topSix.slice(0, 4), topSix) : 0;
  const twoAxisTickets = topSix.length >= 6 ? (topSix.length - 2) * 6 : 0;
  const oneAxisTickets = topFive.length >= 5 ? ((topFive.length - 1) * (topFive.length - 2) * 6) / 2 : 0;
  const formationStake = multiStake(formationTickets, 0.022);
  const twoAxisStake = multiStake(twoAxisTickets, 0.018);
  const oneAxisStake = multiStake(oneAxisTickets, 0.016);
  const formationProbability = clamp(trifectaProbability * formationTickets * 0.58, 0.012, 0.42);
  const twoAxisProbability = clamp(trifectaProbability * twoAxisTickets * 0.52, 0.01, 0.34);
  const oneAxisProbability = clamp(trifectaProbability * oneAxisTickets * 0.48, 0.01, 0.38);
  const formationOdds = formationTickets ? clamp((trifectaOdds * 0.9) / formationTickets, 1.4, 96.0) : 0;
  const twoAxisOdds = twoAxisTickets ? clamp((trifectaOdds * 0.86) / twoAxisTickets, 1.3, 86.0) : 0;
  const oneAxisOdds = oneAxisTickets ? clamp((trifectaOdds * 0.82) / oneAxisTickets, 1.25, 76.0) : 0;

  if (mode === "guard") {
    return [
      {
        type: "複勝",
        selection: `${first.number} ${first.name}`,
        probability: first.placeProbability,
        odds: placeOdds(first),
        edge: first.placeProbability * placeOdds(first) - 1,
        stake: stake(0.018),
        note: "最上位評価の複勝で外しにくさ優先",
      },
      {
        type: "ワイド",
        selection: `${first.number}-${second.number}`,
        probability: wideProbability,
        odds: wideOdds,
        edge: wideProbability * wideOdds - 1,
        stake: stake(0.014),
        note: `${first.name} / ${second.name}`,
      },
      {
        type: "枠連",
        selection: `${first.gate}-${second.gate}`,
        probability: frameProbability,
        odds: frameOdds,
        edge: frameProbability * frameOdds - 1,
        stake: stake(0.01),
        note: "馬番より広く構える低リスク枠",
      },
      {
        type: "複勝",
        selection: `${second.number} ${second.name}`,
        probability: second.placeProbability,
        odds: placeOdds(second),
        edge: second.placeProbability * placeOdds(second) - 1,
        stake: stake(0.01),
        note: "対抗の複勝で回収を補う",
      },
    ];
  }

  const balancedBets: Bet[] = [
    {
      type: "単勝",
      selection: `${first.number} ${first.name}`,
      probability: first.winProbability,
      odds: first.odds,
      edge: first.edge,
      stake: stake(0.014),
      note: "能力と安定度の軸",
    },
    {
      type: "ワイド",
      selection: `${first.number}-${second.number}`,
      probability: wideProbability,
      odds: wideOdds,
      edge: wideProbability * wideOdds - 1,
      stake: stake(0.012),
      note: `${first.name} / ${second.name}`,
    },
    {
      type: "馬連",
      selection: `${first.number}-${second.number}`,
      probability: quinellaProbability,
      odds: quinellaOdds,
      edge: quinellaProbability * quinellaOdds - 1,
      stake: stake(0.008),
      note: "上位2頭の組み合わせ",
    },
    {
      type: "馬単",
      selection: `${first.number}-${second.number}`,
      probability: exactaProbability,
      odds: exactaOdds,
      edge: exactaProbability * exactaOdds - 1,
      stake: stake(0.006),
      note: "本命から対抗への順序指定",
    },
    {
      type: "複勝",
      selection: `${darkHorse.number} ${darkHorse.name}`,
      probability: darkHorse.placeProbability,
      odds: placeOdds(darkHorse),
      edge: darkHorse.placeProbability * placeOdds(darkHorse) - 1,
      stake: stake(0.008),
      note: "妙味寄りの保険",
    },
  ];

  if (mode === "balanced" || !third || runners.length < 5) {
    return balancedBets;
  }

  return [
    {
      type: "3連単",
      strategy: "フォーメーション",
      selection: `1着 ${topSix.slice(0, 2).map((runner) => runner.number).join(",")} / 2着 ${topSix
        .slice(0, 4)
        .map((runner) => runner.number)
        .join(",")} / 3着 ${topSix.map((runner) => runner.number).join(",")}`,
      probability: formationProbability,
      odds: formationOdds,
      edge: formationProbability * formationOdds - 1,
      stake: formationStake.stake,
      tickets: formationTickets,
      unitStake: formationStake.unitStake,
      note: "1点勝負より的中範囲を広げる本線",
    },
    {
      type: "3連単",
      strategy: "2頭軸マルチ",
      selection: `軸 ${first.number}-${second.number} / 相手 ${topSix
        .slice(2)
        .map((runner) => runner.number)
        .join(",")}`,
      probability: twoAxisProbability,
      odds: twoAxisOdds,
      edge: twoAxisProbability * twoAxisOdds - 1,
      stake: twoAxisStake.stake,
      tickets: twoAxisTickets,
      unitStake: twoAxisStake.unitStake,
      note: "軸2頭の着順入替まで拾う",
    },
    {
      type: "3連複",
      selection: `${first.number}-${second.number}-${third.number}`,
      probability: trioProbability,
      odds: trioOdds,
      edge: trioProbability * trioOdds - 1,
      stake: stake(0.011),
      note: "点数を絞る高回収枠",
    },
    {
      type: "3連単",
      strategy: "1頭軸マルチ",
      selection: `軸 ${first.number} / 相手 ${topFive
        .slice(1)
        .map((runner) => runner.number)
        .join(",")}`,
      probability: oneAxisProbability,
      odds: oneAxisOdds,
      edge: oneAxisProbability * oneAxisOdds - 1,
      stake: oneAxisStake.stake,
      tickets: oneAxisTickets,
      unitStake: oneAxisStake.unitStake,
      note: "本命が3着以内なら順序違いまで拾う",
    },
    {
      type: "馬単",
      selection: `${first.number}-${second.number}`,
      probability: exactaProbability,
      odds: exactaOdds,
      edge: exactaProbability * exactaOdds - 1,
      stake: stake(0.012),
      note: "順序まで取りに行く攻め筋",
    },
    {
      type: "単勝",
      selection: `${first.number} ${first.name}`,
      probability: first.winProbability,
      odds: first.odds,
      edge: first.edge,
      stake: stake(0.009),
      note: "軸馬の勝ち切り",
    },
    {
      type: "馬連",
      selection: `${first.number}-${second.number}`,
      probability: quinellaProbability,
      odds: quinellaOdds,
      edge: quinellaProbability * quinellaOdds - 1,
      stake: stake(0.007),
      note: "順序違いの保険",
    },
    {
      type: "単勝",
      selection: `${darkHorse.number} ${darkHorse.name}`,
      probability: darkHorse.winProbability,
      odds: darkHorse.odds,
      edge: darkHorse.edge,
      stake: stake(0.006),
      note: "穴の跳ね返り狙い",
    },
    {
      type: "ワイド",
      selection: `${first.number}-${darkHorse.number}`,
      probability: attackWideProbability,
      odds: attackWideOdds,
      edge: attackWideProbability * attackWideOdds - 1,
      stake: stake(0.005),
      note: "軸と穴を絡める",
    },
  ];
}

function statusText(status: RaceStatus) {
  if (status === "prediction-ready") {
    return "予想表示中";
  }
  if (status === "card-ready") {
    return "簡易予想";
  }
  if (status === "racecard-available") {
    return "出馬表あり";
  }
  return "予定のみ";
}

function defaultLiveSnapshot(race: Race): LiveSnapshot {
  return {
    racecardStatus: race.status === "schedule-only" ? "waiting" : "available",
    oddsStatus: "waiting",
    resultStatus: "waiting",
    nextPollSeconds: 120,
    updatedAt: "未更新",
    oddsMoves: [],
    scratches: [],
    result: {
      status: "pending",
      message: "結果確定待ち",
    },
    alerts: [
      race.status === "schedule-only" ? "開催予定を監視中" : "JRA accessD出馬表あり",
      "オッズ取得待ち",
      "取消情報なし",
    ],
  };
}

export default function Home() {
  const [selectedRaceId, setSelectedRaceId] = useState("kyoto-20260503-11");
  const [selectedVenue, setSelectedVenue] = useState("京都");
  const [bankroll, setBankroll] = useState(100000);
  const [risk, setRisk] = useState(42);

  const venueTabs = useMemo(() => ["すべて", ...Array.from(new Set(races.map((race) => race.venue)))], []);
  const filteredRaces = useMemo(
    () => (selectedVenue === "すべて" ? races : races.filter((race) => race.venue === selectedVenue)),
    [selectedVenue],
  );
  const selectedRace = races.find((race) => race.id === selectedRaceId) ?? races[0];
  const liveSnapshot = liveSnapshots[selectedRace.id] ?? defaultLiveSnapshot(selectedRace);
  const pricedRunners = useMemo(() => estimate(selectedRace), [selectedRace]);
  const bets = useMemo(() => buildBets(pricedRunners, bankroll, risk), [pricedRunners, bankroll, risk]);
  const top = pricedRunners[0];
  const second = pricedRunners[1];
  const third = pricedRunners[2];
  const totalStake = bets.reduce((sum, bet) => sum + bet.stake, 0);
  const currentRiskLabel = riskLabel(risk);
  const currentRiskDescription = riskDescription(risk);
  const setVenueTab = (venue: string) => {
    setSelectedVenue(venue);
    const nextRaces = venue === "すべて" ? races : races.filter((race) => race.venue === venue);
    if (!nextRaces.some((race) => race.id === selectedRaceId)) {
      setSelectedRaceId(nextRaces[0]?.id ?? races[0].id);
    }
  };

  return (
    <main className="app-shell">
      <section className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <img alt="" src="/racequant-icon.svg" />
          </div>
          <div>
            <p>RaceQuant Lab</p>
            <h1>次のレース予想</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <a className="apps-link" href="https://agoringang.com/#apps" rel="noreferrer" target="_blank">
            <span className="apps-link-icon" aria-hidden="true">
              <Grid2X2 size={17} />
            </span>
            <span>他のアプリを見る</span>
            <ExternalLink size={14} />
          </a>
          <span className="status-pill">
            <CalendarDays size={16} />
            2026年5月2日・3日 / 全{races.length}R
          </span>
          <span className="status-pill caution">
            <ShieldAlert size={16} />
            投資保証なし
          </span>
        </div>
      </section>

      <section className="page-grid">
        <aside className="schedule-panel">
          <div className="panel-heading">
            <div>
              <p>Upcoming JRA</p>
              <h2>全レース予定</h2>
            </div>
            <RefreshCcw size={19} />
          </div>

          <div className="venue-tabs" aria-label="会場タブ">
            {venueTabs.map((venue) => {
              const count = venue === "すべて" ? races.length : races.filter((race) => race.venue === venue).length;
              return (
                <button
                  className={selectedVenue === venue ? "active" : ""}
                  key={venue}
                  onClick={() => setVenueTab(venue)}
                  type="button"
                >
                  <strong>{venue}</strong>
                  <span>{count}R</span>
                </button>
              );
            })}
          </div>

          <div className="race-count">
            {selectedVenue} / 表示 {filteredRaces.length}R
          </div>

          <div className="race-list">
            {filteredRaces.map((race) => (
              <button
                className={`race-button ${race.id === selectedRace.id ? "active" : ""}`}
                key={race.id}
                onClick={() => setSelectedRaceId(race.id)}
                type="button"
              >
                <span>
                  {race.date} {race.day} / {race.venue} {race.raceNo}
                </span>
                <strong>
                  {race.title} <small>{race.grade}</small>
                </strong>
                <em>
                  {race.start}発走 / {race.course}
                </em>
                <b>{statusText(race.status)}</b>
              </button>
            ))}
          </div>

          <div className="bankroll-box">
            <div className="panel-heading compact">
              <div>
                <p>Stake</p>
                <h2>このレースの軍資金</h2>
              </div>
              <WalletCards size={18} />
            </div>
            <label className="field">
              <span>このレースの上限</span>
              <input
                inputMode="numeric"
                min={1000}
                onChange={(event) => setBankroll(Number(event.target.value) || 0)}
                step={1000}
                type="number"
                value={bankroll}
              />
            </label>
            <label className="slider-field">
              <span>
                リスク/リターン {risk} / {currentRiskLabel}
              </span>
              <input
                max={100}
                min={0}
                onChange={(event) => setRisk(Number(event.target.value))}
                type="range"
                value={risk}
              />
            </label>
            <div className="risk-scale" aria-hidden="true">
              <span>守り</span>
              <span>標準</span>
              <span>攻め</span>
            </div>
            <p className="strategy-note">{currentRiskDescription}</p>
          </div>
        </aside>

        <section className="prediction-panel">
          <div className="race-hero">
            <div>
              <p>表示中</p>
              <h2>
                {selectedRace.date} {selectedRace.venue}
                {selectedRace.raceNo} {selectedRace.title}
              </h2>
              <span>
                {selectedRace.meeting} / {selectedRace.start}発走 / {selectedRace.grade} / {selectedRace.course}
              </span>
            </div>
            <div className="hero-badge">{statusText(selectedRace.status)}</div>
          </div>

          {pricedRunners.length > 0 ? (
            <>
              <div className="summary-grid">
                <article>
                  <Target size={19} />
                  <span>本命</span>
                  <strong>
                    {top.number} {top.name}
                  </strong>
                  <small>
                    勝率 {formatPercent(top.winProbability)} / 妥当 {top.fairOdds.toFixed(1)}倍
                  </small>
                </article>
                <article>
                  <Sparkles size={19} />
                  <span>対抗</span>
                  <strong>
                    {second.number} {second.name}
                  </strong>
                  <small>勝率 {formatPercent(second.winProbability)}</small>
                </article>
                <article>
                  <Gauge size={19} />
                  <span>穴候補</span>
                  <strong>
                    {third.number} {third.name}
                  </strong>
                  <small>複勝圏 {formatPercent(third.placeProbability)}</small>
                </article>
                <article>
                  <CircleDollarSign size={19} />
                  <span>投下予定</span>
                  <strong>{formatYen(totalStake)}</strong>
                  <small>軍資金の {bankroll ? ((totalStake / bankroll) * 100).toFixed(1) : "0.0"}%</small>
                </article>
              </div>

              <section className="ticket-panel">
                <div className="section-heading">
                  <div>
                    <p>Tickets</p>
                    <h3>今買うならこの順</h3>
                  </div>
                  <ListChecks size={20} />
                </div>
                <div className="ticket-list">
                  {bets.map((bet) => (
                    <article key={`${bet.type}-${bet.selection}`}>
                      <div>
                        <span>{bet.type}</span>
                        <strong>{bet.selection}</strong>
                        <small>
                          {bet.strategy ? `${bet.strategy} / ` : ""}
                          {bet.note}
                          {bet.tickets && bet.tickets > 1 && bet.unitStake
                            ? ` / ${bet.tickets}点 x ${formatYen(bet.unitStake)}`
                            : ""}
                        </small>
                      </div>
                      <div className="ticket-side">
                        <strong>{formatYen(bet.stake)}</strong>
                        <small>
                          確率 {formatPercent(bet.probability)} / 想定 {bet.odds.toFixed(1)}倍
                        </small>
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              <section className="runner-panel">
                <div className="section-heading">
                  <div>
                    <p>Runners</p>
                    <h3>出走馬と推定順位</h3>
                  </div>
                  <Database size={20} />
                </div>
                <div className="runner-table">
                  <div className="runner-row head">
                    <span>印</span>
                    <span>馬番</span>
                    <span>馬名</span>
                    <span>騎手</span>
                    <span>勝率</span>
                    <span>妙味</span>
                  </div>
                  {pricedRunners.map((runner, index) => (
                    <div className="runner-row" key={runner.number}>
                      <span>{index === 0 ? "◎" : index === 1 ? "○" : index === 2 ? "▲" : index < 5 ? "△" : ""}</span>
                      <span className="number">{runner.number}</span>
                      <span className="runner-name">
                        <strong>{runner.name}</strong>
                        <small>{runner.tags.join(" / ")}</small>
                      </span>
                      <span>{runner.jockey}</span>
                      <span>{formatPercent(runner.winProbability)}</span>
                      <span className={runner.edge > 0 ? "positive" : "muted"}>{formatPercent(runner.edge)}</span>
                    </div>
                  ))}
                </div>
              </section>
            </>
          ) : (
            <div className="empty-state">
              <AlertTriangle size={24} />
              <strong>このレースは出馬表解析待ち</strong>
              <span>JRA出馬表は確認対象です。馬名・オッズを取り込んだら予想と買い目を表示します。</span>
            </div>
          )}
        </section>

        <aside className="side-panel">
          <section className={`live-card result-${liveSnapshot.result.status}`}>
            <div className="section-heading">
              <div>
                <p>Live monitor</p>
                <h3>自動取得・更新</h3>
              </div>
              <BellRing size={20} />
            </div>

            <div className="live-status-grid">
              <article>
                <strong>出馬表</strong>
                <span>{liveSnapshot.racecardStatus === "parsed" ? "解析済み" : liveSnapshot.racecardStatus === "available" ? "取得対象" : "待機"}</span>
              </article>
              <article>
                <strong>オッズ</strong>
                <span>{liveSnapshot.oddsStatus === "monitoring" ? "監視中" : liveSnapshot.oddsStatus === "closed" ? "締切" : "待機"}</span>
              </article>
              <article>
                <strong>結果</strong>
                <span>{liveSnapshot.resultStatus === "official" ? "確定" : "待ち"}</span>
              </article>
              <article>
                <strong>更新</strong>
                <span>{liveSnapshot.nextPollSeconds}秒間隔</span>
              </article>
            </div>

            <div className="result-banner">
              {liveSnapshot.result.status === "hit" ? <Trophy size={18} /> : <Activity size={18} />}
              <div>
                <strong>
                  {liveSnapshot.result.status === "hit"
                    ? "的中"
                    : liveSnapshot.result.status === "miss"
                      ? "不的中"
                      : liveSnapshot.result.status === "refund"
                        ? "返還"
                        : "結果待ち"}
                </strong>
                <small>
                  {liveSnapshot.result.message}
                  {liveSnapshot.result.payout ? ` / 払戻 ${formatYen(liveSnapshot.result.payout)}` : ""}
                </small>
              </div>
            </div>

            <div className="live-alerts">
              {liveSnapshot.alerts.map((alert) => (
                <span key={alert}>{alert}</span>
              ))}
            </div>

            <div className="odds-move-list">
              <strong>オッズ変動</strong>
              {liveSnapshot.oddsMoves.length > 0 ? (
                liveSnapshot.oddsMoves.map((move) => (
                  <article key={`${move.number}-${move.currentOdds}`}>
                    <TrendingDown size={16} />
                    <div>
                      <b>
                        {move.number} {move.name}
                      </b>
                      <small>
                        {move.previousOdds.toFixed(1)}倍 to {move.currentOdds.toFixed(1)}倍 / {move.reason}
                      </small>
                    </div>
                  </article>
                ))
              ) : (
                <small>大きな変動なし</small>
              )}
            </div>

            <div className="scratch-list">
              <strong>出走取消</strong>
              {liveSnapshot.scratches.length > 0 ? (
                liveSnapshot.scratches.map((scratch) => (
                  <article key={`${scratch.number}-${scratch.announcedAt}`}>
                    <XCircle size={16} />
                    <div>
                      <b>
                        {scratch.number} {scratch.name}
                      </b>
                      <small>{scratch.reason}</small>
                    </div>
                  </article>
                ))
              ) : (
                <small>取消なし</small>
              )}
            </div>
          </section>

          <section className="status-card">
            <div className="section-heading">
              <div>
                <p>Backend</p>
                <h3>裏側で動く処理</h3>
              </div>
              <Activity size={20} />
            </div>
            <div className="flow-list">
              <article className="done">
                <CheckCircle2 size={16} />
                <div>
                  <strong>開催予定</strong>
                  <small>JRA公式の今週開催を画面へ反映</small>
                </div>
              </article>
              <article className={selectedRace.runners.length > 0 ? "done" : "wait"}>
                <CheckCircle2 size={16} />
                <div>
                  <strong>出馬表</strong>
                  <small>{selectedRace.runners.length > 0 ? `${selectedRace.runners.length}頭を推定対象` : "JRA accessDあり・解析待ち"}</small>
                </div>
              </article>
              <article className={selectedRace.runners.length > 0 ? "running" : "wait"}>
                <Activity size={16} />
                <div>
                  <strong>予想</strong>
                  <small>勝率、複勝圏、買い目金額を計算</small>
                </div>
              </article>
              <article className="wait">
                <RefreshCcw size={16} />
                <div>
                  <strong>リアルタイム更新</strong>
                  <small>オッズ接続後に自動更新へ切替</small>
                </div>
              </article>
            </div>
          </section>

          <section className="source-card">
            <div className="section-heading">
              <div>
                <p>Source</p>
                <h3>今のデータ</h3>
              </div>
              <Database size={20} />
            </div>
            <p>{selectedRace.officialNote}</p>
            <dl>
              <div>
                <dt>予定</dt>
                <dd>JRA公式 今週の開催・注目レース</dd>
              </div>
              <div>
                <dt>出馬表</dt>
                <dd>{selectedRace.runners.length > 0 ? "馬名データを反映済み" : "JRA accessD出馬表を解析待ち"}</dd>
              </div>
              <div>
                <dt>オッズ</dt>
                <dd>現状は想定値。ライブ接続後に更新</dd>
              </div>
            </dl>
          </section>

          <section className="source-card">
            <div className="section-heading">
              <div>
                <p>Simulation</p>
                <h3>回収率バックテスト</h3>
              </div>
              <Trophy size={20} />
            </div>
            <div className="metric-grid">
              <article>
                <span>状態</span>
                <strong>{backtestSummary.status}</strong>
              </article>
              <article>
                <span>期間</span>
                <strong>{backtestSummary.window}</strong>
              </article>
              <article>
                <span>回収率</span>
                <strong>{formatPercent(backtestSummary.roi)}</strong>
              </article>
              <article>
                <span>的中率</span>
                <strong>{formatPercent(backtestSummary.hitRate)}</strong>
              </article>
              <article>
                <span>賭け金</span>
                <strong>{formatYen(backtestSummary.totalStake)}</strong>
              </article>
              <article>
                <span>払戻</span>
                <strong>{formatYen(backtestSummary.totalPayout)}</strong>
              </article>
              <article>
                <span>最大DD</span>
                <strong>{formatYen(backtestSummary.maxDrawdown)}</strong>
              </article>
              <article>
                <span>買い目</span>
                <strong>{backtestSummary.bets.toLocaleString("ja-JP")}</strong>
              </article>
            </div>
            <p>{backtestSummary.note}</p>
          </section>

          <section className="source-card">
            <div className="section-heading">
              <div>
                <p>Coverage</p>
                <h3>特徴量カバレッジ</h3>
              </div>
              <Database size={20} />
            </div>
            <div className="coverage-list">
              {dataCoverage.map((item) => (
                <article key={item.group}>
                  <div>
                    <strong>{item.group}</strong>
                    <small>{item.fields}</small>
                  </div>
                  <span>{item.state}</span>
                </article>
              ))}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}
