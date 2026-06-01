# Third-Party Notices

This software includes or depends on third-party components, each of
which is governed by its own license. Nothing in the project's main license
([Millionaire Source-Available License v2.0](LICENSE)) replaces, limits, or
supersedes the rights and obligations you have under those third-party
licenses.

You must preserve all copyright notices, license texts, NOTICE files, and
attribution statements associated with third-party components when using,
modifying, or distributing this software.

## Direct Runtime Dependencies

The table below lists the project's direct runtime dependencies, with the
version resolved at the time of release and the license that governs
each component. For the complete list of transitive dependencies, run
the command in the next section.

| Component        | Version  | License                          |
|------------------|----------|----------------------------------|
| aiosmtplib       | 5.1.0    | MIT                              |
| apscheduler      | 3.11.2   | MIT                              |
| arrow            | 1.4.0    | Apache-2.0                       |
| bcrypt           | 5.0.0    | Apache-2.0                       |
| bidict           | 0.23.1   | BSD-3-Clause                     |
| cffi             | 2.0.0    | MIT                              |
| loguru           | 0.7.3    | MIT                              |
| monsterui        | 1.0.44   | Apache-2.0                       |
| msgpack          | 1.1.2    | Apache-2.0                       |
| pandas           | 2.3.3    | BSD-3-Clause                     |
| polars           | 1.38.1   | MIT                              |
| polars-talib     | 0.1.5    | MIT                              |
| pyarrow          | 22.0.0   | Apache-2.0                       |
| python-fasthtml  | 0.12.48  | Apache-2.0                       |
| sqlite-utils     | 3.39     | Apache-2.0                       |
| tenacity         | 9.1.4    | Apache-2.0                       |
| tushare          | 1.4.25   | Proprietary (TuShare ToS)        |
| websockets       | 15.0.1   | BSD-3-Clause                     |

## Generating the Complete List

To regenerate this file with the full set of all transitive dependencies
(including their license texts), install `pip-licenses` and run:

```bash
poetry run pip-licenses \
    --format=markdown \
    --with-authors \
    --with-license-file \
    --output-file=NOTICE.md
```

To install the tool itself: `pip install pip-licenses`.

The flags above embed the full license text of each component. If you
prefer a shorter output that omits the embedded texts, drop the
`--with-license-file` flag.

## Apache-2.0 Attribution

The components above licensed under the Apache License, Version 2.0 may
include NOTICE files distributed with the original work. You may obtain
a copy of the Apache License at:

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the Apache License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

## TuShare

The `tushare` package provides access to TuShare's financial data API
under TuShare's own Terms of Service. Use of TuShare data and any
derivative work produced from it is governed by TuShare's terms, not
by this NOTICE or the project's main license.
