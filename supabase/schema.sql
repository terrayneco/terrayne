-- Terrayne accounts schema. Paste into Supabase > SQL Editor and run once (safe to re-run).

-- Profiles: one row per user, created automatically on sign-up.
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  full_name text default '',
  company text default '',
  job_title text default '',
  plan text not null default 'free' check (plan in ('free','pro','enterprise')),
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

-- Watchlist limits: free 0, pro 10, enterprise unlimited.
create or replace function public.watchlist_limit() returns trigger
language plpgsql security definer set search_path = public as $$
declare pl text := public.effective_plan(new.user_id); n int;
begin
  select count(*) into n from public.watchlist where user_id = new.user_id;
  if pl = 'free' then raise exception 'Upgrade to Professional to use the watchlist'; end if;
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
create policy "paid briefs" on public.briefs for select using (public.is_paid(auth.uid()));

-- Owners can remove members from their team.
create or replace function public.remove_member(member uuid) returns void
language sql security definer set search_path = public as $$
  update public.profiles set team_owner = null where id = member and team_owner = auth.uid()
$$;
grant execute on function public.remove_member(uuid) to authenticated;
grant execute on function public.effective_plan(uuid) to authenticated;

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
