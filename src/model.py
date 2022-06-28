from curses import meta
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
import itertools
from operator import neg
from pathlib import Path
from typing import Optional, Set
from sqlalchemy import DATE, DATETIME, DECIMAL, MetaData, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .settings import Settings

metadata = MetaData()

class DatabaseProxy:
    def get_session(self, tenant_id: Optional[str]):
        raise NotImplementedError
    
    def recreate_database(self, tenant_id: Optional[str]):
        raise NotImplementedError


class StaticDatabaseProxy(DatabaseProxy):
    def __init__(self, settings: Settings):
        self._url = SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
        engine = create_engine(
            SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
        )
        self._engine = engine
        self._session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def get_session(self, tenant_id: Optional[str] = None):
        if tenant_id is not None:
            # TODO: logger.warn
            pass
        return self._session_local()


class MultitenantDatabaseProxy(DatabaseProxy):
    def __init__(self, database_directory: Path) -> None:
        if not isinstance(database_directory, Path):
            raise ValueError(f"Multitenant database directory must be specified: {database_directory}")
        database_directory.mkdir(exist_ok=True)
        self._engine_cache = {}
        self._session_local_cache = {}
        self._database_directory = database_directory

    def get_session(self, tenant_id: Optional[str]):
        if tenant_id is None:
            raise ValueError("tenant_id must not be None for MultitenantDatabaseProxy")
        session_local = self._session_local_cache.get(tenant_id)
        if not session_local:
            engine = self._get_or_create_engine(tenant_id)
            metadata.create_all(bind=engine)
            session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            self._session_local_cache[tenant_id] = session_local
        return session_local()

    def _get_or_create_engine(self, tenant_id: str):
        url = self._url_for_tenant(tenant_id)
        engine = self._engine_cache.setdefault(
            tenant_id, 
            create_engine(url, connect_args={"check_same_thread": False})
        )
        return engine

    def _url_for_tenant(self, tenant_id: str):
        db_path = self._database_directory / tenant_id
        return f"sqlite:///{db_path}.db"

    def recreate_database(self, tenant_id: Optional[str]):
        print(f"Recreating database for tenant {tenant_id}")
        engine = self._get_or_create_engine(tenant_id=tenant_id)
        metadata.drop_all(bind=engine)
        metadata.create_all(bind=engine)


from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship


class BaseEntity:
    id = Column(Integer, primary_key=True, index=True)


Base = declarative_base(cls=BaseEntity, metadata=metadata)


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
    line_item = relationship("InvoiceLineItem", uselist=False)

    @property
    def _value(self):
        return self.estimate

    @property
    def invoiced(self):
        return self.line_item is not None

    @property
    def paid(self):
        if self.line_item is not None:
            return self.line_item.invoice.paid is not None


class InvoiceLineItem(BaseValueModel, Base):
    __tablename__ = "invoice_line_item"
    __table_args__ = ()

    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=False)
    deliverable_id = Column(Integer, ForeignKey("deliverable.id"), nullable=False, unique=True)
    amount = Column(DECIMAL, nullable=False)

    invoice = relationship("Invoice")
    deliverable = relationship("Deliverable", back_populates="line_item")

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

    sent = Column(DATE, nullable=True)
    paid = Column(DATE, nullable=True)
    
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