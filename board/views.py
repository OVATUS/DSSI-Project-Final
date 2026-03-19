from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Board, List, Task, Comment , Label , BoardInvitation , ChecklistItem, Attachment, Notification , ActivityLog , ClassSchedule
from .forms import BoardForm, ListForm, TaskForm , ClassScheduleForm 
from users.models import User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Max
from django.db.models import Q, Prefetch
import json
from django.utils import timezone
from django.utils.timezone import localtime
from datetime import timedelta 
from django.db.models import Count
from django.db.models.functions import TruncDate
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from django.conf import settings
import datetime
import requests
from django.core.mail import send_mail
import threading
from django.core.cache import cache
from django.contrib import messages
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils.dateparse import parse_datetime, parse_date

# ==========================================
# 1. Main Dashboard & Project Views
# ==========================================

@login_required
def board_lsit_view(request):
    manual_schedules = ClassSchedule.objects.filter(user=request.user)
    
    # =================================================
    # 1. ส่วนคำเชิญ (Invitations)
    # =================================================
    received_invites = BoardInvitation.objects.filter(
        recipient=request.user, 
        status='pending'
    ).select_related('sender', 'board')

    # =================================================
    # 2. ส่วนบอร์ด (Boards)
    # =================================================
    boards = Board.objects.filter(
        Q(created_by=request.user) | Q(members=request.user)
    ).distinct()

    # =================================================
    # 3. ส่วนงานของฉัน (My Tasks)
    # =================================================
    all_tasks = Task.objects.filter(
        assigned_to=request.user,
        is_completed=False,
        is_archived=False
    ).select_related('list__board').order_by('due_date', '-priority')

    now = timezone.now()
    next_week = now + timedelta(days=7)
    
    task_list_data = []
    counts = {'all': all_tasks.count(), 'overdue': 0, 'week': 0}

    for task in all_tasks:
        is_overdue = False
        is_week = False
        if task.due_date:
            if task.due_date < now:
                is_overdue = True
                counts['overdue'] += 1
            elif task.due_date <= next_week:
                is_week = True
                counts['week'] += 1
        
        task_list_data.append({
            'obj': task,
            'is_overdue': is_overdue,
            'is_week': is_week
        })

    # =================================================
    # 4. ส่วน Google Calendar  - UPDATED
    # =================================================
    google_events = []
    google_course_names = []
    
    if 'google_credentials' in request.session:
        # ตั้งชื่อ Key สำหรับจำข้อมูล (แยกตาม User ID)
        cache_key_events = f"google_events_{request.user.id}"
        cache_key_courses = f"google_courses_{request.user.id}"
        
        # 1. ลองถาม Cache ดูก่อนว่ามีข้อมูลไหม?
        cached_events = cache.get(cache_key_events)
        cached_courses = cache.get(cache_key_courses)

        if cached_events is not None and cached_courses is not None:
            #  เจอ! ใช้ข้อมูลเก่าเลย (เร็วมาก ไม่ต้องรอโหลด)
            google_events = cached_events
            google_course_names = cached_courses
        else:
            #  ไม่เจอ (หรือหมดอายุ) ให้วิ่งไปถาม Google (ยอมช้าหน่อย)
            try:
                creds_data = request.session['google_credentials']
                creds = Credentials(**creds_data)
                service = build('calendar', 'v3', credentials=creds)
                
                now_iso = datetime.datetime.utcnow().isoformat() + 'Z'
                
                # 1. ดึงรายชื่อปฏิทิน
                calendar_list = service.calendarList().list().execute().get('items', [])
                
                all_events = []
                temp_course_names = [] # ใช้ตัวแปรชั่วคราว
                
                # 2. วนลูปดึง Event
                for calendar_entry in calendar_list:
                    cal_name = calendar_entry.get('summary', '')

                    keywords = ['holiday', 'วันหยุด', 'birthday', 'วันเกิด']
                    if any(k in cal_name.lower() for k in keywords):
                        continue

                    if cal_name not in temp_course_names and '@' not in cal_name:
                        temp_course_names.append(cal_name)

                    try:
                        events_result = service.events().list(
                            calendarId=calendar_entry['id'], 
                            timeMin=now_iso,
                            maxResults=5, 
                            singleEvents=True,
                            orderBy='startTime'
                        ).execute()
                        
                        items = events_result.get('items', [])
                        for event in items:
                            event['calendar_name'] = cal_name
                            all_events.append(event)
                            
                    except Exception:
                        continue # ข้ามปฏิทินที่มีปัญหา

                # 3. จัดเรียงข้อมูล
                def get_start_time(e):
                    return e['start'].get('dateTime', e['start'].get('date'))
                
                all_events.sort(key=get_start_time)
                all_events = all_events[:15]

                # 4. แปลงข้อมูล
                final_events = []
                for event in all_events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    try:
                        if isinstance(start, str):
                            if 'T' in start:
                                 start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                            else:
                                 start_dt = datetime.datetime.strptime(start, "%Y-%m-%d")
                        else:
                            start_dt = start
                    except ValueError:
                        start_dt = start

                    final_events.append({
                        'title': event.get('summary', '(ไม่มีชื่อ)'),
                        'start': start_dt,
                        'link': event.get('htmlLink', '#'),
                        'source': event.get('calendar_name', 'Google Calendar')
                    })
                
                # อัปเดตตัวแปรหลัก
                google_events = final_events
                google_course_names = temp_course_names

                # 5. บันทึกลง Cache (จำไว้ 15 นาที = 900 วินาที) 
                cache.set(cache_key_events, google_events, 900)
                cache.set(cache_key_courses, google_course_names, 900)
                
            except Exception as e:
                print(f"Google API Error: {e}")

    # =================================================
    # 5. ส่วนตารางเรียน (Schedule Calculation Logic) 
    # =================================================
    raw_schedules = ClassSchedule.objects.filter(user=request.user)
    my_schedules = []
    
    # ตั้งค่าขอบเขตเวลาของตาราง (08:30 - 17:30)
    START_BASE_MIN = 510   # 08:30 (8*60 + 30)
    END_BASE_MIN = 1050    # 17:30 (17*60 + 30)
    TOTAL_RANGE_MIN = 540  # 9 ชั่วโมง (540 นาที)

    for sched in raw_schedules:
        start_h = sched.start_time.hour
        start_m = sched.start_time.minute
        start_total = (start_h * 60) + start_m

        end_h = sched.end_time.hour
        end_m = sched.end_time.minute
        end_total = (end_h * 60) + end_m

        # 1. คำนวณจุดเริ่ม (Left %)
        # ถ้าเริ่มก่อน 08:30 ให้ปัดเป็น 08:30 (เพื่อให้ Left เป็น 0%)
        effective_start = max(start_total, START_BASE_MIN)
        
        # ถ้าเริ่มหลัง 17:30 (อยู่นอกตาราง) ให้ข้าม หรือปัดเป็น 100%
        if effective_start >= END_BASE_MIN:
             continue 

        left_percent = ((effective_start - START_BASE_MIN) / TOTAL_RANGE_MIN) * 100
        sched.style_left = max(0, min(100, left_percent))

        # 2. คำนวณความกว้าง (Width %)  แก้ตรงนี้
       
        effective_end = min(end_total, END_BASE_MIN)
        
        # ความกว้าง = (เวลาจบที่ปรับแล้ว - เวลาเริ่มที่ปรับแล้ว)
        visible_duration = effective_end - effective_start
        
        # ป้องกันค่าติดลบกรณีข้อมูลผิดพลาด
        visible_duration = max(0, visible_duration)

        width_percent = (visible_duration / TOTAL_RANGE_MIN) * 100
        sched.style_width = width_percent # ไม่ต้อง max(0) ซ้ำเพราะจัดการ visible_duration แล้ว
        
        my_schedules.append(sched)

    days_list = [
        ('Mon', 'จ.'), ('Tue', 'อ.'), ('Wed', 'พ.'), 
        ('Thu', 'พฤ.'), ('Fri', 'ศ.'), ('Sat', 'ส.'), ('Sun', 'อา.')
    ]

    context = {
        'received_invites': received_invites,
        'boards': boards,
        'task_list_data': task_list_data,
        'counts': counts,
        'google_events': google_events,
        'google_course_names': google_course_names, 
        'manual_schedules': manual_schedules, 
        'schedule_form': ClassScheduleForm(),
        'my_schedules': my_schedules, 
        'days_list': days_list        
    }
    
    return render(request, 'boards/dashboard.html', context)

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


