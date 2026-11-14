-- Orders of the EVChargeking webshop checkout (function evck-shop). Only the service role reads or writes:
-- row-level security is on and there are no policies, so no browser key can see this table.
create table if not exists public.evck_orders (
  id uuid primary key default gen_random_uuid(),
  number text not null unique,
  token text not null unique,
  status text not null default 'open' check (status in ('open','pending','paid','failed','canceled','expired')),
  provider text not null check (provider in ('mollie','simulator')),
  test boolean not null default true,
  mollie_id text unique,
  pay_choice text,
  pay_method text,
  amount numeric(12,2) not null,
  currency text not null default 'EUR',
  lang text not null default 'en',
  country text not null,
  buyer text not null check (buyer in ('private','company')),
  email text not null,
  customer jsonb not null,
  items jsonb not null,
  totals jsonb not null,
  events jsonb not null default '[]'::jsonb,
  odoo_order text,
  created_at timestamptz not null default now(),
  paid_at timestamptz
);
alter table public.evck_orders enable row level security;
create index if not exists evck_orders_created_idx on public.evck_orders (created_at desc);
create index if not exists evck_orders_email_idx on public.evck_orders (email);
comment on table public.evck_orders is 'EVChargeking webshop orders created by the evck-shop edge function. Service role only.';
