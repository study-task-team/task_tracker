def test_teacher_can_create_course(client):
    """Преподаватель может создать курс."""
    client.post("/login", data={"role": "teacher"})
    response = client.post(
        "/courses", data={"title": "Физика"}, follow_redirects=False
    )
    assert response.status_code == 303

    response = client.get("/courses")
    assert "Физика" in response.text


def test_teacher_cannot_create_course_empty_title(client):
    """Пустое название курса вызывает ошибку."""
    client.post("/login", data={"role": "teacher"})
    response = client.post("/courses", data={"title": "   "})
    assert response.status_code == 400
    assert "Название обязательно" in response.text


def test_course_detail_404(client):
    """Несуществующий курс дает 404."""
    client.post("/login", data={"role": "teacher"})
    response = client.get("/courses/999")
    assert response.status_code == 404


def test_teacher_can_create_task(client):
    """Преподаватель может создать задание."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Математика"})

    response = client.post(
        "/courses/1/tasks",
        data={"title": "Лабораторная 1", "deadline": "2026-12-31T23:59"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    response = client.get("/courses/1")
    assert "Лабораторная 1" in response.text


def test_student_can_change_status(client):
    """Студент может сменить статус задания."""
    # Создаем курс и задание от лица препода
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Химия"})
    client.post("/courses/1/tasks", data={"title": "Опыт"})
    client.get("/logout")

    # Заходим как студент
    client.post("/login", data={"role": "student"})
    response = client.post(
        "/tasks/1/status", data={"status": "done"}, follow_redirects=False
    )
    assert response.status_code == 303

    response = client.get("/courses/1")
    assert 'value="done" selected' in response.text


def test_health_endpoint(client):
    """Проверка эндпоинта /health."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_db_dependency():
    """Тест на генератор get_db (покрывает db.py)."""
    from src.db import get_db
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass


def test_guest_redirected_from_courses(client):
    """Гость при заходе на /courses перенаправляется на главную."""
    response = client.get("/courses", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_create_task_empty_title(client):
    """Пустое название задания вызывает ошибку."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Биология"})
    response = client.post("/courses/1/tasks", data={"title": "   "})
    assert response.status_code == 400  # <-- поменяли 303 на 400
    assert "Название задания обязательно" in response.text


def test_create_task_invalid_deadline(client):
    """Некорректная дата не ломает сервер."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "География"})
    response = client.post(
        "/courses/1/tasks",
        data={"title": "Карта", "deadline": "не-дата"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_update_task_status_invalid(client):
    """Неверный статус задания возвращает 400."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Астрономия"})
    client.post("/courses/1/tasks", data={"title": "Звезды"})
    client.get("/logout")

    client.post("/login", data={"role": "student"})
    response = client.post("/tasks/1/status", data={"status": "invalid"})
    assert response.status_code == 400


def test_edit_task_page_teacher(client):
    """Преподаватель может открыть страницу редактирования."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Химия"})
    client.post("/courses/1/tasks", data={"title": "Старое задание"})
    response = client.get("/tasks/1/edit")
    assert response.status_code == 200
    assert "Старое задание" in response.text


def test_edit_task_teacher_saves(client):
    """Преподаватель может изменить задание."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Биология"})
    client.post("/courses/1/tasks", data={"title": "Старое"})

    response = client.post(
        "/tasks/1/edit",
        data={"title": "Новое название", "deadline": ""},
        follow_redirects=False
    )
    assert response.status_code == 303

    response = client.get("/courses/1")
    assert "Новое название" in response.text
    assert "Старое" not in response.text


def test_edit_task_403_for_student(client):
    """Студент не может редактировать задание."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Физика"})
    client.post("/courses/1/tasks", data={"title": "Задача"})
    client.get("/logout")

    client.post("/login", data={"role": "student"})
    response = client.get("/tasks/1/edit")
    assert response.status_code == 403


def test_edit_task_empty_title_error(client):
    """Пустое название при редактировании вызывает ошибку 400."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "История"})
    client.post("/courses/1/tasks", data={"title": "Старое"})

    response = client.post(
        "/tasks/1/edit",
        data={"title": "   ", "deadline": ""}
    )
    assert response.status_code == 400
    assert "Название обязательно" in response.text


def test_edit_task_invalid_deadline(client):
    """Некорректная дата при редактировании не ломает сервис."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "География"})
    client.post("/courses/1/tasks", data={"title": "Старое"})

    response = client.post(
        "/tasks/1/edit",
        data={"title": "Новое", "deadline": "не-дата"},
        follow_redirects=False
    )
    assert response.status_code == 303


def test_edit_task_404(client):
    """Редактирование несуществующего задания возвращает 404."""
    client.post("/login", data={"role": "teacher"})
    response = client.get("/tasks/999/edit")
    assert response.status_code == 404


def test_delete_course(client):
    """Проверка удаления курса преподавателем."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Удаляемый курс"})

    # Проверяем, что курс есть
    response = client.get("/courses")
    assert "Удаляемый курс" in response.text

    # Удаляем
    response = client.post("/courses/1/delete", follow_redirects=False)
    assert response.status_code == 303

    # Проверяем, что курса больше нет
    response = client.get("/courses")
    assert "Удаляемый курс" not in response.text


def test_delete_course_403_for_student(client):
    """Студент не может удалять курсы."""
    client.post("/login", data={"role": "teacher"})
    client.post("/courses", data={"title": "Защищенный курс"})
    client.get("/logout")

    client.post("/login", data={"role": "student"})
    response = client.post("/courses/1/delete")
    assert response.status_code == 403