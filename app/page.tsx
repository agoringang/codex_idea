"use client";

import { useMemo, useState } from "react";

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

type TicketProjection = Omit<TicketTemplate, "selection"> & {
  selection: string;
  edge: number;
  stake: number;
  expectedReturn: number;
};

type CalendarDay = {
  date: string;
  label: string;
  day: string;
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

const calendarDays: CalendarDay[] = [
  { date: "2026-05-05", label: "5/5", day: "火" },
  { date: "2026-05-06", label: "5/6", day: "水" },
  { date: "2026-05-07", label: "5/7", day: "木" },
  { date: "2026-05-08", label: "5/8", day: "金" },
  { date: "2026-05-09", label: "5/9", day: "土" },
  { date: "2026-05-10", label: "5/10", day: "日" },
  { date: "2026-05-11", label: "5/11", day: "月" },
];

const ticketTemplates: TicketTemplate[] = [
  { type: "複勝", selection: (top) => `${top[0].number}`, risk: 16, probability: 0.62, odds: 1.9, model: "Place" },
  { type: "ワイド", selection: (top) => `${top[0].number}-${top[1].number}`, risk: 32, probability: 0.31, odds: 5.4, model: "Pair" },
  { type: "単勝", selection: (top) => `${top[0].number}`, risk: 46, probability: 0.19, odds: 5.6, model: "Win" },
  { type: "馬連", selection: (top) => `${top[0].number}-${top[2].number}`, risk: 58, probability: 0.13, odds: 12.8, model: "Pair" },
  { type: "3連複", selection: (top) => `${top[0].number}-${top[1].number}-${top[2].number}`, risk: 74, probability: 0.055, odds: 31.2, model: "EV" },
  { type: "3連単", selection: (top) => `${top[0].number}-${top[2].number}-${top[1].number}`, risk: 91, probability: 0.018, odds: 128.4, model: "EV" },
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
  const [activeTab, setActiveTab] = useState<ViewTab>("predict");
  const [selectedRaceId, setSelectedRaceId] = useState(races[0].id);
  const [selectedDate, setSelectedDate] = useState(races[0].date);
  const [riskLevel, setRiskLevel] = useState(48);
  const [bankroll, setBankroll] = useState(100000);

  const race = races.find((item) => item.id === selectedRaceId) ?? races[0];
  const selectedDateRaces = races.filter((item) => item.date === selectedDate);
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

  const tickets = useMemo<TicketProjection[]>(() => {
    return ticketTemplates
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
  }, [activeBankroll, projections, riskLevel, riskRatio]);

  const totalStake = tickets.reduce((sum, ticket) => sum + ticket.stake, 0);
  const expectedReturn = tickets.reduce((sum, ticket) => sum + ticket.expectedReturn, 0);
  const expectedRoi = totalStake > 0 ? expectedReturn / totalStake : 0;
  const riskLabel = riskLevel < 34 ? "堅実" : riskLevel < 67 ? "標準" : "攻め";

  function selectRace(raceId: string, nextTab: ViewTab = activeTab) {
    const nextRace = races.find((item) => item.id === raceId);
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
            projections={projections}
            race={race}
            races={races}
            riskLabel={riskLabel}
            riskLevel={riskLevel}
            tickets={tickets}
            totalStake={totalStake}
          />
        )}

        {activeTab === "calendar" && (
          <CalendarPanel
            calendarDays={calendarDays}
            onDateSelect={setSelectedDate}
            onRaceSelect={(raceId) => selectRace(raceId, "predict")}
            races={races}
            selectedDate={selectedDate}
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
          <label className="field-card">
            <span>リスク {riskLabel} / {riskLevel}</span>
            <input
              max={100}
              min={0}
              onChange={(event) => onRiskChange(Number(event.target.value))}
              type="range"
              value={riskLevel}
            />
          </label>
        </div>
      </div>

      <div className="summary-strip">
        <Metric label="候補" value={`${tickets.length}件`} />
        <Metric label="投資" value={formatYen(totalStake)} />
        <Metric label="期待ROI" value={formatPercent(expectedRoi, 1)} />
        <Metric label="露出" value={formatPercent(totalStake / activeBankroll, 2)} />
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
              <strong>{ticket.selection}</strong>
              <small>{ticket.model}</small>
            </div>
            <div className="ticket-data">
              <Value label="的中" value={formatPercent(ticket.probability)} />
              <Value label="オッズ" value={ticket.odds.toFixed(1)} />
              <Value label="Edge" value={formatPercent(ticket.edge)} tone={ticket.edge >= 0 ? "positive" : "negative"} />
              <Value label="金額" value={formatYen(ticket.stake)} />
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
  onDateSelect,
  onRaceSelect,
  races,
  selectedDate,
  selectedDateRaces,
  selectedRaceId,
}: {
  calendarDays: CalendarDay[];
  onDateSelect: (date: string) => void;
  onRaceSelect: (raceId: string) => void;
  races: Race[];
  selectedDate: string;
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
          return (
            <button
              className={selectedDate === day.date ? "active" : ""}
              key={day.date}
              onClick={() => onDateSelect(day.date)}
              type="button"
            >
              <span>{day.day}</span>
              <strong>{day.label}</strong>
              <em>{dayRaces.length}R</em>
            </button>
          );
        })}
      </div>

      <div className="calendar-list">
        {selectedDateRaces.length > 0 ? (
          selectedDateRaces.map((item) => (
            <article className={item.id === selectedRaceId ? "active" : ""} key={item.id}>
              <div>
                <span>{item.start} / {item.market}</span>
                <strong>{item.venue} {item.title}</strong>
                <em>{item.course}</em>
              </div>
              <button onClick={() => onRaceSelect(item.id)} type="button">予想へ</button>
            </article>
          ))
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

function RunnerList({ projections }: { projections: RunnerProjection[] }) {
  return (
    <div className="runner-list">
      {projections.map((runner, index) => (
        <article key={runner.number}>
          <span>{index + 1}</span>
          <strong>{runner.number}. {runner.name}</strong>
          <em>{runner.jockey}</em>
          <b>{formatPercent(runner.winProbability)}</b>
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