# ==========================================
# 2. Board CRUD Operations
# ==========================================

@login_required
def board_create(request):
    if request.method == "POST":
        form = BoardForm(request.POST, request.FILES)
        if form.is_valid():
            board = form.save(commit=False)
            board.created_by = request.user
            board.save()
            
            if not board.lists.exists():
                List.objects.create(board=board, title="TO DO",  position=1)
                List.objects.create(board=board, title="Doing", position=2)
                List.objects.create(board=board, title="Done",  position=3)

            return redirect("board_detail", board_id=board.id)
    else:
        form = BoardForm()

    return render(request, "boards/board_form.html", {"form": form})

@login_required
def board_list(request):
    boards = Board.objects.filter(created_by=request.user)
    return render(request, "boards/board_list.html", {"boards": boards})

@login_required
def board_detail(request, board_id):
    board = get_object_or_404(
        Board.objects.filter(
            Q(created_by=request.user) | Q(members=request.user)
        ).distinct(),  
        id=board_id
    )
    
    lists = List.objects.filter(board=board).order_by('position').prefetch_related(
        Prefetch(
            'tasks',
            queryset=Task.objects.filter(is_archived=False).prefetch_related('assigned_to', 'labels').select_related('list').order_by('position')
        )
    )

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
def toggle_star_board(request, board_id):
    board = get_object_or_404(Board, id=board_id)

    is_owner = (board.created_by == request.user)
    is_member = board.members.filter(id=request.user.id).all() 

    if is_owner or is_member:
        if request.user in board.starred_by.all():
            board.starred_by.remove(request.user)
            is_starred = False
        else:
            board.starred_by.add(request.user)
            is_starred = True
            
        return JsonResponse({'is_starred': is_starred})

    return JsonResponse({'error': 'Permission denied'}, status=403)

@login_required
@require_POST
def leave_board(request, board_id):
    board = get_object_or_404(Board, id=board_id)
    user = request.user
    # ป้องกันเจ้าของบอร์ดกดออก (Backend Validation)
    if user == board.created_by:
        return redirect('board_detail', board_id=board.id)

    if user in board.members.all():
        board.members.remove(user)

        log_activity(board, user, f"ได้ออกจากบอร์ด '{board.name}'")
        
    return redirect('project_page') # ออกเสร็จเด้งกลับหน้าแรก


# ==========================================
# 3. List Management
# ==========================================

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


# ==========================================
# 4. Task Management
# ==========================================

@login_required
def task_create(request, list_id):
    # 1. ดึง List และเช็คสิทธิ์
    list_obj = get_object_or_404(
        List.objects.filter(
            Q(board__created_by=request.user) | Q(board__members=request.user)
        ).distinct(),
        id=list_id
    )

    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            # 2. บันทึก Task เบื้องต้น
            task = form.save(commit=False)
            task.created_by = request.user
            task.list = list_obj
            task.save() 
            
            # 3. จัดการ Labels
            label_ids = request.POST.getlist('labels')
            if label_ids:
                task.labels.set(label_ids)

            # 4. จัดการ Assignees
            assignee_ids = request.POST.getlist('assigned_to')
            if assignee_ids:
                users_to_assign = User.objects.filter(id__in=assignee_ids)
                task.assigned_to.set(users_to_assign)

            # บันทึก Log
            log_activity(list_obj.board, request.user, f"สร้างการ์ด '{task.title}' ในรายการ '{list_obj.title}'")
            

            # ==================================================
            # 5. แจ้งเตือน Notification (Real-time) & Email
            # ==================================================
            assigned_users = task.assigned_to.all()
            for user in assigned_users:
                if user != request.user:
                    # A. สร้าง Notification ลง Database
                    Notification.objects.create(
                        recipient=user,
                        actor=request.user,
                        task=task,
                        message=f"ได้มอบหมายงานใหม่ '{task.title}' ให้คุณ"
                    )

                    # B. ✅ ส่งสัญญาณ Real-time เข้าห้องส่วนตัวของ User
                    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"user_{user.id}",  # ส่งหา user คนนี้โดยเฉพาะ
                        {
                            "type": "send_notification",
                            "message": f"งานเข้า! '{task.title}'",
                            "unread_count": unread_count
                        }
                    )

                    # C. ส่ง Email (แยก Thread)
                    try:
                        threading.Thread(
                            target=send_email_notify, 
                            args=(task, user)
                        ).start()
                    except Exception as e:
                        print(f"Email Thread Error: {e}")

            # ==================================================
            # 6. แจ้งเตือน DISCORD
            # ==================================================
            webhook_url = list_obj.board.discord_webhook_url 

            if webhook_url:
                try:
                    if assigned_users:
                        names = []
                        for u in assigned_users:
                            names.append(u.username)
                        assignee_names = ", ".join(names) # เอามาต่อกันคั่นด้วยลูกน้ำ
                    else:
                        # ถ้าไม่มีคน ให้บอกว่า Unassigned
                        assignee_names = "Unassigned"
                    
                    discord_msg = (
                        f"🆕 **New Task Created!**\n"
                        f"**Task:** {task.title}\n"
                        f"**Board:** {list_obj.board.name}\n"
                        f"**Assignees:** {assignee_names}\n"
                        f"**By:** {request.user.username}"
                    )
                    
                    threading.Thread(
                        target=send_discord_notify, 
                        args=(discord_msg, webhook_url)
                    ).start()
                
                except Exception as e:
                    print(f"Discord Notify Error: {e}")

            return redirect("board_detail", board_id=list_obj.board.id)
    else:
        form = TaskForm()

    return render(request, "tasks/task_form.html", {
        "form": form,
        "list": list_obj,
    })

