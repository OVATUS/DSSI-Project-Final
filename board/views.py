from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Board, List, Task    
from .forms import BoardForm, ListForm, TaskForm
from users.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Max
from django.db.models import Q

def board_lsit_view(request):
    return render (request, 'boards/dashboard.html')


@login_required
def project_page(request):
    boards = Board.objects.filter(
        Q(created_by=request.user) | Q(members=request.user)
    ).distinct().order_by("-created_at")

    starred_boards = boards.filter(description__icontains="⭐")[:3]
    form = BoardForm()

    return render(request, "boards/project_list.html", {
        "boards": boards,
        "starred_boards": starred_boards,
        "form": form,
    })

# CREATE
from .models import Board, List, Task
# ...

@login_required
def board_create(request):
    if request.method == "POST":
        form = BoardForm(request.POST, request.FILES)
        if form.is_valid():
            board = form.save(commit=False)
            board.created_by = request.user
            board.save()

            # ✅ สร้าง 3 ลิสต์เริ่มต้นให้บอร์ดนี้อัตโนมัติ
            # (กันกรณีเผื่อเรียกซ้ำ ไม่ให้สร้างซ้ำ)
            if not board.lists.exists():
                List.objects.create(board=board, title="TO DO",  position=1)
                List.objects.create(board=board, title="Doing", position=2)
                List.objects.create(board=board, title="Done",  position=3)

            return redirect("board_detail", board_id=board.id)
    else:
        form = BoardForm()

    return render(request, "boards/board_form.html", {"form": form})

# READ (All)
@login_required
def board_list(request):
    boards = Board.objects.filter(created_by=request.user)
    return render(request, "boards/board_list.html", {"boards": boards})


# READ (Detail)
@login_required
def board_detail(request, board_id):
    board = get_object_or_404(
        Board, 
        Q(created_by=request.user) | Q(members=request.user),
        id=board_id
    )

    # ... (code ส่วนดึง lists, tasks เหมือนเดิม)
    lists = board.lists.all().prefetch_related("tasks").order_by("position")
    
    # ✅ ส่ง members ทั้งหมดไปที่ template ด้วย (เผื่อใช้แสดงรูปคนในบอร์ด)
    # เราจะรวมเจ้าของบอร์ด + สมาชิก
    # (หรือถ้าจะเอาแค่รายชื่อ user ทั้งหมดในระบบเพื่อให้เลือกมอบหมายงาน ก็ใช้ User.objects.all() เหมือนเดิมได้ครับ 
    # แต่ปกติควรให้เลือก assign ได้เฉพาะคนในบอร์ดนะ)
    
    # ตัวอย่าง: เอา User ทั้งหมดในระบบมาแสดงใน Dropdown (แบบเดิมของคุณ)
    users = User.objects.all() 
    
    priority_choices = Task.Priority.choices

    return render(request, "boards/board_detail.html", {
        "board": board,
        "lists": lists,
        "users": users,
        "priority_choices": priority_choices,
    })

# UPDATE
@login_required
def board_update(request, board_id):
    board = get_object_or_404(Board, id=board_id, created_by=request.user)

    if request.method == "POST":
        form = BoardForm(request.POST, request.FILES, instance=board)
        if form.is_valid():
            form.save()
            return redirect("project_page")   
            
    return redirect("project_page")



# DELETE
@login_required
def board_delete(request, board_id):
    board = get_object_or_404(Board, id=board_id, created_by=request.user)

    if request.method == "POST":
        board.delete()
        return redirect("project_page")

    return redirect("project_page")

# LIST CREATE
@login_required
def list_create(request, board_id):
    board = get_object_or_404(Board, id=board_id, created_by=request.user)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if title:
            max_pos = board.lists.aggregate(Max("position"))["position__max"] or 0
            List.objects.create(
                board=board,
                title=title,
                position=max_pos + 1
            )
        return redirect("board_detail", board_id=board.id)
    form = ListForm()
    return render(request, "boards/list_form.html", {"form": form, "board": board})


