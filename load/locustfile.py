import random
from locust import HttpUser, task, between


class TrackerUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        """При старте создаем тестовый курс (чтобы было что смотреть)."""
        self.client.post("/login", data={"role": "teacher"})
        self.client.post("/courses", data={"title": "Нагрузочный тест"})

    @task(3)
    def view_courses(self):
        """Пользователь просматривает список курсов."""
        self.client.get("/courses")

    @task(2)
    def view_course_detail(self):
        """Пользователь открывает конкретный курс."""
        self.client.get("/courses/1")

    @task(1)
    def view_dashboard(self):
        """Пользователь смотрит главную страницу."""
        self.client.get("/")