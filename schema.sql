-- Run this in Supabase SQL Editor

create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null,
  role text not null check (role in ('admin','teacher','student','parent'))
);

create table if not exists classes (
  id bigint generated always as identity primary key,
  name text not null,
  grade_level text
);

create table if not exists students (
  id bigint generated always as identity primary key,
  full_name text not null,
  admission_no text unique not null,
  gender text check (gender in ('Male','Female')),
  date_of_birth date,
  class_id bigint references classes(id),
  parent_phone text,
  created_at timestamptz default now()
);

create table if not exists teachers (
  id bigint generated always as identity primary key,
  full_name text not null,
  phone text,
  subject text,
  created_at timestamptz default now()
);

create table if not exists attendance (
  id bigint generated always as identity primary key,
  student_id bigint not null references students(id) on delete cascade,
  date date not null,
  status text not null check (status in ('Present','Absent','Late','Excused')),
  recorded_by uuid references profiles(id),
  created_at timestamptz default now(),
  unique (student_id, date)
);

create table if not exists results (
  id bigint generated always as identity primary key,
  student_id bigint not null references students(id) on delete cascade,
  subject text not null,
  exam_name text not null,
  marks numeric not null,
  grade text,
  created_at timestamptz default now()
);

create table if not exists fees (
  id bigint generated always as identity primary key,
  student_id bigint not null references students(id) on delete cascade,
  term text not null,
  amount numeric not null,
  paid numeric default 0,
  status text default 'Unpaid' check (status in ('Paid','Unpaid','Partial')),
  created_at timestamptz default now()
);

create table if not exists announcements (
  id bigint generated always as identity primary key,
  title text not null,
  body text not null,
  posted_by uuid references profiles(id),
  created_at timestamptz default now()
);

-- Seed a class
insert into classes (name, grade_level) values ('Form 1A', 'Form 1'), ('Form 2A', 'Form 2');

-- Enable Row Level Security (basic: anon can do everything while developing;
-- tighten before production!)
alter table profiles enable row level security;
alter table students enable row level security;
alter table teachers enable row level security;
alter table classes enable row level security;
alter table attendance enable row level security;
alter table results enable row level security;
alter table fees enable row level security;
alter table announcements enable row level security;

create policy "dev_all" on profiles for all using (true) with check (true);
create policy "dev_all" on students for all using (true) with check (true);
create policy "dev_all" on teachers for all using (true) with check (true);
create policy "dev_all" on classes for all using (true) with check (true);
create policy "dev_all" on attendance for all using (true) with check (true);
create policy "dev_all" on results for all using (true) with check (true);
create policy "dev_all" on fees for all using (true) with check (true);
create policy "dev_all" on announcements for all using (true) with check (true);
