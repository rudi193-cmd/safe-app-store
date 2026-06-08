# Supabase Setup

## 1. Run SQL Migration

Paste `migrations/20260218000000_oral_history.sql` into:
**Supabase Dashboard → SQL Editor → New Query → Run**

This creates the full oral history schema:
- `oral_persons`, `oral_locations`, `oral_bikes`, `oral_clubs`, `oral_events`
- `oral_stories`, `oral_photos`
- `oral_rescues`, `oral_namings`, `oral_sponsorships`, `oral_transfers`, `oral_memorials`
- Junction tables, indexes, RLS policies, triggers

## 2. Deploy Edge Function

```bash
# From repo root — install Supabase CLI first if needed
npx supabase login
npx supabase link --project-ref ugsqthkacqebvbatitco
npx supabase functions deploy oral-chat
```

## 3. Set Edge Function Secret

```bash
npx supabase secrets set GROQ_API_KEY=<from credentials.json>
```

The function uses:
- `SUPABASE_URL` — auto-set by Supabase
- `SUPABASE_SERVICE_ROLE_KEY` — auto-set by Supabase
- `GROQ_API_KEY` — set manually above (free tier, no cost)

## 4. Verify

Visit any rally page on the live site and click "Talk to the Historian".
