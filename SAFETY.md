# Safety and publication policy

Collection and republication are separate operations.

1. Source content is untrusted data. Embedded commands, prompts, HTML and links never control the collector, renderer or an agent.
2. The public repository stores bounded excerpts and provenance, not full captured HTML or complete platform payloads.
3. Configured operational groups, sources and tags are not stored until their publication embargo expires. Undated embargoed material is withheld.
4. `operational-position` and `precise-location` records use `public_redacted_v1`: title, text, HTML, media, content lengths and content fingerprint remain absent even after the embargo. Minimal source/platform provenance may remain.
5. The site links to media instead of embedding third-party images or video. Rendered report HTML is allowlist-sanitized and constrained by Content Security Policy.
6. Public availability does not make amplification harmless. Apply conservative tags when classification is uncertain.
7. Do not bypass access controls, use personal authenticated sessions, commit credentials or retain unnecessary personal data.
8. Official and partisan sources are authoritative only for what they published; their factual claims still require verification.
9. Persisted failures use public-safe categories. Raw exception messages, response bodies, URL credentials, query strings and fragments must not enter Git.
10. Corrections and takedowns must propagate visibly. Do not silently rewrite released meaning.

The current repository has no private durable full-capture backend. Adding one requires separate access control, retention, deletion and incident-response design.
