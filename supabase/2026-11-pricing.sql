-- Nov 2026 pricing: Free / Pro / Team. Updates the upgrade messages only (limits unchanged).
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.

create or replace function public.watchlist_limit() returns trigger
language plpgsql security definer set search_path = public as $$
declare pl text := public.effective_plan(new.user_id); n int;
begin
  select count(*) into n from public.watchlist where user_id = new.user_id;
  if pl = 'free' then raise exception 'Upgrade to Pro to save places'; end if;
  if pl = 'investor' and n >= 3 then raise exception 'Investor includes up to 3 saved places'; end if;
  if pl = 'pro' and n >= 10 then raise exception 'Pro watchlists hold up to 10 neighbourhoods'; end if;
  return new;
end $$;

create or replace function public.invite_limit() returns trigger
language plpgsql security definer set search_path = public as $$
declare n int;
begin
  if public.effective_plan(new.owner) <> 'enterprise' or (select team_owner from public.profiles where id = new.owner) is not null then
    raise exception 'Only Team account owners can invite colleagues'; end if;
  select (select count(*) from public.profiles where team_owner = new.owner) + (select count(*) from public.team_invites where owner = new.owner) into n;
  if n >= 4 then raise exception 'Team includes up to 5 people'; end if;
  new.email := lower(new.email);
  return new;
end $$;

create or replace function public.places_limit() returns trigger
language plpgsql security definer set search_path = public as $$
declare pl text := public.effective_plan(new.owner); n int;
begin
  select count(*) into n from public.saved_places where owner = new.owner;
  if pl = 'free' then raise exception 'Upgrade to Pro to save places and get alerts'; end if;
  if pl = 'investor' and n >= 3 then raise exception 'Investor includes up to 3 saved places'; end if;
  if pl = 'pro' and n >= 10 then raise exception 'Pro includes up to 10 saved places'; end if;
  if pl <> 'enterprise' then new.radius_m := 800; end if;  -- custom catchment sizes are Enterprise
  return new;
end $$;
