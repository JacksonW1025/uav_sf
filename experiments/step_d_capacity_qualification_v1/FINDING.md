# Registration capacity as a timed action — reached, but incompatible with the moving profile

## What was attempted

`exhaust_registration_capacity` was wired as a sixth selectable action and flown
in two batches: a six-action qualification and a narrowed probe designed to
select it more often.

Specs: [qualification.spec.json](qualification.spec.json),
[probe.spec.json](probe.spec.json).
Results: [qualification.result.json](qualification.result.json),
[probe.result.json](probe.result.json).
Environment: [environment-attestation.json](environment-attestation.json),
image `uav-sf-family-a-thor:step-d-523e20e`.

## Result

Both batches failed, and both failures were this action. Every other action
passed. The two attempts that selected it failed identically:

```text
outcome                 INCONCLUSIVE
physical execution      FAIL
  motion_phase_entered        true
  nominal_profile_coverage    false
  completion progress         0.0 m
strategy lifecycle      complete
action contract         valid
```

## The action works; the episode does not survive it

The capacity boundary is genuinely reached. In the probe attempt the requester
recorded eight registration replies while the tested route was executing, and
two of them were refused:

```text
 11.86s  dynamic mode active
 15.13s  motion entered at 0.751 m
 15.30s  registration reply  accepted
   ...   six more replies
 18.65s  registration reply  refused
 19.64s  registration reply  refused
 19.90s  completion
```

Registering the components spans from motion entry to the scheduled completion,
about 4.3 s. The vehicle travelled 0.751 m in that window instead of the 2.5 m
the moving profile requires, so the physical-validity contract correctly refused
the attempt. The simulation was not slow: the central real-time factor was
0.999.

## Why the Stage A1 cell did not hit this

That cell exhausted the slots while hovering, before the tested activation,
where no motion contract applies. Timing the same stimulus during the tested
route is a different experiment, and it is the one that conflicts.

## What was done

The action is unwired again and its note carries this evidence, exactly as the
producer reclaim was handled before its blocker was fixed. The physical-validity
contract was **not** relaxed to admit the attempts: `nominal_profile_coverage`
exists to catch flights that did not perform the intended task, and these did
not.

Making it selectable needs a pre-activation anchor — the hover phase, where the
Stage A1 variant lives — which in turn needs a live marker for an established
source route. That is a marker and anchor change, not a wiring change.

## Effect on the corpus

Five actions remain qualified and selectable: the owned stall, the producer
termination, route re-entry, the producer reclaim, and the adjacent Land
request. The corpus freeze is not signable while two of the seven proposed
actions are unwired.
