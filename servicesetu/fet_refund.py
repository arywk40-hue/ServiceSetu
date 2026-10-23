"""Operator reconciliation for a separately sent Dorado FET refund transfer."""
import argparse
import os

from dotenv import load_dotenv

from .core import Rejected,Store
from .payments import Payments


def main():
    load_dotenv()
    parser=argparse.ArgumentParser(description='Verify a separately sent Dorado testnet refund transfer')
    parser.add_argument('booking',help='Booking ID shown in the local operator record')
    parser.add_argument('transaction',help='Dorado refund transaction hash')
    args=parser.parse_args()
    store=Store(os.getenv('SERVICESETU_DB','data/servicesetu.db'))
    with store.connect() as db:
        row=db.execute('SELECT owner FROM bookings WHERE id=?',(args.booking,)).fetchone()
    if not row:raise SystemExit('Booking not found')
    owner=row['owner']
    try:
        with store.connect() as db:
            payment=db.execute('SELECT invoice FROM payments WHERE booking=?',(args.booking,)).fetchone()
        if not payment or not payment['invoice']:raise Rejected('Dorado invoice not found')
        import json
        invoice=json.loads(payment['invoice'])
        result=Payments(store,'fet_testnet',fet_recipient=invoice['recipient']).record_fet_refund(owner,args.booking,args.transaction)
        print('Verified Dorado refund transfer; booking payment status:',result['payment_state'])
    except (Rejected,ValueError) as exc:
        raise SystemExit(str(exc)) from None


if __name__=='__main__':main()
