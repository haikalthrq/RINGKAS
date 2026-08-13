# Reverse Proxy Boundary

The repository intentionally does not choose a domain, certificate authority,
or reverse-proxy vendor. Those values remain deployment decisions.

The production Compose overlay exposes only the web service on loopback. The
selected reverse proxy must:

- terminate HTTPS for the production domain;
- proxy the whole site to `http://127.0.0.1:${WEB_PORT}`;
- preserve the `Host` header and standard `X-Forwarded-For`/`X-Forwarded-Proto`
  headers;
- redirect HTTP to HTTPS;
- enforce request-body and timeout limits;
- keep PostgreSQL, Qdrant, and `rag-query` unreachable from the public network.

Verify the public HTTPS URL, secure auth cookie behavior, Google callback URL,
health endpoint policy, and a cited chat smoke test before accepting traffic.
