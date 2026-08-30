# GenomeTriage submission checklist

**For research/expert review. Not a medical diagnosis.**

## Repository and evidence

- [x] Complete source code included.
- [x] Versioned model instructions/prompts included.
- [x] Improvement Changelog included.
- [x] Intended user and bottleneck stated.
- [x] Baseline and same-case evaluation documented.
- [x] V0-top3 control documented.
- [x] Runtime, token, model, and pricing assumptions documented.
- [x] Public-data provenance and versioned record IDs retained.
- [x] Phase 1/2/3 and Phase 4 input hashes validate.
- [x] Historical predictions/results are not rewritten by reproduction commands.

## Product and demo

- [x] V1 is the visible default workflow.
- [x] V2/V3 are visibly experimental/non-retained.
- [x] Offline Judge Mode works without an API key.
- [x] Replay identifies itself as recorded/deterministic.
- [x] Same-case V0/V1 comparison is available.
- [x] Evaluation dashboard loads frozen machine-readable metrics.
- [x] Evidence IDs, strength/category, and provenance render.
- [x] Uncertainty/counterevidence render where present.
- [x] Product mode does not expose evaluator ground truth.
- [x] Malformed uploaded input is rejected safely.
- [x] Human-review checkpoint and safety statement are prominent.
- [x] Representative challenging and public cases are available.
- [x] Demo screenshot captured in `docs/images/`.

## Submission artifacts

- [x] README landing page and architecture diagram.
- [x] Exact offline and optional live commands.
- [x] `docs/FINAL_REPORT.md`.
- [x] `docs/TRAJECTORIES.md` plus five JSON trajectories.
- [x] `docs/VIDEO_SCRIPT.md` targeting 4:40.
- [x] Removed experiments and Hot Take documented.
- [x] Tests, dependency checks, benchmark checks, freeze checks, and secret scan.

## Human-only steps before upload

- [ ] Record the ≤5-minute video using `docs/VIDEO_SCRIPT.md`.
- [ ] Watch the final video once at normal speed and verify all text is legible.
- [ ] Upload the video and add its final URL to the submission form/README if desired.
- [ ] Confirm the challenge form's current title, summary, team, repository URL, and
  licensing fields.
- [ ] Verify the submitted repository revision/tag is
  `phase4-judge-ready-submission`.
- [ ] Perform a clean-clone rehearsal on the machine used for the final demo.
- [ ] Ensure `.env` and any local screen recordings containing secrets are excluded
  from the uploaded repository/archive.

Do not start a new research phase as part of submission cleanup.
