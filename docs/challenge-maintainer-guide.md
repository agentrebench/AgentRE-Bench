# AgentRE Challenge Season 1 Maintainer Guide

This guide is for operating AgentRE Challenge Season 1 using public-safe pull request registrations and private contestant repositories.

## Public vs Private Storage

`~/Projects/AgentRE-Bench/`

Public website code and public-safe registration metadata only. Do not store private contestant repositories, binaries, source code, private repository URLs, ground truth, private evaluation notes, or full model transcripts here.

`~/Private/agentre-submissions/season-1/`

Private DGX Spark working area for cloned contestant repositories and evaluations.

Suggested private layout:

```text
~/Private/agentre-submissions/season-1/
|-- ARENA-001/
|   |-- repo/
|   |-- evaluation/
|   |-- evaluated-commit.txt
|   |-- review-notes.md
|   `-- metadata.json
|-- ARENA-002/
|   |-- repo/
|   |-- evaluation/
|   |-- evaluated-commit.txt
|   |-- review-notes.md
|   `-- metadata.json
`-- registry.json
```

Setup:

```bash
mkdir -p ~/Private/agentre-submissions/season-1
chmod 700 ~/Private/agentre-submissions
chmod 700 ~/Private/agentre-submissions/season-1
```

## Registration Architecture

The public website remains a static GitHub Pages site from `docs/`.

Registration is handled by pull request:

1. Entrant creates a private GitHub repository named `agentre-challenge-entry`.
2. Entrant invites `agentrebench` as a collaborator.
3. Entrant forks `AgentRE-Bench`.
4. Entrant copies `docs/challenge/registrations/template.json` to a new public-safe registration file.
5. Entrant adds the new filename to `docs/challenge/registrations/index.json`.
6. Entrant opens a public registration pull request using `.github/PULL_REQUEST_TEMPLATE/challenge-registration.md`.
7. After merge, the static leaderboard loads the registration file from the manifest.

The pull request is public. It must not include private repository URLs, binaries, source code, ground truth, secrets, private download links, private evaluation notes, or model transcripts.

## Public Files To Edit

Challenge configuration:

```text
docs/challenge/challenge-config.js
```

Static fallback leaderboard data:

```text
docs/challenge/challenge-data.js
```

Registration manifest:

```text
docs/challenge/registrations/index.json
```

Registration template:

```text
docs/challenge/registrations/template.json
```

Participant registration files:

```text
docs/challenge/registrations/<github-handle>-<challenge-slug>.json
```

Challenge registration PR template:

```text
.github/PULL_REQUEST_TEMPLATE/challenge-registration.md
```

Do not scatter Season 1 values across pages. Challenge pages read status, dates, prize, organizer account, size limit, maximum entries, minimum accepted submissions, minimum model-panel wins, final tag, official model panel, PR URL, registration manifest URL, template path, private repository name, scoring method, result metrics, and tie-breakers from `challenge-config.js`.

## Updating Competition Configuration

Edit `docs/challenge/challenge-config.js`.

Update dates:

- `dates.submissionOpens`
- `dates.registrationDeadline`
- `dates.finalCommitDeadline`
- `dates.validationDates`
- `dates.evaluationDates`
- `dates.winnerAnnouncement`

Update the organizer username:

- `organizerGithubUsername`

Update the required private repository name:

- `privateRepositoryName`

Update registration paths:

- `registrationPageUrl`
- `registrationPullRequestUrl`
- `registrationManifestUrl`
- `registrationTemplatePath`

Update the prize:

- `prizeAmount`
- `firstPlaceSubscriptionPrize`
- `secondPlaceSubscriptionPrize`

Update entry and prize limits:

- `minimumAcceptedSubmissions`
- `maximumEntriesPerEntrant`
- `minimumModelPanelWinsForPrize`

Update the final tag:

- `finalSubmissionTag`

Update the official model panel:

- `officialModelPanel`

Update overall competition status:

- `competitionStatus`

Supported statuses:

- `upcoming`
- `open`
- `validation`
- `judging`
- `complete`
- `archived`

Archive Season 1 by setting:

```js
competitionStatus: "archived"
```

## Reviewing Registration PRs

A valid registration PR should:

1. Add exactly one public-safe JSON registration file under `docs/challenge/registrations/`.
2. Add that filename to `docs/challenge/registrations/index.json`.
3. Use `private_repository_name: "agentre-challenge-entry"` unless the organizer explicitly approved a different name.
4. Include the final tag `agentre-season-1-final`.
5. Include the resolved full 40-character final commit SHA.
6. Include a full 64-character binary SHA-256 digest.
7. Confirm private repository access, required files, rules, age, U.S. eligibility, free entry, designated prize recipient, original-work rights, and public PR safety.
8. Avoid private repository URLs and private artifacts.

Before merging:

```bash
jq empty docs/challenge/registrations/index.json
jq empty docs/challenge/registrations/*.json
```

Also run the site validation checks described below.

## Assigning Entry IDs

Participant files may start with:

```json
"entry_id": "PENDING"
```

After accepting a registration, the maintainer may assign the next `ARENA-###` ID by editing the entrant JSON file in the PR before merge, or in a follow-up public-safe PR.

Do not expose private rejection details. For rejected entries, set:

```json
"validation_status": "Rejected",
"evaluation_status": "Not evaluated"
```

## Status Management

Update each entrant public-safe registration JSON file.

Mark an entrant validated:

```json
"validation_status": "Validated"
```

Mark an entrant rejected without exposing private reasons:

```json
"validation_status": "Ineligible",
"evaluation_status": "Not evaluated"
```

Mark an entrant under evaluation:

```json
"evaluation_status": "Under evaluation"
```

Add final scores:

```json
"rank": 1,
"models_tested": 6,
"average_model_correctness": 27.0,
"median_model_correctness": 25.0,
"model_panel_wins": 4,
"models_below_passing_threshold": 4,
"complete_failures": 1,
"difficulty_score": 73.0,
"award": "$1,000 + one month of ChatGPT Pro or Claude Max 20x",
"public_summary": "Sanitized public result summary.",
"evaluation_status": "Complete"
```

Publish award recipients:

1. Confirm at least the configured minimum accepted submissions qualified.
2. Confirm the evaluation produced reliable valid scores.
3. Confirm the provisional first-place entry is the lowest-scoring entry on at least `minimumModelPanelWinsForPrize` official models.
4. Rank qualifying entries by lowest average official model correctness, equivalently highest difficulty score.
5. Update the first-place public entry with rank, model-panel wins, difficulty score, award, and sanitized summary.
6. If a distinct second eligible entry exists, update it with rank, difficulty score, the second-place subscription award, and a sanitized summary.
7. Set `competitionStatus: "complete"` in `docs/challenge/challenge-config.js`.
8. Do not publish private ground truth, raw transcripts, private notes, or private repository URLs.

Add a public repository URL after participant approval:

1. Confirm the participant explicitly approved the public link.
2. Set `public_repository_url` to the approved public repository URL.
3. Only link public repositories, never private ones.

## Safe Clone Workflow

Run this only in the private DGX storage tree. The public PR must not include private repository URLs. Infer the private repository from the public `github_handle` and required repository name after confirming collaborator access.

```bash
cd ~/Private/agentre-submissions/season-1
mkdir -p ARENA-001
git clone git@github.com:PARTICIPANT/agentre-challenge-entry.git ARENA-001/repo
cd ARENA-001/repo
git fetch --tags
git rev-parse agentre-season-1-final^{commit} | tee ../evaluated-commit.txt
git checkout FULL_40_CHARACTER_COMMIT_SHA
sha256sum -c SHA256SUMS
```

The tag `agentre-season-1-final` must exist before the deadline. Moving or deleting the tag after registration may disqualify the entry. Evaluate only the resolved full 40-character commit SHA recorded in `evaluated-commit.txt`.

Safety rules:

- Do not store private material in the public website repository.
- Do not push changes to contestant repositories.
- Do not run GitHub Actions from contestant repositories.
- Do not trust build scripts.
- Treat all contestant code as hostile.
- When verification materials are requested, inspect source before building.
- Build and evaluate in isolated disposable environments.
- Disable networking during build and evaluation.
- Do not expose private repository names or URLs.
- Do not publish private ground truth.
- Sanitize transcripts before publication.
- Record private acceptance, rejection, and scoring notes outside the website repository.

## Official Tool Environment

Season 1 uses the standard AgentRE static-analysis tool surface from the harness. Do not create a separate challenge-only tool environment unless the public rules are updated before entries open.

Official image:

```text
agentre-bench-tools:latest
```

Build from the repository root:

```bash
docker build --platform linux/amd64 -t agentre-bench-tools:latest -f Dockerfile.tools .
```

The official tool image should be pinned to the same harness commit recorded for the competition opening. Record the image digest privately with the evaluation notes.

Official AgentRE tools exposed to models:

- `file`
- `strings`
- `readelf`
- `objdump`
- `nm`
- `hexdump`
- `xxd`
- `entropy`
- `final_answer` is the structured answer submission tool.

Default limits from the harness are 25 tool calls, 30 seconds per tool call, and 50,000 output characters per tool result. If these values change, update `docs/challenge/challenge-config.js` and publish the new rule before entries open.

Not allowed in official scoring unless a public rules update says otherwise:

- Dynamic execution, debugging, `strace`, `ltrace`, or runtime sandboxing.
- Model-generated or arbitrary Python or code in any other programming language.
- Ghidra, IDA, Binary Ninja, radare2, decompilers, custom parsers, symbolic executors, deobfuscators, package installs, or internet access.
- Participant-supplied helper tools or undocumented analysis dependencies.

The fixed tool surface is required for fair, reproducible comparisons. Do not let a model create or execute new analysis tools during evaluation.

## Official Scoring Operations

Season 1 ranks eligible entries by lowest average official model correctness, but the prize winner must also be the lowest-scoring entry on at least `minimumModelPanelWinsForPrize` official models. The public difficulty score is:

```text
100 - average official model correctness
```

Use the official model panel configured in `docs/challenge/challenge-config.js`:

- Gemini 3.1 Flash Lite
- DeepSeek V4 Pro
- Claude Opus 4.8
- Kimi K3
- DeepSeek V4 Flash
- GPT-5.5

For every accepted binary, use the same harness commit, system prompt, static-analysis tools, tool-call limit, token budget, time limit, attempt policy, and scoring rubric. Freeze exact model identifiers, harness commit, prompt version, budgets, attempt policy, and test date when submissions open.

A model-panel win means the entry has the lowest valid correctness score for that official model among eligible entries. If entries tie for the lowest valid score on a model, each tied entry may count that model as a panel win for qualification.

Invalid runs are not scored as zero. Do not count safety refusals unrelated to technical difficulty, infrastructure failures, API errors, tool crashes, challenge-unrelated resource abuse, malformed or unsupported binaries, missing files, or undocumented dependencies as model failures. A model's failure to solve a valid, difficult binary within the standard budget is a valid outcome.

Tie-break order is configured in `challenge-config.js`:

1. More official model panel wins.
2. Lower median official model correctness.
3. More official models below the passing threshold.
4. Higher manual meaningful reverse-engineering difficulty score.
5. Higher reproducibility score.
6. Earlier frozen submission timestamp.

If entries remain exactly tied after all tie-breakers, divide the $1,000 prize equally.

## Local Preview

The site is a plain static GitHub Pages site published from `docs/`. From the DGX Spark:

```bash
cd ~/Projects/AgentRE-Bench
python3 -m http.server 8081 --bind 127.0.0.1 --directory docs
```

From the maintainer's Mac:

```bash
ssh -L 8081:127.0.0.1:8081 dgx
```

Then open:

```text
http://localhost:8081
```

Port 8080 may already be used by another service on this machine. If you choose a different free port, replace both forwarded port values with that port.

Challenge routes:

- `http://localhost:8081/challenge/`
- `http://localhost:8081/challenge/register/`
- `http://localhost:8081/challenge/rules/`
- `http://localhost:8081/challenge/submit/`
- `http://localhost:8081/challenge/leaderboard/`

## Validation Commands

```bash
node --check docs/challenge/challenge-config.js
node --check docs/challenge/challenge-render.js
jq empty docs/challenge/registrations/index.json
jq empty docs/challenge/registrations/*.json
```

Also verify the local preview routes and scan registration files before merge for private URLs, secrets, binaries, source code, and ground truth.
