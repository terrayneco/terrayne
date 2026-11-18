-- Terrayne accounts schema. Paste into Supabase > SQL Editor and run once (safe to re-run).

-- Profiles: one row per user, created automatically on sign-up.
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text default '',
  company text default '',
  job_title text default '',
  plan text not null default 'free' check (plan in ('free','investor','pro','enterprise')),
  status text not null default 'none',          -- Stripe subscription status: active, trialing, past_due, canceled, none
  billing_interval text,                        -- month | year
  current_period_end timestamptz,
  cancel_at_period_end boolean not null default false,
  stripe_customer_id text unique,
  stripe_subscription_id text,
  team_owner uuid references public.profiles(id) on delete set null,  -- set for Enterprise team members
  brief_email boolean not null default true,
  is_admin boolean not null default false,
  created_at timestamptz not null default now()
);

-- Neighbourhoods a user follows (names match data "n" field, e.g. 'Nine Elms').
alter table public.profiles add column if not exists is_admin boolean not null default false;
alter table public.profiles drop constraint if exists profiles_plan_check;
alter table public.profiles add constraint profiles_plan_check check (plan in ('free','investor','pro','enterprise'));

create table if not exists public.watchlist (
  user_id uuid not null references public.profiles(id) on delete cascade,
  area text not null,
  created_at timestamptz not null default now(),
  primary key (user_id, area)
);

-- Enterprise invitations (owner invites colleagues by email).
create table if not exists public.team_invites (
  owner uuid not null references public.profiles(id) on delete cascade,
  email text not null,
  created_at timestamptz not null default now(),
  primary key (owner, email)
);

-- Full weekly Momentum Index (all neighbourhoods); history for paid users.
create table if not exists public.snapshots (
  generated date primary key,
  data jsonb not null
);

-- Weekly Monday briefs, one per neighbourhood per week.
create table if not exists public.briefs (
  week date not null,
  area text not null,
  title text not null,
  body text not null,
  data jsonb not null default '{}'::jsonb,
  primary key (week, area)
);

-- Effective plan: own subscription, or the Enterprise owner's if on a team.
create or replace function public.effective_plan(uid uuid) returns text
language sql stable security definer set search_path = public as $$
  select case
    when p.plan <> 'free' and p.status in ('active','trialing','past_due','comp') then p.plan
    when o.plan = 'enterprise' and o.status in ('active','trialing','past_due','comp') then 'enterprise'
    else 'free' end
  from public.profiles p left join public.profiles o on o.id = p.team_owner
  where p.id = uid
$$;

