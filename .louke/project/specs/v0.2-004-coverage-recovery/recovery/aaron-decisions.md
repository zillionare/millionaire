# Aaron Decisions

> No deletion or waiver is decided here. Evidence and inference are separate.

| ID | Path | Evidence | Inference/options |
|---|---|---|---|
| AD-01 | `quantide/web/auth/admin_routes.py` | legacy admin registration route excluded by FR-0504 | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-02 | `quantide/web/auth/forms.py` | legacy registration/reset forms excluded by FR-0504 | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-03 | `quantide/web/auth/repository.py` | multi-user repository overlaps single-admin contract | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-04 | `quantide/web/auth/utils.py` | helper tied to legacy auth surface | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-05 | `quantide/core/utils.py` | missing from coverage and no static consumer/importer | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-06 | `quantide/web/pages/analysis.py` | source explicitly renders retired placeholder | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |

**Decision count: 6.** No generic waiver; no v0.2-added waiver.
