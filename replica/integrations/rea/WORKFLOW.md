# Inspect → build → test → inherit: first release

Status: deployed on October 26, 2026 as `rea-runner-20261026-v1`. Saved skill packages, exact wallet inheritance, discoveries and the owner-paired private investigation queue are live. The companion runs REA 6.8.0 on one locally selected source file after local approval, then returns a reviewed summary. The original ASCII design is preserved. The standalone specialist companion now provides bounded local builds without a language model or upstream agent service; see STANDALONE-AGENTS.md for its exact scope. See RUNNER.md for setup and data handling.

## Match to the requested experience

| Requested behavior | This candidate |
| --- | --- |
| Investigate a small app with REA | Real REA 6.8.0 static analysis of the included MIT reference notes app; source digest and portable observations retained |
| Build something useful | Working browser search demo, with original reconstruction and descendant extension |
| Test the supported behavior | 20 parent checks; 35 descendant checks, including parent regression and five fresh extension cases |
| Save more than prose | One versioned package embeds implementation, source identity, tests, test record, requirements, evidence excerpt, origin and sharing choices |
| Preserve evidence while character prose changes | Package files and the package itself are SHA-256 addressed; journal mutations do not touch artifacts |
| Copy to another wallet | The existing invite/claim/delegation flow adds exact approved package IDs to the child's signed inherit entry |
| Child continues useful work | Child downloads the same package and can save a new tested version referencing the inherited parent package |
| See lineage and discoveries | Owner skill list shows inheritance/extension provenance; public discovery records show signed save/inherit events; sample page offers working demos and package history |
| Owner controls publication and inheritance | Explicit whole-package publication checkbox and per-save inheritance choice; author inheritance restrictions enforced |

## What this does not yet provide

The sample is a recorded real investigation and coding-agent build. It is clearly labeled as a package lineage, not a fabricated minted-wallet lineage. Live replica ownership/copying was exercised with real Ed25519 signatures and synthetic wallets against the real HTTP handler, with blockchain reads mocked. No real tokens were minted by this work.

The website can queue a selected-file inspection for a paired runner. It does not start an autonomous coding session or inspect arbitrary files: the owner selects one file and approves each inspection locally. The owner selected native specialists only. Local builds require separate approval and execute only admitted recipes or constrained numeric generation. Private sharing between owners, practice rooms and controlled model-performance comparisons remain later phases. No weight learning or benchmark improvement is claimed.

## Storage and API changes

- Additive SQLite table `skill_package`: digest, exact JSON bytes, size, uploading replica and timestamp. Existing memory/log/model formats remain compatible.
- `POST /api/skills`: current wallet session and ownership required; validates the package and embedded file digests, then stores immutable bytes. Uploading is separate from signed skill approval.
- `GET /api/skills/<digest>`: returns exact public package text for digest-verified export.
- `GET /api/replica/<asset>/skills`: derives active approvals from signed teach/inherit/forget records.
- `GET /api/discoveries`: bounded historical signed skill events, including parent references.
- A teach record's `body.skill` binds package ID and inheritance permission. A copy's `body.skills` contains package IDs approved by its actual parent at a valid signed snapshot and still permitted at the time of append.
- The relay rechecks package limits and parent permissions under its append lock. Ownership/delegation signatures remain the existing authority; tools and local file permissions are not inherited.

Limits: 1.5 MB per package, at most 32 files, 20 active skills, and 64 uploads / 20 MB per replica. Version updates use new package digests. Public artifacts may remain stored after a failed signed approval, so the UI obtains publication consent before uploading. Forgotten parent skills do not erase descendants' already approved packages.

The package's test record must report all cases passed, but the relay never executes uploaded code and cannot certify those claims. The UI labels these as author-reported checks. Only the supplied sample's checks were executed by this implementation work. Artifact authorship labels are also self-reported; the wallet's signed record establishes who approved publication.

Public evidence is a complete selected module observation from a genuine REA result, packaged as an explicitly labeled excerpt with source ranges/digests and the original result's identity. The complete original inspection result is retained separately; it is not published because it includes local machine paths. The sample package also includes the inspected source, implementation, tests and actual test outputs, so it can be checked without the original MCP session.

## Verification

