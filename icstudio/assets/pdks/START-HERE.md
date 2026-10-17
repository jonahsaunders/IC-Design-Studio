# Included simulation PDKs

In IC Design Studio, choose **Tools → Set up an open PDK → Use included PDKs**. Then select a revision and choose **New project with this PDK**. These packages install offline.

- SKY130A: 71 placeable / 74 indexed symbols, selected primitive models and a layer display map. The default package includes the reviewed resistor parallel-factor and deterministic NPN corner corrections.
- GF180MCU C and D: 64 placeable / 68 indexed symbols per variant, transistor/bipolar/passive models, layer maps and distinct physical decks.
- IHP SG13G2: 35 placeable / 45 indexed symbols, model sources, layer maps and physical decks. The default package includes the reviewed standard-MIM checking correction.

These are bounded public PDK subsets with incomplete device qualification. Unavailable symbols remain visibly unavailable. The separately prepared physical runtime supplies matching IHP compiled models and digital-flow resources. Every package asset is checksummed; original revisions, licenses and modification notices are retained. Existing projects keep their registered revisions until you explicitly migrate them.
