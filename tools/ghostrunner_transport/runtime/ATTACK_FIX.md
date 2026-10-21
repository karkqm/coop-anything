# Katana attack correction in progress

The owner reported the remote katana swing is broken. The previous receiver used
`ESP_12_pst_Attack1`, a pistol firing sequence, for a sword attack. The earlier test
only asserted that the receiver entered an attack animation; it did not establish
that the body and blade performed a slash. That substitution is not a valid fix.

This commit adds the real source montage's active animation segment, phase and
duration to `motion.clip`, `motion.phase`, and `motion.duration`. Segments are read
from the actual hands' active montage, including segment start/rate/loop count;
only loaded first-person view-model animation sequence paths are exported. Existing
fields remain unchanged. The receiver still needs the retarget/grip correction.

An isolated Steam prototype has transferred the real `H10_1hk_att_sword_R1` arm
rotations onto an Enemy_Pistol_01 poseable body, retaining the original limb lengths
and lower-body pose. Rendered frames show the arm swing. Katana grip/orientation and
production lifecycle cleanup remain under investigation; this is not yet a verified
visual correction. No first-person player component or game asset is changed.

Useful reflection detail for DEEPSEEK FRIEND: `Actor:GetTransform()` returns a
transform table here; `K2_GetActorTransform()` does not. Creating a poseable component
with `AddComponentByClass` works, but explicit unit relative scale and enabled tick
are required. Passing transform tables back through the native transform setters
produced zero-scale results in the probe; separate vector/rotator setters avoided
that. This observation is Steam-build-specific, not a GOG compatibility claim.

Before declaring this fixed, test both sources' real melee actions, verify a real
slash path and grip on rendered frames, and exercise repeats, return to idle and
packet loss. The old pistol clip must be a failing negative control.
