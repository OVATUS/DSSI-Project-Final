from django.db import models
from users.models import User


class Board(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    cover_image = models.ImageField(upload_to="board_covers/", blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="boards")
    
    members = models.ManyToManyField(User, related_name="joined_boards", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class List(models.Model):
    board = models.ForeignKey('Board', on_delete=models.CASCADE, related_name='lists')
    title = models.CharField(max_length=255)
    position = models.IntegerField()

    def __str__(self):
        return f"{self.title} (Board: {self.board.name})"


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    list = models.ForeignKey(List, on_delete=models.CASCADE, related_name="tasks")  # list_id
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    # ผู้รับผิดชอบงาน (nullable)
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks_assigned"
    )

    due_date = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
    )

    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username} on {self.task.title}"