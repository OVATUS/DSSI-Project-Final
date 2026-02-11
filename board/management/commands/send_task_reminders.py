from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, datetime
from board.models import Task, Notification
from django.core.mail import send_mail
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import requests 

class Command(BaseCommand):
    help = 'ส่งแจ้งเตือนงานที่ใกล้ถึงกำหนด (Web, Email, Discord)'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        
        tasks = Task.objects.filter(
            is_completed=False, 
            due_date__isnull=False, 
            is_reminded=False
        )

        count = 0
        self.stdout.write("⏳ กำลังตรวจสอบงานที่ต้องแจ้งเตือน...")

        for task in tasks:
            if task.remind_days == 0: continue 

            task_due_date = task.due_date
            if isinstance(task_due_date, datetime):
                task_due_date = task_due_date.date()

            reminder_date = task_due_date - timedelta(days=task.remind_days)

            if today >= reminder_date:
                
                self.stdout.write(f"🔔 กำลังแจ้งเตือนงาน: {task.title}")
                
                assignees = task.assigned_to.all()
                if not assignees: continue

                channel_layer = get_channel_layer()

                for user in assignees:
                    # ----------------------------------------
                    # A. แจ้งเตือน Web (Real-time) + DB
                    # ----------------------------------------
                    try:
                       
                        Notification.objects.create(
                            recipient=user,
                            actor=task.list.board.created_by, 
                            task=task,
                            message=f"⏳ เตือนความจำ! งาน '{task.title}' ครบกำหนดในอีก {task.remind_days} วัน"
                        )
                        
                        unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
                        async_to_sync(channel_layer.group_send)(
                            f"user_{user.id}",
                            {
                                "type": "send_notification",
                                "message": f"⏳ ใกล้ครบกำหนด! '{task.title}'",
                                "unread_count": unread_count
                            }
                        )
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Web/DB Error: {e}"))

                    # ----------------------------------------
                    # B. แจ้งเตือน Email (Gmail)
                    # ----------------------------------------
                    if user.email:
                        try:
                            formatted_date = task.due_date.strftime('%d/%m/%Y')
                            send_mail(
                                subject=f"แจ้งเตือนงานใกล้ครบกำหนด: {task.title}",
                                message=(
                                    f"สวัสดีคุณ {user.username},\n\n"
                                    f"งาน '{task.title}' จะครบกำหนดในวันที่ {formatted_date}\n"
                                    f"(เหลือเวลาอีก {task.remind_days} วัน)\n\n"
                                    f"กรุณาตรวจสอบสถานะงานของคุณ\n\n"
                                    f"ขอบคุณครับ,\nทีมงาน Work Wai D"
                                ),
                                from_email=settings.EMAIL_HOST_USER,
                                recipient_list=[user.email],
                                fail_silently=True,
                            )
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Email Error: {e}"))

                # ----------------------------------------
                # C. แจ้งเตือน Discord
                # ----------------------------------------
                webhook_url = task.list.board.discord_webhook_url
                if webhook_url:
                    assignee_names = ", ".join([u.username for u in assignees])
                    formatted_date = task.due_date.strftime('%d/%m/%Y')
                    
                    discord_msg = {
                        "content": (
                            f"⚠️ **Upcoming Deadline Warning!**\n"
                            f"**Task:** {task.title}\n"
                            f"**Due Date:** {formatted_date}\n"
                            f"**Remaining:** {task.remind_days} Days\n"
                            f"**Team:** {assignee_names}\n"
                            f"---------------------------------"
                        )
                    }
                    try:
                        requests.post(webhook_url, json=discord_msg)
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Discord Error: {e}"))

                task.is_reminded = True
                task.save()
                count += 1

        self.stdout.write(self.style.SUCCESS(f'✅ ส่งแจ้งเตือนสำเร็จทั้งหมด {count} รายการ'))