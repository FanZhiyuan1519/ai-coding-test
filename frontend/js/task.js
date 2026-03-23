let currentTask = null;
let pollingInterval = null;

async function loadTask() {
    const params = new URLSearchParams(window.location.search);
    const taskId = params.get('id');

    if (!taskId) {
        showToast('缺少任务ID', 'error');
        setTimeout(() => window.location.href = 'index.html', 2000);
        return;
    }

    try {
        currentTask = await getTask(taskId);
        renderTaskInfo();
        renderDocuments();
        startPolling();
    } catch (error) {
        showToast(error.message, 'error');
        setTimeout(() => window.location.href = 'index.html', 2000);
    }
}

function renderTaskInfo() {
    document.getElementById('taskName').textContent = currentTask.name;
    document.getElementById('taskId').textContent = `BD-${String(currentTask.id).padStart(2, '0')}`;
    document.getElementById('taskCreatedAt').textContent = formatDateTime(currentTask.created_at);

    const statusBadge = document.getElementById('taskStatusBadge');
    statusBadge.innerHTML = getStatusBadge(currentTask.status, currentTask.progress);

    const progressSection = document.getElementById('progressSection');
    if (currentTask.status === 'processing') {
        progressSection.classList.remove('hidden');
        document.getElementById('progressBar').style.width = `${currentTask.progress}%`;
        document.getElementById('progressText').textContent = `${currentTask.progress}% - ${getProgressLabel(currentTask.progress)}`;
    } else {
        progressSection.classList.add('hidden');
    }

    const uploadSection = document.getElementById('uploadSection');
    const runSection = document.getElementById('runSection');
    const reportSection = document.getElementById('reportSection');

    if (currentTask.status === 'pending' || currentTask.status === 'failed') {
        uploadSection.classList.remove('hidden');
        runSection.classList.remove('hidden');
        reportSection.classList.add('hidden');
    } else if (currentTask.status === 'processing') {
        uploadSection.classList.add('hidden');
        runSection.classList.add('hidden');
        reportSection.classList.add('hidden');
    } else if (currentTask.status === 'completed') {
        uploadSection.classList.add('hidden');
        runSection.classList.add('hidden');
        reportSection.classList.remove('hidden');
    }
}

function renderDocuments() {
    const tbody = document.getElementById('documentsTableBody');
    const docCount = document.getElementById('docCount');

    if (docCount) {
        docCount.textContent = `${currentTask.documents.length} 份`;
    }

    if (currentTask.documents.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="px-6 py-10 text-center text-slate-400">
                    暂无上传文件，请上传至少 2 份投标文件
                </td>
            </tr>
        `;
        updateRunButton();
        return;
    }

    tbody.innerHTML = currentTask.documents.map(doc => `
        <tr class="hover:bg-slate-50 transition-colors">
            <td class="px-6 py-4 text-sm font-medium">${escapeHtml(doc.supplier_name)}</td>
            <td class="px-6 py-4 text-sm text-slate-600">${escapeHtml(doc.original_filename)}</td>
            <td class="px-6 py-4 text-sm text-slate-500">${doc.file_size ? formatFileSize(doc.file_size) : '-'}</td>
            <td class="px-6 py-4 text-sm text-slate-500">${formatDateTime(doc.uploaded_at)}</td>
            <td class="px-6 py-4 text-right">
                <span class="text-xs ${doc.extracted_text ? 'text-green-600' : 'text-slate-400'}">
                    ${doc.extracted_text ? '已提取' : '待提取'}
                </span>
            </td>
        </tr>
    `).join('');

    updateRunButton();
}

function updateRunButton() {
    const btn = document.getElementById('runBtn');
    const canRun = currentTask.documents.length >= 2 && currentTask.status !== 'processing';
    btn.disabled = !canRun;
    btn.classList.toggle('opacity-50', !canRun);
    btn.classList.toggle('cursor-not-allowed', !canRun);
}

async function handleFileUpload() {
    const supplierName = document.getElementById('supplierNameInput').value.trim();
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];

    if (!supplierName) {
        showToast('请输入供应商名称', 'error');
        return;
    }

    if (!file) {
        showToast('请选择文件', 'error');
        return;
    }

    const allowedTypes = ['.txt', '.pdf', '.docx'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowedTypes.includes(ext)) {
        showToast('仅支持 .txt、.pdf、.docx 格式文件', 'error');
        return;
    }

    const progressContainer = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('uploadBar');
    const progressText = document.getElementById('uploadProgressText');
    progressContainer.classList.remove('hidden');

    try {
        await uploadDocument(currentTask.id, file, supplierName, (percent) => {
            progressBar.style.width = `${percent}%`;
            progressText.textContent = `${percent}%`;
        });

        showToast('文件上传成功', 'success');
        document.getElementById('supplierNameInput').value = '';
        fileInput.value = '';
        progressContainer.classList.add('hidden');
        progressBar.style.width = '0%';

        currentTask = await getTask(currentTask.id);
        renderDocuments();
    } catch (error) {
        showToast(error.message, 'error');
        progressContainer.classList.add('hidden');
    }
}

async function handleRunCompare() {
    if (currentTask.documents.length < 2) {
        showToast('至少需要上传 2 份投标文件', 'error');
        return;
    }

    try {
        await runCompare(currentTask.id);
        showToast('比对任务已启动', 'success');
        currentTask.status = 'processing';
        currentTask.progress = 0;
        renderTaskInfo();
        startPolling();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function startPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
    }

    pollingInterval = setInterval(async () => {
        try {
            const updated = await getTask(currentTask.id);
            currentTask = updated;

            renderTaskInfo();

            if (updated.status !== 'processing') {
                clearInterval(pollingInterval);
                pollingInterval = null;
            }
        } catch (error) {
            console.error('轮询失败:', error);
        }
    }, 10000);
}

function goToReport() {
    window.location.href = `report.html?task_id=${currentTask.id}`;
}

function goBack() {
    window.location.href = 'index.html';
}

function getStatusBadge(status, progress) {
    switch (status) {
        case 'pending':
            return `<span class="px-3 py-1 bg-slate-100 text-slate-600 text-xs font-bold rounded-full">等待中</span>`;
        case 'processing':
            return `<span class="px-3 py-1 bg-teal-100 text-teal-600 text-xs font-bold rounded-full">处理中 ${progress}%</span>`;
        case 'completed':
            return `<span class="px-3 py-1 bg-green-100 text-green-600 text-xs font-bold rounded-full">比对完成</span>`;
        case 'failed':
            return `<span class="px-3 py-1 bg-red-100 text-red-600 text-xs font-bold rounded-full">处理失败</span>`;
        default:
            return '';
    }
}

function getProgressLabel(progress) {
    if (progress < 10) return '准备开始';
    if (progress < 60) return '提取文件内容中';
    if (progress < 75) return '算法检测中';
    if (progress < 90) return 'AI 分析中';
    return '生成报告';
}

function formatDateTime(dateStr) {
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
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

// 文件选择事件
document.getElementById('fileInput')?.addEventListener('change', function() {
    const fileName = this.files[0]?.name || '未选择文件';
    document.getElementById('fileNameDisplay').textContent = fileName;
});

document.addEventListener('DOMContentLoaded', loadTask);
