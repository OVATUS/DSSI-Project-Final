from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm, UserUpdateForm

# --- Register ---
def register_view(request):
    if request.user.is_authenticated:
        return redirect('profile') # ถ้าล็อกอินอยู่แล้ว เด้งไปหน้า Profile

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # สมัครเสร็จ ล็อกอินให้เลย (UX ดีกว่า)
            return redirect('profile') # เปลี่ยนเป็นหน้าแรกที่คุณต้องการให้ไปหลังสมัครเสร็จ
    else:
        form = RegisterForm()
    
    # ส่ง form ไปให้ frontend วาด ({{ form.as_p }})
    return render(request, 'users/registers.html', {'form': form})

# --- Me / Profile (ดู, แก้ไข, ลบ) ---
@login_required(login_url='login') # ต้องล็อกอินก่อนถึงจะเข้าได้
def profile_view(request):
    user = request.user
    
    # กรณีแก้ไขข้อมูล (Update - PUT)
    if request.method == 'POST':
        # เช็คด้วยว่าเป็นการกดปุ่มลบหรือเปล่า
        if 'delete_account' in request.POST:
            user.delete()
            return redirect('login') # ลบเสร็จเด้งไปหน้า login

        # กรณีอัปเดตข้อมูลปกติ
        # request.FILES จำเป็นสำหรับการอัปโหลดรูปภาพ
        form = UserUpdateForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            return redirect('profile') # รีเฟรชหน้าเพื่อโชว์ข้อมูลใหม่
    else:
        form = UserUpdateForm(instance=user)

    context = {
        'form': form,
        'user': user
    }
    return render(request, 'users/profile.html', context)

def logout_view(request):
    logout(request)
    return redirect('login') 