# LIST UPDATE
@login_required
def list_update(request, list_id):
    lst = get_object_or_404(List, id=list_id, board__created_by=request.user)
    board = lst.board

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if title:
            lst.title = title
            lst.save()
        return redirect("board_detail", board_id=board.id)

    form = ListForm(instance=lst)
    return render(request, "boards/list_form.html", {"form": form, "board": board})

# LIST DELETE
@login_required
def list_delete(request, list_id):
    list_obj = get_object_or_404(List, id=list_id, board__created_by=request.user)

    if request.method == "POST":
        board_id = list_obj.board.id
        list_obj.delete()
        return redirect("board_detail", board_id=board_id)

    return render(request, "boards/list_confirm_delete.html", {"list": list_obj})

@login_required
def task_create(request, list_id):
    list_obj = get_object_or_404(List, id=list_id, board__created_by=request.user)

    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.list = list_obj
            task.save()
            return redirect("board_detail", board_id=list_obj.board.id)
    else:
        form = TaskForm()

    return render(request, "tasks/task_form.html", {
        "form": form,
        "list": list_obj,
    })


@login_required
def task_update(request, task_id):
    task = get_object_or_404(Task, id=task_id, list__board__created_by=request.user)

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            form.save()
            return redirect("board_detail", board_id=task.list.board.id)
    else:
        form = TaskForm(instance=task)

    return render(request, "tasks/task_form.html", {
        "form": form,
        "list": task.list,
    })


@login_required
def task_delete(request, task_id):
    task = get_object_or_404(Task, id=task_id, list__board__created_by=request.user)
    board_id = task.list.board.id

    if request.method == "POST":
        task.delete()
        return redirect("board_detail", board_id=board_id)

    return render(request, "tasks/task_confirm_delete.html", {
        "task": task,
    })

@require_POST
@login_required
def task_move(request):
    task_id = request.POST.get("task_id")
    list_id = request.POST.get("list_id")

    task = get_object_or_404(Task, id=task_id, list__board__created_by=request.user)
    target_list = get_object_or_404(List, id=list_id, board=task.list.board)

    task.list = target_list
    task.save()

    return JsonResponse({"success": True})

@require_POST
@login_required
def list_reorder(request, board_id):
    board = get_object_or_404(Board, id=board_id, created_by=request.user)
    list_id = request.POST.get("list_id")
    target_id = request.POST.get("target_id")

    if not list_id or not target_id:
        return JsonResponse({"success": False, "error": "missing params"}, status=400)

    lst = get_object_or_404(List, id=list_id, board=board)
    target = get_object_or_404(List, id=target_id, board=board)

    # ดึงลิสต์ทั้งหมดเรียงตาม position
    lists = list(board.lists.order_by("position"))

    # เอาตัวที่ลากออกก่อน
    lists = [l for l in lists if l.id != lst.id]

    # แทรก lst ไว้ก่อน target
    new_order = []
    for l in lists:
        if l.id == target.id:
            new_order.append(lst)
        new_order.append(l)

    # เซฟ position ใหม่เรียงจาก 1...
    for idx, l in enumerate(new_order, start=1):
        if l.position != idx:
            l.position = idx
            l.save(update_fields=["position"])

    return JsonResponse({"success": True})

@require_POST
@login_required
def add_member(request, board_id):
    # เฉพาะเจ้าของบอร์ดเท่านั้นที่มีสิทธิ์เชิญคนเพิ่ม (หรือจะให้สมาชิกเชิญด้วยก็ได้ แล้วแต่ตกลง)
    # ในที่นี้ให้เฉพาะเจ้าของเชิญได้ก่อน
    board = get_object_or_404(Board, id=board_id, created_by=request.user)
    
    username = request.POST.get("username")
    
    try:
        user_to_add = User.objects.get(username=username)
        # ป้องกันการเชิญตัวเอง หรือเชิญคนที่มีอยู่แล้ว
        if user_to_add != request.user and user_to_add not in board.members.all():
            board.members.add(user_to_add)
    except User.DoesNotExist:
        pass # หรือจะส่ง message error กลับไปก็ได้
        
    return redirect("board_detail", board_id=board.id)