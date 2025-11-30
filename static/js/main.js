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


