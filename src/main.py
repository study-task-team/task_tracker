from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from src.db import Base, engine, get_db
from src.models import Course, Task

BASE_DIR = Path(__file__).resolve().parent

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Трекер учебных задач")

app.add_middleware(SessionMiddleware, secret_key="super-secret-key-for-lab")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def get_current_role(request: Request) -> str:
    return request.session.get("role", "guest")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    role = get_current_role(request)

    if role == "guest":
        return templates.TemplateResponse(
            request=request, name="login.html", context={"title": "Вход"}
        )

    if role == "teacher":
        return RedirectResponse(url="/courses", status_code=303)

    now = datetime.utcnow()
    week_later = now + timedelta(days=7)
    upcoming_tasks = (
        db.query(Task)
        .filter(Task.deadline >= now, Task.deadline <= week_later, Task.status != "done")
        .order_by(Task.deadline.asc())
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Дашборд", "upcoming_tasks": upcoming_tasks, "role": role},
    )


@app.post("/login")
def login(request: Request, role: str = Form(...)):
    if role not in ["teacher", "student"]:
        raise HTTPException(status_code=400, detail="Неверная роль")
    request.session["role"] = role
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/courses", response_class=HTMLResponse)
def list_courses(request: Request, db: Session = Depends(get_db)):
    role = get_current_role(request)
    if role == "guest":
        return RedirectResponse(url="/", status_code=303)

    courses = db.query(Course).order_by(Course.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="courses.html",
        context={"title": "Мои курсы", "courses": courses, "error": None, "role": role},
    )


@app.get("/courses/{course_id}", response_class=HTMLResponse)
def course_detail(
    request: Request, course_id: int, status: str = None, db: Session = Depends(get_db)
):
    role = get_current_role(request)
    if role == "guest":
        return RedirectResponse(url="/", status_code=303)

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")

    tasks = course.tasks
    if status in ["todo", "in_progress", "done"]:
        tasks = [t for t in tasks if t.status == status]

    total_tasks = len(course.tasks)
    done_tasks = sum(1 for t in course.tasks if t.status == "done")
    in_progress_tasks = sum(1 for t in course.tasks if t.status == "in_progress")
    todo_tasks = sum(1 for t in course.tasks if t.status == "todo")

    return templates.TemplateResponse(
        request=request,
        name="course_detail.html",
        context={
            "title": course.title,
            "course": course,
            "tasks": tasks,
            "error": None,
            "role": role,
            "current_filter": status,
            "stats": {
                "total": total_tasks,
                "done": done_tasks,
                "in_progress": in_progress_tasks,
                "todo": todo_tasks,
            }
        },
    )


@app.get("/tasks/{task_id}/edit", response_class=HTMLResponse)
def edit_task_page(request: Request, task_id: int, db: Session = Depends(get_db)):
    if get_current_role(request) != "teacher":
        raise HTTPException(status_code=403, detail="Только преподаватель")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    return templates.TemplateResponse(
        request=request,
        name="task_edit.html",
        context={"title": "Редактирование", "task": task, "error": None},
    )


@app.post("/tasks/{task_id}/edit")
def edit_task(
    request: Request,
    task_id: int,
    title: str = Form(...),
    deadline: str = Form(None),
    db: Session = Depends(get_db),
):
    if get_current_role(request) != "teacher":
        raise HTTPException(status_code=403, detail="Только преподаватель")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    if not title.strip():
        return templates.TemplateResponse(
            request=request,
            name="task_edit.html",
            context={"title": "Редактирование", "task": task, "error": "Название обязательно"},
            status_code=400,
        )

    parsed_deadline = None
    if deadline:
        try:
            parsed_deadline = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass

    task.title = title.strip()
    task.deadline = parsed_deadline
    db.commit()
    return RedirectResponse(url=f"/courses/{task.course_id}", status_code=303)


@app.post("/courses")
def create_course(request: Request, title: str = Form(...), db: Session = Depends(get_db)):
    if get_current_role(request) != "teacher":
        raise HTTPException(status_code=403, detail="Доступ только для преподавателя")

    if not title.strip():
        courses = db.query(Course).order_by(Course.created_at.desc()).all()
        return templates.TemplateResponse(
            request=request,
            name="courses.html",
            context={"title": "Мои курсы", "courses": courses, "error": "Название обязательно", "role": "teacher"},
            status_code=400,
        )

    course = Course(title=title.strip())
    db.add(course)
    db.commit()
    return RedirectResponse(url="/courses", status_code=303)


@app.post("/courses/{course_id}/tasks")
def create_task(
    request: Request,
    course_id: int,
    title: str = Form(...),
    deadline: str = Form(None),
    db: Session = Depends(get_db),
):
    if get_current_role(request) != "teacher":
        raise HTTPException(status_code=403, detail="Только преподаватель может создавать задания")

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Курс не найден")

    if not title.strip():
        done_tasks = sum(1 for t in course.tasks if t.status == "done")
        in_progress_tasks = sum(1 for t in course.tasks if t.status == "in_progress")
        todo_tasks = sum(1 for t in course.tasks if t.status == "todo")

        return templates.TemplateResponse(
            request=request,
            name="course_detail.html",
            context={
                "title": course.title,
                "course": course,
                "tasks": course.tasks,
                "error": "Название задания обязательно",
                "role": "teacher",
                "current_filter": None,
                "stats": {
                    "total": len(course.tasks),
                    "done": done_tasks,
                    "in_progress": in_progress_tasks,
                    "todo": todo_tasks,
                }
            },
            status_code=400,
        )

    parsed_deadline = None
    if deadline:
        try:
            parsed_deadline = datetime.strptime(deadline, "%Y-%m-%dT%H:%M")
        except ValueError:
            pass

    task = Task(title=title.strip(), deadline=parsed_deadline, course_id=course_id)
    db.add(task)
    db.commit()
    return RedirectResponse(url=f"/courses/{course_id}", status_code=303)


@app.post("/tasks/{task_id}/status")
def update_task_status(
    request: Request,
    task_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    if get_current_role(request) != "student":
        raise HTTPException(status_code=403, detail="Только студент может менять статус")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    if status not in ["todo", "in_progress", "done"]:
        raise HTTPException(status_code=400, detail="Недопустимый статус")

    task.status = status
    db.commit()
    return RedirectResponse(url=f"/courses/{task.course_id}", status_code=303)