- Parent demo: 20 executed checks against fixed expected results for both reference and reconstruction.
- Descendant: 35 executed checks; extraction from its downloaded package was validated and the same tests reran successfully.
- Nine JavaScript tests cover finding imports, package digests, invalid/private/failed reports, review gates, replay and stable inherited IDs.
- Existing 22 model checks and 41 lineage checks pass.
- A new real-HTTP scenario verifies uploads versus signed approval, ownership, bad hashes/paths, failed tests, private packages, forged inheritance, stale consent, exact inherited bytes, a descendant extension, discovery records and rejection after ownership transfer.
- Headless browser checks cover the interactive sample, mobile width, explicit public consent, no writes on preview, actual signatures, two skill saves, recorded parent linkage, recall and no script errors.

Run `node --test tests/rea.test.cjs tests/skills.test.cjs`, `python tests/test_skills.py`, and the existing model/lineage tests. Use `python tools/unpack_skill.py <package.json> <new-directory>` to verify and extract a package without executing it. Review extracted files, then run the recorded test command.

## Deployment preflight verified on October 26, 2026

`deploy/stage.sh` includes `server/skills.py`, `static/skills.js`, all search sample assets (including the PNG), and the inheritance test. It now checks all required files before any SSH or copy command; `sh deploy/stage.sh --check` performs only that check. The server test sequence now runs `tests/test_skills.py` alongside the existing model and lineage suites.

Verified in `/opt/replica-releases/deployment-check-20261026` with the production Python runtime: shell syntax, complete-file preflight, deliberate missing-`skills.py` refusal, 22 model checks, 41 lineage checks and the signed HTTP skill-inheritance scenario all passed. These checks used temporary test databases and synthetic wallets. No backend deployment or production restart occurred.

## Deployed release

The scoped release saved a consistent SQLite backup and previous backend, static and nginx files before publication. It staged and tested the candidate outside the public web root using the production Python runtime, installed app.py with skills.py and runner.py, restarted the relay, validated the new routes and published the UI. Existing service configuration and chain settings were preserved. Live checks confirmed health, exact public-file hashes, authenticated private review, sample behavior and mobile layout without writing to production wallets.

Rollback restores previous application, UI and nginx files. Keep the additive artifact table and signed log records; old model code already understands the teach/inherit entries and ignores their extra metadata. Do not restore an old database over new user activity. The existing general deployment script is updated to carry the new files, but a scoped release should be used to avoid overwriting unrelated configuration.

## Runner verification

The real REA companion completed a task through the actual HTTP handler with a temporary database and synthetic owner. The private result retained the exact source digest and REA evidence ID while excluding raw source and local paths; it created no public log entry. Browser checks exercised pairing, tasks, private review, signed finding publication, package consent, saving, disconnect and mobile layout.

Checks cover ownership transfer, pairing-code expiry and replay, cancellation, unauthenticated access, source changes and declined local approval. The Linux production runtime passed model, lineage, skill and private-queue checks in isolation. Four local runner checks, including the real pinned REA subprocess on Windows, passed. No production wallet was minted or paired by these checks.

## Standalone specialist verification

The owner selected standalone native specialists with no language model. The coordinator binds each task to a replica asset and a local profile; unknown capabilities and remote settings are rejected. Source evidence, constrained arithmetic helpers, the known notes-search recipe and its reviewed-parent extension are the first capabilities. Unsupported software is declined, with no core fallback. This is bounded synthesis and recipe reuse, not a general-purpose coding agent.

Eight native-agent boundary tests passed, including denied Python network access during a numeric build, independent additional numeric inputs, source/evidence tampering, failed tests, local approval, disabled capabilities, cancellation and parent validation. Real REA numeric inspection produced a reconstruction with 14 executed passing checks. A separate real HTTP flow ran REA and the parent recipe (20 checks), privately returned its package, saved it with a synthetic owner's signature, copied the exact package to a synthetic descendant, and extended it through that descendant's own local agent (35 checks). No production wallet was used. Browser checks passed for private review, publication consent, signed saves and mobile layout.

The bundle includes all local runtime helpers and its profile. Deployment preflight and copy lists include these dependencies and native tests. Publication updates the static guide, public explanation, preview and companion download; it requires no database change or backend restart.
