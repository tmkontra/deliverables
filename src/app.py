from ast import Del
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from http import HTTPStatus
from lib2to3.pytree import Base
from pathlib import Path
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

ROOT_DIR = Path(__file__).parent

server = FastAPI()

server.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")

Render = Callable[[str, dict], Response]


class RenderTemplate:
    def __init__(self, **globals):
        self._templates = Jinja2Templates(directory=ROOT_DIR / "templates")
        self._set_globals(self._templates, globals)

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



class Database:
    def __init__(self, db):
        self._db = db
        self.Projects = Query()
    
    def get_project(self, id) -> Optional[Project]:
        project = self._db.get(self.Projects.id == id)
        if project:
            return Project(**project)

    def insert(self, entity: Entity):
        return self._db.insert(entity.dict())

    def all_projects(self):
        return self._db.all()
    
    def update_project(self, project: Project):
        return self._db.update(project.dict())

    @staticmethod
    def _serialize(entity: Entity):
        data = entity.dict()



_db = TinyDB("./deliverables.tinydb", storage=serialization)
db = Database(_db)


@server.get("/projects", name="new_project")
def new_project(render: Render = Depends(Templates)):
    context = {}
    return render("new_project.html.jinja2", context=context)


@server.post("/projects", name="create_project")
def create_project(request: Request, name: str = Form()):
    project = Project(name=name)
    db.insert(project)
    return RedirectResponse(request.url_for("index"), status_code=HTTPStatus.SEE_OTHER)


@server.get("/projects/{id}", name="project_detail")
def project_detail(request: Request, id: str, render: Render = Depends(Templates)):
    print("GET project", id)
    project = db.get_project(id)
    context = {"project": project}
    return render("project_detail.html.jinja2", context=context)


@server.post("/projects/{id}/delete", name="project_delete")
def project_delete(request: Request, id: str):
    project = db.get_project(id)
    if project:
        db.remove(Query().id == id)
    return RedirectResponse(request.url_for("index"), status_code=HTTPStatus.SEE_OTHER)


@server.post("/project/{project_id}/deliverable", name="create_deliverable")
def create_deliverable(
    project_id: str, request: Request, 
    name: str = Form(), estimate: Decimal = Form(), due_date: Optional[date] = Form(default=None)
    ):
    project = db.get_project(project_id)
    if not project:
        raise ValueError
    deliverable = Deliverable(
        project_id=project.id, name=name, estimate=estimate, due_date=due_date,
        created=datetime.utcnow(),
        )
    project.deliverables.append(deliverable)
    db.update_project(project)
    return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)



@server.post("/project/{project_id}/deliverable/{deliverable_id}/delete", name="delete_deliverable")
def delete_deliverable(
    project_id: str, deliverable_id: str, request: Request, 
    ):
    project: Project = db.get_project(project_id)
    if not project:
        raise ValueError
    deliverable = project.get_deliverable(deliverable_id)
    if not deliverable:
        raise ValueError
    project.deliverables.remove(deliverable)
    db.update_project(project)
    return RedirectResponse(request.url_for("project_detail", id=project.id), status_code=HTTPStatus.SEE_OTHER)


@server.get("/", name="index")
def index(request: Request, render: Render = Depends(Templates)):
    projects = db.all_projects()
    context = {"request": request, "projects": projects}
    return render("index.html.jinja2", context=context)
