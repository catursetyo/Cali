# Security Policy

## Sensitive Data

Do not submit or commit:

- financial databases;
- bank statements;
- transaction exports;
- receipt images;
- Telegram bot tokens;
- AI provider API keys;
- Azure credentials;
- GitHub tokens;
- rclone configuration;
- age private keys;
- Hermes `.env` or `state.db`.

## Reporting a Vulnerability

Do not include real financial data or credentials in public issues.

When reporting a problem, use:

- sanitized logs;
- dummy transaction values;
- redacted paths and usernames;
- synthetic CSV or receipt samples.

## Supported Versions

Security fixes are applied to the latest major release.

| Version | Supported |
|---|---|
| 2.x | Yes |
| 1.x | No |

## Exposed Credentials

If a credential is accidentally committed:

1. Revoke or rotate the credential immediately.
2. Remove it from the Git history.
3. Review repository access and logs.
4. Generate a new credential.

Deleting the file in a later commit is not sufficient because it remains in
the Git history.
