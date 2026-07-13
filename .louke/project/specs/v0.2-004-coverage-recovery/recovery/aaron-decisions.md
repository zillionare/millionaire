# Aaron Decisions

> No deletion or waiver is decided here. Evidence and inference are separate.

Final Sage precedence review used production index `8410d32fb4b64c0d38ef21f947c45be7164185dcaa09f36a7061bc99b9c8bfbe` and shard manifest `4ec8dbdbf8eaabfe1d8a355df778ae438e03b6dc3b18b0038955ba91472cac39`. All 55 additional `Sage-review-required` candidates were resolved by locked evidence; **0** were promoted. The six original decisions below remain unresolved because each still requires Aaron to choose a user-observable retention/deletion/waiver or retirement outcome.

| ID | Path | Evidence | Inference/options |
|---|---|---|---|
| AD-01 | `quantide/web/auth/admin_routes.py` | legacy admin registration route excluded by FR-0504 | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-02 | `quantide/web/auth/forms.py` | legacy registration/reset forms excluded by FR-0504 | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-03 | `quantide/web/auth/repository.py` | multi-user repository overlaps single-admin contract | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-04 | `quantide/web/auth/utils.py` | helper tied to legacy auth surface | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-05 | `quantide/core/utils.py` | missing from coverage and no static consumer/importer | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |
| AD-06 | `quantide/web/pages/analysis.py` | source explicitly renders retired placeholder | Candidate only: Aaron chooses delete after consumer/route review, retain and test to target, or (pre-v0.2 only) specific expiring waiver. |

## Final decision set

- Unresolved IDs: `AD-01`, `AD-02`, `AD-03`, `AD-04`, `AD-05`, `AD-06`
- Unresolved count: **6**
- New decisions promoted by the 55-candidate review: **0**
- Resolved/waived/deleted by Sage: **0**

No generic waiver; no v0.2-added waiver. Silence, compatibility evidence, coverage status and the 55-candidate review do not decide any of these six on Aaron's behalf.
