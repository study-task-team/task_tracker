def test_index_shows_login_for_guest(client):
    """Гость видит страницу выбора роли."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Кто вы?" in response.text
    assert "Я Студент" in response.text
    assert "Я Преподаватель" in response.text


def test_login_as_teacher(client):
    """Преподаватель попадает в список курсов."""
    response = client.post("/login", data={"role": "teacher"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Мои курсы" in response.text
    assert "Добавить новый курс" in response.text


def test_login_as_student(client):
    """Студент попадает на дашборд."""
    response = client.post("/login", data={"role": "student"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Привет, Студент!" in response.text


def test_student_cannot_create_course(client):
    """Студент получает ошибку 403 при попытке создать курс."""
    client.post("/login", data={"role": "student"})
    response = client.post("/courses", data={"title": "Хакерский курс"})
    assert response.status_code == 403


def test_teacher_cannot_change_status(client):
    """Преподаватель получает 403 при попытке изменить статус задания."""
    client.post("/login", data={"role": "teacher"})
    response = client.post("/tasks/1/status", data={"status": "done"})
    assert response.status_code == 403


def test_logout(client):
    """Выход сбрасывает сессию."""
    client.post("/login", data={"role": "teacher"})
    response = client.get("/logout", follow_redirects=True)
    assert "Кто вы?" in response.text