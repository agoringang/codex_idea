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
