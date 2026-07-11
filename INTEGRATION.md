# Dominex Core integration

SSOD Auth is the credentials/session/passkey layer; Dominex Core
(`D:\projects\dominex`) is the identity/product-access master data source.

**For the full ecosystem picture** (Dominex's data model, access-class
system, console UI conventions, all three repos, deployment/dev setup —
not just this integration), read `dominex/ARCHITECTURE.md` first. Deep-dive
on just the integration architecture: `dominex/docs/module-interactions.md`.
Full dated history/reasoning for everything: `dominex/PROJECT_CONTEXT.md`.

## What exists today (Phase 1, added 2026-07-11)

- `accounts/services/dominex_client.py` - `fetch_user_projection(username)`
  calls Dominex's `GET /api/v1/identity/projection/users/<username>` (auth
  via the `X-Dominex-Api-Key` header, `DOMINEX_API_KEY` setting). Returns
  `None` on any failure - never raises, this is a best-effort sync path.
- `python manage.py sync_dominex_products` - for every `CustomUser`, pulls
  their Dominex projection and upserts local `Organization`/`Product`/
  `UserProductAccess` rows (tagging them with `dominex_grant_id`/
  `synced_at`). Run manually; no scheduler wired up yet. Matches users by
  exact username string - a user without a same-named Dominex account is
  silently skipped.
- `account_products()` / "Мои продукты" itself is **unchanged** - it still
  reads local `Product`/`UserProductAccess` directly. The sync command
  just keeps that local data current; nothing here made a live network
  call from the request path.
- Settings: `DOMINEX_API_BASE_URL` (default `http://dominex_app:5000`,
  Docker-internal DNS name - both compose stacks share the `ssod_auth_net`
  Docker network for this), `DOMINEX_API_KEY`.

## What's still local-only / not yet built

- No SSO/session handoff - logging into SSOD Auth and logging into Dominex
  are still two independent logins.
- No account-linking mechanism beyond matching username strings.
- No scheduled sync (cron/Celery) - `sync_dominex_products` is a manual
  command today.
- Avatar and the "Мои заявки" tickets module are deliberately not part of
  this integration yet (see `dominex/PROJECT_CONTEXT.md`'s 2026-07-11 entry
  for why and what's planned).
