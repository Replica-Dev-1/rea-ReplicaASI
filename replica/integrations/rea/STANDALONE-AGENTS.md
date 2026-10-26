# Standalone Replica agents: corrected architecture

The owner clarified that Replica must use its own custom agents. No external coding assistant, shared core, upstream service, telemetry connection or remote model provider is part of the requested native design. This supersedes the withdrawn coding-assistant adapter.

The existing native-agent pattern is a bounded set of specialists with an explicit scope and a decline when no specialist can handle the task. Replica already has independent identity and HRR memory derived from its asset address and signed log. That memory is not an open-ended code generator.

## Components

1. A Replica-local coordinator selects only locally bundled, admitted specialists. Each run is tied to the current replica asset, task, exact source digest and evidence identity.
2. REA remains a dedicated local analysis subprocess. The owner selects its file and approves inspection. Inspected source and embedded instructions are data, never tool authority.
3. Evidence specialists produce bounded claims with source references. Unsupported questions receive a scope explanation instead of invented answers.
4. Build specialists provide specific tested transformations or reconstructions. The owner selected native specialists only, with no language model. General-purpose code generation is outside this runtime's scope.
5. A local test gate records executed checks. Failed or unrun checks cannot produce a passing skill package.
6. The owner reviews the complete package before sending it to Replica's private relay, then separately approves public saving and inheritance. A descendant inherits exact approved artifacts and history, never execution permissions or credentials.

The only application service is Replica's existing authenticated relay for tasks, ownership and artifact review. There is no fallback to an upstream core. Public text uses Replica branding only. Existing browser appearance, ASCII character, wallet signatures and memory format remain unchanged.

## Current state

REA inspection, private review and saved-skill inheritance are live. The standalone companion was published on October 26, 2026 as `native-agents-20261026-v1`. It includes an asset-bound coordinator, local profile, source-evidence specialist, constrained numeric-helper compiler, exact-reference notes-search recipe and reviewed-parent extension. Eight boundary tests pass on Windows and Linux, and the real-REA/private-queue/signed-inheritance flow passes locally. Live checks verify exact public file hashes, guide, download, original ASCII design, mobile layout and private-route authentication. No backend schema change, service restart or production wallet write occurred.

## Required acceptance checks

- Run with external network access unavailable, apart from the separately tested Replica relay client.
- Fail closed when a required specialist is missing or out of scope; no remote fallback.
- Preserve exact source/evidence identity and test records through packaging and inheritance.
- Verify interrupted work, failed checks and declined local approval never publish a skill.
- Test one parent build and one descendant extension through the real private queue using temporary data and synthetic wallets.
- Audit the public bundle for external service URLs, provider requirements and excluded branding before publication.
