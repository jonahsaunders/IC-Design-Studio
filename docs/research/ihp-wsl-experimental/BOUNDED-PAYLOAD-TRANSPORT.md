# Lossless bounded payload transport

The full experimental payload artifact is retained for future same-run Windows
consumption. It is not the only retrieval route. Separate payload artifacts each
contain one raw part (at most 240 MiB) and PAYLOAD.json (at most 1 MiB).
At most 16 parts and 4 GiB aggregate source bytes are accepted; the 16-part bound
can impose a lower effective maximum because each of the three files has its own
parts. Exceeding either limit fails without dropping bytes. A 1.55 GB archive
plus the two small JSON files needs nine or fewer parts at this ceiling.

Full host-proof ZIP parts now also have a 240 MiB ceiling, and their DELIVERY.json
is bounded to 8 MiB. Both routes leave ample outer Actions ZIP framing headroom
below the optional conservative 256 MiB ingestion bound. The actual connector
service cap is 512 MiB, not 256 MiB. Payload manifests are bounded to 1 MiB;
this implementation additionally bounds proof DELIVERY.json to 8 MiB (the
separate small metadata artifact has a 16 MiB total limit). Do not infer actual artifact identity
or size from these source limits: record service artifact metadata and verify the
actual downloaded outer ZIP length and SHA256 before reading its members.

For payload parts, transport_ihp_wsl_payload.py ingest-artifact enforces that
outer identity and cap, exact two-member inventory, raw/original name equality,
regular nonencrypted files, bounded decompression, exact manifest and part hash.
It retains partial failures rather than silently accepting truncated parts.
Merge each validated part into a fresh local parts directory, then use reconstruct
with the independently retained PAYLOAD.json SHA256. The reconstruction verifies
all part offsets, exact inventory, complete file sizes/hashes and inner runtime
archive identity. Only the three exact payload basenames are written. No tar is
extracted or executed. An incomplete reconstruction retains INCOMPLETE.

Packaging streams and independently reads back every part, checks complete source
identity before and afterward, and publishes PAYLOAD.json in small metadata too.
If an incomplete payload prevents splitting, proof parts and explicit failure
metadata are finalized before the packaging command fails. This never establishes
clean preparation or native acceptance. All existing scientific and host-provenance
requirements remain unchanged; no runtime/default promotion is authorized.
