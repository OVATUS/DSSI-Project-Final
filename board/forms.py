# boards/forms.py
from django import forms
from .models import Board, List, Task, ClassSchedule   
from users.models import User


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["name", "description", "cover_image", "discord_webhook_url"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Style พื้นฐานสำหรับ Input ทั่วไป
        base_style = (
            "w-full rounded-md border border-gray-300 px-3 py-2 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-[#0094FF]"
        )

        for name, field in self.fields.items():
            # 1. กรณีเป็นช่องอัปโหลดรูป (Cover Image)
            if name == "cover_image":
                field.widget.attrs.update({
                    "class": (
                        "block w-full text-sm text-gray-700 file:mr-3 "
                        "file:py-1.5 file:px-3 file:rounded-full "
                        "file:border-0 file:bg-[#0094FF] file:text-white "
                        "hover:file:bg-[#0077cc]"
                    )
                })

            # ✅ 2. กรณีเป็นช่อง Discord (เพิ่ม Placeholder)
            elif name == "discord_webhook_url":
                field.widget.attrs.update({
                    "class": base_style,
                    "placeholder": "https://discord.com/api/webhooks/..." # ใส่ตัวอย่างลิงก์ให้ User เห็น
                })

            # 3. กรณีอื่นๆ (ใช้ Style พื้นฐาน)
            else:
                field.widget.attrs.update({"class": base_style})


class ListForm(forms.ModelForm):
    class Meta:
        model = List
        fields = ["title", "position"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base = ("w-full rounded-md border border-gray-300 px-3 py-2 text-sm "
                "focus:outline-none focus:ring-2 focus:ring-[#0094FF]")
        for field in self.fields.values():
            field.widget.attrs.update({"class": base})


class TaskForm(forms.ModelForm):   
    due_date = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
            }
        ),
    )

    class Meta:
        model = Task
        fields = ["title", "description", "assigned_to", "due_date",  "priority",'remind_days']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base = ("w-full rounded-md border border-gray-300 px-3 py-2 text-sm "
                "focus:outline-none focus:ring-2 focus:ring-[#0094FF]")

        for name, field in self.fields.items():
            if name in ["status", "priority", "assigned_to"]:
                field.widget.attrs.update({
                    "class": base.replace("px-3 py-2", "px-3 py-2")  # select ใช้ class เดียวกันได้
                })
            else:
                field.widget.attrs.update({"class": base})

class ClassScheduleForm(forms.ModelForm):
    class Meta:
        model = ClassSchedule
        fields = ['subject_name', 'day', 'start_time', 'end_time']
        widgets = {
            'subject_name': forms.TextInput(attrs={'class': 'w-full text-sm border-gray-300 rounded-md', 'placeholder': 'ชื่อวิชา (เช่น Math 101)'}),
            'day': forms.Select(attrs={'class': 'w-full text-sm border-gray-300 rounded-md'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full text-sm border-gray-300 rounded-md'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full text-sm border-gray-300 rounded-md'}),
        }