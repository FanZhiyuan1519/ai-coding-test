let currentPage = 1;
let totalPages = 1;
let pollingIntervals = {};

async function loadTasks(page = 1) {
    try {
        const data = await getTasks(page);
        currentPage = data.page;
        totalPages = data.total_pages;
        renderTasks(data.items);
        renderPagination(data);
        startPolling(data.items);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function renderTasks(tasks) {
    const tbody = document.getElementById('taskTableBody');
    if (!tbody) return;

    if (tasks.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="px-6 py-12 text-center text-slate-400">
                    暂无任务，点击上方"新建比对任务"开始
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = tasks.map(task => {
        const statusHtml = getStatusHtml(task);
        const taskId = `BD-${String(task.id).padStart(2, '0')}`;
        return `
            <tr class="hover:bg-slate-50 transition-colors">
                <td class="px-6 py-5 text-sm font-mono text-slate-500">${taskId}</td>
                <td class="px-6 py-5 text-sm font-semibold">${escapeHtml(task.name)}</td>
                <td class="px-6 py-5 text-sm text-slate-500">${formatDate(task.created_at)}</td>
                <td class="px-6 py-5">${statusHtml}</td>
                <td class="px-6 py-5 text-right space-x-4">
                    <button onclick="goToTaskDetail(${task.id})" class="text-primary hover:text-primary/80 text-sm font-bold">查看详情</button>
                    ${task.status === 'failed' ? `<button onclick="restartTask(${task.id})" class="text-primary hover:text-primary/80 text-sm font-bold">重新开始</button>` : ''}
                    <button onclick="confirmDelete(${task.id}, '${escapeHtml(task.name).replace(/'/g, "\\'")}')" class="text-red-500 hover:text-red-600 text-sm font-bold">删除</button>
                </td>
            </tr>
        `;
    }).join('');
}

function getStatusHtml(task) {
    switch (task.status) {
        case 'pending':
            return `<span class="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-100 text-slate-500 text-xs font-bold rounded-full">
                <span class="w-1.5 h-1.5 bg-slate-500 rounded-full"></span>等待中
            </span>`;
        case 'processing':
            return `<div class="flex flex-col gap-1.5 w-48">
                <div class="flex justify-between text-[10px] font-bold text-primary">
                    <span>${getProgressLabel(task.progress)}</span>
                    <span>${task.progress}%</span>
                </div>
                <div class="w-full bg-primary/10 rounded-full h-1.5">
                    <div class="bg-primary h-1.5 rounded-full" style="width: ${task.progress}%"></div>
                </div>
            </div>`;
        case 'completed':
            return `<span class="inline-flex items-center gap-1.5 px-3 py-1 bg-green-50 text-green-600 text-xs font-bold rounded-full">
                <span class="w-1.5 h-1.5 bg-green-600 rounded-full"></span>比对完成
            </span>`;
        case 'failed':
            return `<span class="inline-flex items-center gap-1.5 px-3 py-1 bg-red-50 text-red-600 text-xs font-bold rounded-full">
                <span class="w-1.5 h-1.5 bg-red-600 rounded-full"></span>处理失败
            </span>`;
        default:
            return '';
    }
}

function getProgressLabel(progress) {
    if (progress < 10) return '准备中';
    if (progress < 60) return '提取内容中';
    if (progress < 75) return '算法检测中';
    if (progress < 90) return 'AI分析中';
    return '生成报告中';
}

function startPolling(tasks) {
    Object.values(pollingIntervals).forEach(clearInterval);
    pollingIntervals = {};

    tasks.filter(t => t.status === 'processing').forEach(task => {
        pollingIntervals[task.id] = setInterval(async () => {
            try {
                const updated = await getTask(task.id);
                if (updated.status !== 'processing') {
                    clearInterval(pollingIntervals[task.id]);
                    delete pollingIntervals[task.id];
                    loadTasks(currentPage);
                } else {
                    updateTaskRow(updated);
                }
            } catch (error) {
                clearInterval(pollingIntervals[task.id]);
                delete pollingIntervals[task.id];
            }
        }, 10000);
    });
}

function updateTaskRow(task) {
    const rows = document.querySelectorAll('#taskTableBody tr');
    rows.forEach(row => {
        const btns = row.querySelectorAll('button');
        btns.forEach(btn => {
            if (btn.textContent === '查看详情' && btn.getAttribute('onclick')?.includes(`(${task.id})`)) {
                const statusCell = row.querySelector('td:nth-child(4)');
                if (statusCell) {
                    statusCell.innerHTML = getStatusHtml(task);
                }
            }
        });
    });
}

function renderPagination(data) {
    const container = document.getElementById('pagination');
    const totalText = document.getElementById('totalText');
    if (!container) return;

    if (totalText) {
        const start = (data.page - 1) * data.limit + 1;
        const end = Math.min(data.page * data.limit, data.total);
        totalText.textContent = `显示 ${start} 到 ${end} 条，共 ${data.total} 条任务`;
    }

    let html = '';
    html += `<button onclick="loadTasks(${currentPage - 1})" class="p-1.5 rounded border border-slate-200 hover:bg-slate-50" ${currentPage <= 1 ? 'disabled' : ''}>
        <span class="material-symbols-outlined text-sm">chevron_left</span>
    </button>`;

    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
            html += `<button onclick="loadTasks(${i})" class="w-8 h-8 rounded ${i === currentPage ? 'bg-primary text-white' : 'border border-slate-200 hover:bg-slate-50'} text-xs font-medium">${i}</button>`;
        } else if (i === currentPage - 2 || i === currentPage + 2) {
            html += `<span class="text-slate-400">...</span>`;
        }
    }

    html += `<button onclick="loadTasks(${currentPage + 1})" class="p-1.5 rounded border border-slate-200 hover:bg-slate-50" ${currentPage >= totalPages ? 'disabled' : ''}>
        <span class="material-symbols-outlined text-sm">chevron_right</span>
    </button>`;

    container.innerHTML = html;
}

function openCreateModal() {
    document.getElementById('createModal').classList.remove('hidden');
    document.getElementById('taskNameInput').value = '';
    document.getElementById('taskNameInput').focus();
}

function closeCreateModal() {
    document.getElementById('createModal').classList.add('hidden');
}

async function handleCreateTask() {
    const name = document.getElementById('taskNameInput').value.trim();
    if (!name) {
        showToast('请输入任务名称', 'error');
        return;
    }

    try {
        await createTask(name);
        closeCreateModal();
        showToast('任务创建成功', 'success');
        loadTasks(currentPage);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function confirmDelete(taskId, taskName) {
    document.getElementById('deleteTaskId').value = taskId;
    document.getElementById('deleteTaskName').textContent = taskName;
    document.getElementById('deleteModal').classList.remove('hidden');
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
}

async function handleDeleteTask() {
    const taskId = document.getElementById('deleteTaskId').value;
    try {
        await deleteTask(taskId);
        closeDeleteModal();
        showToast('任务删除成功', 'success');
        if (pollingIntervals[taskId]) {
            clearInterval(pollingIntervals[taskId]);
            delete pollingIntervals[taskId];
        }
        loadTasks(currentPage);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function goToTaskDetail(taskId) {
    window.location.href = `task.html?id=${taskId}`;
}

async function restartTask(taskId) {
    try {
        await runCompare(taskId);
        showToast('任务已重新启动', 'success');
        loadTasks(currentPage);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    const bgColor = type === 'success' ? 'bg-green-600' : type === 'error' ? 'bg-red-600' : 'bg-slate-600';
    toast.className = `${bgColor} text-white px-6 py-3 rounded-lg shadow-lg mb-2`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function formatDate(dateStr) {
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', () => {
    loadTasks(1);
});
