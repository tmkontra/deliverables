import json
import logging
import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from http import HTTPStatus
from io import UnsupportedOperation
from pathlib import Path
from typing import Optional

import sqlalchemy
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi_jinja_utils import Jinja2TemplatesDependency, Renderable
from fastapi_utils.cbv import cbv
from sqlalchemy.orm import joinedload

from . import model
from .auth import MultitenantAuth, NoopAuth, PrivateInstanceAuth
from .exceptions import RefreshDatabaseError, Unauthorized
from .settings import Settings
from .utils import render_currency

logger = logging.getLogger(__name__)

settings = Settings()

ROOT_DIR = Path(__file__).parent

server = FastAPI()

server.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")

# invoice config data
try:
    with open(ROOT_DIR.parent / ".deliverables.json", "r") as f:
        config_constants = json.load(f)
except FileNotFoundError:
    config_constants = {
        "my_name": os.getenv("CONFIG_MY_NAME", "<Name>"),
        "my_address_1": os.getenv("CONFIG_ADDRESS_1", "<Address 1>"),
        "my_address_2": os.getenv("CONFIG_MY_ADDRESS_2", "<Address 2>"),
    }

templates_dir = ROOT_DIR / "templates"
jinja_globals = {
    "currency": render_currency,
    **config_constants
}
Templates = Jinja2TemplatesDependency(template_dir=templates_dir, env_globals=jinja_globals)

match settings.DEPLOYMENT:
    case "local":
        auth = NoopAuth(server)
        db_proxy = model.StaticDatabaseProxy(settings=settings)    
    case "private":
        auth = PrivateInstanceAuth(settings.PASSWORD, settings.SECRET_KEY, "/login", server)
        db_proxy = model.StaticDatabaseProxy(settings=settings)
    case "demo":
        auth = MultitenantAuth(server)
        db_proxy = model.MultitenantDatabaseProxy(database_directory=settings.DATABASE_DIRECTORY)
    case other:
        raise RuntimeError(f"DEPLOYMENT variable invalid value: {other}")



def get_tenant_id(request: Request):
    return auth.get_tenant_id(request=request)


@server.middleware("http")
async def authentication_middleware(request: Request, call_next):
    try: 
        auth.is_authenticated(request=request)
        return await call_next(request)
    except Unauthorized as e:
        return e.response

@server.middleware("http")
async def retry_refreshed_database_middleware(request: Request, call_next):
    try: 
        return await call_next(request)
    except RefreshDatabaseError:
        return RedirectResponse(request.url, status_code=303)
    except model.DatabaseLimitExceededError:
        return RedirectResponse("/db-limit-exceeded", status_code=303)


@contextmanager
def get_db(tenant_id: Optional[str]):
    db = db_proxy.get_session(tenant_id=tenant_id)
    try:
        yield db
    except sqlalchemy.exc.OperationalError as e:
        logger.exception("Database OperationalError")
        db_proxy.recreate_database(tenant_id=tenant_id)
        raise RefreshDatabaseError()
    except model.DatabaseLimitExceededError as e:
        logger.exception("Database at max size!")
        raise
    finally:
        db.close()


def get_project(id, db):
    return db.query(model.Project).filter_by(id=id).options(joinedload(model.Project.deliverables), joinedload(model.Project.invoices)).first()


def get_invoice(invoice_id, db):
    return db.query(model.Invoice).get(invoice_id)


