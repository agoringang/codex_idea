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

create or replace function public.set_umalab_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists prediction_history_set_updated_at on public.prediction_history;
create trigger prediction_history_set_updated_at
  before update on public.prediction_history
  for each row execute function public.set_umalab_updated_at();

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

drop trigger if exists race_cards_set_updated_at on public.race_cards;
create trigger race_cards_set_updated_at
  before update on public.race_cards
  for each row execute function public.set_umalab_updated_at();

create table if not exists public.race_schedule (
  race_date date not null,
  market text not null,
  venue text not null,
  race_count integer not null default 0,
  grade_races jsonb not null default '[]'::jsonb,
  source text not null default 'unknown',
  source_checked_at timestamptz,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (race_date, market, venue)
);

create index if not exists race_schedule_race_date_idx
  on public.race_schedule (race_date desc, market, venue);

drop trigger if exists race_schedule_set_updated_at on public.race_schedule;
create trigger race_schedule_set_updated_at
  before update on public.race_schedule
  for each row execute function public.set_umalab_updated_at();

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

alter table public.prediction_history enable row level security;
alter table public.race_cards enable row level security;
alter table public.race_schedule enable row level security;
alter table public.race_ingest_runs enable row level security;

drop policy if exists prediction_history_service_role_all on public.prediction_history;
create policy prediction_history_service_role_all
  on public.prediction_history
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists race_cards_service_role_all on public.race_cards;
create policy race_cards_service_role_all
  on public.race_cards
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists race_schedule_service_role_all on public.race_schedule;
create policy race_schedule_service_role_all
  on public.race_schedule
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists race_ingest_runs_service_role_all on public.race_ingest_runs;
create policy race_ingest_runs_service_role_all
  on public.race_ingest_runs
  for all
  to service_role
  using (true)
  with check (true);
