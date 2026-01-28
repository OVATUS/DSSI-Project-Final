from django.urls import path , include
from .views import *

urlpatterns = [
    path('home/',board_lsit_view, name="home"),
    path("projects/", project_page, name="project_page"),

    # BOARD
    path('board/<int:board_id>/star/', toggle_star_board, name='board_star'),
    path("create/", board_create, name="board_create"),
    path("<int:board_id>/", board_detail, name="board_detail"),
    path("<int:board_id>/edit/", board_update, name="board_update"),
    path("<int:board_id>/delete/", board_delete, name="board_delete"),
    path('board/<int:board_id>/archived-tasks/', get_archived_tasks, name='get_archived_tasks'),
    path('task/<int:task_id>/toggle-complete/', toggle_task_completion, name='task_toggle_complete'),
    path('board/<int:board_id>/leave/', leave_board, name='leave_board'),

    # Menber
    path("<int:board_id>/add_member/", add_member, name="add_member"),
    path('board/<int:board_id>/remove_member/<int:user_id>/', remove_member, name='remove_member'),
    path('invite/<int:invite_id>/<str:action>/', respond_invitation, name='respond_invitation'),
   
    # LIST
    path("<int:board_id>/list/create/", list_create, name="list_create"),
    path("list/<int:list_id>/edit/", list_update, name="list_update"),
    path("list/<int:list_id>/delete/", list_delete, name="list_delete"),
    path("<int:board_id>/list/reorder/", list_reorder, name="list_reorder"),

    # Checklist URLs
    path('task/<int:task_id>/checklist/create/', create_checklist_item, name='create_checklist_item'),
    path('checklist/<int:item_id>/update/', update_checklist_item_status, name='update_checklist_item_status'),
    path('checklist/<int:item_id>/delete/', delete_checklist_item, name='delete_checklist_item'),

    # Attachment URLs
    path('task/<int:task_id>/attachment/create/', create_attachment, name='create_attachment'),
    path('attachment/<int:attachment_id>/delete/', delete_attachment, name='delete_attachment'),

     # Task 
    path("task/create/<int:list_id>/", task_create, name="task_create"),
    path("task/<int:task_id>/edit/", task_update, name="task_update"),
    path("task/<int:task_id>/delete/", task_delete, name="task_delete"),
    path("task/move/", task_move, name="task_move"),
    path('api/calendar/update-date/', api_update_task_date, name='api_update_task_date'),

    # Label URLs
    path('label/<int:label_id>/delete/', delete_label, name='delete_label'),
    path('board/<int:board_id>/label/create/', create_label, name='create_label'),

    # API สำหรับ Archive/Unarchive Task
   path('task/<int:task_id>/toggle-archive/',toggle_task_archive, name='toggle_task_archive'),
   path('<int:board_id>/archived-tasks/',get_archived_tasks, name='get_archived_tasks'),

    #Comment 
    path("task/<int:task_id>/comments/", get_comments, name="get_comments"),
    path("task/<int:task_id>/comments/add/", add_comment, name="add_comment"),
    path('comment/<int:comment_id>/update/', update_comment, name='update_comment'),
    path('comment/<int:comment_id>/delete/', delete_comment, name='delete_comment'),

    # API สำหรับ Search 
    path("api/search/", search_boards_api, name="search_boards_api"),

    # notification
   path('notifications/', get_notifications, name='get_notifications'),
    path('notifications/<int:pk>/read/', read_notification, name='read_notification'),
    path('notifications/mark-all-read/', mark_all_read, name='mark_all_read'),

    # ประวัติการทำงาน
    path('<int:board_id>/activities/', get_board_activities, name='get_board_activities'),

    # 1. หน้าปฏิทิน
    path('my-calendar/', global_calendar_view, name='global_calendar'),
    path('api/calendar/events/', api_calendar_events, name='api_calendar_events'),
    path('google-calendar/init/', google_calendar_init, name='google_calendar_init'),
    path('google-calendar/callback/', google_calendar_callback, name='google_calendar_callback'),
    path('api/calendar-widget/', fetch_google_calendar_partial, name='fetch_google_calendar'),

    # หน้าเลือกวิชา 
    path('sync-google/select/', sync_google_classroom_page, name='sync_google_classroom_page'),
    # กดยืนยัน 
    path('sync-google/confirm/', sync_google_classroom_confirm, name='sync_google_classroom_confirm'),

    # 2. Reporting
    path('reporting/', reporting_view, name='reporting'),

    path('schedule/create/', create_class_schedule, name='create_class_schedule'),
    path('schedule/delete/<int:schedule_id>/', delete_class_schedule, name='delete_class_schedule'),
]