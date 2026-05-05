"use client";

import { useMemo, useState } from "react";

type Market = "JRA" | "NAR";

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
  status: "card" | "odds" | "watch";
  runners: Runner[];
};

type TicketTemplate = {
  type: string;
  selection: (top: RunnerProjection[]) => string;
  risk: number;
  probability: number;
  odds: number;
  model: string;
};

type RunnerProjection = Runner & {
  winProbability: number;
  placeProbability: number;
  fairOdds: number;
  edge: number;
  score: number;
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

const ticketTemplates: TicketTemplate[] = [
  {
    type: "複勝",
    selection: (top) => `${top[0].number}`,
    risk: 16,
    probability: 0.62,
    odds: 1.9,
    model: "place-calibrated",
  },
  {
    type: "ワイド",
    selection: (top) => `${top[0].number}-${top[1].number}`,
    risk: 32,
    probability: 0.31,
    odds: 5.4,
    model: "rank-pair",
  },
  {
    type: "単勝",
    selection: (top) => `${top[0].number}`,
    risk: 46,
    probability: 0.19,
    odds: 5.6,
    model: "win-ensemble",
  },
  {
    type: "馬連",
    selection: (top) => `${top[0].number}-${top[2].number}`,
    risk: 58,
    probability: 0.13,
    odds: 12.8,
    model: "rank-pair",
  },
  {
    type: "3連複",
    selection: (top) => `${top[0].number}-${top[1].number}-${top[2].number}`,
    risk: 74,
    probability: 0.055,
    odds: 31.2,
    model: "ticket-ev",
  },
  {
    type: "3連単",
    selection: (top) => `${top[0].number}-${top[2].number}-${top[1].number}`,
    risk: 91,
    probability: 0.018,
    odds: 128.4,
    model: "ticket-ev",
  },
];

const modelStack = [
  ["Win/Place", "単勝・複勝の確率校正"],
  ["RankDist", "着順分布から組合せ確率へ展開"],
  ["TicketEV", "券種別の期待値と購入点数"],
  ["OddsWatch", "パドック中のオッズ変動検知"],
];

const backtest = {
  window: "local backtest pending",
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

function formatPercent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatYen(value: number) {
  return yenFormatter.format(Math.round(value));
}

function roundStake(value: number) {
  return Math.max(100, Math.round(value / 100) * 100);
}

export default function Home() {
  const [selectedRaceId, setSelectedRaceId] = useState(races[0].id);
  const [riskLevel, setRiskLevel] = useState(48);
  const [bankroll, setBankroll] = useState(100000);

  const race = races.find((item) => item.id === selectedRaceId) ?? races[0];
  const activeBankroll = Number.isFinite(bankroll) ? Math.max(bankroll, 1000) : 100000;
  const riskRatio = riskLevel / 100;

  const projections = useMemo<RunnerProjection[]>(() => {
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

  const tickets = ticketTemplates
    .filter((ticket) => Math.abs(ticket.risk - riskLevel) <= 40 || ticket.risk <= riskLevel + 12)
    .map((ticket) => {
      const top = projections.slice(0, 3);
      const edge = ticket.probability * ticket.odds - 1 + (riskRatio - 0.45) * 0.08;
      const exposure = 0.006 + riskRatio * 0.027;
      const stake = roundStake(activeBankroll * exposure * Math.max(0.35, 1 + edge) * (ticket.risk / 100));
      return {
        ...ticket,
        selection: ticket.selection(top),
        edge,
        stake,
        expectedReturn: stake * ticket.odds * ticket.probability,
      };
    })
    .sort((a, b) => b.edge + b.risk / 150 - (a.edge + a.risk / 150))
    .slice(0, 5);

  const totalStake = tickets.reduce((sum, ticket) => sum + ticket.stake, 0);
  const expectedReturn = tickets.reduce((sum, ticket) => sum + ticket.expectedReturn, 0);
  const expectedRoi = totalStake > 0 ? expectedReturn / totalStake : 0;
  const riskLabel = riskLevel < 34 ? "ローリスク" : riskLevel < 67 ? "バランス" : "ハイリスク";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <img src="/racequant-icon.svg" alt="" />
          <div>
            <p>UmaLab</p>
            <h1>AI予想オペレーション</h1>
          </div>
        </div>
        <div className="topbar-metrics" aria-label="system status">
          <span>JRA/NAR</span>
          <span>UV backend</span>
          <span>Local CSV ready</span>
        </div>
      </header>

      <div className="workspace-grid">
        <aside className="panel schedule-panel">
          <div className="panel-title">
            <p>Calendar</p>
            <h2>開催カレンダー</h2>
          </div>

          <div className="race-list">
            {races.map((item) => (
              <button
                className={`race-button ${item.id === race.id ? "active" : ""}`}
                key={item.id}
                onClick={() => setSelectedRaceId(item.id)}
                type="button"
              >
                <span>{item.date} ({item.day}) {item.start}</span>
                <strong>{item.venue} {item.title}</strong>
                <em>{item.course}</em>
                <b>{item.market}</b>
              </button>
            ))}
          </div>

          <div className="control-stack">
            <label className="field">
              <span>軍資金</span>
              <input
                min={1000}
                onChange={(event) => setBankroll(Number(event.target.value))}
                step={1000}
                type="number"
                value={bankroll}
              />
            </label>

            <label className="field">
              <span>リスク許容度: {riskLabel} / {riskLevel}</span>
              <input
                max={100}
                min={0}
                onChange={(event) => setRiskLevel(Number(event.target.value))}
                type="range"
                value={riskLevel}
              />
            </label>

            <div className="risk-scale" aria-hidden="true">
              <span>堅実</span>
              <span>標準</span>
              <span>攻め</span>
            </div>
          </div>
        </aside>

        <section className="panel prediction-panel">
          <div className="race-heading">
            <div>
              <p>{race.grade} / {race.status.toUpperCase()}</p>
              <h2>{race.title}</h2>
              <span>{race.date} {race.start} / {race.venue} / {race.course}</span>
            </div>
            <strong>{riskLabel}</strong>
          </div>

          <div className="summary-grid">
            <Metric label="購入候補" value={`${tickets.length}件`} />
            <Metric label="想定投資" value={formatYen(totalStake)} />
            <Metric label="期待回収率" value={formatPercent(expectedRoi, 1)} />
            <Metric label="最大露出" value={formatPercent(totalStake / activeBankroll, 2)} />
          </div>

          <div className="section-title">
            <p>Recommendations</p>
            <h3>券種別AI出力</h3>
          </div>

          <div className="ticket-table">
            {tickets.map((ticket) => (
              <article key={`${ticket.type}-${ticket.selection}`}>
                <div>
                  <span>{ticket.type}</span>
                  <strong>{ticket.selection}</strong>
                  <small>{ticket.model}</small>
                </div>
                <dl>
                  <div>
                    <dt>的中率</dt>
                    <dd>{formatPercent(ticket.probability)}</dd>
                  </div>
                  <div>
                    <dt>想定オッズ</dt>
                    <dd>{ticket.odds.toFixed(1)}</dd>
                  </div>
                  <div>
                    <dt>Edge</dt>
                    <dd className={ticket.edge >= 0 ? "positive" : "negative"}>{formatPercent(ticket.edge)}</dd>
                  </div>
                  <div>
                    <dt>金額</dt>
                    <dd>{formatYen(ticket.stake)}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>

          <div className="section-title">
            <p>Runner ranking</p>
            <h3>出走馬スコア</h3>
          </div>

          <div className="runner-table">
            {projections.map((runner, index) => (
              <div key={runner.number} className="runner-row">
                <span>{index + 1}</span>
                <strong>{runner.number}. {runner.name}</strong>
                <em>{runner.jockey}</em>
                <b>{formatPercent(runner.winProbability)}</b>
                <small className={runner.drift < 0 ? "positive" : "negative"}>
                  {runner.drift > 0 ? "+" : ""}{runner.drift.toFixed(1)}%
                </small>
              </div>
            ))}
          </div>
        </section>

        <aside className="side-column">
          <section className="panel">
            <div className="panel-title">
              <p>Proof</p>
              <h2>シミュレーション実績</h2>
            </div>
            <div className="proof-grid">
              <Metric label="回収率" value={formatPercent(backtest.roi)} />
              <Metric label="的中率" value={formatPercent(backtest.hitRate)} />
              <Metric label="対象R" value={numberFormatter.format(backtest.races)} />
              <Metric label="最大DD" value={formatYen(backtest.maxDrawdown)} />
            </div>
            <p className="note">{backtest.window}</p>
          </section>

          <section className="panel">
            <div className="panel-title">
              <p>Live</p>
              <h2>直前オッズ監視</h2>
            </div>
            <div className="alert-list">
              {projections.slice(0, 3).map((runner) => (
                <article key={runner.number}>
                  <strong>{runner.number}. {runner.name}</strong>
                  <span className={runner.drift < 0 ? "positive" : "negative"}>
                    {runner.drift < 0 ? "買い方向" : "過熱"} {Math.abs(runner.drift).toFixed(1)}%
                  </span>
                </article>
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="panel-title">
              <p>Model stack</p>
              <h2>複数AIモデル</h2>
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

          <section className="panel">
            <div className="panel-title">
              <p>Data</p>
              <h2>自動取得基盤</h2>
            </div>
            <ol className="pipeline-list">
              <li>中央CSV: backend/data/keiba_data</li>
              <li>地方競馬: NARアダプタ追加枠</li>
              <li>出馬表・オッズ: 開催日ポーリング</li>
              <li>結果・払戻: 確定後に回収率へ反映</li>
            </ol>
          </section>
        </aside>
      </div>
    </main>
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
