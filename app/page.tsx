type Status = {
  raw_files: string[];
  normalized_tables: { name: string; rows: number; columns: string[]; updated_at?: string | null }[];
  feature_tables: { name: string; rows: number; columns: string[]; updated_at?: string | null }[];
  latest_model: string | null;
  message: string;
};

async function getStatus(): Promise<Status | null> {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${baseUrl}/status`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function Home() {
  const status = await getStatus();

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-50">
      <section className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
        <div className="rounded-3xl border border-zinc-800 bg-zinc-900/70 p-8 shadow-2xl">
          <p className="text-sm font-semibold text-emerald-300">UmaLab foundation v0.2</p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight md:text-6xl">
            データを読み込ませっぱなしにしない競馬AI基盤
          </h1>
          <p className="mt-5 max-w-3xl text-zinc-300">
            取得済みの豊富なデータは raw に保存し、parquet に正規化して、特徴量とモデルだけをAPIが軽く参照します。
            目指すのは情報量の多さではなく、勝率・適正オッズ・期待値・見送り判断まで一画面で出せるプロダクトです。
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <Metric title="Raw files" value={status?.raw_files.length ?? 0} />
          <Metric title="Normalized tables" value={status?.normalized_tables.length ?? 0} />
          <Metric title="Feature tables" value={status?.feature_tables.length ?? 0} />
          <Metric title="Model" value={status?.latest_model ? "ready" : "none"} />
        </div>

        <section className="grid gap-4 md:grid-cols-3">
          <Step title="1. Ingest" body="CSVを一度だけ正規化し、backend/data/normalized にparquet保存する。" />
          <Step title="2. Feature" body="オッズ順位、頭数、適性、騎手・調教師成績などを特徴量テーブルにまとめる。" />
          <Step title="3. Train / Predict" body="モデルはjoblibとして保存。APIは必要なレースだけを読み、期待値を返す。" />
        </section>

        <section className="rounded-3xl border border-zinc-800 bg-zinc-900 p-6">
          <h2 className="text-2xl font-bold">Pipeline status</h2>
          <p className="mt-2 text-zinc-300">{status?.message ?? "APIに接続できません。backendを起動してください。"}</p>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <TableList title="Normalized" rows={status?.normalized_tables ?? []} />
            <TableList title="Features" rows={status?.feature_tables ?? []} />
          </div>
        </section>
      </section>
    </main>
  );
}

function Metric({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-5">
      <p className="text-sm text-zinc-400">{title}</p>
      <p className="mt-2 text-3xl font-bold">{value}</p>
    </div>
  );
}

function Step({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
      <h3 className="text-xl font-bold">{title}</h3>
      <p className="mt-3 text-sm leading-6 text-zinc-300">{body}</p>
    </div>
  );
}

function TableList({
  title,
  rows,
}: {
  title: string;
  rows: { name: string; rows: number; columns: string[]; updated_at?: string | null }[];
}) {
  return (
    <div className="rounded-2xl bg-zinc-950 p-4">
      <h3 className="font-semibold">{title}</h3>
      <div className="mt-3 space-y-3">
        {rows.length === 0 ? (
          <p className="text-sm text-zinc-500">No tables yet.</p>
        ) : (
          rows.map((row) => (
            <div key={row.name} className="rounded-xl border border-zinc-800 p-3">
              <p className="font-medium">{row.name}</p>
              <p className="text-sm text-zinc-400">
                {row.rows.toLocaleString()} rows / {row.columns.length} columns
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