@login_required
def task_update(request, task_id):
    task = get_object_or_404(
        Task.objects.filter(
            Q(list__board__created_by=request.user) | Q(list__board__members=request.user)
        ).distinct(),
        id=task_id
    )

    # จำค่าเดิมไว้เปรียบเทียบ
    old_assignee_ids = set(task.assigned_to.values_list('id', flat=True))
    old_due_date = task.due_date
    old_remind_days = task.remind_days # ✅ เพิ่ม: จำค่าวันเตือนเดิม

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            updated_task = form.save(commit=False)
            
            # ✅ เช็ค: ถ้ามีการเปลี่ยน "วันกำหนดส่ง" หรือ "วันแจ้งเตือน" ให้ Reset สถานะการเตือน
            if updated_task.due_date != old_due_date or updated_task.remind_days != old_remind_days:
                updated_task.is_reminded = False
            
            updated_task.save()
            form.save_m2m() # บันทึก Many-to-Many

            # -----------------------------------------------
            # A. จัดการ Assignees ใหม่ 
            # -----------------------------------------------
            label_ids = request.POST.getlist('labels')
            if label_ids:
                 updated_task.labels.set(label_ids)

            new_assignee_ids = request.POST.getlist('assigned_to')
            new_assignee_ids_set = set(map(int, new_assignee_ids)) if new_assignee_ids else set()
            
            users_to_assign = User.objects.filter(id__in=new_assignee_ids_set)
            updated_task.assigned_to.set(users_to_assign)

            # หาคนที่ "เพิ่งถูกเพิ่ม" (New - Old)
            added_ids = new_assignee_ids_set - old_assignee_ids
            added_users = User.objects.filter(id__in=added_ids)

            channel_layer = get_channel_layer()
            import threading

            # -----------------------------------------------
            # ✅ B. แจ้งเตือนคนใหม่ (Real-time) 
            # -----------------------------------------------
            for user in added_users:
                if user != request.user:
                    # 1. ลง DB
                    Notification.objects.create(
                        recipient=user,
                        actor=request.user,
                        task=updated_task,
                        message=f"ได้มอบหมายงาน '{updated_task.title}' ให้คุณ"
                    )
                    
                    # 2. ส่ง Real-time (ต้องอยู่ใน Loop เพื่อส่งหาทีละคน)
                    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
                    async_to_sync(channel_layer.group_send)(
                        f"user_{user.id}",
                        {
                            "type": "send_notification",
                            "message": f"งานเข้าใหม่! '{updated_task.title}'",
                            "unread_count": unread_count
                        }
                    )

            # -----------------------------------------------
            # ✅ C. แจ้งเตือนเมื่อเปลี่ยน Due Date (Real-time)
            # -----------------------------------------------
            if old_due_date != updated_task.due_date:
                if updated_task.due_date:
                    if isinstance(updated_task.due_date, datetime.datetime):
                        date_msg = localtime(updated_task.due_date).strftime('%d/%m/%Y')
                    else:
                        date_msg = updated_task.due_date.strftime('%d/%m/%Y')
                else:
                    date_msg = "ไม่มีกำหนด"
                
                # แจ้งทุกคนที่รับผิดชอบงาน
                for user in updated_task.assigned_to.all():
                    if user != request.user:
                        # ลง DB
                        Notification.objects.create(
                            recipient=user,
                            actor=request.user,
                            task=updated_task,
                            message=f"ได้เปลี่ยนกำหนดส่งงาน '{updated_task.title}' เป็น {date_msg}"
                        )
                        # ส่ง Real-time
                        unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
                        async_to_sync(channel_layer.group_send)(
                            f"user_{user.id}",
                            {
                                "type": "send_notification",
                                "message": f" เลื่อนกำหนดส่งงาน '{updated_task.title}'",
                                "unread_count": unread_count
                            }
                        )

            # -----------------------------------------------
            # D. แจ้งเตือน DISCORD
            # -----------------------------------------------
            webhook_url = task.list.board.discord_webhook_url
            if webhook_url and (old_assignee_ids != new_assignee_ids_set):
                current_assignees = updated_task.assigned_to.all()
                assignee_names = ", ".join([u.username for u in current_assignees]) if current_assignees else "Unassigned"
                
                msg = (
                    f"🔄 **Task Updated (Assignees Changed)**\n"
                    f"**Task:** {updated_task.title}\n"
                    f"**New Team:** {assignee_names}\n"
                    f"**By:** {request.user.username}"
                )
                threading.Thread(target=send_discord_notify, args=(msg, webhook_url)).start()

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
    
        # ค้นหา Task (เช็คสิทธิ์ Owner หรือ Member)
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
            old_list_title = task.list.title 

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

