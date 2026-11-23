-- 0001: saved trips (no sign-in). Run in the Supabase SQL Editor: dev first, prod only after review.
-- Only the Flask server touches this table, using the secret key (which bypasses RLS).

create table if not exists public.trips (
  id          uuid primary key default gen_random_uuid(),  -- random, unguessable: the trip's private link
  state       jsonb not null default '{}'::jsonb,          -- { origin, notes, ideas, decided, prefs, rejected }
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint trips_state_size check (pg_column_size(state) < 40000)  -- backstop for the server's 20 KB cap
);

-- Row Level Security ON and NO policies = the public (anon / publishable) key can't select, insert,
-- update or delete anything. The server's secret key bypasses RLS.
alter table public.trips enable row level security;

-- Belt and braces: also remove the table privileges Supabase grants to the public roles by default.
revoke all on table public.trips from anon, authenticated;
