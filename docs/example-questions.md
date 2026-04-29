# Example Questions

RepoLens works best when questions are concrete and repo-specific.

In the default cheap deployment, the backend uses grounded retrieval plus extractive answering, so it is much better at locating files, symbols, endpoints, settings, and implementations than answering vague architecture questions.

## Good question formats

- `Which file defines the <ClassName> class?`
- `Where is the <functionName> function implemented?`
- `Where is <feature-name> implemented?`
- `Where are <settings/configuration> declared?`
- `Which endpoint handles <action>?`
- `Where are environment variables loaded?`
- `Where is authentication implemented?`
- `Where is the database connection configured?`
- `Which file starts the server or app?`
- `Where are tests for <feature-name>?`

## Generic examples that work on many repos

- `Which file defines the main entrypoint?`
- `Where is the server started?`
- `Which file defines the API routes?`
- `Where is authentication implemented?`
- `Where is logging configured?`
- `Where are environment variables loaded?`
- `Where is the database connection configured?`
- `Where is deployment configured?`
- `Which file defines the main React page for this feature?`
- `Where are tests for this module?`

## Better implementation-style phrasing

Prefer:

- `Which file defines the ControlPanelProvider class?`
- `Where are Code Spa settings declared?`
- `Where is Spotify integration implemented?`

Over:

- `How does this whole app work?`
- `Why was this architecture chosen?`
- `Explain the codebase`

## How to tell if an answer is good

Check three things:

1. The retrieved chunks look relevant.
2. The cited `file:start-end` range actually contains the evidence.
3. The answer is specific instead of hand-wavy.

If the evidence is weak, RepoLens should return:

`I don't know from the indexed repo.`

That is expected behavior and is usually better than making something up.