@login_required
@require_POST
def toggle_task_completion(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Check Permission
    if request.user not in task.list.board.members.all() and request.user != task.list.board.created_by:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

    # สลับสถานะ
    task.is_completed = not task.is_completed
    task.save()


    # -----------------------------------------------
    # ✅ 1. แจ้งเตือน Notification & Real-time (เฉพาะตอนเสร็จ)
    # -----------------------------------------------
    if task.is_completed:
        # เตรียมรายชื่อคนที่จะแจ้งเตือน (คนสร้าง + คนรับผิดชอบทุกคน ยกเว้นตัวเอง)
        target_users = set()
        if task.created_by and task.created_by != request.user:
            target_users.add(task.created_by)
        
        for assignee in task.assigned_to.all():
            if assignee != request.user:
                target_users.add(assignee)

        channel_layer = get_channel_layer()
        for user in target_users:
            # A. ลง Database
            Notification.objects.create(
                recipient=user,
                actor=request.user,
                task=task,
                message=f"ได้ทำงาน '{task.title}' เสร็จเรียบร้อยแล้ว! 🎉"
            )

            # B. ส่ง Real-time
            unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
            async_to_sync(channel_layer.group_send)(
                f"user_{user.id}",
                {
                    "type": "send_notification",
                    "message": f"งานเสร็จแล้ว! '{task.title}'",
                    "unread_count": unread_count
                }
            )

    # -----------------------------------------------
    # ✅ 2. แจ้งเตือน DISCORD
    # -----------------------------------------------
    webhook_url = task.list.board.discord_webhook_url
    if webhook_url and task.is_completed:
        msg = (
            f"✅ **Task Completed!** 🎉\n"
            f"**Task:** {task.title}\n"
            f"**List:** {task.list.title}\n"
            f"**Completed By:** {request.user.username}"
        )
        threading.Thread(target=send_discord_notify, args=(msg, webhook_url)).start()

    return JsonResponse({
        'success': True, 
        'is_completed': task.is_completed,
        'completed_at': task.completed_at.isoformat() if task.completed_at else None
    })

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

@login_required
def get_archived_tasks(request, board_id):
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
        'archived_at': localtime(task.created_at).strftime('%d/%m/%Y %H:%M')
    } for task in tasks]

    return JsonResponse({'tasks': data})

@require_POST
@login_required
def api_update_task_date(request):
    try:
        data = json.loads(request.body)
        task_id = data.get('task_id')
        new_date_str = data.get('new_date') # Format: YYYY-MM-DD
        
        if not task_id or not new_date_str:
            return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)

        # หา Task (เช็คสิทธิ์ด้วย)
        task = get_object_or_404(
            Task, 
            Q(list__board__created_by=request.user) | Q(list__board__members=request.user),
            id=task_id
        )
        
       
        new_date = parse_date(new_date_str)
        
        if task.due_date:
            # คงเวลาเดิมไว้ เปลี่ยนแค่วัน
            task.due_date = task.due_date.replace(year=new_date.year, month=new_date.month, day=new_date.day)
        else:
            # ถ้าของเดิมไม่มีเวลา ให้ตั้งเป็นเที่ยงวัน
            
            task.due_date = timezone.make_aware(datetime.datetime.combine(new_date, datetime.time(12, 0)))

        task.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==========================================
# 5. Task Components (Labels, Checklists, Attachments)
# ==========================================
# --- Labels ---

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

# --- Checklists ---

@login_required
@require_POST
def create_checklist_item(request, task_id):
    task = get_object_or_404(Task, id=task_id)    
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

# --- Attachments ---

@login_required
@require_POST
def create_attachment(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    if 'file' in request.FILES:
        file = request.FILES['file']
        attachment = Attachment.objects.create(task=task, file=file)
        
        return JsonResponse({
            'success': True,
            'id': attachment.id,
            'filename': attachment.filename(),
            'url': attachment.file.url,
            'is_image': attachment.is_image(),
            'uploaded_at': localtime(attachment.uploaded_at).strftime('%d/%m/%Y %H:%M')
        })
        
    return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

@login_required
@require_POST
def delete_attachment(request, attachment_id):
    attachment = get_object_or_404(Attachment, id=attachment_id)
    attachment.delete()
    return JsonResponse({'success': True})

# ==========================================
# 6. Comment System
# ==========================================

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
            'created_at': localtime(c.created_at).strftime('%d/%m/%Y %H:%M'),
        })
    return JsonResponse({'comments': data})

