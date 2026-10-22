"""W41: run probes/w41_props.lua once per class; stop and report the class if the game dies."""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\coop mods\tools\grdebug")
import repl  # noqa: E402

PAIR = sys.argv[1] if len(sys.argv) > 1 else "A"
CLASSES = sys.argv[2:] or [
    "BP_Door_Sliding_01_C", "BP_Holo_Doors_01_C", "BP_Level_Elevator_C", "Checkpoint_C",
    "BP_electric_arches_01_C", "AccessPoint_C", "AccessPointNew2_C", "BP_TriggerSwitchEnemiesLogicOn_C",
    "BP_Group_Killed_C", "BP_ShieldBeaconEnergyShieldBeacon_C", "BP_ShieldBeaconEnergyShieldEnemy_C",
    "Grapling_Point_C", "BP_CollectibleStoryItemTrigger_C", "BP_ObjectiveTrigger_C",
    "Teleport_to_taget_point_with_offset_C", "BP_Electric_Panel_C",
]
probe = Path(r"C:\coop mods\work\grdebug\probes\w41_props.lua").read_text(encoding="utf-8")
pid = Path(rf"C:\coop mods\work\grdebug\pid-{PAIR}.txt").read_text().strip()


def alive() -> bool:
    # tasklist prints in the OEM code page; compare bytes so decoding can never fail
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True).stdout
    return pid.encode() in out


for c in CLASSES:
    text = repl.run(PAIR, f'local CNAME = "{c}"\n' + probe, 30)
    sys.stdout.write(text.replace("--ok=true nil\n", ""))
    sys.stdout.flush()
    time.sleep(1)
    if not alive():
        print(f"GAME DIED on {c}")
        sys.exit(1)
