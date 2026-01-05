// static/js/main.js

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function projectPage() {
    return {
        openCreate: false,
        coverPreview: null,
        openEdit: false,
        editActionUrl: '',
        editName: '',
        editDescription: '',
        editCoverPreview: null,
        openDelete: false,
        deleteUrl: '',
        menuBoardId: null,
        
        
    };
}

window.boardDetailPage = function (config) {
    return {
        // ==== Configuration ====
        moveUrl: (config && config.moveUrl) ? config.moveUrl : '',
        listMoveUrl: (config && config.listMoveUrl) ? config.listMoveUrl : '',

        // ==== Member & UI ====
        addMemberOpen: false,
        filterMember: '',
        manageMembersOpen: false,

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
        taskLabels: [],
        archivedDrawerOpen: false, // เปิด/ปิดลิ้นชัก
        archivedTasks: [],         // เก็บรายการงานที่ดึงมา
        isLoadingArchived: false,  // สถานะโหลด
        
        // ✅ 1. เพิ่มตัวแปรนี้ (สำคัญมาก ไม่งั้น Alpine จะหาไม่เจอ)
        taskIsArchived: false, 

        // ==== List Modal ====
        listModalOpen: false,
        listModalMode: 'create',
        listTitle: '',
        listActionUrl: '',
        listDeleteOpen: false,
        listDeleteActionUrl: '',

        checklistItems: [],
        newChecklistItem: '',
        attachmentItems: [],
        taskId: null,

        // ==== Drag & Drop State ====
        draggingTaskId: null,
        draggingListId: null,

        // ==== Comment System ====
        currentTaskId: null,
        comments: [],
        newCommentText: '',
        isLoadingComments: false,
        //  Filter 
        searchQuery: '',      // เก็บข้อความที่พิมพ์
        filterMember: '',     // เก็บ ID สมาชิกที่เลือก
        filterLabel: '',      // เก็บ ID ป้ายกำกับที่เลือก
        // ประวัติการทำงาน
        activityDrawerOpen: false,
        activities: [],
        isLoadingActivities: false,
        menuOpen: false,

       async loadArchivedTasks(boardId) {
            this.archivedDrawerOpen = true; // เปิดลิ้นชักทันที
            this.isLoadingArchived = true;
            this.archivedTasks = [];

            try {
                const res = await fetch(`/board/${boardId}/archived-tasks/`);
                const data = await res.json();
                this.archivedTasks = data.tasks || [];
            } catch (err) {
                console.error("Error loading archived tasks:", err);
            } finally {
                this.isLoadingArchived = false;
            }
        },
        async loadActivities(boardId) {
            this.activityDrawerOpen = true;
            this.isLoadingActivities = true;
            this.activities = [];

            try {
                const res = await fetch(`/board/${boardId}/activities/`);
                const data = await res.json();
                this.activities = data.activities || [];
            } catch (err) {
                console.error("Error loading activities:", err);
            } finally {
                this.isLoadingActivities = false;
            }
        },

        // ✅ 3. ฟังก์ชันกู้คืนงาน (ใช้ API ตัวเดิมที่มีอยู่แล้วได้เลย)
        async restoreTask(taskId, csrfToken) {
            if(!confirm('ต้องการกู้คืนงานนี้กลับไปที่บอร์ด?')) return;
            
            // เรียกใช้ฟังก์ชัน toggleArchive ตัวเดิม (เพราะมันสลับ True <-> False ให้อยู่แล้ว)
            await this.toggleArchive(taskId, csrfToken);
            
            // หมายเหตุ: toggleArchive เดิมของเราสั่ง reload หน้าเว็บอยู่แล้ว 
            // ดังนั้นพอกู้คืนเสร็จ หน้าเว็บจะรีเฟรชและงานจะกลับมาเองครับ
        },
        // ------------------------------------------------------------------
        // ✅ Section 1: Comment Logic
        // ------------------------------------------------------------------
        
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

        async postComment() {
            if (!this.newCommentText.trim() || !this.currentTaskId) return;

            const content = this.newCommentText;
            this.newCommentText = ''; 

            const csrftoken = getCookie('csrftoken');

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
                    this.comments.unshift(newComment); 
                } else {
                    alert('ส่งคอมเมนต์ไม่สำเร็จ');
                    this.newCommentText = content; 
                }
            } catch (err) {
                console.error(err);
                this.newCommentText = content;
            }
        },

        // ------------------------------------------------------------------
        // ✅ Section 2: Archive Logic (ย้ายมาไว้ข้างในนี้)
        // ------------------------------------------------------------------
        async toggleArchive(taskId, csrfToken) {
            try {
                const response = await fetch(`/board/task/${taskId}/toggle-archive/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken }
                });
                const data = await response.json();

                if (data.success) {
                    // ใช้ this. เพื่ออ้างอิงตัวแปรใน Alpine scope
                    this.taskIsArchived = data.is_archived; 
                    this.taskModalOpen = false;
                    window.location.reload(); 
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Archive failed:', error);
            }
        },

        // ------------------------------------------------------------------
        // ✅ Section 3: Drag & Drop Logic
        // ------------------------------------------------------------------

        onDragStartTask(event, taskId) {
            this.draggingTaskId = taskId;
            this.draggingListId = null;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.dropEffect = 'move';
            event.target.classList.add('opacity-50', 'dragging');
        },

        onDragEndTask(event) {
            event.target.classList.remove('opacity-50', 'dragging');
            this.draggingTaskId = null;
        },

        onDragStartList(event, listId) {
            this.draggingListId = listId;
            this.draggingTaskId = null;
            event.dataTransfer.effectAllowed = 'move';
        },

        onDragOver(event) {
            if (this.draggingListId) {
                event.preventDefault();
                return;
            }

            if (this.draggingTaskId) {
                event.preventDefault();
                const container = event.currentTarget;
                const draggingEl = document.querySelector('.dragging');

                if (!draggingEl) return;

                const afterElement = this.getDragAfterElement(container, event.clientY);
                
                if (afterElement == null) {
                    container.appendChild(draggingEl);
                } else {
                    container.insertBefore(draggingEl, afterElement);
                }
            }
        },

        getDragAfterElement(container, y) {
            const draggableElements = [...container.querySelectorAll('[draggable="true"]:not(.dragging)')];

            return draggableElements.reduce((closest, child) => {
                const box = child.getBoundingClientRect();
                const offset = y - box.top - box.height / 2;
                
                if (offset < 0 && offset > closest.offset) {
                    return { offset: offset, element: child };
                } else {
                    return closest;
                }
            }, { offset: Number.NEGATIVE_INFINITY }).element;
        },

        async onDrop(event, listId) {
            const csrftoken = getCookie('csrftoken');

            // --- CASE A: วาง Task ---
            if (this.draggingTaskId && this.moveUrl) {
                event.preventDefault();
                const container = event.currentTarget;
                
                const taskElements = container.querySelectorAll('[data-task-id]');
                let orderedIds = [];
                taskElements.forEach(el => {
                    orderedIds.push(el.dataset.taskId);
                });

                const formData = new FormData();
                formData.append('task_id', this.draggingTaskId);
                formData.append('list_id', listId);
                formData.append('order', orderedIds.join(','));

              try {
                    const res = await fetch(this.moveUrl, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrftoken },
                        body: formData,
                    });
                    
                    if (!res.ok) {
                        console.error('Task move failed');
                        window.location.reload();
                    } else {
                        // ✅ เพิ่มบรรทัดนี้: ถ้าย้ายสำเร็จ ให้รีโหลดหน้าเพื่อซิงค์ข้อมูลล่าสุดจาก Server
                        window.location.reload(); 
                    }
                } catch (err) {
                    console.error(err);
                    alert("เกิดข้อผิดพลาดในการย้ายการ์ด"); // เพิ่ม Alert ให้รู้ถ้าเน็ตหลุด
                }
                
                this.draggingTaskId = null;
                return;
            }

            // --- CASE B: วาง List ---
            if (this.draggingListId && this.listMoveUrl) {
                const fromId = this.draggingListId;
                this.draggingListId = null;

                const formData = new FormData();
                formData.append('list_id', fromId);
                formData.append('target_id', listId);

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
};