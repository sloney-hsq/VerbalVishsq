# Security and privacy reporting

During the current private-collaboration stage, report security or privacy problems only through an existing private channel for a repository owner or maintainer. If no private channel is available, do not disclose the issue publicly. Include the affected version, a minimal reproduction, likely impact, and whether credentials or participant data may have been exposed. Do not attach real API keys, raw audio, participant transcripts, or research traces.

This project treats the following as sensitive even when they are not conventional software vulnerabilities:

- accidental persistence or publication of credentials;
- participant identity, audio, transcript, tool arguments, or task schedules;
- a stale response bypassing authority and modifying a committed dashboard;
- cross-session or cross-trial state leakage;
- trace corruption that silently changes research metrics.

Nothing in this policy authorizes publishing participant data, traces, credentials, or details that would make the repository public. Public release remains blocked by [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

The dataset adapter is trusted local Python code, not a sandbox for untrusted uploads. Do not load an interface path supplied by a model, browser client, or study participant.
