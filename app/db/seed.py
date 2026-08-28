from app.db.database import SessionLocal
from app.db.models import Payment


def seed_demo_payment():
    db = SessionLocal()

    try:
        existing_payment = (
            db.query(Payment)
            .filter(Payment.id == "pay_demo_001")
            .first()
        )

        if existing_payment:
            print("Demo payment already exists.")
            return

        payment = Payment(
            id="pay_demo_001",
            merchant_id="merchant_demo_001",
            amount_paise=1_000_000,
            currency="INR",
            status="CAPTURED"
        )

        db.add(payment)
        db.commit()

        print("Demo payment created successfully.")
        print("Payment ID: pay_demo_001")
        print("Amount: ₹10,000")
        print("Status: CAPTURED")

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_payment()