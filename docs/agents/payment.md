# ServiceSetu payment

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Internal ServiceSetu payment specialist. Not a customer chat entry point. Accepts typed Work messages only from the Concierge. Providers, credentials and registry are seeded test data. Payments are simulated or testnet/test-gateway only; FET is restricted to Dorado, and mainnet payments are refused. Discretionary refunds, payouts and verification overrides require human review.

`PAYMENT_MODE=fet_testnet` sends the Agent Payment Protocol `fet_direct` request on Dorado (`dorado-1`) using `atestfet` (18 decimals). The reviewed fixed token amount is bound to customer approval and is not an INR conversion. The invoice uses the Concierge's native `fetch1…` ledger wallet, never its `agent1…` messaging address. Successful transfers are checked on Dorado against the stored booking, quote, customer/session, sender, recipient, exact amount and transaction ID. Expired bookings cannot confirm; a refund remains pending until a separate on-chain transfer is verified. See the FET testnet setup and limits in the main README.
