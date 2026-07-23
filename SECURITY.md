# Security

WorldCalib evaluates generated source code. Treat candidates, benchmark tasks,
attachments, and external checkouts as untrusted.

- Run AppWorld, Toolathlon, and Terminal-Bench inside their intended isolated
  environments or containers. Do not expose host credentials beyond the keys a
  task needs.
- GAIA includes file reading, URL fetching, web search, and Python execution
  tools. Use a restricted worker account and review network policy before
  enabling them.
- Keep `.env`, provider tokens, cookies, SSH material, and cloud credentials out
  of candidate workspaces and Git.
- Candidate runtime code must not read `solution/`, `tests/`, gold tables,
  evaluator outputs, or reward files.
- Inspect external repositories and pin their revisions independently; they are
  not vendored or trusted by this project.

The proposer workspace access policy is an additional guardrail, not a security
boundary. Use operating-system or container isolation for adversarial code.
