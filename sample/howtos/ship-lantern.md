# Ship a new build of Lantern

Made up, like the rest of Fernhollow.

## Before you start

- The tests pass: `npm test` in the Lantern folder.
- Nobody else is changing `reader/` today. The building shows a warning if two agents are.

## Steps

1. Raise the version in `package.json` by one minor step.
2. Run `npm run build`. It writes the app to `build/`.
3. Open the build on the spare laptop and read three pages, one of them at night.
4. Write the release notes (see "Write release notes").
5. Send the build to the store with `npm run release`.

## If something goes wrong

Stop, and tell the person who asked you. Never send a build twice in one day.
