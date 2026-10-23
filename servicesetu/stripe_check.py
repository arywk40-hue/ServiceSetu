"""Read-only Stripe test authentication check; never prints keys or balance data."""
from .core import Rejected
from .payments import Payments


def check(adapter=None):
    stripe=(adapter or Payments(None,'stripe_test')).stripe()
    balance=stripe.Balance.retrieve()
    if balance.livemode:raise Rejected('Live Stripe access refused')


def main():
    from dotenv import load_dotenv
    load_dotenv()
    try:check()
    except Rejected as exc:
        print(str(exc));raise SystemExit(1) from None
    except Exception:
        print('Stripe test authentication failed. Check the private test keys and account access locally. No checkout was attempted.')
        raise SystemExit(1) from None
    print('Stripe TEST authentication passed. No payment was created. Complete ASI:One checkout separately to verify the UI and transaction.')


if __name__=='__main__':main()
