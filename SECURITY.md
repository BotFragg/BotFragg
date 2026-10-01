# Security Policy

## Report a vulnerability

Report BotFragg security vulnerabilities only through Discord using one of
these channels:

1. The [BotFragg support server](https://discord.gg/VjZ5N8nT4K). Use its
   designated support channel. If the server does not offer
   a private channel, do not post sensitive technical details there; contact
   the developer directly instead.
2. A direct Discord message to **kumkashree (kks)**:
   [Discord profile](https://canary.discord.com/users/798605852642115676).

Do not report vulnerabilities through public issues, discussions, social
media, or other channels. For sensitive reports, direct message the developer
so exploit details are not exposed in a public server post.

Include the affected BotFragg version, a concise description of the impact,
steps to reproduce the issue, and relevant configuration details. Redact
Discord or Riot IDs, passwords, authorization codes, cookies, tokens, webhook
URLs, and other secrets. Test only with accounts and data you control; avoid
actions that disrupt the service or access other users' data.

The maintainers will review reports and may ask for additional details through
Discord. Do not assume a report is resolved until the maintainers confirm it.

## If credentials may be exposed

Do not repost the exposed value. Contact the developer through Discord. A
BotFragg operator should revoke an exposed Discord bot token through the
Discord Developer Portal. The operator should coordinate Fernet key changes
carefully: replacing `TOKEN_ENCRYPTION_KEY` without re-encrypting stored Riot
credentials can make those records unreadable.
