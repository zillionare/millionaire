# Contributing

Contributions of all sizes are welcome, and the maintainers are grateful
for your time and effort. You can contribute in many ways — reporting
bugs, fixing issues, implementing features, improving documentation,
reviewing pull requests, and more.

Before you send a pull request, please take a moment to read the notes
below — they describe what happens to your contribution and what it does
and does not grant you.

## Your Contribution

This project is released under the [Millionaire Source-Available License v2.0](LICENSE).

- By submitting a contribution (whether as a pull request, patch, file,
  or any other form), you confirm that the project may use, modify, and
  redistribute it as part of the project, in accordance with that
  license and any future license the maintainers may adopt for the
  project as a whole.

- You retain copyright to your contribution. Submitting a contribution
  does not transfer, and is not intended to transfer, any ownership of,
  equity in, or commercial interest in the project, its name, its
  branding, or its future releases. The project name, branding, and
  trademarks are not granted to contributors by virtue of their
  contribution.

- If you are contributing on behalf of an employer or other organization,
  please make sure you have the right to do so, and that you have the
  authority to make the confirmations above on its behalf.

- The maintainers may, at their sole discretion, accept, reject, modify,
  or remove contributions, including after they have been merged, without
  obligation to provide a reason or notice.

If anything in this section is unclear, or if you would like to discuss
the terms under which you would like to contribute, please open an issue
before submitting your pull request, or contact the maintainers directly.
The maintainers are happy to talk — a short conversation up front usually
saves time on both sides.

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/zillionare/millionaire/issues.

If you are reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and
"help wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with
"enhancement" and "help wanted" is open to whoever wants to implement it.

### Write Documentation

Millionaire could always use more documentation, whether as part of the
official docs, in docstrings, or even on the web in blog posts,
articles, and similar write-ups.

### Submit Feedback

The best way to send feedback is to file an issue at
https://github.com/zillionare/millionaire/issues.

If you are proposing a feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible, to make it easier to implement.
- Remember that this is a volunteer-driven project, and that
  contributions are welcome.

## Get Started!

Ready to contribute? Here's how to set up `millionaire` for local development.

1. Fork the `millionaire` repo on GitHub.
2. Clone your fork locally:

   ```bash
   git clone git@github.com:your_name_here/millionaire.git
   ```

3. Ensure Python 3.13 is available, and that [Poetry](https://python-poetry.org/docs/) is installed.
4. Create a virtual environment and install dependencies:

   ```bash
   python3.13 -m venv .venv --prompt=millionaire-py3.13
   source .venv/bin/activate
   poetry install
   ```

5. Create a branch for local development:

   ```bash
   git checkout -b name-of-your-bugfix-or-feature
   ```

   Now you can make your changes locally.

6. When you're done making changes, run the relevant tests:

   ```bash
   pytest tests
   ```

   The release-gate evidence suite and the minimum pre-commit checks are
   documented in `docs/developer-acceptance.md`.

7. Commit your changes and push your branch to GitHub:

   ```bash
   git add .
   git commit -m "Your detailed description of your changes."
   git push origin name-of-your-bugfix-or-feature
   ```

8. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated.
   Put your new functionality into a function with a docstring, and add
   the feature to the list in `README.md` if it is user-facing.
3. The pull request should work on the supported Python version. Check
   https://github.com/zillionare/millionaire/actions and make sure that
   the tests pass for the supported version.
