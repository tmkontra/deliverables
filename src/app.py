from ast import Del
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from http import HTTPStatus
from lib2to3.pytree import Base
from operator import inv
from pathlib import Path
import re
from typing import Callable, List, Optional
import uuid
from tinydb import JSONStorage, TinyDB, Query
from fastapi import Depends, FastAPI, Form, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from tinydb_serialization import SerializationMiddleware, Serializer
from tinydb_serialization.serializers import DateTimeSerializer
from . import model
from sqlalchemy.orm import joinedload

ROOT_DIR = Path(__file__).parent

server = FastAPI()

server.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")

Render = Callable[[str, dict], Response]


def render_currency(input):
    """$1,352.02"""
    return f"${input:,.2f}"


class RenderTemplate:
    def __init__(self, **globals):
        self._templates = Jinja2Templates(directory=ROOT_DIR / "templates")
        self._set_globals(self._templates, globals)
        self._templates.env.globals["currency"] = render_currency

    @staticmethod
    def _set_globals(template_cls, globals: dict):
        for key, value in globals.items():
            template_cls.env.globals[key] = value

    def _render(self, request, name, context):
        context.update({"request": request})
        return self._templates.TemplateResponse(name, context)

    def __call__(self, request: Request) -> Render:
        return partial(self._render, request)


Templates = RenderTemplate()

EntityId = str


def entity_id() -> EntityId:
    return str(uuid.uuid4())


class Entity(BaseModel):
    id: EntityId = Field(default_factory=entity_id)


class Deliverable(Entity):
    project_id: EntityId
    name: str
    estimate: Decimal
    created: datetime
    due_date: Optional[date] = Field(default=None)


class InvoiceLineItem(Entity):
    deliverable_id: EntityId
    amount: Decimal


class InvoiceCredit(Entity):
    reason: str
    amount: Decimal
    

class InvoiceReimbursement(Entity):
    reason: str
    amount: Decimal


class Invoice(BaseModel):
    line_items: List[InvoiceLineItem]
    credits: List[InvoiceCredit]
    reimbursements: List[InvoiceReimbursement]


class Project(Entity):
    name: str
    deliverables: List[Deliverable] = Field(default_factory=list)
    invoices: List[Invoice] = Field(default_factory=list)

    def get_deliverable(self, id: EntityId):
        for deliverable in self.deliverables:
            if deliverable.id == id:
                return deliverable


serialization = SerializationMiddleware(JSONStorage)
serialization.register_serializer(DateTimeSerializer(), 'TinyDate')

class DecimalSerializer(Serializer):
    OBJ_CLASS = Decimal  # The class this serializer handles

    def encode(self, obj: Decimal):
        return str(obj)

    def decode(self, s):
        return Decimal(s)

serialization.register_serializer(DecimalSerializer(), 'TinyDecimal')


@contextmanager
def get_db():
    db = model.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_project(id, db):
    return db.query(model.Project).filter_by(id=id).options(joinedload(model.Project.deliverables), joinedload(model.Project.invoices)).first()


@server.get("/projects", name="new_project")
def new_project(render: Render = Depends(Templates)):
    context = {}
    return render("new_project.html.jinja2", context=context)


@server.post("/projects", name="create_project")
def create_project(request: Request, name: str = Form()):
    project = model.Project(name=name)
    with get_db() as db:
        db.add(project)
        db.commit()
    return RedirectResponse(request.url_for("index"), status_code=HTTPStatus.SEE_OTHER)


@server.get("/projects/{id}", name="project_detail")
def project_detail(request: Request, id: str, render: Render = Depends(Templates)):
    print("GET project", id)
    with get_db() as db:
        project = get_project(id, db)
        context = {"project": project}
        return render("project_detail.html.jinja2", context=context)


@server.post("/projects/{id}/delete", name="project_delete")
def project_delete(request: Request, id: str):
    with get_db() as db:
        project = get_project(id, db)
        db.delete(project)
        db.commit()
        return RedirectResponse(request.url_for("index"), status_code=HTTPStatus.SEE_OTHER)


@server.post("/project/{project_id}/deliverable", name="create_deliverable")
def create_deliverable(
    project_id: str, request: Request, 
    name: str = Form(), estimate: Decimal = Form(), due_date: Optional[date] = Form(default=None)
    ):
    with get_db() as db:
        project = get_project(project_id, db)
        if not project:
            raise ValueError
        deliverable = model.Deliverable(
            project_id=project.id, name=name, estimate=estimate, due_date=due_date,
            created=datetime.utcnow(),
        )
        project.deliverables.append(deliverable)
        db.commit()
        return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)



