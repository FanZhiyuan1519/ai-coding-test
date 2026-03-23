const API_BASE = '/api/v1';

async function request(url, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${url}`, {
            ...options,
            headers: {
                ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
                ...options.headers,
            },
        });

        if (response.status === 204) {
            return null;
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || `请求失败 (${response.status})`);
        }

        return data;
    } catch (error) {
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
            throw new Error('网络连接失败，请检查服务器是否正常运行');
        }
        throw error;
    }
}

// ==================== 任务相关 ====================

async function getTasks(page = 1, limit = 10) {
    return request(`/tasks?page=${page}&limit=${limit}`);
}

async function getTask(taskId) {
    return request(`/tasks/${taskId}`);
}

async function createTask(name) {
    return request('/tasks', {
        method: 'POST',
        body: JSON.stringify({ name }),
    });
}

async function deleteTask(taskId) {
    return request(`/tasks/${taskId}`, { method: 'DELETE' });
}

// ==================== 文件相关 ====================

async function uploadDocument(taskId, file, supplierName, onProgress) {
    const formData = new FormData();
    formData.append('supplier_name', supplierName);
    formData.append('file', file);

    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${API_BASE}/tasks/${taskId}/documents`);

        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable && onProgress) {
                const percent = Math.round((e.loaded / e.total) * 100);
                onProgress(percent);
            }
        };

        xhr.onload = () => {
            try {
                const data = JSON.parse(xhr.responseText);
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(data);
                } else {
                    reject(new Error(data.detail || `上传失败 (${xhr.status})`));
                }
            } catch {
                reject(new Error('解析响应失败'));
            }
        };

        xhr.onerror = () => reject(new Error('网络连接失败'));

        xhr.send(formData);
    });
}

// ==================== 比对相关 ====================

async function runCompare(taskId) {
    return request(`/tasks/${taskId}/run`, { method: 'POST' });
}

// ==================== 报告相关 ====================

async function getReport(taskId) {
    return request(`/reports/task/${taskId}`);
}
