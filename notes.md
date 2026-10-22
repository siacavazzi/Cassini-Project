# Cassini's reaction control thrusters: where they are and which way they fire

Sources fetched from the Mac Mini on 2026-10-22. The full PDFs are not in this branch, only the crops.
- **JPL Basics of Space Flight, tca.html.** The live host would not connect, so I used the Wayback copy from 2014-01-08 (`jpl_basics_tca_archived.html`).
  Its one image is `casprop.gif`, saved here as `jpl_basics_casprop.png`.
- **Curt Henry, An Introduction to the Design of the Cassini Spacecraft** (Wikimedia PDF, 24 pp). Crops: `henry_p8_fig7_propulsion_module.png`,
  `henry_p18_fig14_pms_schematic.png`, `henry_p20_rcs_text.png`.
- **Julie Webster, Cassini Spacecraft Engineering Tutorial** (CHARM, 2006-03-28, 28 slides). Crops: `webster_p8_propulsion_module_photo.png`,
  `webster_p9_propulsion_text.png`.
- **Cassini launch press kit** (jpl.nasa.gov, 71 pp). Its spacecraft section (p. 53) only describes the system in text, with no figure of the thrusters.

## What the sources say (quotes)
- Henry p. 8: the propulsion module's shell has, attached to its outside, "a helium tank, spherical monopropellant tank, four thruster booms, two main engines…"
- Henry p. 8, axes: "+X axis is radially outward in the direction of the stellar reference units' boresights… The +Y axis is in the direction of the magnetometer boom. The +Z axis is down toward the main rocket engines."
- Henry p. 20: "block redundant branches of eight thrusters pointed in the spacecraft +Z and +Y directions mounted in four clusters." Thrust is 1 N (0.2 lbf) per thruster.
- Henry p. 18, Fig. 14: "0.9 N EACH, 4 CLUSTERS", fed by two branches (A and B) from one hydrazine tank.
- Henry p. 21: radioisotope heater units are used "in other places such as the thruster clusters".
- Webster p. 8, photo caption: "Small Thruster Cluster (1 of 4) with nozzles facing down and out".
- Webster p. 9: "16 Redundant ~1 Newton thrusters, 4 per 'cluster'".
- JPL Basics: "The four hydrazine Thruster Clusters (4 thrusters on each) can be seen at the lower part of the illustration… which shows the entire Cassini Propulsion Module Subsystem."
- Press kit p. 53: "four clusters of four hydrazine thrusters each."

## What the figures show (my reading of Henry Fig. 7, the JPL illustration and the Webster photo)
- **Mount.** Each cluster sits at the outer end of a thruster boom: a truss of thin struts running from the lower part of the propulsion module's cylindrical shell, outward and slightly down.
  The clusters are not on the upper electronics bus near the high-gain antenna. They are at the aft (+Z) end, on the propulsion module.
- **Height.** The clusters sit low on the propulsion module, around the level of the main engines' gimbal mounts, a little above the engine bells.
  They are above the very bottom of the spacecraft (the lower equipment module, RTGs and engine cover).
- **Radius.** The booms reach out roughly as far as the outer edge of the helium and hydrazine tanks, so the clusters sit clearly outside the propulsion module shell.
  No source gives a number.
- **Azimuth.** The four clusters are spread evenly around the module, two on each side in every view, so they sit at the corners of a square around the Z axis.
  The figures don't let me pin their angle to the RTGs or to ±X/±Y.
- **Firing directions.** The text says +Z and +Y. The photo says "down and out".
  My reading of these two together is that each cluster has 2 nozzles firing along +Z (aft, the same way as the main engines; one from branch A, one from B)
  and 2 firing sideways along ±Y (outward, roughly; one from each branch). The lateral ones point +Y on the +Y-side clusters and -Y on the -Y side.
  That split is an inference, not a quote.
- **Size.** Each cluster is a small block of four nozzles, a few tens of cm across, much smaller than the main engine bells.
  The exhaust from 1 N hydrazine thrusters is faint and nearly invisible in vacuum.

## Not found here
No radius, height or azimuth numbers. The repo's model (`web/replay/data/models/cassini.glb.b64.txt`) is split by material
(aluminum, black_krinkle, dish, foil_gold, …), not by part, so the clusters have no node of their own. You would have to find them by geometry: four small
blocks at the ends of struts near the aft end, around z ≈ +Z max minus the engine height in model space.
