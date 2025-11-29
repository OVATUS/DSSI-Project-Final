from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User
from django.contrib.auth.forms import AuthenticationForm

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ซ่อน help_text ทั้งหมดของ password
        self.fields['password1'].help_text = ""
        self.fields['password2'].help_text = ""

        # ปรับ UI ของทุก field
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "w-full px-3 py-2 rounded-lg bg-white/70 focus:ring-2 focus:ring-blue-500 outline-none"
            })


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email", "profile_image"] 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "w-full rounded-md border border-gray-300 px-3 py-2 "
                         "focus:outline-none focus:ring-2 focus:ring-[#0094FF] text-sm"
            })


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "w-full px-3 py-2 rounded-lg bg-white/70 focus:ring-2 focus:ring-blue-500 outline-none"
            })
