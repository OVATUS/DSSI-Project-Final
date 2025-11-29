# boards/forms.py
from django import forms
from .models import Board, List, Task   # 👈 ใช้ Task แทน Card
from users.models import User


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ["name", "description", "cover_image"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base = ("w-full rounded-md border border-gray-300 px-3 py-2 text-sm "
                "focus:outline-none focus:ring-2 focus:ring-[#0094FF]")
        for name, field in self.fields.items():
            if name == "cover_image":
                field.widget.attrs.update({
                    "class": (
                        "block w-full text-sm text-gray-700 file:mr-3 "
                        "file:py-1.5 file:px-3 file:rounded-full "
                        "file:border-0 file:bg-[#0094FF] file:text-white "
                        "hover:file:bg-[#0077cc]"
                    )
                })
            else:
                field.widget.attrs.update({"class": base})


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
        fields = ["title", "description", "assigned_to", "due_date",  "priority"]

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
