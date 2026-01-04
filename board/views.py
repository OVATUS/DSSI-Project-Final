from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Board, List, Task, Comment , Label , BoardInvitation , ChecklistItem, Attachment, Notification , ActivityLog
from .forms import BoardForm, ListForm, TaskForm  
from users.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Max
from django.db.models import Q, Prefetch
import json
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
from django.db.models.functions import TruncDate
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from django.conf import settings
import datetime



@login_required
def board_lsit_view(request):
    # --- 1. ส่วนคำเชิญ (Invitations) ---
    received_invites = BoardInvitation.objects.filter(
        recipient=request.user, 
        status='pending'
    ).select_related('sender', 'board')

    # --- 2. ส่วนบอร์ด (Boards) ---
    boards = Board.objects.filter(
        Q(created_by=request.user) | Q(members=request.user)
    ).distinct()

    # --- 3. ส่วนงานของฉัน (My Tasks) ---
    # ✅ แก้ไขตรงนี้: เปลี่ยนจาก exclude(status='done') เป็น filter(is_completed=False)
    all_tasks = Task.objects.filter(
        assigned_to=request.user,
        is_completed=False,  # เอาเฉพาะงานที่ "ยังไม่เสร็จ" (ยังไม่ติ๊กถูก)
        is_archived=False    # เอาเฉพาะงานที่ "ยังไม่ถูกเก็บเข้าคลัง"
    ).select_related('list__board').order_by('due_date', '-priority')

    now = timezone.now()
    next_week = now + timedelta(days=7)
    
    # เตรียมข้อมูลสำหรับส่งไปหน้าเว็บ
    task_list_data = []
    
    # ตัวนับจำนวนงาน (Counters)
    counts = {
        'all': all_tasks.count(),
        'overdue': 0,
        'week': 0
    }

    for task in all_tasks:
        is_overdue = False
        is_week = False

        if task.due_date:
            # เช็คว่าเลยกำหนดไหม
            if task.due_date < now:
                is_overdue = True
                counts['overdue'] += 1
            # เช็คว่าอยู่ในสัปดาห์นี้ไหม
            elif task.due_date <= next_week:
                is_week = True
                counts['week'] += 1
        
        task_list_data.append({
            'obj': task,
            'is_overdue': is_overdue,
            'is_week': is_week
        })

    context = {
        'received_invites': received_invites,
        'boards': boards,
        'task_list_data': task_list_data,
        'counts': counts,
    }
    
    return render(request, 'boards/dashboard.html', context)

@login_required
@require_POST
def toggle_star_board(request, board_id):
    board = get_object_or_404(Board, id=board_id)
    
    # ตรวจสอบสิทธิ์ (ต้องเป็นสมาชิกบอร์ดถึงจะติดดาวได้)
    if request.user not in board.members.all() and board.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.user in board.starred_by.all():
        board.starred_by.remove(request.user)
        is_starred = False
    else:
        board.starred_by.add(request.user)
        is_starred = True

    return JsonResponse({'is_starred': is_starred})

