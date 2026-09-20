# Statistical campaign worker acceptance

Saved plans can capture 2–10,000 explicit statistical trials, subject to the
10,000 total-case limit. Every trial reuses its sampled values across all selected
tests, process corners, temperatures and supplies. Trial IDs, seed, mappings,
model evidence and sampled values are saved in immutable inputs. Restarting
replays those values; it never draws replacement samples.

Use **Verification test plans → Edit plan → Statistical verification…** to select
independent tolerances, correlated tolerances or an evidence-backed PDK model.
**Create resumable campaign…** captures the inputs. **Statistical results…**
reports each PVT condition separately and the joint result across all conditions.
Numerical failures, missing requirements and measurement errors are unresolved
trials. Pass fractions and 95% Wilson intervals remain unavailable until all
trials resolve. The denominator is trials, never the multiplied PVT case count.
Component tolerance results are not foundry manufacturing yield.
The saved seed governs these explicit numeric parameter mappings. It does not
control or qualify opaque random functions inside third-party SPICE model
libraries; those need a separate model-specific seeding and validation adapter.

## Real local workload

```sh
python scripts/qualify_statistical_campaign.py \
  --output build/statistical-campaign-qualification \
  --executable /absolute/path/to/ngspice \
  --trials 128 --workers 4 --snapshot
```

The default workload executes **1,152 actual ngspice operating-point cases**:
128 correlated resistor-divider trials × 3 temperatures × 3 supplies. It kills
the coordinator abruptly after at least 12 cases complete, starts a fresh runner,
waits for expired five-second leases and verifies immutable inputs and stale-token
rejection. Each waveform-derived ratio and pass/fail classification is checked
against the exact resistor-divider formula. Deliberately narrow ratio limits
produce measurable specification failures; correct classification of those
failures is part of qualification, not a script failure.

`qualification.json` records source identity, executable hash and version,
throughput, sampled process-tree resident memory, attempts, recovery evidence,
analytical errors and separate/joint statistical results. The optional source
snapshot copies the Python implementation and dispatcher, checks all hashes, and
runs from that frozen copy. It does not freeze system libraries or the external
simulator installation; retain the recorded runtime with the evidence.

This small ideal circuit qualifies sampling, numerical bookkeeping and scheduler
behavior. It is not a benchmark of a large extracted analog circuit or a foundry
mismatch model. Measured throughput is hardware- and workload-specific.

## Two-host filesystem probe

Two-host acceptance remains **not run** unless evidence was actually captured
from both machines. A same-host smoke run cannot satisfy this acceptance.

Provision trusted worker hosts A and B with the same Studio source/build,
Python ABI, simulator/tool binaries and dependency versions. Mount the shared
campaign directory at the same absolute path. Verify that clocks are synchronized
to within five seconds when using the default 60-second lease. Record the host
identities, filesystem type, mount options and clock synchronization evidence.
Cloud-synchronization folders do not provide the required shared database locks.
No network filesystem is assumed qualified based solely on its name.

On host A, start a new probe directory:

```sh
python scripts/probe_campaign_workers.py leader \
  --directory /shared/icstudio/worker-probe-001 --timeout 120
```

While A holds its lock, run on host B:

```sh
python scripts/probe_campaign_workers.py follower \
  --directory /shared/icstudio/worker-probe-001 --timeout 120
```

Both commands must succeed. Inspect `report.json`: distinct hostnames, peer write
exclusion and commit visibility in both directions must be true. Record actual
physical placement separately; distinct hostnames alone do not prove separate
physical machines. Do not add `--allow-same-host-smoke` to acceptance commands.
That flag only validates the script locally and reports `same_host_smoke_only`.

## Two-host campaign and crash acceptance

1. Capture a new statistical campaign on the qualified shared mount. Preserve the
   plan and inputs, including the chosen PDK model evidence when applicable.
2. Start `python main.py --cli campaign run /shared/icstudio/CAMPAIGN --workers 2
   --trust-project` on both hosts. The trust flag authorizes execution of the
   captured project inputs; it is not filesystem qualification.
3. Record `status` and the `worker` column in `campaign.sqlite3`. Both actual
   hostnames must appear in claimed case rows, with no duplicate active claim
   token for a case. Retain coordinator logs from each host.
4. Abruptly terminate the coordinator on A while it owns running cases. Record
   their case indices, claim tokens and input SHA-256 values. Keep B running.
   After the leases expire, B must reclaim and finish these exact inputs. An
   attempt count above one and retained attempt directories provide evidence.
5. Restart A. Let both hosts drain the campaign. `status` must show all cases
   complete. `python main.py --cli campaign statistics /shared/icstudio/CAMPAIGN`
   must report zero unresolved trials before showing a yield interval.
6. Confirm input hashes and seeds match the pre-crash record. Inspect saved
   result hashes, waveform identities and expected numerical outputs. Exercise
   `Campaign.finish(index, old_token, 'Complete')` with a recorded retired token;
   it must return false without changing the completed row.
7. Archive the filesystem probe, host/runtime identities, clock evidence, plan,
   campaign directory, both host logs and numerical/yield comparison. A failed
   lock probe, changed runtime, unresolved trial or stale publication blocks
   qualification. Do not label a one-host benchmark as two-host acceptance.

`run` exits 2 for unresolved/incomplete cases or failed saved specifications.
An electrically failed trial can be a valid statistical observation. Review
`statistics` and the actual requirements rather than changing limits to make a
coordinator exit zero. `retry-failed` reuses the original captured realization.
