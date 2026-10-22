# Booking-linked customer and provider communication

## Scope

Confirmed bookings have a private customer/provider thread. Customers use their original ASI:One conversation; the booking owner is derived from the signed sender and chat session. Providers use a loopback-only browser inbox protected by a provider-scoped bearer token. The token is provisioned by the trusted local operator; this is not production provider identity verification.

Messaging is optional and never blocks booking. Reply notices and message confirmations offer View conversation; the thread offers Reply to provider, More messages and Refresh conversation. Booking/message identifiers stay in action metadata instead of customer-facing text. Customer commands remain available as an alternative:

```text
message provider: Please use the side gate.
show messages
show more messages
show messages b_<booking-reference>
```

The confirmation card also offers Message provider, View messages, Booking history, and Add address when it has been skipped. Phone/email details are not required. Providers see a pending-address notice if the customer has not supplied one yet. A message form is bound to the current booking. Messages are data and never modify price, appointment, scope, cancellation or payment state. Those operations keep their existing approval requirements.

Provider replies enter the same persisted booking thread. The concierge queues a generic reply notice to the original customer session. Notices contain a booking reference, not the message text or address. Delivery is best effort with bounded retries; a saved message is not proof of delivery or reading. `show messages` retrieves stored replies even if a notice fails. External ASI:One/Agentverse connectivity is still required for the customer chat.

## Access boundaries

- The customer can access only bookings owned by their sender/session, including their own historical thread after cancellation.
- Providers can list, read or message only currently confirmed bookings assigned to their provider identity. Held, cancelled, completed, foreign and nonexistent bookings do not expose customer details.
- A cancellation removes the previous provider's address/thread access on subsequent API requests. New replacement bookings have a separate thread; the old provider's conversation is not copied to the replacement provider.
- The provider view includes the service, appointment, service area and recorded visit address. It excludes the customer's agent/session identity, payment credentials and unrelated history. Phone numbers and email addresses are not automatically collected or shared.
- Reply notices retain the customer's original session. No provider credential is treated as a customer credential.

A provider who already viewed information cannot be made to forget it; revocation prevents further application access. Keep demo data fictional.

## Local provider inbox

Use the same database as the mesh. In another PowerShell terminal:

```powershell
cd C:\Users\PALAKM\Documents\Codex\ServiceSetu
$env:SERVICESETU_DB = 'data/demo-nationwide.db'
.\.venv\Scripts\python.exe -m servicesetu provider-inbox --provider p1
```

The command prints a local URL and a private token. Open `http://127.0.0.1:8765/` and paste the token into the password field. `p1` is CoolCare AC; `p2` is Breeze AC. Choose the actual assigned provider. A different provider will see no booking rather than the customer's information.

The token lasts one hour. Starting another inbox for that provider revokes its earlier token; normal shutdown revokes the current token. Tokens are stored only as hashes. Browser credentials stay in memory, not local/session storage or URLs. Lock inbox clears the displayed details; five minutes without an API action locks it automatically. Expired/revoked credentials require fresh local provisioning. Keep tokens private and do not paste them into the customer chat, screenshots, issue reports or GitHub.

The server binds only to `127.0.0.1`. Host and Origin checks reject foreign origins and DNS-rebinding hosts. APIs require bearer authentication and JSON POST bodies. The interface uses text DOM APIs, a restrictive Content Security Policy, no third-party assets, no caching and no request logging. Message bodies are limited to 2,000 characters; sending is rate limited, and stable request identifiers prevent duplicate saves.

## Storage and limits

Message bodies use PyNaCl SecretBox authenticated encryption. The booking, sender and side are bound inside the encrypted payload and rechecked on read. Audit events contain only message references and sender side, never the message body. Messaging does not invoke the ASI1 reasoning API. Customer chat messages still pass through ASI:One and the existing agent transport; this is not an end-to-end encrypted chat service.

A separate `.message-key` file beside the database is required to decrypt messages. Windows protects that key with current-user DPAPI. Other systems create an owner-only key file and reject permissive file permissions. Key files, databases, `.env` and local evidence are ignored by Git. Missing keys fail closed; do not delete or lose them. A Windows-protected key cannot simply be moved to another machine/user; a managed key-transfer design is required before such a migration.

Existing service-address records and other booking data remain in the existing local SQLite database without encryption. This change does not retroactively encrypt the booking store. Local-machine administrators and applications running as the same user remain trusted. Production use requires HTTPS hosting, verified provider accounts, managed encryption for all personal data, session/account recovery, retention/deletion and backup policies, and notification monitoring. Do not expose the development HTTP server to a network or treat the local demo as production security.

No real SMS, email, WhatsApp, masked calling or remote provider hosting is integrated. The local inbox is the provider interface for testing.

## Validation

Security tests cover customer/provider isolation, credential expiry/rotation, cancellation revocation, encrypted storage, ciphertext substitution, missing keys, message limits, idempotency, pagination, model bypass, booking-bound forms, session-correct notices, authenticated HTTP access, hostile origins/hosts and forged request fields. The local AC uAgent lifecycle additionally sends a customer message, saves an authenticated provider reply, receives a customer notice and reads the thread before cancellation/replacement. The browser check uses fictional data and verifies login, assigned booking/address display, replies and locking.
