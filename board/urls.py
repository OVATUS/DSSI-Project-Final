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

    # Menber
    path("<int:board_id>/add_member/", add_member, name="add_member"),
    path('board/<int:board_id>/remove_member/<int:user_id>/', remove_member, name='remove_member'),
    path('invite/<int:invite_id>/<str:action>/', respond_invitation, name='respond_invitation'),
   
    # LIST
    path("<int:board_id>/list/create/", list_create, name="list_create"),
    path("list/<int:list_id>/edit/", list_update, name="list_update"),
    path("list/<int:list_id>/delete/", list_delete, name="list_delete"),
     path("<int:board_id>/list/reorder/", list_reorder, name="list_reorder"),

     # Task 🆕
    path("task/create/<int:list_id>/", task_create, name="task_create"),
    path("task/<int:task_id>/edit/", task_update, name="task_update"),
    path("task/<int:task_id>/delete/", task_delete, name="task_delete"),
    path("task/move/", task_move, name="task_move"),
    path('board/<int:board_id>/label/create/', create_label, name='create_label'),

    #Comment 
    path("task/<int:task_id>/comments/", get_comments, name="get_comments"),
    path("task/<int:task_id>/comments/add/", add_comment, name="add_comment"),

    # API สำหรับ Search (เพิ่มบรรทัดนี้)
    path("api/search/", search_boards_api, name="search_boards_api"),
]