@cbv(server)
class Views:
    tenant_id: Optional[str] = Depends(get_tenant_id)

    @server.post("/projects", name="create_project")
    def create_project(self, request: Request, name: str = Form()):
        project = model.Project(name=name)
        with get_db(self.tenant_id) as db:
            db.add(project)
            db.commit()
        return RedirectResponse(request.url_for("index"), status_code=HTTPStatus.SEE_OTHER)


    @server.get("/projects/{id}", name="project_detail")
    def project_detail(self, request: Request, id: str, render: Renderable = Depends(Templates)):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(id, db)
            available_deliverables = db.query(model.Deliverable).outerjoin(
                (model.InvoiceLineItem, model.Deliverable.id == model.InvoiceLineItem.deliverable_id)
            ).filter(model.InvoiceLineItem.id == None)
            context = {
                "project": project,
                "available_deliverables": available_deliverables,
                "invoices": project.invoices,
            }
            return render("project_detail.html.jinja2", context=context)


    @server.post("/projects/{id}/delete", name="project_delete")
    def project_delete(self, request: Request, id: str):
        with get_db(self.tenant_id) as db:
            project = get_project(id, db)
            db.delete(project)
            db.commit()
            return RedirectResponse(request.url_for("index"), status_code=HTTPStatus.SEE_OTHER)


    @server.post("/project/{project_id}/deliverable", name="create_deliverable")
    def create_deliverable(
        self,
        project_id: str, request: Request, 
        name: str = Form(), estimate: Decimal = Form(), due_date: Optional[date] = Form(default=None)
        ):
        with get_db(self.tenant_id) as db:
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
        self,
        project_id: str, deliverable_id: str, request: Request, 
        ):
        with get_db(self.tenant_id) as db:
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
        self,
        project_id: str, request: Request, name: str = Form()
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice = model.Invoice(project=project, name=name)
            db.add(invoice)
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)
            

    @server.get("/project/{project_id}/invoice/{invoice_id}", name="invoice_detail")
    def invoice_detail(
        self,
        project_id: str, invoice_id: str, request: Request
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice = get_invoice(invoice_id, db)
            return RedirectResponse(request.url_for("invoice_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)


    @server.post("/project/{project_id}/invoice/{invoice_id}/line_items", name="add_line_item")
    def add_line_item(
        self,
        project_id: str, invoice_id: str, request: Request, deliverable_id: str = Form()
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            deliverable = project.get_deliverable(deliverable_id)
            invoice.line_items.append(model.InvoiceLineItem(deliverable=deliverable, amount=deliverable.estimate))
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)
            
    @server.post("/project/{project_id}/invoice/{invoice_id}/line_items/{line_item_id}", name="remove_line_item")
    def remove_line_item(
        self,
        project_id: str, invoice_id: str, request: Request, line_item_id: str,
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            line_item = db.query(model.InvoiceLineItem).get(line_item_id)
            invoice.line_items.remove(line_item)
            db.delete(line_item)
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

    @server.post("/project/{project_id}/invoice/{invoice_id}/credit", name="add_credit")
    def add_credit(
        self,
        project_id: str, invoice_id: str, request: Request, reason: str = Form(), amount: Decimal = Form()
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            credit = model.InvoiceCredit(reason=reason, amount=amount)
            invoice.credits.append(credit)
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

    @server.post("/project/{project_id}/invoice/{invoice_id}/credit/{credit_id}", name="remove_credit")
    def remove_credit(
        self,
        project_id: str, invoice_id: str, request: Request, credit_id: str,
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            credit = db.query(model.InvoiceCredit).get(credit_id)
            invoice.credits.remove(credit)
            db.delete(credit)
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

    @server.post("/project/{project_id}/invoice/{invoice_id}/reimbursement", name="add_reimbursement")
    def add_reimbursement(
        self,
        project_id: str, invoice_id: str, request: Request, reason: str = Form(), amount: Decimal = Form()
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            reimbursement = model.InvoiceReimbursement(reason=reason, amount=amount)
            invoice.reimbursements.append(reimbursement)
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

    @server.post("/project/{project_id}/invoice/{invoice_id}/reimbursement/{reimbursement_id}", name="remove_reimbursement")
    def remove_reimbursement(
        self,
        project_id: str, invoice_id: str, request: Request, reimbursement_id: str,
        ):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            reimbursement = db.query(model.InvoiceReimbursement).get(reimbursement_id)
            invoice.reimbursements.remove(reimbursement)
            db.delete(reimbursement)
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)


    @server.get("/", name="index")
    def index(self, request: Request, render: Renderable = Depends(Templates)):
        with get_db(self.tenant_id) as db:
            projects = db.query(model.Project).limit(100).all()
            context = {"request": request, "projects": projects}
            return render("index.html.jinja2", context=context)

    @server.post("/project/{project_id}/contact", name="update_contact") 
    def update_contact(self, project_id: str, request: Request, company_name: str = Form(), contact_name: str = Form(), contact_email: str = Form()):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            bill_to = project.bill_to
            if not bill_to:
                bill_to = model.BillTo(company_name=company_name, contact_name=contact_name, contact_email=contact_email)
                db.add(bill_to)
                project.bill_to = bill_to
            else:
                bill_to.company_name = company_name
                bill_to.contact_name = contact_name
                bill_to.contact_email = contact_email
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

    @server.get("/project/{project_id}/invoice/{invoice_id}/render", name="render_invoice")
    def render_invoice(self, request: Request, project_id: str, invoice_id: str, render: Renderable = Depends(Templates)):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            context = {
                "date": date.today().strftime("%b %d, %Y"),
                "bill_to": project.bill_to,
                "invoice_number": invoice.name,
                "deliverables": invoice.line_items,
                "reimbursements": invoice.reimbursements,
                "credits": invoice.credits,
                "balance_due": invoice.balance_due,
                "reimbursements_total": invoice.reimbursements_total,
                "net_pay": invoice.net_pay,
            }
            return render("invoice.html.jinja2", context=context)


    @server.post("/project/{project_id}/invoice/{invoice_id}/sent", name="invoice_sent")
    def invoice_sent(self, request: Request, project_id: str, invoice_id: str, sent: Optional[date] = Form(None)):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            invoice.sent = sent
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)


    @server.post("/project/{project_id}/invoice/{invoice_id}/paid", name="invoice_paid")
    def invoice_paid(self, request: Request, project_id: str, invoice_id: str, paid: Optional[date] = Form(None)):
        with get_db(self.tenant_id) as db:
            project: model.Project = get_project(project_id, db)
            if not project:
                raise ValueError
            invoice: model.Invoice = get_invoice(invoice_id, db)
            invoice.paid = paid
            db.commit()
            return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)

    @server.get("/db-limit-exceeded")
    def db_limit_exceeded_confirmation(self):
        html = """
        <h1>It looks like you've added too much data to your database!</h1>
        <p>To make sure "noisy neighbors" don't ruin the demo for everyone else, we limit the maximum demo database size</p>
        <form action="/db-limit-exceeded" method="POST">
            <label>To continue using the demo, you'll need to wipe your database and start fresh.</p>
            <button type="submit">Confirm Database Wipe</button>
        </form>
        """
        return HTMLResponse(html)
    
    @server.post("/db-limit-exceeded")
    def wipe_database(self):
        if not isinstance(db_proxy, model.MultitenantDatabaseProxy):
            raise UnsupportedOperation()
        else:
            db_proxy.recreate_database(self.tenant_id)
        return RedirectResponse("/", status_code=303)
