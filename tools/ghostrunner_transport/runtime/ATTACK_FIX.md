# Katana attack correction

The owner reported the remote katana swing is broken. The previous receiver used
`ESP_12_pst_Attack1`, a pistol firing sequence, for a sword attack. The earlier test
only asserted that the receiver entered an attack animation; it did not establish
that the body and blade performed a slash. That substitution is not a valid fix.

This commit adds the real source montage's active animation segment, phase and
duration to `motion.clip`, `motion.phase`, and `motion.duration`. Segments are read
from the actual hands' active montage, including segment start/rate/loop count;
only loaded first-person view-model animation sequence paths are exported. Existing
fields remain unchanged.

`sword_pose.lua` transfers the real loaded player sword sequences onto an
Enemy_Pistol_01 poseable body, retaining target limb lengths and the base lower-body
pose. It calibrates clavicle/arm/hand rotations using both meshes' reference poses.
The katana grip follows the animated `Weapon_rSocket` relative to the hand, including
the original socket-relative katana transform. The receiver whitelists eight known
loaded sword sequences; remote paths cannot load arbitrary assets. Hidden samplers
and the poseable component are removed on cleanup. Source components/assets are unchanged.

`verify_sword.py` passed against two actual Steam clients: two real melee actions
from each source, 5/6/6/6 observed poses. It checks the actual source clip, advancing
phase, evaluated hand travel over 20 cm, blade sweep over 45 degrees, real blade
length, visible unit-scale parts and their evaluated grip. Pistol/static-blade
negative controls were rejected. Freezing the actual receiver pose through a local
QA mutation failed the clock and slash-arc checks; restoring it passed again.
Both avatars then returned to idle and converged.

Rendered prototype frames show the arm and katana swing. Rendered inspection after
production integration and broader pair/movement reruns are still pending.

Useful reflection detail for DEEPSEEK FRIEND: `Actor:GetTransform()` returns a
transform table here; `K2_GetActorTransform()` does not. Creating a poseable component
with `AddComponentByClass` works, but explicit unit relative scale and enabled tick
are required. Passing transform tables back through the native transform setters
produced zero-scale results in the probe; separate vector/rotator setters avoided
that. This observation is Steam-build-specific, not a GOG compatibility claim.

Reproduce with `verify_sword.py` and the same directory/PID/output arguments as
`verify_motion.py`.
