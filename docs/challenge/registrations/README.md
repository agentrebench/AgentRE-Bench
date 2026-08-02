# AgentRE Challenge Registration Files

Register by opening a pull request that adds one public-safe JSON file to this directory and adds that filename to `index.json`.

Do not include private repository URLs, binaries, source code, ground truth, secrets, private download links, or evaluation notes in this public repository.

## File Naming

Use a lowercase filename based on your GitHub handle and challenge title:

```text
docs/challenge/registrations/example-user-example-challenge.json
```

## Required Private Repository

Create a private repository named:

```text
agentre-challenge-entry
```

Invite the organizer account as a collaborator before opening the pull request. AgentRE infers the private repository from the GitHub handle in the registration file and this required repository name.

## Registration Steps

1. Copy `template.json` to a new filename in this directory.
2. Fill in only public-safe values, including the final tag, resolved commit SHA, binary checksum, display permissions, and eligibility confirmations.
3. Add the new filename to the `files` array in `index.json`.
4. Open a pull request using the challenge registration pull request template.

The leaderboard loads these files as static public data after the pull request is merged. Personal payment, tax, and identity details are collected only from a provisional winner through private verification, never in a public PR.
