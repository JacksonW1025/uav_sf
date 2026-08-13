# Thor supplemental study

This study is the separately preregistered follow-up to the two invalid primary
cells. It uses only new Thor evidence and leaves the primary ledger immutable.

Run or resume it with:

```bash
python3 -m scripts.runtime.run_campaign \
  --matrix experiments/motivation_thor_remediation_v1/matrix.json \
  --attestation experiments/motivation_thor_remediation_v1/environment-attestation.json \
  --study-root experiments/motivation_thor_remediation_v1 \
  --run-root runs \
  --image uav-sf-family-a-thor:remediation-221b989
```

Raw evidence is written under ignored
`runs/motivation-thor-remediation-v1/`. Compact evidence and the hash-chained
ledger are retained here only after each attempt is closed.
