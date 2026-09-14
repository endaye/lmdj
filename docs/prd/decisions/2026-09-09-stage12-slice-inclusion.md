# Stage 12 K4: include Slice as a reference implementation

Status: confirmed, 2026-09-09. Relates to #1036, #467, #472.

After the K3 benchmark and the registration/Host distinction were explained,
the user approved including Slice as a reference implementation ("行，按你说的来").

Register local.sample.slice in Product Assembly with its existing test platform.
Do not auto-select it, expand default permissions, or claim a usable Host slicing
journey. K5 owns the real audio owner, explicit execution authorization and result
handling. Registering an implementation is distinct from selecting it for users.

K3's unchanged smoke corpus measured precision 1, recall 0.8 and F1 8/9; one
overlapping-tail onset was missed. This is accepted reference evidence, not a
production-quality threshold. Algorithm semantics and R1/C-Q1–C-Q5 remain intact.

K4a allocates coherent current identities and registration. K4b freezes the clean
source in the same integration PR. No release, deployment or promotion follows
from this decision.
