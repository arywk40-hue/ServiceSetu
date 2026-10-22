# Generated evidence

Routine commands write new reports and identity manifests into `artifacts/local/`,
which Git ignores. The committed files directly under `artifacts/` are published
snapshots, not live status. Test results and registration checks must be dated
and interpreted according to what each check actually verifies.

Registration preparation and remote diagnostics read local manifests first and
fall back to published manifests if no local copy exists. Verification evidence
is retained only for matching agent addresses. The private seed, credentials,
database and registered identities are not changed by this output policy.

Regular registration preparation and verification do not rewrite the README.
To intentionally refresh published evidence, set `SERVICESETU_ARTIFACT_DIR` to
`artifacts` for the relevant command, inspect the resulting diff, and unset the
variable afterwards. In that explicit publication mode, registration preparation
and verification can also refresh the README's generated address table. This
does not itself register agents; `--apply` remains a separate operation.

Example in PowerShell, for a deliberate local proof publication:

```powershell
$env:SERVICESETU_ARTIFACT_DIR = 'artifacts'
try {
    .\.venv\Scripts\python.exe -m servicesetu prove --core-only
} finally {
    Remove-Item Env:SERVICESETU_ARTIFACT_DIR
}
```

The normal `prove`, `demo`, `prepare`, mesh startup and verification commands
need no additional options. CI uploads the newly generated local reports as job
artifacts, without replacing published repository evidence. Review all reports
for private information before choosing to publish them.
