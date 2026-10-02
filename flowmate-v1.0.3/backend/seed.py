"""DEMO ONLY - never run on a real server (public passwords). Creates demo data: 4 locations (2 gyms + 2 cafes), users for each role, suppliers, products, an order and an invoice.
Run:  python seed.py      (login: owner@demo.com / demo12345)"""
from datetime import date, timedelta
from app.db import engine, Base, SessionLocal
from app import models
from app.security import hash_password

def seed(db):
    import os
    if os.getenv("ENV") == "production" and os.getenv("DEMO_MODE") != "1": raise SystemExit("seed.py is demo-only. Use create_owner.py in production.")
    if db.query(models.User).first(): return print("Already seeded")
    from app.tenancy import use_business
    b = models.Business(id=1, name="Demo business", slug="demo", kind="general", inbound_token="demo-inbound-token-123456"); db.add(b); db.flush(); use_business(db, b.id)
    locs = [models.Location(name=n, kind=k) for n, k in [("Gym A", "gym"), ("Gym A Cafe", "cafe"), ("Gym B", "gym"), ("Gym B Cafe", "cafe")]]
    db.add_all(locs); db.flush()
    pw = hash_password("demo12345")
    for name, email, role, loc in [("Owner", "owner@demo.com", "owner", None), ("Manager", "manager@demo.com", "manager", None),
                                   ("Cashier A", "cashier@demo.com", "employee", locs[1].id), ("Accountant", "accountant@demo.com", "accountant", None),
                                   ("Payer", "payer@demo.com", "bank_payment", None), ("Driver", "driver@demo.com", "driver", None)]:
        db.add(models.User(name=name, email=email, password_hash=pw, role=role, location_id=loc))
    sup = models.Supplier(name="ABC Foods Ltd", vat_number="CY10000000X", iban="CY17002001280000001200527600", email="orders@abcfoods.example")
    sup2 = models.Supplier(name="Fresh Dairy Co", iban="CY99002001280000001200000000"); db.add_all([sup, sup2]); db.flush()
    cat = models.Category(name="Cafe"); db.add(cat); db.flush()
    milk = models.Product(sku="MILK1", name="Milk 1L", category_id=cat.id, supplier_id=sup2.id, purchase_cents=130, sell_cents=0, min_stock=15, max_stock=60)
    coffee = models.Product(sku="COF1", name="Coffee", category_id=cat.id, supplier_id=sup.id, purchase_cents=60, sell_cents=250, min_stock=20, max_stock=100)
    water = models.Product(sku="WAT1", name="Water 500ml", category_id=cat.id, supplier_id=sup.id, purchase_cents=20, sell_cents=100, min_stock=24, max_stock=200)
    db.add_all([milk, coffee, water]); db.flush()
    for p in (milk, coffee, water):
        db.add(models.Stock(product_id=p.id, location_id=locs[1].id, quantity=40))
    db.add(models.BankAccount(name="Business account", iban="CY00DEMO", provider="sandbox", balance_cents=1245000))
    db.add(models.Customer(name="Maria Georgiou"))
    db.add(models.Invoice(supplier_id=sup.id, number="INV-5521", issue_date=date.today() - timedelta(days=10), due_date=date.today() + timedelta(days=5), total_cents=45000, vat_cents=7350))
    plans = [models.Plan(name="Monthly membership", kind="membership", duration_days=30, price_cents=4500), models.Plan(name="3-month membership", kind="membership", duration_days=90, price_cents=11900),
             models.Plan(name="10-class pack", kind="class_pack", duration_days=90, sessions=10, price_cents=6000), models.Plan(name="Personal training x5", kind="personal_training", duration_days=90, sessions=5, price_cents=20000)]
    db.add_all(plans); db.flush()
    from datetime import timedelta as td
    m1 = models.Member(name="Andreas Constantinou", phone="99111222", location_id=locs[0].id); m2 = models.Member(name="Elena Petrou", phone="99333444", location_id=locs[0].id)
    db.add_all([m1, m2]); db.flush()
    s1 = models.Subscription(member_id=m1.id, plan_id=plans[0].id, location_id=locs[0].id, start_on=date.today() - td(days=25), end_on=date.today() + td(days=4), price_cents=4500)
    s2 = models.Subscription(member_id=m2.id, plan_id=plans[1].id, location_id=locs[0].id, start_on=date.today() - td(days=10), end_on=date.today() + td(days=79), price_cents=11900)
    db.add_all([s1, s2]); db.flush()
    db.add(models.SubPayment(subscription_id=s1.id, amount_cents=4500, method="CASH", location_id=locs[0].id)); db.add(models.SubPayment(subscription_id=s2.id, amount_cents=5000, method="CARD", location_id=locs[0].id))
    db.commit()

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as db: seed(db)
    print("Seeded. Login owner@demo.com / demo12345")
