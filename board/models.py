from django.db import models
from users.models import User
from django.conf import settings
import os
from django.utils import timezone  
from datetime import timedelta

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
    discord_webhook_url = models.URLField(
        blank=True, 
        null=True, 
        verbose_name="Discord Webhook URL",
        help_text="วางลิงก์ Webhook จาก Discord Channel ที่ต้องการให้แจ้งเตือน"
    )

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
 
    list = models.ForeignKey('List', on_delete=models.CASCADE, related_name="tasks") 

    is_completed = models.BooleanField(default=False)  # สถานะเสร็จสิ้น
    completed_at = models.DateTimeField(null=True, blank=True) # เวลาที่เสร็จ (ไว้ทำ Report)
    def save(self, *args, **kwargs):
        # Logic: ถ้าติ๊กถูก ให้บันทึกเวลา ถ้าติ๊กออก ให้ลบเวลา
        if self.is_completed and not self.completed_at:
            from django.utils import timezone
            self.completed_at = timezone.now()
        elif not self.is_completed:
            self.completed_at = None
        super().save(*args, **kwargs)
        
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    position = models.IntegerField(default=0)
    is_archived = models.BooleanField(default=False) 
    assigned_to = models.ManyToManyField(User, related_name='tasks', blank=True)

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
    
   
    labels = models.ManyToManyField('Label', blank=True, related_name='tasks')

    # ---------------- META & METHODS ----------------

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    
    @property
    def due_status(self):
        if not self.due_date:
            return 'no_date'
            
        now = timezone.now()
        
        # กรณีเลยกำหนดแล้ว (Overdue)
        if self.due_date < now:
            return 'overdue'
            
        # กรณีเหลือเวลาน้อยกว่า 24 ชม. (Due Soon)
        elif self.due_date < now + timedelta(days=1):
            return 'soon'
            
        return 'future'


class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username} on {self.task.title}"

class ChecklistItem(models.Model):
    task = models.ForeignKey(
        Task, 
        on_delete=models.CASCADE, 
        related_name='checklist_items'
    )
    content = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)  # เผื่อเรียงลำดับ (Optional)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'created_at']

    def __str__(self):
        return f"{self.content} ({'Done' if self.is_completed else 'To Do'})"

class Attachment(models.Model):
    task = models.ForeignKey(
        Task, 
        on_delete=models.CASCADE, 
        related_name='attachments'
    )
    file = models.FileField(upload_to='task_attachments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return os.path.basename(self.file.name)
    
    # ฟังก์ชันช่วยดึงชื่อไฟล์มาแสดงแบบสวยๆ
    def filename(self):
        return os.path.basename(self.file.name)
        
    # เช็คว่าเป็นรูปภาพหรือไม่ (เผื่อเอาไปโชว์พรีวิว)
    def is_image(self):
        name = self.filename().lower()
        return name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications') # ผู้รับแจ้งเตือน
    actor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='triggered_notifications') # ผู้กระทำ (เช่น คนที่ assign)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True)
    message = models.CharField(max_length=255) # ข้อความแจ้งเตือน
    is_read = models.BooleanField(default=False) # อ่านหรือยัง
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at'] # ใหม่สุดขึ้นก่อน

    def __str__(self):
        return f"{self.actor.username} -> {self.recipient.username}: {self.message}"

class ActivityLog(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='activities')
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)  # เช่น "สร้างการ์ด 'ออกแบบ Logo'"
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.actor.username} - {self.action}"

class ClassSchedule(models.Model):
    DAYS = [
        ('Mon', 'Monday'),
        ('Tue', 'Tuesday'),
        ('Wed', 'Wednesday'),
        ('Thu', 'Thursday'),
        ('Fri', 'Friday'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject_name = models.CharField(max_length=100)
    day = models.CharField(max_length=3, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    # ถ้าดึงมาจาก Google Calendar อาจจะเก็บ Event ID ไว้
    google_event_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.subject_name} ({self.day})"