# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

You can contribute in many ways:

## Your Contribution

Contributions of all sizes are welcome, and the maintainers are grateful
for your time and effort. Before you send a pull request, please take a
moment to read the notes below — they describe what happens to your
contribution and what it does and does not grant you.

This project is released under the [Quantide Source-Available License v2.0](LICENSE).

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

Report bugs at https://github.com/zillionare/quantide/issues.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

### Write Documentation

quantide could always use more documentation, whether as part of the
official quantide docs, in docstrings, or even on the web in blog posts,
articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at https://github.com/zillionare/quantide/issues.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `quantide` for local development.

1. Fork the `quantide` repo on GitHub.
2. Clone your fork locally

```
    $ git clone git@github.com:your_name_here/quantide.git
```

3. Ensure [poetry](https://python-poetry.org/docs/) is installed.
4. Install dependencies and start your virtualenv:

```
    $ poetry install -E test -E doc -E dev
```

5. Create a branch for local development:

```
    $ git checkout -b name-of-your-bugfix-or-feature
```

   Now you can make your changes locally.

6. When you're done making changes, check that your changes pass the
   tests, including testing other Python versions, with tox:

```
    $ tox
```

7. Commit your changes and push your branch to GitHub:

```
    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature
```

8. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in README.md.
3. The pull request should work for Python 3.6, 3.7, 3.8, 3.9 and for PyPy. Check
   https://github.com/zillionare/quantide/actions
   and make sure that the tests pass for all supported Python versions.

## Tips

```
    $ pytest tests
```

To run a subset of tests.


## Deploying

A reminder for the maintainers on how to deploy.
Make sure all your changes are committed (including an entry in HISTORY.md).
Then run:

```
$ poetry patch # possible: major / minor / patch
$ git push
$ git push --tags
```

Github Actions will then deploy to PyPI if tests pass.
