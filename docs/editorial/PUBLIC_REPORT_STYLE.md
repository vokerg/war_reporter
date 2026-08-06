# Public report style

## Purpose

A public report should help a reader understand what happened, what the main sources said, and what remains uncertain. It is not a visible copy of the repository's evidence graph or review workflow.

## Separation of concerns

The JSON report manifest is the canonical audit record. It retains the full claim set, assessment set, deterministic hash, record status, translation lineage, and content path.

The Markdown report is the public editorial product. It must not contain:

- claim, assessment, observation, source-item, report, task, or map IDs;
- hashes, task names, queue states, review receipts, or branch references;
- bracketed internal reference lists;
- phrases that describe repository mechanics, such as `frozen record`, `input contract`, or `approved set`.

Internal traceability must be verified during review and preserved in machine-readable records, not printed in prose.

## Reader-first structure

Daily reports should normally use this order:

1. title and compact date metadata;
2. three to five key points;
3. subject-based sections ordered by materiality;
4. one short section describing the main unresolved questions.

A report does not need to mention every approved input. Include material developments and omit low-salience, duplicative, or out-of-period details when omission does not alter the overall account.

## Attribution and uncertainty

Use attribution as the default uncertainty mechanism:

- `the ministry said`;
- `Reuters reported`;
- `officials alleged`;
- `the available reporting indicates`;
- `the result remains unclear`.

Do not attach the same verification disclaimer to every paragraph. Consolidate general limitations in the closing section. Place a specific caveat next to an item only when it prevents a material misunderstanding, including:

- figures that use incompatible intervals or categories;
- territorial-control or damage claims whose outcome is disputed;
- identity, date, or location uncertainty;
- allegations with legal significance;
- reporting that depends on a shared upstream source.

Confidence labels may be used when they help the reader, but they should not replace direct, natural-language explanation.

## Sources

Name sources and institutions in ordinary language. Public external links may be included only when they already resolve through the approved provenance chain. Never use repository IDs as reader citations.

## Language

Prefer short sentences, concrete verbs, and paragraphs with one main idea. Avoid audit terminology, repetitive throat-clearing, and exhaustive inventories of missing evidence.

Translations must preserve the public structure, factual meaning, attribution, and material caveats while using idiomatic target-language prose. They must not reintroduce internal references removed from the source report.