@require_POST
@login_required
def add_comment(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    
    # Check สิทธิ์
    if request.user != task.list.board.created_by and request.user not in task.list.board.members.all():
         return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
        content = data.get('content')
        if not content:
            return JsonResponse({'error': 'Empty content'}, status=400)

        # 1. สร้างคอมเมนต์ลง DB
        comment = Comment.objects.create(task=task, author=request.user, content=content)
        
        # ==================================================
        # ⚠️ แจ้งเตือน Notification (Real-time)
        # ==================================================
        # วนลูปแจ้งทุกคนที่รับผิดชอบงานนี้ (ยกเว้นตัวเราเอง)
        for user in task.assigned_to.all():
            if user != request.user:
                # A. สร้าง Notification ลง Database
                Notification.objects.create(
                    recipient=user,
                    actor=request.user,
                    task=task,
                    message=f"ได้แสดงความคิดเห็นในงาน '{task.title}': \"{content[:20]}{'...' if len(content)>20 else ''}\""
                )

                # B. ✅ ส่งสัญญาณ Real-time เข้าห้องส่วนตัวของ User
                unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"user_{user.id}",
                    {
                        "type": "send_notification",
                        "message": f"มีความคิดเห็นใหม่ในงาน '{task.title}'",
                        "unread_count": unread_count
                    }
                )

        # 2. เตรียมข้อมูลส่งกลับ (Response)
        avatar_url = comment.author.profile_image.url if comment.author.profile_image else None

        return JsonResponse({
            'id': comment.id,
            'author': comment.author.username,
            'author_avatar': avatar_url,
            'content': comment.content,
            'created_at': localtime(comment.created_at).strftime('%d/%m/%Y %H:%M'),
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

# ==========================================
# 7. Members & Invitations
# ==========================================

@require_POST
@login_required
def add_member(request, board_id):
    board = get_object_or_404(Board, id=board_id, created_by=request.user)
    username = request.POST.get("username")
    
    try:
        user_to_invite = User.objects.get(username=username)
        
        if user_to_invite in board.members.all() or user_to_invite == board.created_by:
            pass
        else:
            existing_invite = BoardInvitation.objects.filter(
                board=board, 
                recipient=user_to_invite, 
                status='pending'
            ).exists()
            
            if not existing_invite:
                # 1. สร้างคำเชิญ
                BoardInvitation.objects.create(
                    board=board,
                    sender=request.user,
                    recipient=user_to_invite
                )
                
                # 2. สร้าง Notification ลง DB
                Notification.objects.create(
                    recipient=user_to_invite,
                    actor=request.user,
                    board=board,  
                    message=f"ได้เชิญคุณเข้าร่วมบอร์ด '{board.name}'"
                )

                # ✅ 3. ส่ง Real-time Notification
                channel_layer = get_channel_layer()
                unread_count = Notification.objects.filter(recipient=user_to_invite, is_read=False).count()
                async_to_sync(channel_layer.group_send)(
                    f"user_{user_to_invite.id}",
                    {
                        "type": "send_notification",
                        "message": f"คุณได้รับเชิญเข้าบอร์ด '{board.name}'",
                        "unread_count": unread_count
                    }
                )

    except User.DoesNotExist:
        pass 
        
    return redirect("board_detail", board_id=board.id)

@login_required
@require_POST
def remove_member(request, board_id, user_id):
    board = get_object_or_404(Board, id=board_id)
    
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
        invite.board.members.add(request.user)
    elif action == 'decline':
        invite.status = 'declined'
        invite.save()
        
    return redirect('project_page') # หรือหน้า inbox ที่เราจะสร้าง

# ==========================================
# 8. Notifications 
# ==========================================

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

        
        board_id = None
        if n.task and n.task.list and n.task.list.board:
            board_id = n.task.list.board.id

        data.append({
            'id': n.id,
            'actor': n.actor.username if n.actor else 'ระบบ',
            'actor_avatar': avatar_url,
            'message': n.message,  
            'created_at': localtime(n.created_at).strftime('%d/%m %H:%M'),
            'is_read': n.is_read,
            'board_id': board_id,  
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


# ==============================#
#  8.1 Activities 
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
        'created_at': localtime(act.created_at).strftime('%d/%m/%Y %H:%M')
    } for act in activities]
    
    return JsonResponse({'activities': data})

# ==========================================
# 9. Calendar & Schedule
# ==========================================

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
    events = []

    # ==========================================
    # 1. LOCAL TASKS: งานจากบอร์ดของเรา
    # ==========================================
    board_id = request.GET.get('board_id')
    
    tasks = Task.objects.filter(
        due_date__isnull=False,
        is_archived=False
    )

    user_boards = Board.objects.filter(Q(created_by=request.user) | Q(members=request.user))
    tasks = tasks.filter(list__board__in=user_boards)

    if board_id and board_id != 'all':
        tasks = tasks.filter(list__board_id=board_id)
    
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
            'allDay': False,
            # เพิ่ม extendedProps เพื่อให้ Frontend รู้ว่าเป็น Task (ยอมให้ลากได้)
            'extendedProps': {
                'type': 'task'
            }
        })

    # ==========================================
    # 2. CLASS SCHEDULE: ตารางเรียน 
    # ==========================================
    # Map วันให้ตรงกับ format ของ FullCalendar (0=Sun, 1=Mon, ...)
    day_map = {
        'Sun': 0, 'Mon': 1, 'Tue': 2, 'Wed': 3, 'Thu': 4, 'Fri': 5, 'Sat': 6
    }
    
    schedules = ClassSchedule.objects.filter(user=request.user)
    
    for sched in schedules:
        if sched.day in day_map:
            events.append({
                'title': f"📚 {sched.subject_name}", 
                'daysOfWeek': [day_map[sched.day]], # สั่งให้ Event นี้เกิดซ้ำทุกๆ วันที่ระบุ
                'startTime': sched.start_time.strftime('%H:%M'), 
                'endTime': sched.end_time.strftime('%H:%M'),    
                'backgroundColor': '#8B5CF6', # สีม่วง (Schedule)
                'borderColor': '#7C3AED',
                'textColor': '#ffffff',
                'editable': False, # ห้ามลากเปลี่ยนวัน
                'extendedProps': {
                    'type': 'schedule'
                }
            })

    # ==========================================
    # 3. GOOGLE CALENDAR: ดึงงาน + ลิงก์ Meet
    # ==========================================
    if 'google_credentials' in request.session:
        try:
            creds_data = request.session['google_credentials']
            creds = Credentials(**creds_data)
            service = build('calendar', 'v3', credentials=creds)
            
            # ย้อนหลัง 1 ปี
            start_time = (datetime.datetime.utcnow() - datetime.timedelta(days=365)).isoformat() + 'Z'
            
            calendar_list_result = service.calendarList().list(showHidden=True).execute()
            calendars = calendar_list_result.get('items', [])
            
            for calendar_entry in calendars:
                cal_id = calendar_entry['id']
                cal_summary = calendar_entry.get('summary', 'Unknown')
                
                if 'holiday' in cal_id or 'addressbook' in cal_id or 'th.thai' in cal_id:
                    continue

                try:
                    events_result = service.events().list(
                        calendarId=cal_id,
                        timeMin=start_time, 
                        maxResults=50,      
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    
                    google_events = events_result.get('items', [])
                    
                    for event in google_events:
                        start = event['start'].get('dateTime', event['start'].get('date'))
                        event_title = event.get('summary', 'No Title')
                        is_all_day = 'date' in event['start']
                        
                        # ✅ Check หา Google Meet Link
                        meet_link = event.get('hangoutLink')
                        html_link = event.get('htmlLink')
                        
                        # ถ้ามี Meet Link ให้ใช้เป็น URL หลัก (กดแล้วไป Meet เลย)
                        # ถ้าไม่มี ให้ไปหน้าปฏิทิน Google ปกติ
                        final_url = meet_link if meet_link else html_link
                        
                        events.append({
                            'title': f"[{cal_summary}] {event_title}", 
                            'start': start,
                            'url': final_url,
                            'backgroundColor': '#F59E0B', # สีส้ม
                            'borderColor': '#F59E0B',
                            'textColor': '#ffffff',
                            'allDay': is_all_day,
                            'editable': False, # ห้ามลากแก้ไข
                            'extendedProps': {
                                'is_google': True,
                                'has_meet': bool(meet_link) # ส่ง Flag ไปบอก Frontend ให้โชว์ไอคอนกล้อง
                            }
                        })
                        
                except Exception:
                    continue
                
        except Exception:
            pass

    return JsonResponse(events, safe=False)

@login_required
def create_class_schedule(request):
    if request.method == 'POST':
        form = ClassScheduleForm(request.POST)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.user = request.user
            schedule.save()
    return redirect('home') 

@login_required
def delete_class_schedule(request, schedule_id):
    schedule = get_object_or_404(ClassSchedule, id=schedule_id, user=request.user)
    schedule.delete()
    return redirect('home')

# ==========================================
# 10. Google Integration
# ==========================================

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
def fetch_google_calendar_partial(request):

    google_events = [] 
    # เช็คว่ามี Credentials ไหม
    if 'google_credentials' in request.session:
        try:
            creds_data = request.session['google_credentials']
            creds = Credentials(**creds_data)
            service = build('calendar', 'v3', credentials=creds)
            
            now_iso = datetime.datetime.utcnow().isoformat() + 'Z'
            
            # 1. ดึงรายชื่อปฏิทิน
            calendar_list = service.calendarList().list().execute().get('items', [])
            
            all_events = []
            
            # 2. วนลูปดึง Event (ส่วนนี้แหละที่ช้า เราเลยย้ายมาทำทีหลัง)
            for calendar_entry in calendar_list:
                cal_name = calendar_entry.get('summary', '')

                # กรองปฏิทินที่ไม่ต้องการ
                keywords = ['holiday', 'วันหยุด', 'birthday', 'วันเกิด']
                if any(k in cal_name.lower() for k in keywords):
                    continue

                try:
                    # ดึง Event จากแต่ละปฏิทิน
                    events_result = service.events().list(
                        calendarId=calendar_entry['id'], 
                        timeMin=now_iso,
                        maxResults=5, 
                        singleEvents=True,
                        orderBy='startTime'
                    ).execute()
                    
                    items = events_result.get('items', [])
                    for event in items:
                        event['calendar_name'] = cal_name
                        all_events.append(event)
                        
                except Exception as e:
                    # ถ้าปฏิทินไหน error ก็ข้ามไป ไม่ให้เว็บพัง
                    continue

            # 3. จัดเรียงตามเวลา
            def get_start_time(e):
                return e['start'].get('dateTime', e['start'].get('date'))
            
            all_events.sort(key=get_start_time)
            all_events = all_events[:15] # เอาแค่ 15 อันดับแรก

            # 4. จัด Format ข้อมูล
            for event in all_events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                try:
                    if isinstance(start, str):
                        if 'T' in start:
                             start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                        else:
                             start_dt = datetime.datetime.strptime(start, "%Y-%m-%d")
                    else:
                        start_dt = start
                except ValueError:
                    start_dt = start

                google_events.append({
                    'title': event.get('summary', '(ไม่มีชื่อ)'),
                    'start': start_dt,
                    'link': event.get('htmlLink', '#'),
                    'source': event.get('calendar_name', 'Google Calendar')
                })
                
        except Exception as e:
            print(f"Google API Error in Partial View: {e}")

    # ส่งไปที่ Template ย่อย (เฉพาะส่วน Widget)
    return render(request, 'boards/partials/calendar_widget.html', {
        'google_events': google_events
    })

@login_required
def sync_google_classroom_page(request):
    if 'google_credentials' not in request.session:
        return redirect('google_calendar_init')

    try:
        creds_data = request.session['google_credentials']
        creds = Credentials(**creds_data)
        service = build('calendar', 'v3', credentials=creds)

        # ดึงปฏิทินทั้งหมด (รวมถึงที่ซ่อนอยู่ด้วย showHidden=True)
        calendar_list = service.calendarList().list(showHidden=False).execute().get('items', [])
        
        # กรองปฏิทินที่ไม่ใช่วิชาเรียนออกเบื้องต้น
        filtered_calendars = []
        for cal in calendar_list:
            cal_id = cal['id']
            # กรองพวกวันหยุด, เบอร์โทร, หรือปฏิทินระบบออก
            if 'holiday' in cal_id or 'addressbook' in cal_id or 'th.thai' in cal_id or 'weeknum' in cal_id:
                continue
            filtered_calendars.append(cal)

        return render(request, 'boards/google_sync_select.html', {
            'calendars': filtered_calendars
        })

    except Exception as e:
        print(f"Fetch Calendars Error: {e}")
        return redirect('project_page')


@login_required
@require_POST
def sync_google_classroom_confirm(request):
    # 1. เช็คสิทธิ์ Google
    if 'google_credentials' not in request.session:
        return redirect('google_calendar_init')

    selected_items = request.POST.getlist('selected_calendars')
    if not selected_items:
        return redirect('project_page')

    try:
        # 2. เตรียม Service
        creds_data = request.session['google_credentials']
        creds = Credentials(**creds_data)
        service = build('calendar', 'v3', credentials=creds)
        
        # กำหนดช่วงเวลา (ย้อนหลัง 90 วัน)
        now = datetime.datetime.utcnow()
        time_min = (now - datetime.timedelta(days=90)).isoformat() + 'Z'

        created_count = 0
        error_logs = []

        for item in selected_items:
            if '|' in item:
                cal_id, cal_name = item.split('|', 1)
            else:
                continue

            # ---------------------------------------------------
            # STEP A: สร้าง Board (ถ้ายังไม่มี)
            # ---------------------------------------------------
            board, created = Board.objects.get_or_create(
                name=cal_name[:255], # ตัดชื่อกันเหนียว (Model Board คุณน่าจะแก้เป็น 255 แล้ว)
                created_by=request.user,
                defaults={'description': f"Google Classroom: {cal_name}"}
            )

            if created:
                List.objects.create(board=board, title="To Do", position=1)
                List.objects.create(board=board, title="Doing", position=2)
                List.objects.create(board=board, title="Done", position=3)
            
            # หา List เป้าหมาย (To Do)
            todo_list = board.lists.filter(title__icontains="To Do").first()
            if not todo_list:
                todo_list = board.lists.first() # ถ้าไม่มี To Do เอาอันแรกสุด
            
            if not todo_list: continue # ถ้าไม่มี List เลยก็ข้าม

            # ---------------------------------------------------
            # STEP B: ดึงงานจาก Google Calendar
            # ---------------------------------------------------
            try:
                events_result = service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    maxResults=50,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                google_events = events_result.get('items', [])

                for event in google_events:
                    g_id = event['id']
                    summary = event.get('summary', '(No Title)')

                    # 1. เช็คงานซ้ำ (Duplicate Check)
                    if Task.objects.filter(google_event_id=g_id).exists():
                        continue 
                    
                    # 2. เตรียมข้อมูล Description + Link
                    desc_text = event.get('description', '') or "-"
                    link = event.get('htmlLink', '#')
                    final_desc = f"{desc_text}\n\n🔗 Google Link:\n{link}"

                    # 3. แปลงวันที่ (Due Date Parsing)
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    due_date = None
                    if start:
                        try:
                            if 'T' in start:
                                # มีเวลา (datetime)
                                due_date = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                            else:
                                # มีแต่วันที่ (date) -> ตั้งเป็น 23:59 ของวันนั้น
                                due_date = datetime.datetime.strptime(start, "%Y-%m-%d")
                                due_date = due_date.replace(hour=23, minute=59)
                                due_date = timezone.make_aware(due_date)
                        except Exception:
                            pass

                    # 4. สร้าง Task
                    try:
                        task = Task.objects.create(
                            list=todo_list,
                            title=summary[:255],     # ตัดชื่อไม่ให้เกิน 255
                            description=final_desc,
                            due_date=due_date,
                            google_event_id=g_id,
                            
                            # ค่า Default ตาม Model
                            position=0, 
                            priority=Task.Priority.MEDIUM,
                            status=Task.Status.TODO,
                            is_completed=False,
                            is_archived=False
                            
                        
                        )
                        
                        # ✅ เพิ่มคนรับผิดชอบ (Assigned To) เป็นคนกด Sync
                        task.assigned_to.add(request.user)
                        
                        created_count += 1
                        
                    except Exception as e:
                        print(f"❌ Error Saving Task '{summary}': {e}")
                        error_logs.append(f"{summary}: {e}")

            except Exception as e:
                print(f"❌ API Error for Calendar {cal_name}: {e}")
                continue

        # แจ้งผลลัพธ์
        if error_logs:
            messages.warning(request, f"นำเข้าได้ {created_count} งาน แต่มีข้อผิดพลาดบางรายการ")
        elif created_count == 0:
            messages.info(request, "ไม่พบงานใหม่ในช่วง 90 วันที่ผ่านมา")
        else:
            messages.success(request, f"สำเร็จ! นำเข้า {created_count} งานเรียบร้อยแล้ว")

        return redirect('project_page')

    except Exception as e:
        messages.error(request, f"Critical Error: {e}")
        return redirect('project_page')

# ==========================================
# 11. Reporting
# ==========================================

@login_required
def reporting_view(request):
    # ==========================================
    # ส่วน Filter บอร์ด และดึงข้อมูล Tasks
    # ==========================================
    user_boards = Board.objects.filter(Q(created_by=request.user) | Q(members=request.user)).distinct()
    tasks = Task.objects.filter(
        Q(list__board__created_by=request.user) | Q(list__board__members=request.user)
    ).distinct() \
    .select_related('list', 'list__board') \
    .prefetch_related('assigned_to', 'labels')

    selected_board_id = request.GET.get('board_id')
    if selected_board_id and selected_board_id != 'all':
        tasks = tasks.filter(list__board_id=selected_board_id)
        current_board_name = user_boards.filter(id=selected_board_id).first().name
    else:
        current_board_name = "ทุกโปรเจกต์"

    # ==========================================
    # เตรียม QuerySet สำหรับ Modal List
    # ==========================================
    all_tasks_qs = tasks.select_related('list__board').order_by('-created_at')
    completed_tasks_qs = tasks.filter(is_completed=True).select_related('list__board').order_by('-completed_at')
    overdue_tasks_qs = tasks.filter(due_date__lt=timezone.now(), is_completed=False).select_related('list__board').order_by('due_date')
    remaining_tasks_qs = tasks.filter(is_completed=False).select_related('list__board').order_by('due_date')

    # ==========================================
    # คำนวณ KPIs
    # ==========================================
    total_tasks = tasks.count()
    completed_tasks = completed_tasks_qs.count()
    remaining_count = remaining_tasks_qs.count()
    overdue_tasks = overdue_tasks_qs.count()
    completion_rate = round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0

    # ==========================================
    # เตรียมข้อมูลกราฟ (Charts Data)
    # ==========================================

    # Chart 1: Priority
    priority_data = {
        'high': tasks.filter(priority='high', is_completed=False).count(),
        'medium': tasks.filter(priority='medium', is_completed=False).count(),
        'low': tasks.filter(priority='low', is_completed=False).count(),
    }

    # Chart 2: Trend (✅ แก้ไขบั๊ก NoneType ตรงนี้แล้ว)
    last_7_days = timezone.now() - timedelta(days=7)
    completed_trend = (
        tasks.filter(
            is_completed=True, 
            completed_at__isnull=False, # 👈 กรองค่าว่างออกไปตั้งแต่ระดับ Database
            completed_at__gte=last_7_days
        )
        .annotate(date=TruncDate('completed_at'))
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    
    # 👈 ดัก if item['date'] อีกชั้นเพื่อความปลอดภัย 100%
    trend_labels = [item['date'].strftime('%d/%m/%Y') for item in completed_trend if item['date']]
    trend_data = [item['count'] for item in completed_trend if item['date']]

    # Chart 3: Member Workload
    member_stats = tasks.values('assigned_to__username').annotate(total=Count('id')).order_by('-total')
    member_labels = [m['assigned_to__username'] if m['assigned_to__username'] else 'Unassigned' for m in member_stats]
    member_data = [m['total'] for m in member_stats]

    # Chart 4: Task Distribution 
    list_stats = tasks.values('list__title').annotate(count=Count('id')).order_by('list__position')
    list_labels = [l['list__title'] for l in list_stats]
    list_data = [l['count'] for l in list_stats]

    context = {
        'boards': user_boards,
        'selected_board_id': selected_board_id,
        'current_board_name': current_board_name,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'remaining_count': remaining_count,
        'completion_rate': completion_rate,
        'overdue_tasks': overdue_tasks,
        'all_tasks_qs': all_tasks_qs,
        'completed_tasks_qs': completed_tasks_qs,
        'remaining_tasks_qs': remaining_tasks_qs,
        'overdue_tasks_qs': overdue_tasks_qs,
        'priority_data': priority_data,
        'trend_labels': trend_labels,
        'trend_data': trend_data,
        'member_labels': member_labels,
        'member_data': member_data,
        'list_labels': list_labels, 
        'list_data': list_data,    
    }

    return render(request, 'boards/reporting.html', context)
# =========
# DISCORD NOTIFICATION FUNCTION
# =========
def send_discord_notify(message, webhook_url=None):
    if not webhook_url:
        return
    try:
        data = {
            "username": "Work Wai D Borad", 
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/2991/2991148.png", 
            "content": message
        }
        requests.post(webhook_url, json=data, timeout=3)
    except Exception as e:
        print(f"Discord Error: {e}") 


# ==========================================
# 12. Utils & Helper Functions
# ==========================================

def send_invitation_email(invite, sender):
    if not invite.recipient.email:
        return

    subject = f" คำเชิญเข้าร่วมบอร์ด: {invite.board.name}"
    message = (
        f"สวัสดีคุณ {invite.recipient.username},\n\n"
        f"คุณ {sender.username} ได้เชิญคุณเข้าร่วมโปรเจกต์ '{invite.board.name}'\n\n"
        f"สามารถเข้าไปตอบรับคำเชิญได้ที่เว็บไซต์ของเรา"
    )
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [invite.recipient.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Invite Email Error: {e}")


def send_email_notify(task, recipient):
    """ฟังก์ชันส่งเมลแจ้งเตือนเมื่อได้รับมอบหมายงาน"""
    if not recipient.email:
        print(f"Email Warning: User {recipient.username} has no email address.")
        return

    subject = f" งานใหม่: {task.title}"
    message = (
        f"สวัสดีคุณ {recipient.username},\n\n"
        f"คุณได้รับมอบหมายงานใหม่ในระบบ Board Management\n\n"
        f" ชื่องาน: {task.title}\n"
        f" กำหนดส่ง: {task.due_date if task.due_date else 'ไม่ระบุ'}\n"
        f" โปรเจกต์: {task.list.board.name}\n"
        f" มอบหมายโดย: {task.created_by.username if task.created_by else 'ระบบ'}\n\n"
        f"ตรวจสอบรายละเอียดได้ที่เว็บไซต์ของเรา"
    )
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient.email],
            fail_silently=False,
        )
        print(f" Email sent to {recipient.email}")
    except Exception as e:
        print(f" Email Error: {e}")


# ==========================================
# 18. Automated Reminder System
# ==========================================

@require_POST
def send_task_reminders(request):
    """Send automated reminders for upcoming task deadlines via Web/Email/Discord"""
    
    # ✅ ใช้ timezone.now() แทน .date() เพื่อเช็คให้ละเอียด
    now = timezone.now()
    today = now.date()
    
    tasks = Task.objects.filter(
        is_completed=False, 
        due_date__isnull=False, 
        # ✅ ลบตรงนี้ออก - ยังไม่บันทึกให้ไปตรวจสอบวันที่ก่อน
    ).select_related('list__board', 'list__board__created_by').prefetch_related('assigned_to')

    count = 0
    channel_layer = get_channel_layer()

    for task in tasks:
        # ✅ แก้: ตรวจสอบ remind_days ให้ถูกต้อง
        if not task.remind_days or task.remind_days < 0: 
            continue 

        # ✅ แก้: จัดการ datetime vs date ให้ครบถ้วน
        if isinstance(task.due_date, datetime.datetime):
            task_due_date = task.due_date.date()
            task_due_time = task.due_date.time()
        else:
            task_due_date = task.due_date
            task_due_time = datetime.time(0, 0)  # ตั้งเป็นเที่ยงคืน

        # ✅ แก้: คำนวณวันที่ที่ควรเตือน
        reminder_date = task_due_date - timedelta(days=task.remind_days)

        # ✅ สำคัญ: เช็คก่อนว่าเคยเตือนไปแล้วหรือยัง (ตรวจสอบด้วย reminder_date)
        # ป้องกันไม่ให้ส่งซ้ำในวันเดียวกัน
        last_reminder_log = ActivityLog.objects.filter(
            board=task.list.board,
            action__contains=f"Reminder: {task.id}"
        ).order_by('-created_at').first()
        
        if last_reminder_log and last_reminder_log.created_at.date() == today:
            continue  # เตือนไปแล้วในวันนี้

        # ✅ เตือนถ้า: วันนี้ >= วันที่ต้องเตือน
        if today >= reminder_date:
            assignees = task.assigned_to.all()
            if not assignees: 
                continue

            # ----------------------------------------
            # A. Web Notification (Real-time) + DB
            # ----------------------------------------
            for user in assignees:
                try:
                    Notification.objects.create(
                        recipient=user,
                        actor=task.list.board.created_by, 
                        task=task,
                        message=f"⏳ เตือนความจำ! งาน '{task.title}' ครบกำหนดในอีก {task.remind_days} วัน"
                    )
                    
                    unread_count = Notification.objects.filter(
                        recipient=user, 
                        is_read=False
                    ).count()
                    
                    async_to_sync(channel_layer.group_send)(
                        f"user_{user.id}",
                        {
                            "type": "send_notification",
                            "message": f"⏳ ใกล้ครบกำหนด! '{task.title}'",
                            "unread_count": unread_count
                        }
                    )
                except Exception as e:
                    print(f"❌ Web/DB Error for user {user.id}: {e}")

                # ----------------------------------------
                # B. Email Notification
                # ----------------------------------------
                if user.email:
                    try:
                        # ✅ แก้: ใช้ localtime ให้ถูกต้อง
                        if isinstance(task.due_date, datetime.datetime):
                            formatted_date = localtime(task.due_date).strftime('%d/%m/%Y %H:%M')
                        else:
                            formatted_date = task.due_date.strftime('%d/%m/%Y')
                        
                        send_mail(
                            subject=f"⏳ แจ้งเตือนงานใกล้ครบกำหนด: {task.title}",
                            message=(
                                f"สวัสดีคุณ {user.username},\n\n"
                                f"งาน '{task.title}' จะครบกำหนดในวันที่ {formatted_date}\n"
                                f"(เหลือเวลาอีก {task.remind_days} วัน)\n"
                                f"โปรเจกต์: {task.list.board.name}\n\n"
                                f"กรุณาตรวจสอบสถานะงานของคุณ\n\n"
                                f"ขอบคุณครับ,\nทีมงาน Work Wai D"
                            ),
                            from_email=settings.EMAIL_HOST_USER,
                            recipient_list=[user.email],
                            fail_silently=False,  # ✅ แก้เป็น False เพื่อให้รู้ error
                        )
                        print(f"✅ Email sent to {user.email}")
                    except Exception as e:
                        print(f"❌ Email Error for {user.email}: {e}")

            # ----------------------------------------
            # C. Discord Webhook Notification
            # ----------------------------------------
            webhook_url = task.list.board.discord_webhook_url
            if webhook_url:
                try:
                    assignee_names = ", ".join([u.username for u in assignees]) or "ไม่มีผู้รับผิดชอบ"
                    
                    if isinstance(task.due_date, datetime.datetime):
                        formatted_date = localtime(task.due_date).strftime('%d/%m/%Y %H:%M')
                    else:
                        formatted_date = task.due_date.strftime('%d/%m/%Y')
                    
                    discord_msg = {
                        "content": (
                            f"⚠️ **Upcoming Deadline Warning!**\n"
                            f"**Task:** {task.title}\n"
                            f"**Board:** {task.list.board.name}\n"
                            f"**Due Date:** {formatted_date}\n"
                            f"**Remaining:** {task.remind_days} Days\n"
                            f"**Assigned To:** {assignee_names}\n"
                            f"---------------------------------"
                        )
                    }
                    requests.post(webhook_url, json=discord_msg, timeout=5)
                    print(f"✅ Discord notification sent")
                except Exception as e:
                    print(f"❌ Discord Error: {e}")

            # ✅ บันทึก Log แทนการใช้ is_reminded
            # (เพราะ is_reminded ไม่ควรใช้ - มันจะไม่รีเซตเมื่อเปลี่ยนวันที่)
            log_activity(
                task.list.board,
                request.user if request.user.is_authenticated else task.list.board.created_by,
                f"Reminder: {task.id} - งาน '{task.title}' ได้รับการเตือน"
            )
            
            count += 1

    return JsonResponse({
        'success': True, 
        'message': f'✅ ส่งแจ้งเตือนสำเร็จทั้งหมด {count} รายการ',
        'sent': count
    })