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

    # Label URLs
    path('label/<int:label_id>/delete/', delete_label, name='delete_label'),
    path('board/<int:board_id>/label/create/', create_label, name='create_label'),

    # API สำหรับ Archive/Unarchive Task
   path('task/<int:task_id>/toggle-archive/',toggle_task_archive, name='toggle_task_archive'),
   path('<int:board_id>/archived-tasks/',get_archived_tasks, name='get_archived_tasks'),

    #Comment 
    path("task/<int:task_id>/comments/", get_comments, name="get_comments"),
    path("task/<int:task_id>/comments/add/", add_comment, name="add_comment"),

    # API สำหรับ Search 
    path("api/search/", search_boards_api, name="search_boards_api"),

    # notification
   path('notifications/', get_notifications, name='get_notifications'),
    path('notifications/<int:pk>/read/', read_notification, name='read_notification'),
    path('notifications/mark-all-read/', mark_all_read, name='mark_all_read'),

    # ประวัติการทำงาน
    path('<int:board_id>/activities/', get_board_activities, name='get_board_activities'),
]