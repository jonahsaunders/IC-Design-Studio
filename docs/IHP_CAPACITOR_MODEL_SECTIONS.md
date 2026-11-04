# IHP capacitor model sections

For a catalog-backed project using the reviewed bundled IHP SG13G2 package, the analysis panel offers **Enable IHP capacitor-only corners**. This adds three project-local model-corner choices: `cap_typ`, `cap_bcs`, and `cap_wcs` for the capacitor model library. Each choice keeps every other included model library at its existing nominal section. The visible names identify both the capacitor section and the nominal setting for other models.

The action checks the package lock and model files before adding the choices. Existing global corners and the linked package remain unchanged. The choices and their project-local provenance are saved with the project, can be undone, and do not claim a physical operating range or establish a global process correlation. Native SPICE projects use their embedded libraries and do not offer this action.

The [combined source check](validation/ihp-capacitor-ui-feedback-2026-10-30.json)
passes on Windows and Linux. It verifies actual button selection, undo/redo,
save/reopen, all three exported mixed capacitor/transistor model mappings, and
rejection of changed package inputs. This is source desktop evidence; exact
installed acceptance and full device qualification remain separate.
