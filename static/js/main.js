// static/js/main.js

function projectPage() {
    return {
        /* popup: create */
        openCreate: false,
        coverPreview: null,

        /* popup: edit */
        openEdit: false,
        editActionUrl: '',
        editName: '',
        editDescription: '',
        editCoverPreview: null,

        /* popup: delete */
        openDelete: false,
        deleteUrl: '',

        /* dot menu */
        menuBoardId: null,
    };
}

function boardDetailPage(config) {
    return {
        moveUrl: (config && config.moveUrl) ? config.moveUrl : '',
        listMoveUrl: (config && config.listMoveUrl) ? config.listMoveUrl : '',

        addMemberOpen: false,
        // ==== Task Modal ====
        taskModalOpen: false,
        taskMode: 'create',
        taskListTitle: '',
        taskActionUrl: '',
        taskTitle: '',
        taskDescription: '',
        taskAssignedTo: '',
        taskDueDate: '',
        taskPriority: 'medium',

        draggingTaskId: null,
        draggingListId: null,

        listModalOpen: false,
        listModalMode: 'create',
        listTitle: '',
        listActionUrl: '',
        listDeleteOpen: false,
        listDeleteActionUrl: '',

        currentTaskId: null,     // เก็บ ID ของ Task ที่กำลังเปิดอยู่
        comments: [],            // เก็บรายการคอมเมนต์
        newCommentText: '',      // ข้อความที่กำลังพิมพ์
        isLoadingComments: false,

        async loadComments(taskId) {
            this.currentTaskId = taskId;
            this.comments = [];
            this.isLoadingComments = true;
            
            try {
                const res = await fetch(`/board/task/${taskId}/comments/`);
                const data = await res.json();
                this.comments = data.comments || [];
            } catch (err) {
                console.error("Load comments error:", err);
            } finally {
                this.isLoadingComments = false;
            }
        },

        // ✅ ฟังก์ชัน: ส่งคอมเมนต์
        async postComment() {
            if (!this.newCommentText.trim() || !this.currentTaskId) return;

            const content = this.newCommentText;
            this.newCommentText = ''; // เคลียร์ช่องพิมพ์ก่อนเพื่อให้ UX ดูลื่น

            const csrftoken = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))?.split('=')[1];

            try {
                const res = await fetch(`/board/task/${this.currentTaskId}/comments/add/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken
                    },
                    body: JSON.stringify({ content: content })
                });
                
                if (res.ok) {
                    const newComment = await res.json();
                    // แทรกคอมเมนต์ใหม่ไปบนสุด
                    this.comments.unshift(newComment);
                } else {
                    alert('ส่งคอมเมนต์ไม่สำเร็จ');
                    this.newCommentText = content; // คืนค่าข้อความถ้าส่งไม่ผ่าน
                }
            } catch (err) {
                console.error(err);
                this.newCommentText = content;
            }
        },

        // ==== Task Drag ====
        onDragStartTask(event, taskId) {
            this.draggingTaskId = taskId;
            this.draggingListId = null;
            event.dataTransfer.effectAllowed = 'move';
        },

        // ==== List Drag ====
        onDragStartList(event, listId) {
            this.draggingListId = listId;
            this.draggingTaskId = null;
            event.dataTransfer.effectAllowed = 'move';
        },
        // ✅ ฟังก์ชัน: โหลดคอมเมนต์
        
        async onDrop(event, listId) {
            // เคสลาก Task
            if (this.draggingTaskId && this.moveUrl) {
                const taskId = this.draggingTaskId;
                this.draggingTaskId = null;

                const formData = new FormData();
                formData.append('task_id', taskId);
                formData.append('list_id', listId);

                const csrftoken = document.cookie
                    .split('; ')
                    .find(row => row.startsWith('csrftoken='))
                    ?.split('=')[1];

                try {
                    await fetch(this.moveUrl, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrftoken },
                        body: formData,
                    });
                    window.location.reload();
                } catch (err) {
                    console.error(err);
                }
                return;
            }

            // เคสลาก List
            if (this.draggingListId && this.listMoveUrl) {
                const fromId = this.draggingListId;
                this.draggingListId = null;

                const formData = new FormData();
                formData.append('list_id', fromId);
                formData.append('target_id', listId);

                const csrftoken = document.cookie
                    .split('; ')
                    .find(row => row.startsWith('csrftoken='))   
                    ?.split('=')[1];

                try {
                    await fetch(this.listMoveUrl, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrftoken },
                        body: formData,
                    });
                    window.location.reload();
                } catch (err) {
                    console.error(err);
                }
            }
        },
    };
}


