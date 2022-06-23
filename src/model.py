from datetime import datetime
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


class Deliverable(Base):
    __tablename__ = "deliverable"

    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String, nullable=False)
    estimate = Column(DECIMAL, nullable=True)
    created = Column(DATETIME, nullable=False, default=datetime.utcnow)
    due_date = Column(DATE, nullable=True)

    project = relationship("Project")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_item"
    __table_args__ = ()

    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=False)
    deliverable_id = Column(Integer, ForeignKey("deliverable.id"), nullable=False, unique=True)
    amount = Column(DECIMAL, nullable=False)

    invoice = relationship("Invoice")
    deliverable = relationship("Deliverable")


class InvoiceReimbursement(Base):
    __tablename__ = "invoice_reimbursement"

    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=False)
    reason = Column(String, nullable=False)
    amount = Column(DECIMAL, nullable=False)

    invoice = relationship("Invoice")


class InvoiceCredit(Base):
    __tablename__ = "invoice_credit"

    invoice_id = Column(Integer, ForeignKey("invoice.id"), nullable=False)
    reason = Column(String, nullable=False)
    amount = Column(DECIMAL, nullable=False)

    invoice = relationship("Invoice")


class Invoice(Base):
    __tablename__ = "invoice"

    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    name = Column(String, nullable=False)

    line_items = relationship("InvoiceLineItem", back_populates="invoice")
    credits = relationship("InvoiceCredit", back_populates="invoice")
    reimbursements = relationship("InvoiceReimbursement", back_populates="invoice")
    
    project = relationship("Project")


class Project(Base):
    __tablename__ = "project"

    name = Column(String, unique=True, index=True)
    
    deliverables = relationship("Deliverable", back_populates="project")
    invoices = relationship("Invoice", back_populates="project")

    def get_deliverable(self, deliverable_id):
        return next((d for d in self.deliverables if str(d.id) == deliverable_id), None)