# Current-package hierarchical resistor export companion

The previously accepted [October 28 source result](SKY130_METAL_HIERARCHY_ELECTRICAL.md)
already covers the selected repeated-cell LI and M1–M4 electrical class. The
[October 29 companion](validation/sky130-current-hierarchical-export-companion-2026-10-29.json)
adds a separate check using candidate SKY130 package revision `5dda725c94efe3c2`.
It executes the actual emitted child subcircuit and its two X calls inside a
wrapper, after removing the export's exact external model directives. The
earlier check inspected the emitted hierarchy and executed a numerically
resolved flattened application subcircuit.

Both records use the same ten retained physical extractions and five passive
sections at 27 °C, but their protocols differ. The earlier acceptance uses
four DC basis sweeps, four AC basis excitations at eight frequencies from 1 kHz
to 10 GHz and a 10⁻¹² A absolute current tolerance. The companion uses one
simultaneous DC vector, four AC bases at five frequencies from 1 kHz to 10 MHz
and a 10⁻¹⁰ A absolute current tolerance. The companion therefore does not
replace or narrow the earlier acceptance. Its literal wrong-model and finite
conductive-bridge controls are additional selected checks; they do not replace
the earlier actual native-extraction fault controls or wrong-section check.
Different selections and batching do not support a like-for-like speed claim.

Windows and Linux each pass the companion's 50 contexts and 250 literal fault
instances. Independent readback and 32 rehashed full-reader corruption
controls pass. Original and corrected attempt identities, exact producer and
reader sources, model assets, runtime identities and raw data remain in the
separate content-addressed archive identified by the validation record. Those
archived tools belong to the companion capture; the repository's October 28
producer, reader, contract and acceptance record remain unchanged.

The initial companion draft incorrectly described the class as newly closed;
the superseded draft and the scope-correction receipts are retained alongside
the archive. This companion does not qualify a complete device family, a full
geometry or operating envelope, distributed RC, measured-model accuracy,
reliability or installed hierarchy behavior. Python interpreter and package
identities were not independently bound before execution, so complete source
environment reproducibility remains unestablished.
