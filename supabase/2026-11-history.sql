-- History backup: lets admin accounts read every weekly snapshot and brief, so admin.html can
-- download the full history as one file. Paste into Supabase → SQL Editor → Run. Safe to run more than once.
drop policy if exists "admins read snapshots" on public.snapshots;
create policy "admins read snapshots" on public.snapshots for select
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_admin));
drop policy if exists "admins read briefs" on public.briefs;
create policy "admins read briefs" on public.briefs for select
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.is_admin));
