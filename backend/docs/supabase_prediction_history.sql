create table if not exists public.prediction_history (
  id uuid primary key default gen_random_uuid(),
  race_id text not null,
  race_date date not null,
  prediction jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (race_id, race_date)
);

create index if not exists prediction_history_race_date_idx
  on public.prediction_history (race_date desc);

create table if not exists public.race_cards (
  race_id text primary key,
  race_date date not null,
  venue text not null,
  race_no integer not null default 0,
  status text not null default '',
  market text not null default '',
  source_url text,
  source_checked_at timestamptz,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists race_cards_race_date_idx
  on public.race_cards (race_date desc, venue, race_no);

create table if not exists public.race_ingest_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz,
  finished_at timestamptz not null default now(),
  source text not null default 'netkeiba',
  start_date date,
  end_date date,
  races_found integer not null default 0,
  races_stored integer not null default 0,
  rows_found integer not null default 0,
  status text not null default 'unknown',
  message text,
  payload jsonb not null default '{}'::jsonb
);

create index if not exists race_ingest_runs_finished_at_idx
  on public.race_ingest_runs (finished_at desc);
