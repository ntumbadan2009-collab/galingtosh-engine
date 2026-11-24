-- Minimal isolated Postgres contract, not a dump of production data.
create role anon;
create role authenticated;
create role service_role bypassrls;
create schema auth;
create schema storage;
create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
create table storage.objects(bucket_id text,name text);
create table public.projects(id uuid primary key default gen_random_uuid(),user_id uuid not null,title text not null,type text not null,updated_at timestamptz default now());
create table public.conversations(id uuid primary key default gen_random_uuid(),user_id uuid not null,project_id uuid not null,title text not null);
create table public.films(id uuid primary key default gen_random_uuid(),project_id uuid not null,user_id uuid not null,version int not null,data jsonb not null,rev int not null default 0,unique(project_id,version));
create table public.film_operations(id uuid primary key default gen_random_uuid(),film_id uuid not null,user_id uuid not null,op jsonb not null,snapshot_before jsonb,applied_at timestamptz default now(),undone_at timestamptz);
create table public.render_jobs(id uuid primary key default gen_random_uuid(),project_id uuid not null,user_id uuid not null,film_version int not null,status text default 'queued',created_at timestamptz default now(),updated_at timestamptz default now(),finished_at timestamptz,worker_id text,progress int default 0,attempts int default 0,error text,output_path text);
grant usage on schema public,auth,storage to service_role;
grant all on all tables in schema public,auth,storage to service_role;
