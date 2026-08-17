# Stage A2 workload qualification

Qualification is excluded from the formal ledger and every paper denominator.

The first four-arm probe established motion coverage but ended in
`FORMAL_SAFETY_STOP`: the provisional 2 m altitude-loss limit necessarily
crossed during the intended descent from a 3 m mission altitude. The limit was
corrected to 5 m; the failed probes remain retained under
`runs/stage-a2-moving-qualification/`.

The second four-arm probe was runtime-accepted. It exposed that
Legacy Offboard's active-duration clock began at mode activation during climb, so its
nominal arm did not reach the frozen 2.5 m post-takeoff coverage. No threshold
was relaxed. The motion clock was anchored to sustained physical takeoff; the
probe remains under `runs/stage-a2-moving-qualification-v2/`.

The final matched four-arm probe uses the exact formal image and paired seeds.
All four arms were runtime-accepted, passed sustained takeoff, entered motion
at 0.752--0.768 m, and completed the intended terminal cleanup. Both nominal
arms and both stall arms recorded at least 2.501 m progress; each fault was
recorded after motion entry. These inputs remain under
`runs/stage-a2-moving-qualification-v3/` and are not formal evidence.

Qualified image: `sha256:e9f913b23798f052295abc8a643d56e499d8d1b4b669ea869f7892683f516f3d`.
Qualified repository revision: `b10b475015e1d0a91b0f138946445b179de334e6`.
