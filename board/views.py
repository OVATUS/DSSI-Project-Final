from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Board, List, Task, Comment , Label , BoardInvitation , ChecklistItem, Attachment, Notification
from .forms import BoardForm, ListForm, TaskForm  
from users.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Max
from django.db.models import Q, Prefetch
import json
from django.utils import timezone
from datetime import timedelta

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

    # --- 3. ส่วนงานของฉัน (My Tasks) พร้อม Logic ตัวกรอง ---
    # ดึงงานที่ยังไม่เสร็จทั้งหมด (ไม่จำกัดแค่ 10 อันแล้ว เพราะต้องเอามาทำ Filter)
    all_tasks = Task.objects.filter(
        assigned_to=request.user
    ).exclude(
        status='done'
    ).select_related('list__board').order_by('due_date', '-priority')

    now = timezone.now()
    next_week = now + timedelta(days=7)
    
    # เตรียมข้อมูลสำหรับส่งไปหน้าเว็บ (เพื่อให้ Filter ง่าย)
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
            # เช็คว่าอยู่ในสัปดาห์นี้ไหม (ภายใน 7 วันข้างหน้า)
            elif task.due_date <= next_week:
                is_week = True
                counts['week'] += 1
        
        task_list_data.append({
            'obj': task,          # ตัว Object Task จริงๆ
            'is_overdue': is_overdue,
            'is_week': is_week
        })

    context = {
        'received_invites': received_invites,
        'boards': boards,
        'task_list_data': task_list_data, # ส่งไปแบบ List ที่มี flag
        'counts': counts,                 # ส่งจำนวนนับไปโชว์ที่ปุ่ม
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
    # หมายเหตุ: ตรงนี้คุณล็อคไว้ให้เฉพาะเจ้าของบอร์ดสร้างงานได้ (board__created_by=request.user)
    # ถ้าอยากให้สมาชิกสร้างได้ด้วย ต้องแก้ query ตรงนี้เพิ่มในอนาคตครับ
    list_obj = get_object_or_404(List, id=list_id, board__created_by=request.user)

    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.list = list_obj
            task.save()
            
            label_ids = request.POST.getlist('labels')
            if label_ids:
                task.labels.set(label_ids)
            
            # ✅ [ส่วนที่เพิ่ม] Logic แจ้งเตือนตอนสร้างงาน
            # ถ้ามีการระบุคนรับผิดชอบ และคนนั้นไม่ใช่ตัวเอง
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


@login_required
def task_update(request, task_id):
    # หมายเหตุ: query นี้อนุญาตเฉพาะเจ้าของบอร์ดแก้ไขงาน
    task = get_object_or_404(Task, id=task_id, list__board__created_by=request.user)

    if request.method == "POST":
        # ✅ [ส่วนที่เพิ่ม 1] จำคนรับผิดชอบคนเก่าไว้ก่อน save
        old_assigned_to = task.assigned_to

        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            updated_task = form.save() # บันทึกค่าใหม่

            label_ids = request.POST.getlist('labels')
            updated_task.labels.set(label_ids)

            # ✅ [ส่วนที่เพิ่ม 2] Logic แจ้งเตือนตอนแก้ไข
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
    task = get_object_or_404(Task, id=task_id, list__board__created_by=request.user)
    board_id = task.list.board.id

    if request.method == "POST":
        task.delete()
        return redirect("board_detail", board_id=board_id)

    return render(request, "tasks/task_confirm_delete.html", {
        "task": task,
    })

# board/views.py

@require_POST
@login_required
def task_move(request):
    try:
        # รับ task_id และ list_id เป้าหมาย
        task_id = request.POST.get("task_id")
        list_id = request.POST.get("list_id")
        
        # ✅ รับ list ของ ID ทั้งหมดในคอลัมน์นั้น (เรียงมาแล้วจาก JS)
        # ส่งมาเป็น string เช่น "10,5,8" -> แปลงเป็น list [10, 5, 8]
        order_str = request.POST.get("order", "") 
        
        task = get_object_or_404(Task, id=task_id, list__board__created_by=request.user)
        target_list = get_object_or_404(List, id=list_id, board=task.list.board)

        # 1. ย้าย Task ไปลิสต์ใหม่ (ถ้ามีการเปลี่ยนลิสต์)
        if task.list != target_list:
            task.list = target_list
            task.save()

        # 2. อัปเดต position ของทุก Task ในลิสต์นั้น
        if order_str:
            ordered_ids = [int(id) for id in order_str.split(",") if id]
            
            # ดึง tasks ทั้งหมดในลิสต์เป้าหมายมา
            tasks_in_list = Task.objects.filter(list=target_list, id__in=ordered_ids)
            
            # สร้าง dict เพื่อให้เข้าถึงง่าย {task_id: task_obj}
            task_map = {t.id: t for t in tasks_in_list}
            
            # วนลูปเซฟ position ตามลำดับที่ส่งมา
            for index, t_id in enumerate(ordered_ids, start=1):
                if t_id in task_map:
                    t = task_map[t_id]
                    # เซฟเฉพาะถ้าค่าเปลี่ยน (ลด query)
                    if t.position != index:
                        t.position = index
                        t.save(update_fields=['position'])

        return JsonResponse({"success": True})
        
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@require_POST
@login_required
def toggle_task_archive(request, task_id):
    # ต้องมั่นใจว่า Task นั้นเป็นของบอร์ดที่เราสร้าง/เป็นสมาชิก
    task = get_object_or_404(Task, id=task_id, list__board__members=request.user)
    
    # หรือใช้ logic ตรวจสอบสิทธิ์แบบละเอียดที่คุณมีอยู่
    # if request.user != task.list.board.created_by and request.user not in task.list.board.members.all():
    #      return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    # สลับสถานะ (True เป็น False, False เป็น True)
    task.is_archived = not task.is_archived
    task.save()
    
    return JsonResponse({
        'success': True, 
        'is_archived': task.is_archived,
        'message': 'Task archived successfully' if task.is_archived else 'Task unarchived successfully'
    })

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
    board = get_object_or_404(Board, id=board_id, created_by=request.user)
    username = request.POST.get("username")
    
    try:
        user_to_invite = User.objects.get(username=username)
        
        # เช็คว่าอยู่ในบอร์ดแล้วหรือยัง
        if user_to_invite in board.members.all() or user_to_invite == board.created_by:
            # (อาจจะส่ง message บอกว่าอยู่แล้ว)
            pass
        else:
            # เช็คว่าเคยเชิญไปแล้วและสถานะเป็น Pending ไหม (กันส่งซ้ำ)
            existing_invite = BoardInvitation.objects.filter(
                board=board, 
                recipient=user_to_invite, 
                status='pending'
            ).exists()
            
            if not existing_invite:
                BoardInvitation.objects.create(
                    board=board,
                    sender=request.user,
                    recipient=user_to_invite
                )
    except User.DoesNotExist:
        pass 
        
    return redirect("board_detail", board_id=board.id)

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

# board/views.py
from django.http import JsonResponse # (เช็คดูด้านบนไฟล์ว่ามีหรือยัง)

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


# --- Attachment Views ---
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

@login_required
def get_notifications(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:10] # เอาแค่ 10 อันล่าสุด
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    
    data = [{
        'id': n.id,
        'actor': n.actor.username,
        'actor_avatar': n.actor.profile_image.url if n.actor.profile_image else None,
        'message': n.message,
        'task_id': n.task.id,
        'board_id': n.task.list.board.id,
        'is_read': n.is_read,
        'created_at': n.created_at.strftime('%d/%m %H:%M')
    } for n in notifications]
    
    return JsonResponse({'notifications': data, 'unread_count': unread_count})

@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'success': True})

@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'success': True})

@login_required
def get_archived_tasks(request, board_id):
    # ตรวจสอบว่ามีสิทธิ์ในบอร์ดนี้
    board = get_object_or_404(Board, id=board_id)
    if request.user != board.created_by and request.user not in board.members.all():
         return JsonResponse({'error': 'Unauthorized'}, status=403)

    # ดึงงานที่ is_archived=True ของบอร์ดนี้
    tasks = Task.objects.filter(
        list__board=board, 
        is_archived=True
    ).select_related('list').order_by('-updated_at')

    # แปลงเป็น JSON
    data = [{
        'id': task.id,
        'title': task.title,
        'list_title': task.list.title,
        'archived_at': task.updated_at.strftime('%d/%m/%Y %H:%M')
    } for task in tasks]

    return JsonResponse({'tasks': data})