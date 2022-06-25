from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
import itertools
from operator import neg
from turtle import pos
from unicodedata import decimal
from sqlalchemy import DATE, DATETIME, DECIMAL, DateTime, MetaData, UniqueConstraint, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relation

SQLALCHEMY_DATABASE_URL = "sqlite:///./deliverables.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship


class BaseEntity:
    id = Column(Integer, primary_key=True, index=True)


Base = declarative_base(cls=BaseEntity)


class BaseValueModel:
    _value: Decimal

    @property
    def value(self):
        return Decimal(self._value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Deliverable(Base, BaseValueModel):
    __tablename__ = "deliverable"

    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String, nullable=False)
    estimate = Column(DECIMAL, nullable=True)
    created = Column(DATETIME, nullable=False, default=datetime.utcnow)
    due_date = Column(DATE, nullable=True)

    project = relationship("Project")

    @property
    def _value(self):
        return self.estimate

class InvoiceLineItem(BaseValueModel, Base):
    __tablename__ = "invoice_line_item"
    __table_args__ = ()

    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=False)
    deliverable_id = Column(Integer, ForeignKey("deliverable.id"), nullable=False, unique=True)
    amount = Column(DECIMAL, nullable=False)

    invoice = relationship("Invoice")
    deliverable = relationship("Deliverable")

    @property
    def _value(self):
        return self.amount


class InvoiceReimbursement(BaseValueModel, Base):
    __tablename__ = "invoice_reimbursement"

    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=False)
    reason = Column(String, nullable=False)
    amount = Column(DECIMAL, nullable=False)

    invoice = relationship("Invoice")

    @property
    def _value(self):
        return self.amount


class InvoiceCredit(BaseValueModel, Base):
    __tablename__ = "invoice_credit"

    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=False)
    reason = Column(String, nullable=False)
    amount = Column(DECIMAL, nullable=False)

    invoice = relationship("Invoice")

    @property
    def _value(self):
        return neg(self.amount)


class Invoice(Base):
    __tablename__ = "invoice"

    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String, nullable=False)

    line_items = relationship("InvoiceLineItem", back_populates="invoice")
    credits = relationship("InvoiceCredit", back_populates="invoice")
    reimbursements = relationship("InvoiceReimbursement", back_populates="invoice")
    
    project = relationship("Project")

    @property
    def balance_due(self):
        values = (
            i.value for i in itertools.chain(self.line_items, self.credits, self.reimbursements)
        )
        return sum(values)

    @property
    def gross_pay(self):
        values = (
            i.value for i in itertools.chain(self.line_items, self.credits, self.reimbursements)
        )
        return sum((value for value in values if value > 0))
    
    @property
    def reimbursements_total(self):
        values = (
            i.value for i in itertools.chain(self.reimbursements)
        )
        return sum(values)
        
    @property
    def net_pay(self):
        return self.balance_due - self.reimbursements_total
        

class BillTo(Base):
    __tablename__ = "bill_to"

    company_name = Column(String, nullable=False)
    contact_name = Column(String, nullable=False)
    contact_email = Column(String, nullable=False)


class Project(Base):
    __tablename__ = "project"

    name = Column(String, unique=True, index=True)
    
    deliverables = relationship("Deliverable", back_populates="project", order_by="desc(Deliverable.created)")
    invoices = relationship("Invoice", back_populates="project", order_by="desc(Invoice.id)")
    bill_to_id = Column(Integer, ForeignKey("bill_to.id"), nullable=True)

    bill_to = relationship("BillTo")

    def get_deliverable(self, deliverable_id):
        return next((d for d in self.deliverables if str(d.id) == deliverable_id), None)