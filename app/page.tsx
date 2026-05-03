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
import { useEffect, useMemo, useState } from "react";
import type { Race, PricedRunner, Bet, LiveSnapshot, BackendStatus, RaceStatus } from "./types";

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatYen(value: number) {
  return new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY", maximumFractionDigits: 0 }).format(value);
}

// バックエンドのMLモデルの出力をシミュレートする関数
function estimate(race: Race): PricedRunner[] {
  if (race.runners.length === 0) return [];

  // 各特徴量の重み（本来はモデル学習で決定される）
  const weights = { rating: 0.6, jockey: 0.2, gate: 0.1, odds: 0.1 };

  // 騎手スコア（仮） - 本来は過去の成績データから算出
  const jockeyScores: Record<string, number> = {
    "C.ルメ": 1.1, "川田将": 1.08, "D.レーン": 1.08, "武豊": 1.05, "戸崎圭": 1.03,
    "横山和": 1.01, "北村友": 1.0, "岩田望": 0.99, "松山弘": 0.98,
  };

  // 各馬のスコア（ロジット）を計算
  const logits = race.runners.map((runner) => {
    // 1. ベースとなる能力指数 (rating)
    const ratingScore = (runner.rating - 80) / 10; // 平均が0になるようにスケール調整

    // 2. 騎手補正 (jockey)
    const jockeyScore = Math.log(jockeyScores[runner.jockey] ?? 1.0);

    // 3. 枠番補正 (gate) - コースによる有利不利を簡易的にシミュレート
    const gateScore = (race.course.includes("内") || runner.gate <= 4) ? 1.02 : (runner.gate >= 7 ? 0.98 : 1.0);

    // 4. オッズから市場評価を反映
    const oddsScore = Math.log(20 / runner.odds);

    // 5. タグによる補正（距離適性、調子など）
    let tagBoost = 1.0;
    if (race.course.includes("3200") && runner.tags.some((tag) => tag.includes("長距離"))) tagBoost *= 1.05;
    if (runner.tags.some((tag) => tag.includes("能力") || tag.includes("前年"))) tagBoost *= 1.03;
    if (runner.tags.some((tag) => tag.includes("騎手強化"))) tagBoost *= 1.02;

    // 各スコアを重み付けして合算
    const rawScore = 
        ratingScore * weights.rating +
        jockeyScore * weights.jockey +
        Math.log(gateScore) * weights.gate +
        oddsScore * weights.odds;
        
    return rawScore * tagBoost;
  });

  // ソフトマックス関数で確率に正規化
  const totalExp = logits.reduce((sum, logit) => sum + Math.exp(logit), 0);
  const winProbabilities = logits.map(logit => Math.exp(logit) / totalExp);

  return race.runners
    .map((runner, index) => {
      const winProbability = winProbabilities[index];
      // 複勝確率は、単勝確率と人気（オッズ）から簡易的に推定
      const placeProbability = clamp(winProbability * (2.8 - Math.log10(runner.odds)) + (runner.rating / 700), 0.05, 0.8);
      const fairOdds = 1 / winProbability;
      const edge = winProbability * runner.odds - 1;
      return { ...runner, winProbability, placeProbability, fairOdds, edge };
    })
    .sort((a, b) => b.winProbability - a.winProbability);
}

function riskMode(risk: number) {
  if (risk < 34) return "guard" as const;
  if (risk < 67) return "balanced" as const;
  return "attack" as const;
}

function riskLabel(risk: number) {
  const mode = riskMode(risk);
  if (mode === "guard") return "守り / 的中率重視";
  if (mode === "balanced") return "標準 / 期待値重視";
  return "攻め / 回収率重視";
}

function riskDescription(risk: number) {
  const mode = riskMode(risk);
  if (mode === "guard") return "複勝・ワイド中心。高配当より外しにくさを優先。";
  if (mode === "balanced") return "単勝・ワイド・馬連・馬単を混ぜ、的中率と回収率の中間を狙う。";
  return "3連単フォーメーション・マルチで点数を広げつつ、高回収を狙う。";
}

