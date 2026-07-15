# Secret Governance

## Scope And Classification

| Secret | Current use | Storage boundary | Log/API rule |
|---|---|---|---|
| JWT signing secret | Human bearer token signing | Environment only | Never returned or logged |
| Node ingest token | Machine REST ingestion | Environment/edge provisioning | Never returned; constant-time comparison |
| AI provider key | External DeepSeek access | Encrypted AI vault; unlocked after administrator verification | Status exposes provider/model only |
| Administrator bootstrap password | First user creation only | Environment during bootstrap | Never persisted in plaintext or echoed |
| NATS token | Local shadow broker | Environment/config provisioning | Health exposes presence/status only |
| PostgreSQL DSN | Persistence connection | Environment | Errors must redact credentials |

## Enforced Controls

1. `.env`, environment variants, edge token files and AI vault files are ignored by Git.
2. `scripts/check_secrets.py` blocks provider-key shapes, concrete token assignments and runtime secret files in tracked source paths.
3. Production configuration fails fast when JWT/node secrets are weak or default, legacy token authentication is enabled, PostgreSQL is absent, Demo Seed is enabled, or tenant/site are defaults.
4. First administrator creation requires an explicit bootstrap password; Production requires at least 16 characters.
5. Passwords use PBKDF2-HMAC-SHA256 with a per-user random salt; JWTs use bounded expiration and a unique JTI.
6. Login has a separate IP rate-limit bucket and cannot bypass middleware rate limiting.
7. `scripts/protect-secrets.ps1` removes inherited Windows ACLs from `.env`, the AI secret directory, node token, PostgreSQL/auth environment files, session token and NATS token file. It allows only the current user, SYSTEM and local Administrators. `-CheckOnly` is part of the full verification gate, and the canonical supervisor reapplies protection before launch.
8. API failures use request IDs and hide unhandled internal details outside explicit development mode.

## Rotation Procedure

1. Stop external access and record the rotation ticket/actor.
2. Replace the secret in the managed environment or encrypted vault, never in source.
3. For JWT rotation, invalidate active sessions or support an explicit overlap window before later production rollout.
4. For node/NATS secrets, provision consumers first when overlap is supported, then revoke the old credential.
5. Re-run secret scan, ACL check, authentication tests and strict runtime verification.
6. Record result and rollback status in audit/operations evidence without including the secret.

## Remaining Boundary

This is local Windows digital-twin governance, not enterprise secret management. Runtime secret files are protected, but several are stored under a broader runtime parent directory whose delete semantics are not a managed-vault substitute. Production still requires a managed secret store, automated rotation, per-node workload identity, NATS subject credentials and mTLS. The present controls do not authorize internet exposure or physical equipment access.
