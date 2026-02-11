import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # ตรวจสอบว่า Login หรือยัง
        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            # สร้างห้องส่วนตัวชื่อ "user_ID" (เช่น user_1)
            self.room_group_name = f"user_{self.scope['user'].id}"

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            print(f"User {self.scope['user'].id} Connected to Notifications")

    async def disconnect(self, close_code):
        if not self.scope["user"].is_anonymous:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # ฟังก์ชันรับข้อมูลแจ้งเตือน แล้วส่งต่อให้ Frontend
    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': event['message'],
            'unread_count': event['unread_count']
        }))