function formationTicketCount(firsts: PricedRunner[], seconds: PricedRunner[], thirds: PricedRunner[]) {
  let count = 0;
  firsts.forEach((first) => {
    seconds.forEach((second) => {
      thirds.forEach((third) => {
        if (new Set([first.number, second.number, third.number]).size === 3) count += 1;
      });
    });
  });
  return count;
}

function buildBets(runners: PricedRunner[], bankroll: number, risk: number, actualOrder?: number[]): Bet[] {
  if (runners.length < 2) return [];
  const mode = riskMode(risk);
  const stake = (ratio: number) => (bankroll <= 0 ? 0 : Math.max(100, Math.round((bankroll * ratio) / 100) * 100));
  const multiStake = (tickets: number, ratio: number) => {
    if (bankroll <= 0 || tickets <= 0) return { stake: 0, unitStake: 0 };
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
  const trifectaProbability = third ? clamp(first.winProbability * second.winProbability * third.winProbability * 2.1, 0.001, 0.09) : 0;
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

  // 実際の着順から的中判定を行うヘルパー関数
  const evaluateHits = (betsArray: Bet[]) => {
    if (!actualOrder || actualOrder.length < 3) return betsArray;
    const [first, second, third] = actualOrder;

    return betsArray.map((bet) => {
      let isHit = false;
      if (bet.type === "単勝") {
        isHit = bet.selection.startsWith(`${first} `);
      } else if (bet.type === "複勝") {
        isHit = bet.selection.startsWith(`${first} `) || bet.selection.startsWith(`${second} `) || bet.selection.startsWith(`${third} `);
      } else if (bet.type === "馬連" || bet.type === "ワイド") {
        const match = bet.selection.match(/(\d+)-(\d+)/);
        if (match) {
          const a = Number(match[1]), b = Number(match[2]);
          if (bet.type === "馬連") {
            isHit = (a === first && b === second) || (a === second && b === first);
          } else {
            const top3 = [first, second, third];
            isHit = top3.includes(a) && top3.includes(b);
          }
        }
      } else if (bet.type === "馬単") {
        const match = bet.selection.match(/(\d+)-(\d+)/);
        if (match) isHit = Number(match[1]) === first && Number(match[2]) === second;
      } else if (bet.type === "3連複") {
        const match = bet.selection.match(/(\d+)-(\d+)-(\d+)/);
        if (match) {
          const a = Number(match[1]), b = Number(match[2]), c = Number(match[3]);
          const top3 = [first, second, third];
          isHit = top3.includes(a) && top3.includes(b) && top3.includes(c);
        }
      } else if (bet.type === "3連単") {
        if (bet.strategy === "フォーメーション") {
          const match = bet.selection.match(/1着 ([\d,]+) \/ 2着 ([\d,]+) \/ 3着 ([\d,]+)/);
          if (match) {
            const firsts = match[1].split(",").map(Number);
            const seconds = match[2].split(",").map(Number);
            const thirds = match[3].split(",").map(Number);
            isHit = firsts.includes(first) && seconds.includes(second) && thirds.includes(third);
          }
        } else if (bet.strategy === "1頭軸マルチ") {
          const match = bet.selection.match(/軸 (\d+) \/ 相手 ([\d,]+)/);
          if (match) {
            const axis = Number(match[1]), opp = match[2].split(",").map(Number);
            const top3 = [first, second, third];
            if (top3.includes(axis)) {
              const others = top3.filter((x) => x !== axis);
              isHit = others.every((x) => opp.includes(x));
            }
          }
        } else if (bet.strategy === "2頭軸マルチ") {
          const match = bet.selection.match(/軸 (\d+)-(\d+) \/ 相手 ([\d,]+)/);
          if (match) {
            const axis1 = Number(match[1]), axis2 = Number(match[2]), opp = match[3].split(",").map(Number);
            const top3 = [first, second, third];
            if (top3.includes(axis1) && top3.includes(axis2)) {
              const other = top3.find((x) => x !== axis1 && x !== axis2);
              isHit = other !== undefined && opp.includes(other);
            }
          }
        }
      }
      return { ...bet, isHit };
    });
  };

  if (mode === "guard") {
    return evaluateHits([
      { type: "複勝", selection: `${first.number} ${first.name}`, probability: first.placeProbability, odds: placeOdds(first), edge: first.placeProbability * placeOdds(first) - 1, stake: stake(0.018), note: "最上位評価の複勝で外しにくさ優先" },
      { type: "ワイド", selection: `${first.number}-${second.number}`, probability: wideProbability, odds: wideOdds, edge: wideProbability * wideOdds - 1, stake: stake(0.014), note: `${first.name} / ${second.name}` },
      { type: "枠連", selection: `${first.gate}-${second.gate}`, probability: frameProbability, odds: frameOdds, edge: frameProbability * frameOdds - 1, stake: stake(0.01), note: "馬番より広く構える低リスク枠" },
      { type: "複勝", selection: `${second.number} ${second.name}`, probability: second.placeProbability, odds: placeOdds(second), edge: second.placeProbability * placeOdds(second) - 1, stake: stake(0.01), note: "対抗の複勝で回収を補う" },
    ]);
  }

  const balancedBets: Bet[] = [
    { type: "単勝", selection: `${first.number} ${first.name}`, probability: first.winProbability, odds: first.odds, edge: first.edge, stake: stake(0.014), note: "能力と安定度の軸" },
    { type: "ワイド", selection: `${first.number}-${second.number}`, probability: wideProbability, odds: wideOdds, edge: wideProbability * wideOdds - 1, stake: stake(0.012), note: `${first.name} / ${second.name}` },
    { type: "馬連", selection: `${first.number}-${second.number}`, probability: quinellaProbability, odds: quinellaOdds, edge: quinellaProbability * quinellaOdds - 1, stake: stake(0.008), note: "上位2頭の組み合わせ" },
    { type: "馬単", selection: `${first.number}-${second.number}`, probability: exactaProbability, odds: exactaOdds, edge: exactaProbability * exactaOdds - 1, stake: stake(0.006), note: "本命から対抗への順序指定" },
    { type: "複勝", selection: `${darkHorse.number} ${darkHorse.name}`, probability: darkHorse.placeProbability, odds: placeOdds(darkHorse), edge: darkHorse.placeProbability * placeOdds(darkHorse) - 1, stake: stake(0.008), note: "妙味寄りの保険" },
  ];
  if (mode === "balanced" || !third || runners.length < 5) return evaluateHits(balancedBets);

  return evaluateHits([
    { type: "3連単", strategy: "フォーメーション", selection: `1着 ${topSix.slice(0, 2).map((runner) => runner.number).join(",")} / 2着 ${topSix.slice(0, 4).map((runner) => runner.number).join(",")} / 3着 ${topSix.map((runner) => runner.number).join(",")}`, probability: formationProbability, odds: formationOdds, edge: formationProbability * formationOdds - 1, stake: formationStake.stake, tickets: formationTickets, unitStake: formationStake.unitStake, note: "1点勝負より的中範囲を広げる本線" },
    { type: "3連単", strategy: "2頭軸マルチ", selection: `軸 ${first.number}-${second.number} / 相手 ${topSix.slice(2).map((runner) => runner.number).join(",")}`, probability: twoAxisProbability, odds: twoAxisOdds, edge: twoAxisProbability * twoAxisOdds - 1, stake: twoAxisStake.stake, tickets: twoAxisTickets, unitStake: twoAxisStake.unitStake, note: "軸2頭の着順入替まで拾う" },
    { type: "3連複", selection: `${first.number}-${second.number}-${third.number}`, probability: trioProbability, odds: trioOdds, edge: trioProbability * trioOdds - 1, stake: stake(0.011), note: "点数を絞る高回収枠" },
    { type: "3連単", strategy: "1頭軸マルチ", selection: `軸 ${first.number} / 相手 ${topFive.slice(1).map((runner) => runner.number).join(",")}`, probability: oneAxisProbability, odds: oneAxisOdds, edge: oneAxisProbability * oneAxisOdds - 1, stake: oneAxisStake.stake, tickets: oneAxisTickets, unitStake: oneAxisStake.unitStake, note: "本命が3着以内なら順序違いまで拾う" },
    { type: "馬単", selection: `${first.number}-${second.number}`, probability: exactaProbability, odds: exactaOdds, edge: exactaProbability * exactaOdds - 1, stake: stake(0.012), note: "順序まで取りに行く攻め筋" },
    { type: "単勝", selection: `${first.number} ${first.name}`, probability: first.winProbability, odds: first.odds, edge: first.edge, stake: stake(0.009), note: "軸馬の勝ち切り" },
    { type: "馬連", selection: `${first.number}-${second.number}`, probability: quinellaProbability, odds: quinellaOdds, edge: quinellaProbability * quinellaOdds - 1, stake: stake(0.007), note: "順序違いの保険" },
    { type: "単勝", selection: `${darkHorse.number} ${darkHorse.name}`, probability: darkHorse.winProbability, odds: darkHorse.odds, edge: darkHorse.edge, stake: stake(0.006), note: "穴の跳ね返り狙い" },
    { type: "ワイド", selection: `${first.number}-${darkHorse.number}`, probability: attackWideProbability, odds: attackWideOdds, edge: attackWideProbability * attackWideOdds - 1, stake: stake(0.005), note: "軸と穴を絡める" },
  ]);
}

function statusText(status: RaceStatus) {
  if (status === "finished") return "終了済";
  if (status === "prediction-ready") return "予想表示中";
  if (status === "card-ready") return "簡易予想";
  if (status === "racecard-available") return "出馬表あり";
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
    result: { status: "pending", message: "結果確定待ち" },
    alerts: [race.status === "schedule-only" ? "開催予定を監視中" : "JRA accessD出馬表あり", "オッズ取得待ち", "取消情報なし"],
  };
}

