-- Atlas community reports (Supabase, free tier).
-- 1. Create a project at supabase.com, open SQL Editor, run this file.
-- 2. In GitHub: Settings -> Secrets and variables -> Actions -> Variables, add
--      SUPABASE_URL       = https://<project>.supabase.co
--      SUPABASE_ANON_KEY  = <the anon public key>
--    (the anon key is designed to be public; row-level security below is what protects the data)

create table if not exists public.reports (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  lon         double precision not null check (lon between -7.6 and -6.7),
  lat         double precision not null check (lat between 30.9 and 31.7),
  kind        text not null check (kind in ('water_level','road_blocked','damage','people_trapped','other')),
  severity    smallint not null check (severity between 1 and 3),
  note        text not null default '' check (char_length(note) <= 500),
  verified    boolean not null default false
);

alter table public.reports enable row level security;

-- anyone can read and submit; nobody can edit or delete through the public key
create policy "read reports"   on public.reports for select using (true);
create policy "submit reports" on public.reports for insert with check (verified = false);
-- moderators verify reports from the Supabase dashboard (service role bypasses RLS)

-- live updates in the web app
alter publication supabase_realtime add table public.reports;
