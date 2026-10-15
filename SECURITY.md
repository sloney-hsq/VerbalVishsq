# Security and privacy reporting

Please report security or privacy problems through a private GitHub Security Advisory for the repository rather than a public issue. Include the affected version, a minimal reproduction, likely impact, and whether credentials or participant data may have been exposed. Do not attach real API keys, raw audio, participant transcripts, or research traces.

This project treats the following as sensitive even when they are not conventional software vulnerabilities:

- accidental persistence or publication of credentials;
- participant identity, audio, transcript, tool arguments, or task schedules;
- a stale response bypassing authority and modifying a committed dashboard;
- cross-session or cross-trial state leakage;
- trace corruption that silently changes research metrics.

If private advisory reporting is unavailable, open a public issue that contains no sensitive details and asks the maintainers to establish a private channel.

The dataset adapter is trusted local Python code, not a sandbox for untrusted uploads. Do not load an interface path supplied by a model, browser client, or study participant.