function stageClass(status: BackendStatus["stages"][number]["status"]) {
  if (status === "ready") return "done";
  if (status === "running") return "running";
  return "wait";
}

function stageIcon(status: BackendStatus["stages"][number]["status"]) {
  if (status === "ready") return <CheckCircle2 size={16} />;
  if (status === "blocked") return <AlertTriangle size={16} />;
  return <Activity size={16} />;
}

export default function Home() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null);
  const [racesData, setRacesData] = useState<Race[]>([]); // モックデータを初期値としてセット
  const [snapshotsData, setSnapshotsData] = useState<Record<string, LiveSnapshot>>({});
  const [selectedRaceId, setSelectedRaceId] = useState("kyoto-20260503-11");
  const [selectedVenue, setSelectedVenue] = useState("京都");
  const [bankroll, setBankroll] = useState(100000);
  const [risk, setRisk] = useState(42);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [scheduleView, setScheduleView] = useState("upcoming");

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

    const fetchData = async () => {
      try {
        const [statusRes, racesRes] = await Promise.all([
          fetch(`${baseUrl}/status`).catch(() => null),
          fetch(`${baseUrl}/races`).catch(() => null),
        ]);

        if (statusRes?.ok) setBackendStatus(await statusRes.json());
        
        if (racesRes?.ok) {
          const apiRaces = await racesRes.json();
          if (Array.isArray(apiRaces) && apiRaces.length > 0) {
            setRacesData(apiRaces);
            // If the selected race is not in the new list, default to the first one
            if (!apiRaces.some((race: Race) => race.id === selectedRaceId)) {
              setSelectedRaceId(apiRaces[0].id);
            }
          }
        }
        
      } catch (err) {
        console.error("データの取得に失敗しました", err);
      }
    };

    // 初回マウント時に取得
    fetchData();

    // 30秒ごとに自動更新（ポーリング）
    const intervalId = setInterval(fetchData, 30000);
    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
    let cancelled = false;

    const fetchSnapshot = async () => {
      try {
        const snapshotRes = await fetch(`${baseUrl}/snapshots/${selectedRaceId}`).catch(() => null);
        if (!snapshotRes?.ok) return;

        const apiSnapshot = await snapshotRes.json();
        if (!cancelled && apiSnapshot && typeof apiSnapshot === "object") {
          setSnapshotsData({ [selectedRaceId]: apiSnapshot });
        }
      } catch (err) {
        console.error("スナップショットの取得に失敗しました", err);
      }
    };

    fetchSnapshot();
    const intervalId = setInterval(fetchSnapshot, 30000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [selectedRaceId]);

  const venueTabs = useMemo(() => ["すべて", ...Array.from(new Set(racesData.map((race) => race.venue)))], [racesData]);
  const filteredRaces = useMemo(() => (selectedVenue === "すべて" ? racesData : racesData.filter((race) => race.venue === selectedVenue)), [selectedVenue, racesData]);
  const selectedRace = racesData.find((race) => race.id === selectedRaceId) ?? racesData[0];

  const pricedRunners = useMemo(() => {
    if (!selectedRace) return [];
    return estimate(selectedRace);
  }, [selectedRace]);

  const liveSnapshot = useMemo(() => {
    if (!selectedRace) return null;
    return snapshotsData[selectedRace.id] ?? defaultLiveSnapshot(selectedRace);
  }, [selectedRace, snapshotsData]);

  const bets = useMemo(() => {
    if (!pricedRunners || !liveSnapshot) return [];
    return buildBets(pricedRunners, bankroll, risk, liveSnapshot.result.order);
  }, [pricedRunners, bankroll, risk, liveSnapshot]);

  if (!selectedRace || !liveSnapshot) {
    return <main className="app-shell" style={{ padding: "3rem", display: "flex", justifyContent: "center", color: "var(--muted)" }}><Activity className="animate-spin" style={{ marginRight: "8px" }} />データを読み込んでいます...</main>;
  }
  
  const top = pricedRunners[0];
  const second = pricedRunners[1];
  const third = pricedRunners[2];
  const totalStake = bets.reduce((sum, bet) => sum + bet.stake, 0);
  const apiBacktest = backendStatus?.backtest;
  const apiCoverage = backendStatus?.feature_coverage ?? [];
  const apiStages = backendStatus?.stages ?? [];
  const currentRiskLabel = riskLabel(risk);
  const currentRiskDescription = riskDescription(risk);
  const setVenueTab = (venue: string) => {
    setSelectedVenue(venue);
    const nextRaces = venue === "すべて" ? racesData : racesData.filter((race) => race.venue === venue);
    if (!nextRaces.some((race) => race.id === selectedRaceId)) setSelectedRaceId(nextRaces[0]?.id ?? racesData[0].id);
  };

  const upcomingRaces = filteredRaces.filter((r) => r.status !== "finished");
  const finishedRaces = filteredRaces.filter((r) => r.status === "finished");

  return (
    <main className="app-shell">
      <section className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><img alt="" src="/racequant-icon.svg" /></div>
          <div><p>RaceQuant Lab</p><h1>次のレース予想</h1></div>
        </div>
        <div className="topbar-actions">
          <a className="apps-link" href="https://agoringang.com/#apps" rel="noreferrer" target="_blank">
            <span className="apps-link-icon" aria-hidden="true"><Grid2X2 size={17} /></span>
            <span>他のアプリを見る</span><ExternalLink size={14} />
          </a>
          <span className="status-pill"><CalendarDays size={16} />{currentTime.toLocaleString("ja-JP", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" })} / 全{racesData.length}R</span>
          <span className="status-pill caution"><ShieldAlert size={16} />投資保証なし</span>
        </div>
      </section>

      <section className="page-grid">
        <aside className="schedule-panel">
          <div className="panel-heading"><div><p>Upcoming JRA</p><h2>全レース予定</h2></div><RefreshCcw size={19} /></div>
          <div className="venue-tabs" aria-label="会場タブ">
            {venueTabs.map((venue) => {
              const count = venue === "すべて" ? racesData.length : racesData.filter((race) => race.venue === venue).length;
              return <button className={selectedVenue === venue ? "active" : ""} key={venue} onClick={() => setVenueTab(venue)} type="button"><strong>{venue}</strong><span>{count}R</span></button>;
            })}
          </div>
          <div className="race-count">{selectedVenue} / 表示 {filteredRaces.length}R</div>
          <div className="schedule-tabs">
            <button className={scheduleView === "upcoming" ? "active" : ""} onClick={() => setScheduleView("upcoming")}>開催予定 ({upcomingRaces.length})</button>
            <button className={scheduleView === "finished" ? "active" : ""} onClick={() => setScheduleView("finished")}>終了済 ({finishedRaces.length})</button>
          </div>
          <div className="race-list">
            {scheduleView === "upcoming" && upcomingRaces.map((race) => (
              <button className={`race-button ${race.id === selectedRace.id ? "active" : ""}`} key={race.id} onClick={() => setSelectedRaceId(race.id)} type="button">
                <span>{race.date} {race.day} / {race.venue} {race.raceNo}</span>
                <strong>{race.title} <small>{race.grade}</small></strong>
                <em>{race.start}発走 / {race.course}</em>
                <b>{statusText(race.status)}</b>
              </button>
            ))}
            {scheduleView === "finished" && finishedRaces.map((race) => (
              <button className={`race-button ${race.id === selectedRace.id ? "active" : ""}`} key={race.id} onClick={() => setSelectedRaceId(race.id)} type="button" style={{ opacity: 0.8 }}>
                <span>{race.date} {race.day} / {race.venue} {race.raceNo}</span>
                <strong>{race.title} <small>{race.grade}</small></strong>
                <em>結果確定済み</em>
                <b>{statusText(race.status)}</b>
              </button>
            ))}
          </div>
          <div className="bankroll-box">
            <div className="panel-heading compact"><div><p>Stake</p><h2>このレースの軍資金</h2></div><WalletCards size={18} /></div>
            <label className="field"><span>このレースの上限</span><input inputMode="numeric" min={1000} onChange={(event) => setBankroll(Number(event.target.value) || 0)} step={1000} type="number" value={bankroll} /></label>
            <label className="slider-field"><span>リスク/リターン {risk} / {currentRiskLabel}</span><input max={100} min={0} onChange={(event) => setRisk(Number(event.target.value))} type="range" value={risk} /></label>
            <div className="risk-scale" aria-hidden="true"><span>守り</span><span>標準</span><span>攻め</span></div>
            <p className="strategy-note">{currentRiskDescription}</p>
          </div>
        </aside>

        <section className="prediction-panel">
          <div className="race-hero"><div><p>表示中</p><h2>{selectedRace.date} {selectedRace.venue}{selectedRace.raceNo} {selectedRace.title}</h2><span>{selectedRace.meeting} / {selectedRace.start}発走 / {selectedRace.grade} / {selectedRace.course}</span></div><div className="hero-badge">{statusText(selectedRace.status)}</div></div>
          {pricedRunners.length > 0 ? <>
            <div className="summary-grid">
              <article><Target size={19} /><span>本命</span><strong>{top?.number} {top?.name}</strong><small>勝率 {formatPercent(top?.winProbability ?? 0)} / 妥当 {top?.fairOdds.toFixed(1)}倍</small></article>
              <article><Sparkles size={19} /><span>対抗</span><strong>{second?.number} {second?.name}</strong><small>勝率 {formatPercent(second?.winProbability ?? 0)}</small></article>
              <article><Gauge size={19} /><span>穴候補</span><strong>{third?.number} {third?.name}</strong><small>複勝圏 {formatPercent(third?.placeProbability ?? 0)}</small></article>
              <article><CircleDollarSign size={19} /><span>投下予定</span><strong>{formatYen(totalStake)}</strong><small>軍資金の {bankroll ? ((totalStake / bankroll) * 100).toFixed(1) : "0.0"}%</small></article>
            </div>
            <section className="ticket-panel"><div className="section-heading"><div><p>Tickets</p><h3>{liveSnapshot.result.order ? "シミュレーション結果" : "今買うならこの順"}</h3></div><ListChecks size={20} /></div><div className="ticket-list">{bets.map((bet) => <article key={`${bet.type}-${bet.selection}`} style={bet.isHit ? { borderColor: "#10b981", backgroundColor: "rgba(16, 185, 129, 0.05)" } : {}}><div><span>{bet.type}</span><strong>{bet.selection} {bet.isHit && <span style={{ color: "#10b981", fontSize: "12px", marginLeft: "6px", display: "inline-flex", alignItems: "center", gap: "2px" }}><Trophy size={12} />的中</span>}</strong><small>{bet.strategy ? `${bet.strategy} / ` : ""}{bet.note}{bet.tickets && bet.tickets > 1 && bet.unitStake ? ` / ${bet.tickets}点 x ${formatYen(bet.unitStake)}` : ""}</small></div><div className="ticket-side"><strong>{formatYen(bet.stake)}</strong><small>確率 {formatPercent(bet.probability)} / 想定 {bet.odds.toFixed(1)}倍</small></div></article>)}</div></section>
            <section className="runner-panel"><div className="section-heading"><div><p>Runners</p><h3>出走馬と推定順位</h3></div><Database size={20} /></div><div className="runner-table"><div className="runner-row head"><span>印</span><span>馬番</span><span>馬名</span><span>騎手</span><span>勝率</span><span>妙味</span></div>{pricedRunners.map((runner, index) => <div className="runner-row" key={runner.number}><span>{index === 0 ? "◎" : index === 1 ? "○" : index === 2 ? "▲" : index < 5 ? "△" : ""}</span><span className="number">{runner.number}</span><span className="runner-name"><strong>{runner.name}</strong><small>{runner.tags.join(" / ")}</small></span><span>{runner.jockey}</span><span>{formatPercent(runner.winProbability)}</span><span className={runner.edge > 0 ? "positive" : "muted"}>{formatPercent(runner.edge)}</span></div>)}</div></section>
          </> : <div className="empty-state"><AlertTriangle size={24} /><strong>このレースは出馬表解析待ち</strong><span>JRA出馬表は確認対象です。馬名・オッズを取り込んだら予想と買い目を表示します。</span></div>}
        </section>

        <aside className="side-panel">
          <section className={`live-card result-${liveSnapshot.result.status}`}>
            <div className="section-heading"><div><p>Live monitor</p><h3>自動取得・更新</h3></div><BellRing size={20} /></div>
            <div className="live-status-grid"><article><strong>出馬表</strong><span>{liveSnapshot.racecardStatus === "parsed" ? "解析済み" : liveSnapshot.racecardStatus === "available" ? "取得対象" : "待機"}</span></article><article><strong>オッズ</strong><span>{liveSnapshot.oddsStatus === "monitoring" ? "監視中" : liveSnapshot.oddsStatus === "closed" ? "締切" : "待機"}</span></article><article><strong>結果</strong><span>{liveSnapshot.resultStatus === "official" ? "確定" : "待ち"}</span></article><article><strong>更新</strong><span>{liveSnapshot.nextPollSeconds}秒間隔</span></article></div>
            <div className="result-banner">{liveSnapshot.result.status === "hit" || bets.some((b) => b.isHit) ? <Trophy size={18} /> : <Activity size={18} />}<div><strong>{bets.some((b) => b.isHit) ? "シミュレーション的中" : liveSnapshot.result.status === "official" ? "結果確定" : liveSnapshot.result.status === "hit" ? "的中" : liveSnapshot.result.status === "miss" ? "不的中" : liveSnapshot.result.status === "refund" ? "返還" : "結果待ち"}</strong><small>{liveSnapshot.result.message}{liveSnapshot.result.order ? ` / 着順: ${liveSnapshot.result.order.join(" - ")}` : ""}{liveSnapshot.result.payout ? ` / 払戻 ${formatYen(liveSnapshot.result.payout)}` : ""}</small></div></div>
            <div className="live-alerts">{liveSnapshot.alerts.map((alert) => <span key={alert}>{alert}</span>)}</div>
            <div className="odds-move-list"><strong>オッズ変動</strong>{(liveSnapshot.oddsMoves?.length ?? 0) > 0 ? liveSnapshot.oddsMoves?.map((move) => <article key={`${move.number}-${move.currentOdds}`}><TrendingDown size={16} /><div><b>{move.number} {move.name}</b><small>{move.previousOdds.toFixed(1)}倍 to {move.currentOdds.toFixed(1)}倍 / {move.reason}</small></div></article>) : <small>大きな変動なし</small>}</div>
            <div className="scratch-list"><strong>出走取消</strong>{(liveSnapshot.scratches?.length ?? 0) > 0 ? liveSnapshot.scratches?.map((scratch) => <article key={`${scratch.number}-${scratch.announcedAt}`}><XCircle size={16} /><div><b>{scratch.number} {scratch.name}</b><small>{scratch.reason}</small></div></article>) : <small>取消なし</small>}</div>
          </section>

          <section className="status-card">
            <div className="section-heading"><div><p>Backend</p><h3>裏側で動く処理</h3></div><Activity size={20} /></div>
            <div className="flow-list">
              {(apiStages.length > 0 ? apiStages : []).map((stage) => <article key={stage.id} className={stageClass(stage.status)}>{stageIcon(stage.status)}<div><strong>{stage.label}</strong><small>{stage.detail}</small></div></article>)}
            </div>
          </section>

          <section className="source-card"><div className="section-heading"><div><p>Source</p><h3>今のデータ</h3></div><Database size={20} /></div><p>{selectedRace.officialNote}</p><dl><div><dt>予定</dt><dd>JRA公式 今週の開催・注目レース</dd></div><div><dt>出馬表</dt><dd>{selectedRace.runners.length > 0 ? "馬名データを反映済み" : "JRA accessD出馬表を解析待ち"}</dd></div><div><dt>モデル</dt><dd>{backendStatus ? backendStatus.data_window : "FastAPI接続待ち"}</dd></div></dl></section>

          <section className="source-card">
            <div className="section-heading"><div><p>Simulation</p><h3>回収率バックテスト</h3></div><Trophy size={20} /></div>
            <div className="metric-grid">
              <article><span>状態</span><strong>{apiBacktest?.status ?? "待機"}</strong></article>
              <article><span>期間</span><strong>{apiBacktest?.window ?? "-"}</strong></article>
              <article><span>回収率</span><strong>{formatPercent(apiBacktest?.roi ?? 0)}</strong></article>
              <article><span>的中率</span><strong>{formatPercent(apiBacktest?.hit_rate ?? 0)}</strong></article>
              <article><span>賭け金</span><strong>{formatYen(apiBacktest?.total_stake ?? 0)}</strong></article>
              <article><span>払戻</span><strong>{formatYen(apiBacktest?.total_payout ?? 0)}</strong></article>
              <article><span>最大DD</span><strong>{formatYen(apiBacktest?.max_drawdown ?? 0)}</strong></article>
              <article><span>買い目</span><strong>{(apiBacktest?.bets ?? 0).toLocaleString("ja-JP")}</strong></article>
            </div>
            <p>{apiBacktest?.note ?? "バックエンドからのバックテスト結果を待っています。"}</p>
          </section>

          <section className="source-card">
            <div className="section-heading"><div><p>Coverage</p><h3>特徴量カバレッジ</h3></div><Database size={20} /></div>
            <div className="coverage-list">
              {apiCoverage.map((item: any) => <article key={item.group}><div><strong>{item.group}</strong><small>{Array.isArray(item.fields) ? item.fields.join(" / ") : item.fields}</small></div><span>{item.status ?? item.state}</span></article>)}
            </div>
          </section>
        </aside>
      </section>
    </main>
  );
}
