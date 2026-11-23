-- 0002: let the server's secret key (service_role) use the trips table.
-- Newer Supabase projects don't grant table privileges automatically, so 0001 alone gave
-- "permission denied for table trips" (42501) even with the secret key. anon/authenticated stay revoked.
grant select, insert, update, delete on table public.trips to service_role;
