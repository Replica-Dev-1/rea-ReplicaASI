# Replica Runner: standalone specialists

Replica's own agents run on your computer. They use a defined set of local specialists, with no language model, model account, shared core or upstream agent connection. REA supplies software-inspection evidence. Replica's relay handles paired tasks and reviewed artifacts; it does not run your source code.

## Install

Extract the runner ZIP into a new folder. Use Python 3.10+ and Node supported by REA 6.8.0: Node 22.23.4+, 24.22.1+, or 26.12.1+ in the supported branches. Windows checks used Python 3.11 and Node 24.22.1.

```
npm install --ignore-scripts --prefix integrations/rea
python tools/replica_runner.py doctor
```

Installation contacts npm to install the pinned `rea-agents@6.8.0`. The doctor checks local tools and the bundled agent profile; it does not inspect source, request a model, or pair a wallet.

## Pair and select a file

Connect the wallet hosting your replica on ReplicaASI. Under **investigate with REA → connect your computer**, create a pairing code. Run:

```
python tools/replica_runner.py pair --site https://replicaasi.com --name "my computer"
python tools/replica_runner.py serve --source "samples/notes-target/search.cjs" --label "notes example"
```

Paste the one-time code when asked. Keep the terminal open. On the site, ask **Build the notes search.** The selected file is the included MIT reference application. Change `--source` to inspect another supported JavaScript or TypeScript file; building arbitrary applications is outside this release's scope.

Pairing codes expire after ten minutes and work once. A connection expires after 30 days. Disconnect on the site to revoke it. A wallet transfer does not transfer the previous owner's computer connection or private tasks. `--state` selects a separate private state directory for another replica.

## Inspect → build → review → save

1. Read the requested question and selected filename locally, then type `inspect`. REA analyzes a fresh copy of only that file without executing the inspected application.
2. The native coordinator checks the evidence's source digest and selects an enabled specialist. It records the replica identity, profile, task, source and evidence in a hashed receipt. Unsupported work receives a decline; there is no fallback to another service.
3. If a build is covered, read the specialist's stated scope and type `build`. The agent assembles the supported implementation in a separate `.replica-builds` folder and runs its bundled checks. Unknown source and supplied package commands are never executed. The notes recipe executes only the exact known reference and bundled reconstruction; numeric reconstruction emits constrained code from an admitted source form.
4. Open the printed `skill.json` path and review every embedded file. Type `send` only when ready. An inspection-only result sends its summary, source digest and evidence identity. A build result sends the **whole package**, including source, implementation, tests and evidence, to your private review area.
5. On the site, review the returned package. Public saving and allowing descendants to inherit it are separate choices. No local build signs a public memory entry by itself.

If a build fails or is declined, the completed inspection can still be returned without a package. Tests must actually run and all required cases must pass before a package is created. The relay validates file hashes and structure; it does not independently certify local test claims.

## What the first specialists cover

| Specialist | Supported work | Boundary |
| --- | --- | --- |
| Source evidence | Bind a successful REA module observation to the exact selected source | Static structure does not establish arbitrary runtime behavior |
| Numeric helper | Reconstruct one CommonJS arrow function with one `+`, `-`, `*` or `/` operation and a numeric constant | Exact form below; finite numeric inputs in [-1000000, 1000000], constant magnitude at most 1000000; division by zero declined |
| Notes search | Rebuild the included reference search from an authored recipe; execute 20 checks | Exact reference-source digest required; not inferred general application reconstruction |
| Notes extension | Extend a reviewed inheritable notes-search parent with all-word matching and result limits; execute 35 checks | Parent implementation and tests must match the admitted recipe; arbitrary inherited code is not executed |

Example admitted numeric source:

```javascript
module.exports = { scale: x => x * 3 };
```

Ask **Build a numeric helper from this function.** One exported property, one arrow parameter, a parameter-left operation and a decimal constant are supported. An optional `use strict` directive is allowed. Other source forms decline. The rebuilt helper deliberately rejects strings, null, non-finite and out-of-range values; it does not promise every JavaScript coercion of the original. Fourteen checks cover numeric cases and rejected inputs.

These are native, bounded specialists, not open-ended code generation or model training. Broader capabilities require new specialist implementations and meaningful acceptance tests.

## Continue an inherited search skill

Download the approved parent package from your replica's skill list. Stop the current runner, then restart it with that reviewed file:

```
python tools/replica_runner.py serve --source "samples/notes-target/search.cjs" --label "notes example" --parent "path/to/inherited.skill.json"
```

Ask **Extend the notes search with all words and a limit.** The new package records the exact parent package digest. The signed copying flow determines which skills a descendant actually inherits. Selecting a local file is not proof of wallet ownership and does not grant publication rights. New owners pair their own runner and approve their own work.

## Customize a replica's specialist set

The included `agents/replica/agent.json` selects a name and admitted specialist IDs. Copy it, edit the name or remove capabilities, and select it using `--agent-profile "path/to/agent.json"`. Each run binds the profile digest to the replica's asset-derived agent identity.

`core` must remain `never`, and `language_model` must remain `false`. Unknown specialists, remote endpoints and extra settings are rejected. A profile cannot grant arbitrary commands, add executable code or enable a remote fallback. `--agent inspect` disables the build coordinator entirely.

## Data and local files

The native agent has no network client. The companion communicates with your configured Replica relay over outbound HTTPS, with redirects refused. There is no inbound HTTP listener. Source and evidence are not sent to a model provider. The source text becomes part of a build package and leaves the computer only after the separate `send` approval.

The relay stores questions, chosen labels, filenames and approved results for private review. They are not end-to-end encrypted. Private jobs expire seven days after their last update; cancelling clears the private result. Disconnecting clears that runner's private results. Queued tasks expire after one day; running tasks after 30 minutes without an update. Interrupted tasks are not automatically replayed.

`.replica-runner/connection.json` is a scoped connection credential, not a wallet key. Its directory is restricted to the current OS account. Never publish it. Build folders are separate, and credentials are not copied into them. The runner cannot transfer tokens, mint replicas or sign public memory entries.

Source files are limited to 1 MB. REA has a 60-second process deadline, 20-second analysis timeout and 256 MB JavaScript heap setting. Bundled build checks have a 20-second deadline. Task cancellation or revocation is checked before and after build execution; an already-running check may finish locally before cancellation is observed. The fixed recipes are reviewed code, not a general execution sandbox.

Use `--builds` for a different build folder outside private runner state, `--node` and `--rea` for explicit installed tool paths, and `--once` to handle at most one queued task. Stop polling with Ctrl+C. If the selected source changes, queue a new task. Raw tool errors remain local.
