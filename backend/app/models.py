"""Database schema. Money is stored as integer cents to avoid rounding errors."""
from datetime import datetime, date
from sqlalchemy import String, Integer, ForeignKey, Text, DateTime, Date, Boolean, JSON, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now(): return datetime.utcnow()

class EncStr(TypeDecorator):
    """String encrypted at rest (Fernet). Old plain values still read fine and get encrypted the next time they are saved."""
    impl = String(400); cache_ok = True
    def process_bind_param(self, v, dialect):
        from .crypto import encrypt; return encrypt(v)
    def process_result_value(self, v, dialect):
        from .crypto import decrypt; return decrypt(v)

class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="cafe")  # gym | cafe | shop

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20), default="employee")  # owner|manager|employee|accountant|bank_payment|admin
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    totp_secret: Mapped[str | None] = mapped_column(EncStr, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    iban: Mapped[str | None] = mapped_column(EncStr, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    purchase_cents: Mapped[int] = mapped_column(Integer, default=0)
    sell_cents: Mapped[int] = mapped_column(Integer, default=0)
    vat_percent: Mapped[int] = mapped_column(Integer, default=19)
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    max_stock: Mapped[int] = mapped_column(Integer, default=0)
    show_online: Mapped[bool] = mapped_column(Boolean, default=False)

class Stock(Base):
    """Current quantity of a product at a location."""
    __tablename__ = "stock"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)

class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    change: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(50))  # purchase|sale|adjustment|transfer
    ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="NEW")  # NEW PROCESSING COMPLETED PAID CANCELLED
    payment_method: Mapped[str] = mapped_column(String(20), default="BANK_TRANSFER")  # CASH CARD BANK_TRANSFER ONLINE OTHER
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    external_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    items: Mapped[list["OrderItem"]] = relationship(cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cents: Mapped[int] = mapped_column(Integer, default=0)

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(30), default="receipt")  # receipt|invoice|statement|contract|other
    filename: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(String(300))  # path/key in object storage
    status: Mapped[str] = mapped_column(String(20), default="NEEDS_REVIEW")  # NEEDS_REVIEW|VERIFIED
    extracted: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    related_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)  # upload | scan | email
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Invoice(Base):
    """Supplier invoice (payable)."""
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    number: Mapped[str] = mapped_column(String(100))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    vat_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="UNPAID")  # UNPAID|PAYMENT_PENDING|PAID
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    purchase_order_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paid_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    paid_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    items: Mapped[list["InvoiceItem"]] = relationship(cascade="all, delete-orphan")

class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_cents: Mapped[int] = mapped_column(Integer, default=0)

class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(300), default="")
    amount_cents: Mapped[int] = mapped_column(Integer)
    vat_cents: Mapped[int] = mapped_column(Integer, default=0)
    spent_on: Mapped[date] = mapped_column(Date)
    payment_method: Mapped[str] = mapped_column(String(20), default="CASH")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)

class Shift(Base):
    """Cashier shift + end-of-day cash-up."""
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    cashier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opening_float_cents: Mapped[int] = mapped_column(Integer, default=0)
    cash_sales_cents: Mapped[int] = mapped_column(Integer, default=0)   # from till / Z report
    card_sales_cents: Mapped[int] = mapped_column(Integer, default=0)
    cash_expenses_cents: Mapped[int] = mapped_column(Integer, default=0)
    counted_cash_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difference_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN|CLOSED
    z_report_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")  # DRAFT SENT CONFIRMED RECEIVED INVOICED PAID
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    items: Mapped[list["PurchaseOrderItem"]] = relationship(cascade="all, delete-orphan")

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cents: Mapped[int] = mapped_column(Integer, default=0)

class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    iban: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider: Mapped[str] = mapped_column(String(30), default="csv")  # csv | openbanking providers added later
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    available_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    connection_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_uid: Mapped[str | None] = mapped_column(String(120), nullable=True)
    balance_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    external_id: Mapped[str] = mapped_column(String(100))  # provider id or hash -> prevents duplicates
    booked_on: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(Integer)  # + incoming, - outgoing
    reference: Mapped[str] = mapped_column(String(300), default="")
    counterparty: Mapped[str] = mapped_column(String(200), default="")
    match_status: Mapped[str] = mapped_column(String(20), default="UNMATCHED")  # UNMATCHED|SUGGESTED|RECONCILED
    category: Mapped[str | None] = mapped_column(String(20), nullable=True)  # EXPENSE|BANK_FEE|TRANSFER|OTHER_INCOME|REFUND when classified by hand
    expense_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class PaymentMatch(Base):
    __tablename__ = "payment_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("bank_transactions.id"))
    target_type: Mapped[str] = mapped_column(String(20))  # order | invoice | expense
    target_id: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[int] = mapped_column(Integer)  # 0-100
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(300), default="")

class PaymentRequest(Base):
    """Outgoing payment (e.g. pay a supplier invoice). Never COMPLETED without provider confirmation."""
    __tablename__ = "payment_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("bank_accounts.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    authorization_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_name: Mapped[str] = mapped_column(String(100), default="system")
    action: Mapped[str] = mapped_column(String(100))
    object_type: Mapped[str] = mapped_column(String(50))
    object_id: Mapped[str] = mapped_column(String(50), default="")
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(String(300))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Delivery(Base):
    __tablename__ = "deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    address: Mapped[str] = mapped_column(String(300), default="")
    scheduled_for: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PREPARED")  # PREPARED|ON_THE_WAY|DELIVERED|FAILED|CANCELLED
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    proof_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    eta: Mapped[str | None] = mapped_column(String(5), nullable=True)   # expected arrival HH:MM
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

# ---------------- Gym memberships ----------------
class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="membership")  # membership | class_pack | personal_training | day_pass
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)  # for packs; None = unlimited
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Member(Base):
    __tablename__ = "members"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    joined_on: Mapped[date] = mapped_column(Date, default=date.today)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    start_on: Mapped[date] = mapped_column(Date)
    end_on: Mapped[date] = mapped_column(Date)
    price_cents: Mapped[int] = mapped_column(Integer)
    sessions_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")  # ACTIVE | CANCELLED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class SubPayment(Base):
    __tablename__ = "sub_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(20), default="CASH")  # CASH CARD BANK_TRANSFER ONLINE OTHER
    paid_on: Mapped[date] = mapped_column(Date, default=date.today)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)

class CheckIn(Base):
    __tablename__ = "checkins"
    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=now)

class OnlinePayment(Base):
    """Card payment taken through Stripe Checkout. Marked PAID only by a signature-verified Stripe webhook."""
    __tablename__ = "online_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(120), unique=True)
    target_type: Mapped[str] = mapped_column(String(20))  # order | subscription
    target_id: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING PAID EXPIRED AMOUNT_MISMATCH
    url: Mapped[str | None] = mapped_column(String(600), nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payment_intent: Mapped[str | None] = mapped_column(String(120), nullable=True)

class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(300), default="")
    method: Mapped[str] = mapped_column(String(20), default="CASH")  # how the money went back; ONLINE = via Stripe
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class BankConnection(Base):
    """One consent given by the business to read a bank's data through an Open Banking provider."""
    __tablename__ = "bank_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))            # enablebanking | demo
    institution: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), default="CY")
    psu_type: Mapped[str] = mapped_column(String(10), default="business")
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)   # one-time value that ties the bank's redirect back to this row
    authorization_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING ACTIVE EXPIRED ERROR DISCONNECTED
    consent_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    warned_expiry: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
