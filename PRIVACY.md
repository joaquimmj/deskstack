# Privacy

deskstack's data server is read-only and keeps no user data.

## What the hosted connector receives

- **Tool arguments:** company identifiers, periods, and the values you send to `verify_value` to be checked. These
  are used to answer the call and are not stored.
- **Your IP address:** used only for the per-IP rate limit, in memory for about a minute.
- **A global request counter:** a daily count with no identifiers, used for the free service's daily cap.

## What it doesn't receive

- **Your prompts, conversations and workbooks.** The plugin's scripts run in your own Claude session (claude.ai's
  code sandbox, or your machine in Claude Code). They never call the network.
- **What the server sees of a workbook:** only the values the associate passes to `verify_value`.

## Logs

- **Cloudflare:** the server runs on Cloudflare Workers. Cloudflare keeps its standard invocation logs (request
  metadata and errors) for its retention period.
- **deskstack itself:** logs only error messages, never tool arguments.

## Self-hosting

Your own copy sends nothing to the deskstack project. See [docs/SELF_HOSTING.md](docs/SELF_HOSTING.md).

## Security

Report a vulnerability privately through GitHub's "Report a vulnerability" on this repository.
