# Qualification progress tracking

The user wants progress on chunks 1–12 tracked and updated whenever we work on
this project. Keep `docs/QUALIFICATION_PROGRESS.md` current when evidence,
completion gates, blockers, priorities or forecasts change. Use
`docs/qualification/pdk-matrix.json`, `docs/PDK_QUALIFICATION_PLAN.md` and the
referenced validation records as the authoritative qualification sources.

Record the snapshot date and relevant code commit. Separate verified results,
preliminary work and forecasts. Keep forecasts conditional, explain their
confidence and revise them when new evidence changes the outlook. Do not infer
overall completion from test counts or from the number of closed chunks. Do not
change a completion gate or promote a partial device to make the tracker look
more complete. Preserve the historical scope of each acceptance record.

Update the tracker during project work; the user chose this instead of scheduled
background checks. A documentation-only tracker update need not interrupt long
running CI jobs by triggering a new push. Preserve it locally and include it in
the next appropriate project push, reporting that distinction to the user.

The user also wants every completed work response for the current and future
chunks to include that chunk's estimated completion percentage. State its
uncertainty and distinguish engineering estimates from verified acceptance.
Keep the estimate in the progress tracker consistent with the final response;
do not increase it merely because more tests were run.