create or replace function public.is_paid(uid uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(public.effective_plan(uid) <> 'free', false)
$$;

-- Monday briefs are Professional and Enterprise only.
create or replace function public.has_briefs(uid uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce(public.effective_plan(uid) in ('pro','enterprise'), false)
$$;

-- New user -> profile; join a team if they were invited.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare inv record;
begin
  insert into public.profiles (id, email, full_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name', ''))
  on conflict (id) do nothing;
  select * into inv from public.team_invites where lower(email) = lower(new.email) limit 1;
  if found then
    update public.profiles set team_owner = inv.owner where id = new.id;
    delete from public.team_invites where owner = inv.owner and lower(email) = lower(new.email);
  end if;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Keep profile email in sync when a user changes it.
create or replace function public.handle_email_change() returns trigger
language plpgsql security definer set search_path = public as $$
begin update public.profiles set email = new.email where id = new.id; return new; end $$;
drop trigger if exists on_auth_user_email on auth.users;
create trigger on_auth_user_email after update of email on auth.users
  for each row execute function public.handle_email_change();

-- Users may edit only their own name/company/title/email preference, never billing fields.
create or replace function public.guard_profile() returns trigger
language plpgsql as $$
begin
  if current_user in ('authenticated','anon') then
    new.plan := old.plan; new.status := old.status; new.billing_interval := old.billing_interval;
    new.current_period_end := old.current_period_end; new.cancel_at_period_end := old.cancel_at_period_end;
    new.stripe_customer_id := old.stripe_customer_id; new.stripe_subscription_id := old.stripe_subscription_id;
    new.email := old.email; new.id := old.id; new.is_admin := old.is_admin;
    -- members may leave a team (set null) but not join one themselves
    if new.team_owner is distinct from old.team_owner and new.team_owner is not null then new.team_owner := old.team_owner; end if;
  end if;
  return new;
end $$;
drop trigger if exists guard_profile on public.profiles;
create trigger guard_profile before update on public.profiles for each row execute function public.guard_profile();

-- Watchlist limits: free 0, investor 3 saved places, pro 10, enterprise unlimited.
create or replace function public.watchlist_limit() returns trigger
language plpgsql security definer set search_path = public as $$
declare pl text := public.effective_plan(new.user_id); n int;
begin
  select count(*) into n from public.watchlist where user_id = new.user_id;
  if pl = 'free' then raise exception 'Upgrade to Investor or Professional to save places'; end if;
  if pl = 'investor' and n >= 3 then raise exception 'Investor includes up to 3 saved places'; end if;
  if pl = 'pro' and n >= 10 then raise exception 'Professional watchlists hold up to 10 neighbourhoods'; end if;
  return new;
end $$;
drop trigger if exists watchlist_limit on public.watchlist;
create trigger watchlist_limit before insert on public.watchlist for each row execute function public.watchlist_limit();

-- Enterprise seat limit: owner + 4.
create or replace function public.invite_limit() returns trigger
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if public.effective_plan(new.owner) <> 'enterprise' or (select team_owner from public.profiles where id = new.owner) is not null then
    raise exception 'Only Enterprise account owners can invite colleagues'; end if;
  select (select count(*) from public.profiles where team_owner = new.owner) + (select count(*) from public.team_invites where owner = new.owner) into n;
  if n >= 4 then raise exception 'Enterprise includes up to 5 users'; end if;
  new.email := lower(new.email);
  return new;
end $$;
drop trigger if exists invite_limit on public.team_invites;
create trigger invite_limit before insert on public.team_invites for each row execute function public.invite_limit();

-- Row-level security
alter table public.profiles enable row level security;
alter table public.watchlist enable row level security;
alter table public.team_invites enable row level security;
alter table public.snapshots enable row level security;
alter table public.briefs enable row level security;

drop policy if exists "own profile read" on public.profiles;
create policy "own profile read" on public.profiles for select using (id = auth.uid() or team_owner = auth.uid());
drop policy if exists "own profile update" on public.profiles;
create policy "own profile update" on public.profiles for update using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "own watchlist" on public.watchlist;
create policy "own watchlist" on public.watchlist for all using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "own invites" on public.team_invites;
create policy "own invites" on public.team_invites for all using (owner = auth.uid()) with check (owner = auth.uid());

drop policy if exists "paid snapshots" on public.snapshots;
create policy "paid snapshots" on public.snapshots for select using (public.is_paid(auth.uid()));

drop policy if exists "paid briefs" on public.briefs;
create policy "paid briefs" on public.briefs for select using (public.has_briefs(auth.uid()));

-- Owners can remove members from their team.
create or replace function public.remove_member(member uuid) returns void
language sql security definer set search_path = public as $$
  update public.profiles set team_owner = null where id = member and team_owner = auth.uid()
$$;
grant execute on function public.remove_member(uuid) to authenticated;
grant execute on function public.effective_plan(uuid) to authenticated;
grant execute on function public.has_briefs(uuid) to authenticated;

-- Founding-access requests from the home page form (anyone can submit; only admins read, via the admin function).
create table if not exists public.access_requests (
  id bigint generated always as identity primary key,
  name text, email text not null, company text, interest text,
  created_at timestamptz not null default now()
);
alter table public.access_requests enable row level security;
drop policy if exists "anyone can request" on public.access_requests;
create policy "anyone can request" on public.access_requests for insert to anon, authenticated
  with check (length(email) between 3 and 200 and coalesce(length(name),0) < 200 and coalesce(length(company),0) < 200 and coalesce(length(interest),0) < 2000);

-- Log of each weekly email run (written by send-briefs).
create table if not exists public.brief_sends (
  id bigint generated always as identity primary key,
  week date not null, sent int not null, failed int not null,
  created_at timestamptz not null default now()
);
alter table public.brief_sends enable row level security;

-- Make yourself an admin (run once, with your own email):
--   update public.profiles set is_admin = true where email = 'you@example.com';

-- ============ Saved places, alerts, catchments, branding, Slack ============
alter table public.profiles add column if not exists slack_webhook text;
alter table public.profiles add column if not exists brand_name text;
alter table public.profiles add column if not exists brand_logo text;

-- A saved place: a postcode + radius. Investor 3, Professional 10, Enterprise unlimited (shared with the team).
create table if not exists public.saved_places (
  id bigint generated always as identity primary key,
  owner uuid not null references public.profiles(id) on delete cascade,
  label text not null default '',
  postcode text not null,
  lat double precision not null,
  lon double precision not null,
  radius_m int not null default 800 check (radius_m in (400, 800, 1600)),
  created_at timestamptz not null default now()
);
create index if not exists saved_places_owner on public.saved_places(owner);

-- Who can see a place: its owner, and everyone on the owner's Enterprise team.
create or replace function public.can_see_owner(o uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select o = auth.uid()
      or o = (select team_owner from public.profiles where id = auth.uid())
      or auth.uid() in (select id from public.profiles where team_owner = o)
$$;

alter table public.saved_places enable row level security;
drop policy if exists "see places" on public.saved_places;
create policy "see places" on public.saved_places for select using (public.can_see_owner(owner));
drop policy if exists "add places" on public.saved_places;
create policy "add places" on public.saved_places for insert with check (owner = auth.uid());
drop policy if exists "change places" on public.saved_places;
create policy "change places" on public.saved_places for update using (public.can_see_owner(owner)) with check (public.can_see_owner(owner));
drop policy if exists "remove places" on public.saved_places;
create policy "remove places" on public.saved_places for delete using (public.can_see_owner(owner));

create or replace function public.places_limit() returns trigger
language plpgsql security definer set search_path = public as $$
declare pl text := public.effective_plan(new.owner); n int;
begin
  select count(*) into n from public.saved_places where owner = new.owner;
  if pl = 'free' then raise exception 'Upgrade to Investor to save places and get alerts'; end if;
  if pl = 'investor' and n >= 3 then raise exception 'Investor includes up to 3 saved places'; end if;
  if pl = 'pro' and n >= 10 then raise exception 'Professional includes up to 10 saved places'; end if;
  if pl <> 'enterprise' then new.radius_m := 800; end if;  -- custom catchment sizes are Enterprise
  return new;
end $$;
drop trigger if exists places_limit on public.saved_places;
create trigger places_limit before insert on public.saved_places for each row execute function public.places_limit();

-- Weekly alerts: new filings near a saved place (written by the weekly job).
create table if not exists public.alerts (
  id bigint generated always as identity primary key,
  place_id bigint not null references public.saved_places(id) on delete cascade,
  week date not null,
  items jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (place_id, week)
);
alter table public.alerts enable row level security;
drop policy if exists "see alerts" on public.alerts;
create policy "see alerts" on public.alerts for select using (
  exists (select 1 from public.saved_places p where p.id = place_id and public.can_see_owner(p.owner)));
grant execute on function public.can_see_owner(uuid) to authenticated;

-- ============ Security hardening ============
-- Access-request spam: at most 3 per email per day and 300 in total per day.
create or replace function public.access_rate_limit() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.email := lower(trim(new.email));
  if new.email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'Invalid email'; end if;
  if (select count(*) from public.access_requests where email = new.email and created_at > now() - interval '1 day') >= 3
     or (select count(*) from public.access_requests where created_at > now() - interval '1 day') >= 300 then
    raise exception 'Too many requests, please try again tomorrow';
  end if;
  return new;
end $$;
drop trigger if exists access_rate_limit on public.access_requests;
create trigger access_rate_limit before insert on public.access_requests for each row execute function public.access_rate_limit();

-- Saved places: team members can see shared places, but only the creator or the team owner can change or delete them.
drop policy if exists "change places" on public.saved_places;
create policy "change places" on public.saved_places for update using (owner = auth.uid() or exists (select 1 from public.profiles m where m.id = saved_places.owner and m.team_owner = auth.uid())) with check (owner = auth.uid() or exists (select 1 from public.profiles m where m.id = saved_places.owner and m.team_owner = auth.uid()));
drop policy if exists "remove places" on public.saved_places;
create policy "remove places" on public.saved_places for delete using (owner = auth.uid() or exists (select 1 from public.profiles m where m.id = saved_places.owner and m.team_owner = auth.uid()));
alter table public.saved_places drop constraint if exists saved_places_text_len;
alter table public.saved_places add constraint saved_places_text_len check (length(label) <= 80 and length(postcode) <= 9 and lat between 49 and 61 and lon between -9 and 3);

-- Profile field sizes and safe URLs (stops storing scripts or huge blobs).
alter table public.profiles drop constraint if exists profiles_field_rules;
alter table public.profiles add constraint profiles_field_rules check (
  length(coalesce(full_name,'')) <= 120 and length(coalesce(company,'')) <= 120 and length(coalesce(job_title,'')) <= 120
  and length(coalesce(brand_name,'')) <= 80
  and (brand_logo is null or (brand_logo ~ '^https://' and length(brand_logo) <= 300))
  and (slack_webhook is null or (slack_webhook ~ '^https://hooks\.slack\.com/services/' and length(slack_webhook) <= 300)));

-- Belt and braces: the public (anon) role can't read any table directly.
revoke select on public.access_requests, public.brief_sends from anon, authenticated;

-- Admin panel: devices and IP addresses each account used in the last 7 days (spots shared logins).
-- Only the server (service_role) can call this.
create or replace function public.admin_session_stats()
returns table(user_id uuid, sessions int, ips int, devices int, last_seen timestamptz)
language sql security definer set search_path = '' as $$
  select s.user_id, count(*)::int, count(distinct host(s.ip))::int, count(distinct s.user_agent)::int,
         max(greatest(s.updated_at, s.refreshed_at at time zone 'UTC'))
  from auth.sessions s
  where greatest(s.updated_at, s.refreshed_at at time zone 'UTC', s.created_at) > now() - interval '7 days'
  group by s.user_id
$$;
revoke all on function public.admin_session_stats() from public, anon, authenticated;
grant execute on function public.admin_session_stats() to service_role;

-- Team invites: invitees accept or decline from their own account (owners can't add people without consent).
create or replace function public.my_invites() returns table(owner uuid, owner_name text, company text)
language sql security definer set search_path = public as $$
  select i.owner, coalesce(nullif(p.full_name,''), p.email), coalesce(p.company,'')
  from public.team_invites i join public.profiles p on p.id = i.owner
  where lower(i.email) = lower((select email from auth.users where id = auth.uid()))
$$;
create or replace function public.accept_invite(o uuid) returns void
language plpgsql security definer set search_path = public as $$
declare me uuid := auth.uid(); em text := (select lower(email) from auth.users where id = auth.uid());
begin
  if not exists (select 1 from public.team_invites where owner = o and lower(email) = em) then raise exception 'This invitation is no longer valid.'; end if;
  if (select team_owner from public.profiles where id = me) is not null then raise exception 'You are already in a team. Leave it first.'; end if;
  if exists (select 1 from public.profiles where team_owner = me) then raise exception 'You own a team, so you can’t join another.'; end if;
  if public.effective_plan(o) <> 'enterprise' then raise exception 'That team’s Enterprise plan is no longer active.'; end if;
  update public.profiles set team_owner = o where id = me;
  delete from public.team_invites where lower(email) = em;
end $$;
create or replace function public.decline_invite(o uuid) returns void
language sql security definer set search_path = public as $$
  delete from public.team_invites where owner = o and lower(email) = (select lower(email) from auth.users where id = auth.uid())
$$;
revoke all on function public.my_invites(), public.accept_invite(uuid), public.decline_invite(uuid) from public, anon;
grant execute on function public.my_invites(), public.accept_invite(uuid), public.decline_invite(uuid) to authenticated;
