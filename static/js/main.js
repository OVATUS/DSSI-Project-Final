// static/js/main.js

// ✅ ฟังก์ชันช่วยดึง Cookie (แก้ปัญหา CSRF Token)
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

function boardDetailPage(config) {
    return {
        // ==== Configuration ====
        moveUrl: (config && config.moveUrl) ? config.moveUrl : '',
        listMoveUrl: (config && config.listMoveUrl) ? config.listMoveUrl : '',

        // ==== Member & UI ====
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

        // ==== List Modal ====
        listModalOpen: false,
        listModalMode: 'create',
        listTitle: '',
        listActionUrl: '',
        listDeleteOpen: false,
        listDeleteActionUrl: '',

        // ==== Drag & Drop State ====
        draggingTaskId: null,
        draggingListId: null,

        // ==== Comment System ====
        currentTaskId: null,
        comments: [],
        newCommentText: '',
        isLoadingComments: false,

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
            this.newCommentText = ''; // เคลียร์ช่องพิมพ์ทันที UX จะดูลื่นขึ้น

            const csrftoken = getCookie('csrftoken'); // ใช้ฟังก์ชันใหม่

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
                    this.comments.unshift(newComment); // แทรกบนสุด
                } else {
                    alert('ส่งคอมเมนต์ไม่สำเร็จ');
                    this.newCommentText = content; // คืนค่าถ้าส่งพลาด
                }
            } catch (err) {
                console.error(err);
                this.newCommentText = content;
            }
        },

        // ------------------------------------------------------------------
        // ✅ Section 2: Drag & Drop Logic (Task Reordering)
        // ------------------------------------------------------------------

        // 1. เริ่มลาก Task
        onDragStartTask(event, taskId) {
            this.draggingTaskId = taskId;
            this.draggingListId = null;
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.dropEffect = 'move';
            
            // เพิ่ม class เพื่อให้รู้ว่าตัวไหนกำลังถูกลาก (Visual)
            event.target.classList.add('opacity-50', 'dragging');
        },

        // 2. ลากเสร็จ (ไม่ว่าจะวางได้หรือไม่)
        onDragEndTask(event) {
            event.target.classList.remove('opacity-50', 'dragging');
            this.draggingTaskId = null;
        },

        // 3. เริ่มลาก List
        onDragStartList(event, listId) {
            this.draggingListId = listId;
            this.draggingTaskId = null;
            event.dataTransfer.effectAllowed = 'move';
        },

        // 4. ขณะลากผ่านลิสต์ (หัวใจสำคัญ: คำนวณตำแหน่ง Real-time)
        onDragOver(event) {
            // ถ้ากำลังลาก List อยู่ ไม่ต้องทำ logic แทรกการ์ด
            if (this.draggingListId) {
                event.preventDefault();
                return;
            }

            // ถ้ากำลังลาก Task
            if (this.draggingTaskId) {
                event.preventDefault(); // อนุญาตให้ Drop ได้

                const container = event.currentTarget; // div.task-container
                const draggingEl = document.querySelector('.dragging');

                if (!draggingEl) return;

                // คำนวณตำแหน่งที่จะแทรก
                const afterElement = this.getDragAfterElement(container, event.clientY);
                
                // ย้าย DOM จริงๆ ไปวางตรงนั้นเลย
                if (afterElement == null) {
                    container.appendChild(draggingEl);
                } else {
                    container.insertBefore(draggingEl, afterElement);
                }
            }
        },

        // 5. Helper: หา Element ที่อยู่ถัดไปจากตำแหน่งเมาส์
        getDragAfterElement(container, y) {
            // เอาการ์ดทุกใบในลิสต์ ยกเว้นใบที่เรากำลังลาก
            const draggableElements = [...container.querySelectorAll('[draggable="true"]:not(.dragging)')];

            return draggableElements.reduce((closest, child) => {
                const box = child.getBoundingClientRect();
                const offset = y - box.top - box.height / 2;
                
                // ถ้า offset เป็นลบ (อยู่เหนือ) และใกล้ที่สุดเท่าที่หาเจอ
                if (offset < 0 && offset > closest.offset) {
                    return { offset: offset, element: child };
                } else {
                    return closest;
                }
            }, { offset: Number.NEGATIVE_INFINITY }).element;
        },

        // 6. วาง (Save ลง Database)
        async onDrop(event, listId) {
            const csrftoken = getCookie('csrftoken');

            // --- CASE A: วาง Task (บันทึกลำดับใหม่) ---
            if (this.draggingTaskId && this.moveUrl) {
                event.preventDefault();

                const container = event.currentTarget;
                
                // 1. กวาด ID ทั้งหมดในลิสต์นี้มาเรียงต่อกัน
                const taskElements = container.querySelectorAll('[data-task-id]');
                let orderedIds = [];
                taskElements.forEach(el => {
                    orderedIds.push(el.dataset.taskId);
                });

                // 2. ส่งข้อมูลไป Backend
                const formData = new FormData();
                formData.append('task_id', this.draggingTaskId);
                formData.append('list_id', listId);
                formData.append('order', orderedIds.join(',')); // เช่น "10,5,8"

                try {
                    const res = await fetch(this.moveUrl, {
                        method: 'POST',
                        headers: { 'X-CSRFToken': csrftoken },
                        body: formData,
                    });
                    
                    if (!res.ok) {
                        console.error('Task move failed');
                        window.location.reload(); // ถ้าพัง ให้รีโหลดเพื่อคืนค่า
                    }
                    // ถ้าสำเร็จ ไม่ต้อง reload เพราะหน้าขยับไปแล้ว
                } catch (err) {
                    console.error(err);
                }
                
                this.draggingTaskId = null;
                return;
            }

            // --- CASE B: วาง List (สลับคอลัมน์) ---
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
                    window.location.reload(); // ลิสต์สลับต้องรีโหลดเพื่อให้แสดงผลถูกต้อง
                } catch (err) {
                    console.error(err);
                }
            }
        },
    };
}