@server.post("/project/{project_id}/deliverable/{deliverable_id}/delete", name="delete_deliverable")
def delete_deliverable(
    project_id: str, deliverable_id: str, request: Request, 
    ):
    with get_db() as db:
        project: model.Project = get_project(project_id, db)
        if not project:
            raise ValueError
        deliverable = project.get_deliverable(deliverable_id)
        if not deliverable:
            raise ValueError("No deliverable")
        project.deliverables.remove(deliverable)
        db.delete(deliverable)
        db.commit()
        return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

@server.post("/project/{project_id}/invoice", name="create_invoice")
def create_invoice(
    project_id: str, request: Request, name: str = Form()
    ):
    with get_db() as db:
        project: Project = get_project(project_id, db)
        if not project:
            raise ValueError
        invoice = model.Invoice(project=project, name=name)
        db.add(invoice)
        db.commit()
        return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)
        

@server.get("/project/{project_id}/invoice/{invoice_id}", name="invoice_detail")
def invoice_detail(
    project_id: str, invoice_id: str, request: Request
    ):
    with get_db() as db:
        project: Project = get_project(project_id, db)
        if not project:
            raise ValueError
        invoice = get_invoice(invoice_id, db)
        return RedirectResponse(request.url_for("invoice_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

def get_invoice(invoice_id, db):
    return db.query(model.Invoice).get(invoice_id)

@server.post("/project/{project_id}/invoice/{invoice_id}/line_items", name="add_line_item")
def create_invoice(
    project_id: str, invoice_id: str, request: Request, deliverable_id: str = Form()
    ):
    with get_db() as db:
        project: Project = get_project(project_id, db)
        if not project:
            raise ValueError
        invoice: model.Invoice = get_invoice(invoice_id, db)
        deliverable = project.get_deliverable(deliverable_id)
        invoice.line_items.append(model.InvoiceLineItem(deliverable=deliverable, amount=deliverable.estimate))
        db.commit()
        return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)
        
@server.post("/project/{project_id}/invoice/{invoice_id}/credit", name="add_credit")
def add_credit(
    project_id: str, invoice_id: str, request: Request, reason: str = Form(), amount: Decimal = Form()
    ):
    with get_db() as db:
        project: Project = get_project(project_id, db)
        if not project:
            raise ValueError
        invoice: model.Invoice = get_invoice(invoice_id, db)
        credit = model.InvoiceCredit(reason=reason, amount=amount)
        invoice.credits.append(credit)
        db.commit()
        return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

@server.post("/project/{project_id}/invoice/{invoice_id}/reimbursement", name="add_reimbursement")
def add_reimbursement(
    project_id: str, invoice_id: str, request: Request, reason: str = Form(), amount: Decimal = Form()
    ):
    with get_db() as db:
        project: Project = get_project(project_id, db)
        if not project:
            raise ValueError
        invoice: model.Invoice = get_invoice(invoice_id, db)
        reimbursement = model.InvoiceReimbursement(reason=reason, amount=amount)
        invoice.reimbursements.append(reimbursement)
        db.commit()
        return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

@server.get("/", name="index")
def index(request: Request, render: Render = Depends(Templates)):
    with get_db() as db:
        projects = db.query(model.Project).all()
        print(projects)
        context = {"request": request, "projects": projects}
        return render("index.html.jinja2", context=context)

@server.get("/project/{project_id}/invoice/{invoice_id}/render", name="render_invoice")
def render_invoice(request: Request, project_id: str, invoice_id: str, render: Render = Depends(Templates)):
     with get_db() as db:
        project: Project = get_project(project_id, db)
        if not project:
            raise ValueError
        invoice: model.Invoice = get_invoice(invoice_id, db)
        context = {
            "date": date.today().strftime("%b %d, %Y"),
            "deliverables": invoice.line_items,
            "reimbursements": invoice.reimbursements,
            "credits": invoice.credits,
            "gross_pay": invoice.gross_pay,
            "reimbursements_total": invoice.reimbursements_total,
            "net_pay": invoice.net_pay,
        }
        return render("invoice.html.jinja2", context=context)
