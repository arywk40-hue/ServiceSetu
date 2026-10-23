# Hosting without leaving a laptop on

The current ServiceSetu backend is a long-running Python process containing 13 mailbox agents in one `Bureau`, with a shared SQLite database. Agentverse registration and its mailbox do not host this process. Closing the terminal or sleeping/shutting down the laptop stops replies. A recorded video and shared history remain evidence of the completed demonstration, but they do not replace a running agent for fresh interaction.

No cloud deployment has been created or verified. The owner requested free hosting only; no paid service or trial resource has been provisioned.

## Options checked on 24 October 2026

| Option | Fit for this existing backend |
| --- | --- |
| Oracle Cloud Always Free VM | A candidate for running the backend unchanged with persistent storage. An account, an available eligible VM in the home region, and a verified installation are still required. Signup usually requires phone/card verification. Stay within resources explicitly marked Always Free and do not upgrade to a paid account. Capacity is not guaranteed, and idle instances may be reclaimed. |
| An existing college or personal Linux server | Suitable if its owner grants permission and it provides persistent storage and outbound HTTPS. No such server access has been supplied. |
| Render free web service | Unsuitable for reliable unattended mailbox operation: sleeps after 15 minutes without inbound traffic and cannot attach a persistent disk. SQLite changes can be lost. Outbound mailbox polling does not provide the inbound traffic required to keep it awake. Paid workers/disks are outside the free-only scope. |
| Fetch Agentverse hosted editor | Not a drop-in migration. It disallows `Bureau`, permits one agent per project, and ignores custom seed/address configuration for hosted agents. Recreating the current identities there is not established. Keep the existing external mailbox architecture. |
| Koyeb free instance | Sleeps after one hour, cannot run a worker service and cannot attach persistent volumes. It does not meet the current persistence/uptime need. |

Sources: [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm), [Oracle account requirements](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm), [Render free limitations](https://render.com/docs/free), [Render workers](https://render.com/docs/background-workers), [Agentverse hosted restrictions](https://docs.agentverse.ai/documentation/advanced-usages/allowed-imports), [Koyeb instance restrictions](https://www.koyeb.com/docs/reference/instances).

## Migration checklist once a free VM is available

1. Obtain the VM owner's permission and SSH access. Confirm eligible free compute/storage and outbound HTTPS before creating anything. A VM has not been tested in this task.
2. Clone the public repository. Install Python 3.10–3.13 and create its virtual environment, then install the backend:

   ```sh
   python3 -m venv .venv
   .venv/bin/python -m pip install -e '.[fetch,communications,external]'
   ```

3. Transfer the existing private configuration and a consistent SQLite backup through SSH to the approved private VM, outside Git. Keep file permissions private. If the seed is stored in `data/agent-seed` instead of `SERVICESETU_SEED`, preserve that exact seed file too. Do not regenerate identities or paste secret values into a chat. These sensitive transfers still need the owner's specific authorization for the chosen destination.
4. Before switching over, stop the local mesh with Ctrl+C and wait for shutdown. Use SQLite's backup API for a consistent database copy rather than copying a live `.db` file without its WAL. Preserve the original local database. Run only one mesh for these identities.
5. Configure `SERVICESETU_DB` to the migrated persistent database, `SERVICESETU_MAILBOX=true`, `PAYMENT_MODE=mock`, and an empty `GOOGLE_PLACES_API_KEY`. Preserve `SERVICESETU_SEED`, `AGENTVERSE_API_KEY`, `DEMO_CONTROL_TOKEN` and any existing optional keys privately. No seed/demo/import command is part of this migration.
6. From the repository directory, start `.venv/bin/python -m servicesetu mesh` using the private environment. Compare all derived addresses to `artifacts/registration-manifest.json` before accepting the migration. Do not run registration with a new seed.
7. Install a process supervisor such as systemd to restart this single process after reboot. Restrict the agent port and provider inbox to local/operator access; mailbox mode needs outbound HTTPS, not a public customer frontend. Use an SSH tunnel or an authenticated SSH command for the existing cancellation control.
8. Verify all 13 receivers and public registrations, then a fresh ASI:One mock booking, explicit approval, cancellation, replacement approval and history. Test restart persistence. A running VM alone does not resolve the previously observed Agentverse timeouts/401.
9. Shut down the laptop only after the remote flow and persistence checks pass. Until then the backend remains local and fresh availability is a submission blocker. The owner can record the prior completed conversation without claiming new live execution.