@login_required
def project_page(request):
    # 1. ดึง Query พื้นฐานมาก่อน (คนสร้าง หรือ สมาชิก)
    boards = Board.objects.filter(
        Q(created_by=request.user) | Q(members=request.user)
    ).distinct()

    search_query = request.GET.get('q')  
    if search_query:
        # กรองเฉพาะบอร์ดที่มีชื่อตรงกับคำค้น (icontains = ไม่สนตัวพิมพ์เล็กใหญ่)
        boards = boards.filter(name__icontains=search_query)

    # 3. สั่งเรียงลำดับ (เหมือนเดิม)
    boards = boards.order_by("-created_at")

    starred_boards = boards.filter(starred_by=request.user)
    form = BoardForm()

    return render(request, "boards/project_list.html", {
        "boards": boards,
        "starred_boards": starred_boards,
        "form": form,
        "search_query": search_query, 
    })


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
        Board.objects.filter(
            Q(created_by=request.user) | Q(members=request.user)
        ).distinct(),  # <--- พระเอกของเราอยู่ตรงนี้ครับ
        id=board_id
    )
    # ... (code ส่วนดึง lists, tasks เหมือนเดิม)
    lists = board.lists.all().prefetch_related(
        Prefetch('tasks', queryset=Task.objects.filter(is_archived=False).order_by('position').select_related('assigned_to').prefetch_related('labels'))
        ).order_by('position')

    users = User.objects.filter(
        Q(id=board.created_by.id) | Q(joined_boards=board)
    ).distinct()
    
    priority_choices = Task.Priority.choices

    return render(request, "boards/board_detail.html", {
        "board": board,
        "lists": lists,
        "users": users,
        "priority_choices": priority_choices,
        "labels": board.labels.all(),
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

@login_required
@require_POST
def toggle_task_completion(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Check Permission
    if request.user not in task.list.board.members.all() and request.user != task.list.board.created_by:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # สลับสถานะ True <-> False
    task.is_completed = not task.is_completed
    task.save()

    return JsonResponse({
        'success': True, 
        'is_completed': task.is_completed,
        'completed_at': task.completed_at
    })

# ------------------------------#
# ------------------------------#
#         LIST VIEWS
#-------------------------------#
# ------------------------------#

# LIST CREATE
@login_required
def list_create(request, board_id):
    board = get_object_or_404(
        Board.objects.filter(
            Q(created_by=request.user) | Q(members=request.user)
        ).distinct(),
        id=board_id
    )

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
    lst = get_object_or_404(
        List.objects.filter(
            Q(board__created_by=request.user) | Q(board__members=request.user)
        ).distinct(),
        id=list_id
    )
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
    list_obj = get_object_or_404(
        List.objects.filter(
            Q(board__created_by=request.user) | Q(board__members=request.user)
        ).distinct(),
        id=list_id
    )

    if request.method == "POST":
        board_id = list_obj.board.id
        list_obj.delete()
        return redirect("board_detail", board_id=board_id)

    return render(request, "boards/list_confirm_delete.html", {"list": list_obj})
# แก้ไขเฉพาะส่วน logic ของ view
from django.db.models import Q  # อย่าลืม import Q ด้านบนสุดของไฟล์ด้วยนะครับ

@login_required
def task_create(request, list_id):
    # ✅ แก้ไขตรงนี้: เช็คว่าเป็น Owner (created_by) หรือ Member (members)
    list_obj = get_object_or_404(
        List.objects.filter(
            Q(board__created_by=request.user) | Q(board__members=request.user)
        ).distinct(),
        id=list_id
    )

    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.list = list_obj
            task.save()
            log_activity(list_obj.board, request.user, f"สร้างการ์ด '{task.title}' ในรายการ '{list_obj.title}'")
            label_ids = request.POST.getlist('labels')
            if label_ids:
                task.labels.set(label_ids)
            
            # Logic แจ้งเตือน (เหมือนเดิม)
            if task.assigned_to and task.assigned_to != request.user:
                Notification.objects.create(
                    recipient=task.assigned_to,
                    actor=request.user,
                    task=task,
                    message=f"ได้มอบหมายงานใหม่ '{task.title}' ให้คุณ"
                )

            return redirect("board_detail", board_id=list_obj.board.id)
    else:
        form = TaskForm()

    return render(request, "tasks/task_form.html", {
        "form": form,
        "list": list_obj,
    })

@require_POST
@login_required
def list_reorder(request, board_id):
    board = get_object_or_404(
        Board, 
        Q(id=board_id) & (Q(created_by=request.user) | Q(members=request.user))
    )
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

    
# ------------------------------#
# ------------------------------#
#         TASk VIEWS
#-------------------------------#
# ------------------------------#

@login_required
def task_update(request, task_id):
    # ✅ แก้ไข Query: เช็คว่าเป็น Owner (created_by) หรือ Member (members)
    task = get_object_or_404(
        Task.objects.filter(
            Q(list__board__created_by=request.user) | Q(list__board__members=request.user)
        ).distinct(),
        id=task_id
    )

    if request.method == "POST":
        # จำคนรับผิดชอบคนเก่าไว้ก่อน save
        old_assigned_to = task.assigned_to

        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            updated_task = form.save() # บันทึกค่าใหม่

            label_ids = request.POST.getlist('labels')
            updated_task.labels.set(label_ids)

            # Logic แจ้งเตือนตอนแก้ไข
            new_assigned_to = updated_task.assigned_to

            # เงื่อนไข: มีคนรับผิดชอบ + ไม่ใช่ตัวเอง + และต้องเป็นคนใหม่ (ไม่ซ้ำคนเดิม)
            if new_assigned_to and new_assigned_to != request.user:
                if new_assigned_to != old_assigned_to:
                    Notification.objects.create(
                        recipient=new_assigned_to,
                        actor=request.user,
                        task=updated_task,
                        message=f"ได้มอบหมายงาน '{updated_task.title}' ให้คุณ"
                    )

            return redirect("board_detail", board_id=task.list.board.id)
    else:
        form = TaskForm(instance=task)

    return render(request, "tasks/task_form.html", {
        "form": form,
        "list": task.list,
    })

@login_required
def task_delete(request, task_id):
    # ✅ แก้ไข Query: เช็คว่าเป็น Owner (created_by) หรือ Member (members)
    task = get_object_or_404(
        Task.objects.filter(
            Q(list__board__created_by=request.user) | Q(list__board__members=request.user)
        ).distinct(),
        id=task_id
    )
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
    try:
        # รับ task_id และ list_id เป้าหมาย
        task_id = request.POST.get("task_id")
        list_id = request.POST.get("list_id")
        
        # รับ list ของ ID ทั้งหมดในคอลัมน์นั้น (เรียงมาแล้วจาก JS)
        order_str = request.POST.get("order", "") 
    
        task = get_object_or_404(
            Task.objects.filter(
                Q(list__board__created_by=request.user) | Q(list__board__members=request.user)
            ).distinct(),
            id=task_id
        )
        
        # ตรวจสอบว่าลิสต์เป้าหมายอยู่ในบอร์ดเดียวกัน
        target_list = get_object_or_404(List, id=list_id, board=task.list.board)

        # 1. ย้าย Task ไปลิสต์ใหม่ (ถ้ามีการเปลี่ยนลิสต์)
        if task.list != target_list:
            old_list_title = task.list.title # เก็บชื่อเก่าไว้ทำ Log

            # เปลี่ยนลิสต์ใหม่
            task.list = target_list
            task.save()

            # บันทึก Log
            log_activity(
                target_list.board, 
                request.user, 
                f"ย้ายการ์ด '{task.title}' จาก '{old_list_title}' ไปยัง '{target_list.title}'"
            )

        # 2. อัปเดต position ของทุก Task ในลิสต์นั้น (Reorder)
        if order_str:
            ordered_ids = [int(id) for id in order_str.split(",") if id]
            
            # ดึง tasks ทั้งหมดในลิสต์เป้าหมายมา (เพื่อลด Query ใน Loop)
            tasks_in_list = Task.objects.filter(list=target_list, id__in=ordered_ids)
            
            # สร้าง dict {task_id: task_object} เพื่อให้เข้าถึงข้อมูลเร็วๆ
            task_map = {t.id: t for t in tasks_in_list}
            
            # วนลูปเซฟ position ตามลำดับที่ส่งมา
            for index, t_id in enumerate(ordered_ids, start=1):
                if t_id in task_map:
                    t = task_map[t_id]
                    # เซฟเฉพาะถ้าค่าเปลี่ยนจริง ๆ (ช่วยลดการยิง Database)
                    if t.position != index:
                        t.position = index
                        t.save(update_fields=['position'])

        return JsonResponse({"success": True})
        
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@require_POST
@login_required
def toggle_task_archive(request, task_id):
    # แก้ไขตรงนี้: ใช้ Q เช็คว่า (เป็นสมาชิก OR เป็นคนสร้าง)
    task = get_object_or_404(
        Task, 
        Q(list__board__members=request.user) | Q(list__board__created_by=request.user),
        id=task_id
    )
    
    # ส่วนที่เหลือเหมือนเดิม
    task.is_archived = not task.is_archived
    task.save()
    
    return JsonResponse({
        'success': True, 
        'is_archived': task.is_archived,
        'message': 'Task archived successfully' if task.is_archived else 'Task unarchived successfully'
    })


# =========================== #
#        Label VIEWS          #
# =========================== #

@login_required
@require_POST
def create_label(request, board_id):
    board = get_object_or_404(Board, id=board_id)
    
    # ตรวจสอบสิทธิ์ว่า user เป็นสมาชิกบอร์ดไหม
    if request.user not in board.members.all() and board.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        name = data.get('name')
        color = data.get('color')

        if not name or not color:
             return JsonResponse({'error': 'Missing data'}, status=400)

        # สร้าง Label ใหม่
        label = Label.objects.create(board=board, name=name, color=color)

        return JsonResponse({
            'success': True,
            'id': label.id,
            'name': label.name,
            'color': label.color
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def delete_label(request, label_id):
    label = get_object_or_404(Label, id=label_id)
    board = label.board
    
    # ตรวจสอบสิทธิ์: ต้องเป็นสมาชิก หรือ เจ้าของบอร์ด ถึงจะลบได้
    if request.user not in board.members.all() and board.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        label.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# ------------------------------#
# ------------------------------#
#         Member VIEWS
#-------------------------------#
# ------------------------------#

# board/views.py

@require_POST
@login_required
def add_member(request, board_id):
    board = get_object_or_404(Board, id=board_id, created_by=request.user)
    username = request.POST.get("username")
    
    try:
        user_to_invite = User.objects.get(username=username)
        
        # ... (โค้ดเช็คเงื่อนไขเดิม) ...
        if user_to_invite in board.members.all() or user_to_invite == board.created_by:
            pass
        else:
            existing_invite = BoardInvitation.objects.filter(
                board=board, 
                recipient=user_to_invite, 
                status='pending'
            ).exists()
            
            if not existing_invite:
                # 1. สร้างคำเชิญ (เหมือนเดิม)
                BoardInvitation.objects.create(
                    board=board,
                    sender=request.user,
                    recipient=user_to_invite
                )
                
                # 🟢 2. สร้าง Notification (เพิ่มใหม่ตรงนี้!)
                Notification.objects.create(
                    recipient=user_to_invite,
                    actor=request.user,
                    board=board,  # ระบุบอร์ด
                    message=f"ได้เชิญคุณเข้าร่วมบอร์ด '{board.name}'"
                )

    except User.DoesNotExist:
        pass 
        
    return redirect("board_detail", board_id=board.id)
@login_required
@require_POST
def remove_member(request, board_id, user_id):
    board = get_object_or_404(Board, id=board_id)
    
    # เฉพาะเจ้าของบอร์ดเท่านั้นที่มีสิทธิ์ลบ
    if request.user != board.created_by:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    user_to_remove = get_object_or_404(User, id=user_id)
    board.members.remove(user_to_remove)
    
    return redirect('board_detail', board_id=board.id)

@login_required
def respond_invitation(request, invite_id, action):
    invite = get_object_or_404(BoardInvitation, id=invite_id, recipient=request.user, status='pending')
    
    if action == 'accept':
        invite.status = 'accepted'
        invite.save()
        # เพิ่มเข้าบอร์ดจริงๆ
        invite.board.members.add(request.user)
    elif action == 'decline':
        invite.status = 'declined'
        invite.save()
        
    return redirect('project_page') # หรือหน้า inbox ที่เราจะสร้าง

@login_required
@require_POST
def create_checklist_item(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # ตรวจสอบสิทธิ์ (ถ้าจำเป็น): เช่น user ต้องอยู่ใน board นี้
    
    try:
        data = json.loads(request.body)
        content = data.get('content')
        
        if content:
            item = ChecklistItem.objects.create(task=task, content=content)
            return JsonResponse({
                'success': True,
                'id': item.id,
                'content': item.content,
                'is_completed': item.is_completed
            })
        return JsonResponse({'success': False, 'error': 'No content provided'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



# ------------------------------#
# ------------------------------#
#         Comment VIEWS
#-------------------------------#
# ------------------------------#

@login_required
def get_comments(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Check สิทธิ์: ต้องเป็นเจ้าของบอร์ด หรือ สมาชิกในบอร์ด
    if request.user != task.list.board.created_by and request.user not in task.list.board.members.all():
         return JsonResponse({'error': 'Unauthorized'}, status=403)

    comments = task.comments.select_related('author').order_by('-created_at')
    
    data = []
    for c in comments:
        # ตรวจสอบรูปโปรไฟล์ (ถ้าไม่มีรูป ให้ส่ง null ไป)
        avatar_url = c.author.profile_image.url if c.author.profile_image else None
        
        data.append({
            'id': c.id,
            'author': c.author.username,
            'author_avatar': avatar_url, 
            'content': c.content,
            'created_at': c.created_at.strftime('%d/%m/%Y %H:%M'),
        })
    return JsonResponse({'comments': data})

@require_POST
@login_required
def add_comment(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Check สิทธิ์เหมือนเดิม
    if request.user != task.list.board.created_by and request.user not in task.list.board.members.all():
         return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        content = data.get('content')
        if not content:
            return JsonResponse({'error': 'Empty content'}, status=400)

        # 1. สร้างคอมเมนต์
        comment = Comment.objects.create(task=task, author=request.user, content=content)
        
        # ✅ [ส่วนที่เพิ่ม] Logic แจ้งเตือน Comment
        # แจ้งเตือนเจ้าของงาน (Assignee) ถ้ามีคนมอบหมาย และคนเม้นไม่ใช่เจ้าของงานเอง
        if task.assigned_to and task.assigned_to != request.user:
            Notification.objects.create(
                recipient=task.assigned_to,
                actor=request.user,
                task=task,
                message=f"ได้แสดงความคิดเห็นในงาน '{task.title}': \"{content[:20]}{'...' if len(content)>20 else ''}\""
            )
            # หมายเหตุ: ผมเพิ่มตัดคำ (slice) ให้โชว์เนื้อหาคอมเมนต์สั้นๆ ในแจ้งเตือนด้วย จะได้ดูรู้เรื่องขึ้นครับ

        # 2. เตรียมข้อมูลส่งกลับ
        avatar_url = comment.author.profile_image.url if comment.author.profile_image else None

        return JsonResponse({
            'id': comment.id,
            'author': comment.author.username,
            'author_avatar': avatar_url,
            'content': comment.content,
            'created_at': comment.created_at.strftime('%d/%m/%Y %H:%M'),
        })
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

@login_required
@require_POST
def update_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    
    # เช็คว่าเป็นคนเขียนคอมเมนต์หรือไม่
    if request.user != comment.author:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    try:
        data = json.loads(request.body)
        new_content = data.get('content', '').strip()
        if new_content:
            comment.content = new_content
            comment.save()
            return JsonResponse({'success': True, 'content': comment.content})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Empty content'}, status=400)

@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    
    # เช็คว่าเป็นคนเขียนคอมเมนต์หรือไม่
    if request.user != comment.author:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    comment.delete()
    return JsonResponse({'success': True})


# ------------------------------#
# ------------------------------#
#         seearch VIEWS
#-------------------------------#
# ------------------------------#


@login_required
def search_boards_api(request):
    query = request.GET.get('q', '').strip()
    
    if len(query) < 1:
        return JsonResponse({'results': []})

    # ค้นหาบอร์ดที่เรามีสิทธิ์เห็น (เป็นเจ้าของ หรือ เป็นสมาชิก)
    boards = Board.objects.filter(
        Q(created_by=request.user) | Q(members=request.user),
        name__icontains=query
    ).distinct().order_by('-updated_at')[:5]  # จำกัดแค่ 5 อันดับล่าสุด

    results = []
    for b in boards:
        results.append({
            'id': b.id,
            'name': b.name,
            # ส่ง URL รูปปกไปด้วย (ถ้ามี) เพื่อความสวยงาม
            'cover': b.cover_image.url if b.cover_image else None 
        })

    return JsonResponse({'results': results})


@login_required
@require_POST
def update_checklist_item_status(request, item_id):
    item = get_object_or_404(ChecklistItem, id=item_id)
    
    try:
        data = json.loads(request.body)
        is_completed = data.get('is_completed', False)
        
        item.is_completed = is_completed
        item.save()
        
        return JsonResponse({'success': True, 'is_completed': item.is_completed})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_POST
def delete_checklist_item(request, item_id):
    item = get_object_or_404(ChecklistItem, id=item_id)
    item.delete()
    return JsonResponse({'success': True})

# ------------------------------#
# ------------------------------#
#         Attachment VIEWS
#-------------------------------#
# ------------------------------#

@login_required
@require_POST
def create_attachment(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # รับไฟล์จาก request.FILES
    if 'file' in request.FILES:
        file = request.FILES['file']
        attachment = Attachment.objects.create(task=task, file=file)
        
        return JsonResponse({
            'success': True,
            'id': attachment.id,
            'filename': attachment.filename(),
            'url': attachment.file.url,
            'is_image': attachment.is_image(),
            'uploaded_at': attachment.uploaded_at.strftime('%d/%m/%Y %H:%M')
        })
        
    return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

@login_required
@require_POST
def delete_attachment(request, attachment_id):
    attachment = get_object_or_404(Attachment, id=attachment_id)
    attachment.delete()
    # หมายเหตุ: ปกติ Django จะลบ record ใน DB แต่ไฟล์จริงอาจจะยังอยู่
    # ถ้าอยากให้ลบไฟล์จริงด้วย ต้องใช้ signal หรือ library เสริม (แต่เบื้องต้นแค่นี้ก่อนได้ครับ)
    return JsonResponse({'success': True})

# ------------------------------#
# ------------------------------#
#         notifications VIEWS
#-------------------------------#
# ------------------------------#

@login_required
def get_notifications(request):
    """ดึงรายการแจ้งเตือนล่าสุด 10 รายการ"""
    notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:10]
    
    data = []
    for n in notifs:
        # 1. จัดการรูปโปรไฟล์
        avatar_url = None
        if n.actor and hasattr(n.actor, 'profile_image') and n.actor.profile_image:
            avatar_url = n.actor.profile_image.url

        # 2. หา Board ID จาก Task (เพราะ Notification ผูกกับ Task)
        # Model ของคุณคือ Notification -> Task -> List -> Board
        board_id = None
        if n.task and n.task.list and n.task.list.board:
            board_id = n.task.list.board.id

        data.append({
            'id': n.id,
            'actor': n.actor.username if n.actor else 'ระบบ',
            'actor_avatar': avatar_url,
            'message': n.message,  # ✅ แก้จาก n.verb เป็น n.message
            'created_at': n.created_at.strftime('%d/%m %H:%M'),
            'is_read': n.is_read,
            'board_id': board_id,  # ✅ ดึง ID จาก Task แทน target_board
        })
    
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    
    return JsonResponse({
        'notifications': data,
        'unread_count': unread_count
    })

@login_required
def read_notification(request, pk):
    """กดอ่านแจ้งเตือนรายตัว"""
    if request.method == "POST":
        notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notif.is_read = True
        notif.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)

@login_required
def mark_all_read(request):
    """กด 'อ่านทั้งหมด'"""
    if request.method == "POST":
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)
@login_required
def get_archived_tasks(request, board_id):
    # 1. แก้ไขการหา Board: ให้เจอทั้ง "คนสร้าง" และ "สมาชิก"
    board = get_object_or_404(
        Board, 
        Q(members=request.user) | Q(created_by=request.user),
        id=board_id
    )

    # 2. ดึงงานที่ is_archived=True
    tasks = Task.objects.filter(
        list__board=board, 
        is_archived=True
    ).select_related('list').order_by('-created_at')

    # 3. ส่งข้อมูลกลับ
    data = [{
        'id': task.id,
        'title': task.title,
        'list_title': task.list.title,
        'archived_at': task.created_at.strftime('%d/%m/%Y %H:%M')
    } for task in tasks]

    return JsonResponse({'tasks': data})

# ==============================#
# ======= ประวัติกิจกรรม ==========#
# ==============================#

def log_activity(board, user, action_text):
    ActivityLog.objects.create(board=board, actor=user, action=action_text)

# API ดึงประวัติกิจกรรม (สำหรับ JavaScript)
@login_required
def get_board_activities(request, board_id):
    board = get_object_or_404(Board, pk=board_id)
    
    # ดึง 50 รายการล่าสุด
    activities = board.activities.select_related('actor').order_by('-created_at')[:50]
    
    data = [{
        'actor': act.actor.username,
        'actor_initial': act.actor.username[0].upper(), # ตัวอักษรแรกของชื่อ
        'action': act.action,
        'created_at': act.created_at.strftime('%d/%m/%Y %H:%M')
    } for act in activities]
    
    return JsonResponse({'activities': data})

# ==========================================
# ======= Google Calendar Authentication ===
# ==========================================


@login_required
def google_calendar_callback(request):
    state = request.session.get('google_oauth_state')
    
    try:
        flow = Flow.from_client_secrets_file(
            settings.GOOGLE_OAUTH_CLIENT_SECRETS_FILE,
            scopes=settings.GOOGLE_CALENDAR_SCOPES,
            state=state,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )
        
        # แปลง Code ที่ Google ส่งมา ให้กลายเป็น Token
        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials
        
        # เก็บ Token ลง Session (เพื่อให้ใช้งานต่อได้)
        # หมายเหตุ: ใน Production จริงๆ ควรเก็บลง Database ผูกกับ User
        request.session['google_credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        return redirect('global_calendar') # เด้งกลับไปหน้าปฏิทิน
        
    except Exception as e:
        print(f"Google Auth Error: {e}")
        return redirect('global_calendar') # ถ้า error ก็กลับไปหน้าเดิม

@login_required
def global_calendar_view(request):
    # ดึงรายชื่อบอร์ดทั้งหมดที่ user เป็นสมาชิก หรือ เป็นคนสร้าง (เพื่อเอาไปใส่ Dropdown)
    boards = Board.objects.filter(
        Q(created_by=request.user) | Q(members=request.user)
    ).distinct()
    
    return render(request, 'boards/calendar_main.html', {
        'boards': boards
    })

@login_required
def api_calendar_events(request):
    # ส่วนที่ 1: ดึงงานจาก Board (Local Database)
    board_id = request.GET.get('board_id')
    
    tasks = Task.objects.filter(
        due_date__isnull=False,
        is_archived=False
    )

    user_boards = Board.objects.filter(Q(created_by=request.user) | Q(members=request.user))
    tasks = tasks.filter(list__board__in=user_boards)

    if board_id and board_id != 'all':
        tasks = tasks.filter(list__board_id=board_id)

    events = []
    
    for task in tasks:
        color = '#3B82F6' 
        if task.priority == 'high': color = '#EF4444'
        elif task.priority == 'low': color = '#10B981'
            
        events.append({
            'title': f"[{task.list.board.name}] {task.title}",
            'start': task.due_date.isoformat(),
            'url': f"/board/{task.list.board.id}/?task_id={task.id}",
            'backgroundColor': color,
            'borderColor': color,
            'textColor': '#ffffff',
            'allDay': False
        })

    # ส่วนที่ 2: ดึงงานจาก Google Calendar (API)
    if 'google_credentials' in request.session:
        try:
            creds_data = request.session['google_credentials']
            creds = Credentials(**creds_data)
            service = build('calendar', 'v3', credentials=creds)
            
            # กำหนดเวลาย้อนหลัง 1 ปี (เพื่อให้เห็นงานเก่าใน Classroom ด้วย)
            start_time = (datetime.datetime.utcnow() - datetime.timedelta(days=365)).isoformat() + 'Z'
            
            # ดึงรายชื่อปฏิทินทั้งหมด
            calendar_list_result = service.calendarList().list(showHidden=True).execute()
            calendars = calendar_list_result.get('items', [])
            
            for calendar_entry in calendars:
                cal_id = calendar_entry['id']
                cal_summary = calendar_entry.get('summary', 'Unknown')
                
                # Filter: ข้ามปฏิทินที่ไม่จำเป็น
                if 'holiday' in cal_id or 'addressbook' in cal_id or 'th.thai' in cal_id:
                    continue

                try:
                    events_result = service.events().list(
                        calendarId=cal_id,
                        timeMin=start_time,  # ดึงย้อนหลัง 1 ปี
                        maxResults=50,       # เพิ่มจำนวนต่อวิชาเผื่อมีงานเยอะ
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    
                    google_events = events_result.get('items', [])
                    
                    for event in google_events:
                        # ดึงวันที่ (รองรับทั้งแบบระบุเวลา และแบบทั้งวัน)
                        start = event['start'].get('dateTime', event['start'].get('date'))
                        event_title = event.get('summary', 'No Title')
                        is_all_day = 'date' in event['start']
                        
                        events.append({
                            'title': f"[{cal_summary}] {event_title}", 
                            'start': start,
                            'url': event.get('htmlLink'),
                            'backgroundColor': '#F59E0B',
                            'borderColor': '#F59E0B',
                            'textColor': '#ffffff',
                            'allDay': is_all_day
                        })
                        
                except Exception:
                    continue
                
        except Exception:
            # กรณี Session หมดอายุ หรือ Error อื่นๆ ให้ข้ามไปเงียบๆ
            pass

    return JsonResponse(events, safe=False)

@login_required
def google_calendar_init(request):
    # 1. สร้าง Flow สำหรับขอสิทธิ์
    flow = Flow.from_client_secrets_file(
        settings.GOOGLE_OAUTH_CLIENT_SECRETS_FILE,
        scopes=settings.GOOGLE_CALENDAR_SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )
    
    # 2. สร้าง URL สำหรับ Login
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    # 3. เก็บ state ไว้เช็คความปลอดภัยตอนขากลับ
    request.session['google_oauth_state'] = state
    
    return redirect(authorization_url)

# =============================#
# ======= Reporting Views =======#
# =============================#

@login_required
def reporting_view(request):
    # ... (ส่วน Filter บอร์ด เหมือนเดิมเป๊ะ) ...
    user_boards = Board.objects.filter(Q(created_by=request.user) | Q(members=request.user)).distinct()
    tasks = Task.objects.filter(list__board__in=user_boards, is_archived=False)

    selected_board_id = request.GET.get('board_id')
    if selected_board_id and selected_board_id != 'all':
        tasks = tasks.filter(list__board_id=selected_board_id)
        current_board_name = user_boards.filter(id=selected_board_id).first().name
    else:
        current_board_name = "ทุกโปรเจกต์"

    # --- ส่วนที่แก้: เตรียม QuerySet สำหรับ List แต่ละประเภท ---
    
    # 1. งานทั้งหมด
    all_tasks_qs = tasks.select_related('list__board', 'assigned_to').order_by('-created_at')
    
    # 2. งานที่เสร็จแล้ว
    completed_tasks_qs = tasks.filter(is_completed=True).select_related('list__board', 'assigned_to').order_by('-completed_at')
    
    # 3. งานล่าช้า
    overdue_tasks_qs = tasks.filter(due_date__lt=timezone.now(), is_completed=False).select_related('list__board', 'assigned_to').order_by('due_date')

    # ตัวเลข KPI
    total_tasks = tasks.count()
    completed_tasks = completed_tasks_qs.count()
    completion_rate = round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0
    overdue_tasks = overdue_tasks_qs.count()

    # ... (ส่วน Priority Data และ Trend Data เหมือนเดิม) ...
    # Chart 1: Priority
    priority_data = {
        'high': tasks.filter(priority='high', is_completed=False).count(),
        'medium': tasks.filter(priority='medium', is_completed=False).count(),
        'low': tasks.filter(priority='low', is_completed=False).count(),
    }

    # Chart 2: Trend
    last_7_days = timezone.now() - timedelta(days=7)
    completed_trend = (
        tasks.filter(is_completed=True, completed_at__gte=last_7_days)
        .annotate(date=TruncDate('completed_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    trend_labels = [item['date'].strftime('%d/%m') for item in completed_trend]
    trend_data = [item['count'] for item in completed_trend]

    context = {
        'boards': user_boards,
        'selected_board_id': selected_board_id,
        'current_board_name': current_board_name,
        
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'completion_rate': completion_rate,
        'overdue_tasks': overdue_tasks,
        
        # ✅ ส่ง QuerySet ไปด้วย เพื่อเอาไปแสดงใน Modal
        'all_tasks_qs': all_tasks_qs,
        'completed_tasks_qs': completed_tasks_qs,
        'overdue_tasks_qs': overdue_tasks_qs,

        'priority_data': priority_data,
        'trend_labels': trend_labels,
        'trend_data': trend_data,
    }

    return render(request, 'boards/reporting.html', context)

