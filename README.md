# Amani Schools Management System (Flask + Supabase)

Minimal, functional school management system.

## Quick start

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in your Supabase credentials
python app.py
```

Open http://127.0.0.1:5000

## Supabase setup (one time)

1. Create a project at https://supabase.com (free tier is fine).
2. Run `schema.sql` in the **SQL Editor**.
3. Create users: Authentication → Add User. Then insert matching rows into `profiles`.
4. Project Settings → API: copy the **Project URL** and **anon public** key into `.env`.

## Roles

- `admin` — everything
- `teacher` — students, attendance, results
- `student` — view fees/announcements
- `parent` — view fees/announcements
