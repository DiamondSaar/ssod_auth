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

## Service-to-service auth for any new module (added 2026-07-17)

SSOD Auth is now the mandatory issuer of machine-to-machine tokens for
**every** module in the ecosystem that needs to call Dominex (or any other
internal service) - no module holds a static key issued directly by the
target service anymore. New `ServiceClient`/`ServiceClientGrant` models
(`accounts/models.py`), Django-admin managed; `POST /api/v1/service-token/`
(`accounts/api.py::issue_service_token`) mints a 5-minute JWT (own secret,
`M2M_TOKEN_SECRET`, separate from `SSO_TICKET_SECRET`) that the target
service verifies statelessly. Every issuance/denial logs to `AuthEvent`.
atb-portal is the reference implementation (`ServiceClient.code="atb_portal"`,
grant on `audience="dominex"`, replacing its old `ExternalSource`/
`IdentityApiConsumer` static keys). Full mechanism, registration steps for
a new module, and the rationale for accepting "SSOD Auth down = all
inter-module traffic stops" as a deliberate tradeoff: `dominex/docs/
module-interactions.md`, "Service-to-service auth for new modules".

## "Инфраструктура предприятия" (added 2026-08-26)

- Tile on the personal-account home page + `/account/infrastructure/`
  (`accounts/views.py::infrastructure`), read-only. Visible only when
  `CustomUser.can_view_infrastructure` is true: organization set AND
  (position in `INFRA_MANAGER_POSITIONS` OR the per-user
  `infrastructure_access_override` flag, migration 0014). Position comes
  from the Dominex projection, so a position change there opens/closes the
  page on the user's next login; the flag is local and survives syncs.
- All data comes from Dominex in one call -
  `accounts/services/dominex_client.py::fetch_infrastructure_summary()` ->
  `GET /api/v1/infrastructure/summary/users/<username>`. Dominex resolves
  the organization from the username itself and caches the answer for 10
  minutes (Dominex aggregates Zabbix, ssod_auth holds no Zabbix
  credentials and makes no Zabbix calls). Full contract and the reasons
  behind the split: `dominex/docs/module-interactions.md`,
  "Infrastructure Summary for Client Managers".
- Same best-effort contract as `fetch_user_projection` - None on any
  failure, and the page then renders an explicit "сводка недоступна"
  panel instead of an empty table.
- Deploy note: the page ships a new stylesheet
  (`accounts/static/accounts/css/infrastructure.css`), so a deploy needs
  `migrate` **and** `collectstatic`.

## What's still local-only / not yet built

- No SSO/session handoff - logging into SSOD Auth and logging into Dominex
  are still two independent logins.
- No account-linking mechanism beyond matching username strings.
- No scheduled sync (cron/Celery) - `sync_dominex_products` is a manual
  command today.
- Avatar and the "Мои заявки" tickets module are deliberately not part of
  this integration yet (see `dominex/PROJECT_CONTEXT.md`'s 2026-07-11 entry
  for why and what's planned).
