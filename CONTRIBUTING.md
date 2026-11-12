# Helping with Arnheim

Thank you. Arnheim is small on purpose: plain ES modules and Three.js in the browser, one file of
standard-library Python to serve it, no build step and nothing to install. Changes that keep it
that way are the easiest to take.

## Run it

```bash
python3 serve.py
```

Open http://127.0.0.1:8740, change a file and reload: nothing is cached. To try your change with a
company of your own, put it in `data/` (README, "Make it yours"); git ignores that folder.

## Check a change

- Run the tests, which need only Python:

  ```bash
  python3 -m unittest discover tests
  ```

  They check the server's rules (what it serves, and to whom) and that the sample's files hang
  together. Some run rules of the page under Node.js (who may be shown photo-real, what is waiting
  on you, what counts as proven, and what the receptionist remembers), and are skipped where Node
  isn't installed.
- Try what you changed in the page: the building, a floor and a room, the panel, the receptionist, a walk
  through a few floors, light and dark, and `?list` (the panel alone).
- Turn on reduced motion in your system's settings and try it again: the camera should keep still.
- If you changed anything a phone shows, try it on one with `python3 serve.py --lan`.
- If you changed the voice, try it with the voice set up (README, "Voice"), and without.

## Rules

- **No personal data, ever.** No real names, email addresses, machine names, home-folder paths,
  account ids, private company data or secrets, in code, comments, the sample, tests, pictures or
  commit messages. The sample company is made up and says so: anything you add to it is made up
  too, and web addresses end in `.example`.
- **Your own company stays in `data/`.** Never commit it, or a picture of it.
- **Read your diff before you push it**, looking for anything in the first rule. A quick search of
  what you are about to commit helps:

  ```bash
  git diff --cached | grep -inE "password|secret|token|api[_-]?key|@[a-z0-9-]+\.[a-z]{2,}|/Users/|/home/"
  ```

- **Third-party code keeps its licence.** Copy it into `vendor/`, unchanged where you can, and add
  its notice to `THIRD_PARTY_NOTICES.md`. The page loads nothing from other sites.
- **Everything in the 3D view is also in the panel**, as a list, so the building is never the only
  way to see something.
- **Plain words on screen**: short sentences, and no jargon where an everyday word will do.

## Licence

Arnheim is MIT licensed (`LICENSE`). What you contribute is released under the same licence.
