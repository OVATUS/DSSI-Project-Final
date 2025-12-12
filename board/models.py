from django.db import models
from users.models import User
from django.conf import settings

COLOR_CHOICES = [
    ('bg-red-500', 'สีแดง (Red)'),
    ('bg-orange-500', 'สีส้ม (Orange)'),
    ('bg-yellow-400', 'สีเหลือง (Yellow)'),
    ('bg-green-500', 'สีเขียว (Green)'),
    ('bg-blue-500', 'สีฟ้า (Blue)'),
    ('bg-indigo-500', 'สีม่วง (Indigo)'),
    ('bg-pink-500', 'สีชมพู (Pink)'),
    ('bg-gray-500', 'สีเทา (Gray)'),
]

class Board(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True, null=True)
    cover_image = models.ImageField(upload_to="board_covers/", blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="boards")  
    members = models.ManyToManyField(User, related_name="joined_boards", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    starred_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='starred_boards', blank=True)

    def __str__(self):
        return self.name

class BoardInvitation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]
    
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='invitations')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invitations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} invited {self.recipient} to {self.board}"

class Label(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='labels')
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=50, choices=COLOR_CHOICES, default='bg-blue-500')
    
    def __str__(self):
        return f"{self.name} ({self.get_color_display()})"


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
    position = models.IntegerField(default=0)
   

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
    labels = models.ManyToManyField(Label, blank=True, related_name='tasks')
    class Meta:
        ordering = ['position']
    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username} on {self.task.title}"

