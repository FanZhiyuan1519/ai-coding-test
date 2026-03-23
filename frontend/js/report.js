let currentReport = null;
let taskId = null;

async function loadReport() {
    const params = new URLSearchParams(window.location.search);
    taskId = params.get('task_id');

    if (!taskId) {
        showToast('缺少任务ID', 'error');
        setTimeout(() => window.location.href = 'index.html', 2000);
        return;
    }

    try {
        currentReport = await getReport(taskId);
        document.getElementById('taskId').textContent = `ZB-${String(taskId).padStart(2, '0')}`;
        document.getElementById('generatedAt').textContent = formatDateTime(currentReport.generated_at);
        renderOverallRisk();
        renderSimilarityMatrix();
        renderRiskItems();
        renderPriceAnalysis();
    } catch (error) {
        showToast(error.message, 'error');
        setTimeout(() => window.location.href = 'task.html?id=' + taskId, 2000);
    }
}

function renderOverallRisk() {
    const badge = document.getElementById('overallRiskBadge');
    const risk = currentReport.overall_risk;

    let bgClass, textClass, label;
    switch (risk) {
        case 'high':
            bgClass = 'bg-red-100';
            textClass = 'text-red-600';
            label = '高风险';
            break;
        case 'medium':
            bgClass = 'bg-yellow-100';
            textClass = 'text-yellow-600';
            label = '中风险';
            break;
        case 'low':
            bgClass = 'bg-green-100';
            textClass = 'text-green-600';
            label = '低风险';
            break;
        default:
            bgClass = 'bg-slate-100';
            textClass = 'text-slate-600';
            label = '未知';
    }

    badge.className = `inline-flex items-center gap-2 px-4 py-2 ${bgClass} ${textClass} text-sm font-bold rounded-full`;
    badge.innerHTML = `<span class="material-symbols-outlined text-lg">${risk === 'high' ? 'warning' : risk === 'medium' ? 'error' : 'check_circle'}</span>${label}`;
}

function renderSimilarityMatrix() {
    const matrix = currentReport.similarity_matrix;
    if (!matrix) return;

    const suppliers = Object.keys(matrix);
    const tbody = document.getElementById('matrixTableBody');
    const thead = document.getElementById('matrixTableHead');

    // Header
    thead.innerHTML = `
        <tr class="bg-teal-50 text-slate-600">
            <th class="p-4 text-xs font-bold uppercase tracking-wider text-left pl-6">投标单位</th>
            ${suppliers.map(s => `<th class="p-4 text-xs font-bold uppercase tracking-wider">${escapeHtml(s)}</th>`).join('')}
        </tr>
    `;

    // Body
    tbody.innerHTML = suppliers.map(rowSupplier => {
        return `
            <tr>
                <td class="p-4 font-bold text-left pl-6 bg-slate-50/30">${escapeHtml(rowSupplier)}</td>
                ${suppliers.map(colSupplier => {
                    if (rowSupplier === colSupplier) {
                        return `<td class="p-4 text-slate-300">-</td>`;
                    }
                    const value = matrix[rowSupplier][colSupplier];
                    return `<td class="p-4">
                        <div class="mx-auto w-12 h-12 flex items-center justify-center rounded-lg ${getSimilarityBgClass(value)} ${getSimilarityTextClass(value)} font-bold text-sm">
                            ${value.toFixed(1)}%
                        </div>
                    </td>`;
                }).join('')}
            </tr>
        `;
    }).join('');

    // Count high risk pairs
    let highRiskCount = 0;
    suppliers.forEach(a => {
        suppliers.forEach(b => {
            if (a < b && matrix[a] && matrix[a][b] && matrix[a][b] >= 70) {
                highRiskCount++;
            }
        });
    });
    document.getElementById('highRiskCount').textContent = `检出 ${highRiskCount} 对高风险项`;
}

function getSimilarityBgClass(value) {
    if (value >= 70) return 'bg-red-50';
    if (value >= 30) return 'bg-yellow-50';
    return 'bg-emerald-50';
}

function getSimilarityTextClass(value) {
    if (value >= 70) return 'text-red-600';
    if (value >= 30) return 'text-yellow-600';
    return 'text-emerald-600';
}

function renderRiskItems() {
    const container = document.getElementById('riskItemsContainer');
    const items = currentReport.risk_items;

    if (!items || items.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 text-slate-400">
                <span class="material-symbols-outlined text-4xl">check_circle</span>
                <p class="mt-2">未检测到明显风险项</p>
            </div>
        `;
        return;
    }

    // Key info match summary
    const keyInfoTableBody = document.getElementById('keyInfoTableBody');
    const keyInfoRows = [];
    const allFields = ['经营地址', '联系电话', '社会信用代码', '法人代表', '委托人姓名'];

    allFields.forEach(field => {
        const matchingPairs = [];
        items.forEach(item => {
            if (item.detail.key_info_match && item.detail.key_info_match.includes(field)) {
                matchingPairs.push(item.supplier_a, item.supplier_b);
            }
        });
        if (matchingPairs.length > 0) {
            const uniquePairs = [...new Set(matchingPairs)];
            keyInfoRows.push(`
                <tr class="hover:bg-slate-50 transition-colors">
                    <td class="p-4 text-sm font-medium pl-6">${field}</td>
                    ${uniquePairs.map(supplier => `<td class="p-4 text-sm text-slate-600">${escapeHtml(supplier)}</td>`).join('')}
                    ${suppliers.length - uniquePairs.length > 0 ? Array(suppliers.length - uniquePairs.length).fill('<td class="p-4 text-sm text-slate-400">-</td>').join('') : ''}
                    <td class="p-4">
                        <span class="px-2 py-0.5 bg-red-50 text-red-500 rounded text-[10px] font-bold">完全一致</span>
                    </td>
                </tr>
            `);
        }
    });

    if (keyInfoRows.length > 0) {
        keyInfoTableBody.innerHTML = keyInfoRows.join('');
        document.getElementById('keyInfoSection').classList.remove('hidden');
    } else {
        document.getElementById('keyInfoSection').classList.add('hidden');
    }

    // Risk item cards
    document.getElementById('riskItemCount').textContent = `检测到 ${items.length} 个风险项`;

    container.innerHTML = items.map((item, index) => `
        <div class="bg-slate-50 rounded-lg p-4 mb-4">
            <div class="flex items-start justify-between mb-3">
                <div class="flex items-center gap-3">
                    <span class="px-3 py-1 ${item.level === 'high' ? 'bg-red-100 text-red-600' : 'bg-yellow-100 text-yellow-600'} text-xs font-bold rounded-full">
                        ${item.level === 'high' ? '高风险' : '中风险'}
                    </span>
                    <span class="text-sm font-bold text-slate-700">${escapeHtml(item.supplier_a)} vs ${escapeHtml(item.supplier_b)}</span>
                </div>
                <button onclick="toggleRiskDetail(${index})" class="text-teal-600 text-xs font-bold hover:underline">
                    查看详情
                </button>
            </div>
            <p class="text-sm text-slate-600 leading-relaxed">${escapeHtml(item.reason)}</p>
            <div id="riskDetail${index}" class="hidden mt-4 pt-4 border-t border-slate-200">
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div class="bg-white rounded-lg p-3">
                        <div class="text-[10px] text-slate-400 mb-1">雷同比例</div>
                        <div class="text-lg font-bold ${item.detail.similarity_ratio >= 60 ? 'text-red-600' : 'text-yellow-600'}">${item.detail.similarity_ratio.toFixed(1)}%</div>
                    </div>
                    <div class="bg-white rounded-lg p-3">
                        <div class="text-[10px] text-slate-400 mb-1">最长连续相同</div>
                        <div class="text-lg font-bold text-slate-700">${item.detail.lcs_length} 字</div>
                    </div>
                    <div class="bg-white rounded-lg p-3">
                        <div class="text-[10px] text-slate-400 mb-1">报价相关系数</div>
                        <div class="text-lg font-bold ${item.detail.price_correlation && item.detail.price_correlation >= 0.99 ? 'text-red-600' : 'text-slate-700'}">
                            ${item.detail.price_correlation ? item.detail.price_correlation.toFixed(3) : '-'}
                        </div>
                    </div>
                    <div class="bg-white rounded-lg p-3">
                        <div class="text-[10px] text-slate-400 mb-1">关键信息匹配</div>
                        <div class="text-lg font-bold text-red-600">${item.detail.key_info_match ? item.detail.key_info_match.length : 0} 项</div>
                    </div>
                </div>
                ${item.detail.key_info_match && item.detail.key_info_match.length > 0 ? `
                    <div class="mt-3 flex flex-wrap gap-2">
                        ${item.detail.key_info_match.map(field => `<span class="px-2 py-1 bg-red-50 text-red-600 text-xs rounded">${field}</span>`).join('')}
                    </div>
                ` : ''}
                ${item.detail.price_values ? `
                    <div class="mt-3">
                        <div class="text-[10px] text-slate-400 mb-2">报价数据</div>
                        <div class="flex flex-wrap gap-4">
                            ${Object.entries(item.detail.price_values).map(([supplier, price]) => `
                                <div class="bg-white rounded px-3 py-2">
                                    <div class="text-[10px] text-slate-400">${escapeHtml(supplier)}</div>
                                    <div class="text-sm font-bold text-slate-700">${price !== null ? price.toLocaleString() + ' 元' : '-'}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
        </div>
    `).join('');
}

function toggleRiskDetail(index) {
    const detail = document.getElementById(`riskDetail${index}`);
    detail.classList.toggle('hidden');
}

function renderPriceAnalysis() {
    const items = currentReport.risk_items || [];
    const matrix = currentReport.similarity_matrix || {};

    // Collect all price values
    const priceData = {};
    let hasPriceData = false;

    items.forEach(item => {
        if (item.detail.price_values) {
            Object.entries(item.detail.price_values).forEach(([supplier, price]) => {
                if (!priceData[supplier]) {
                    priceData[supplier] = price;
                }
                if (price !== null) hasPriceData = true;
            });
        }
    });

    if (!hasPriceData) {
        document.getElementById('priceAnalysisSection').classList.add('hidden');
        return;
    }

    document.getElementById('priceAnalysisSection').classList.remove('hidden');

    // Find max price for chart scaling
    const prices = Object.values(priceData).filter(p => p !== null);
    const maxPrice = Math.max(...prices);

    // Render price cards
    const container = document.getElementById('priceCards');
    container.innerHTML = Object.entries(priceData).map(([supplier, price]) => {
        const heightPercent = price !== null ? (price / maxPrice * 100) : 0;
        const isAbnormal = items.some(item =>
            item.detail.price_values && item.detail.price_values[supplier] !== null &&
            item.detail.price_correlation && item.detail.price_correlation >= 0.99
        );

        return `
            <div class="flex flex-col items-center flex-1">
                <div class="w-full ${isAbnormal ? 'bg-red-400' : 'bg-teal-400'} rounded-t transition-all relative" style="height: ${heightPercent}%">
                    ${isAbnormal ? '<div class="absolute -top-6 left-1/2 -translate-x-1/2 text-[10px] font-bold text-red-500">异常</div>' : ''}
                </div>
                <span class="text-[10px] mt-2 font-medium text-slate-500">${escapeHtml(supplier)}</span>
                <span class="text-[10px] font-bold ${isAbnormal ? 'text-red-600' : 'text-slate-600'}">
                    ${price !== null ? (price / 10000).toFixed(1) + '万' : '-'}
                </span>
            </div>
        `;
    }).join('');

    // Show correlation info
    const correlationItems = items.filter(item => item.detail.price_correlation !== null);
    if (correlationItems.length > 0) {
        const avgCorrelation = correlationItems.reduce((sum, item) => sum + item.detail.price_correlation, 0) / correlationItems.length;
        document.getElementById('correlationInfo').innerHTML = `
            <div class="p-4 bg-white/5 rounded-lg border border-white/10">
                <h4 class="text-xs font-bold text-red-300 mb-2">报价相关性分析</h4>
                <p class="text-[11px] leading-relaxed text-slate-300">
                    检测到平均报价相关系数为 <span class="text-red-300 font-bold">${avgCorrelation.toFixed(3)}</span>，
                    ${avgCorrelation >= 0.99 ? '存在高度相关性，存在报价串通嫌疑' : '相关性较高，需进一步核查'}
                </p>
            </div>
        `;
    }
}

function goBack() {
    window.location.href = `task.html?id=${taskId}`;
}

function formatDateTime(dateStr) {
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
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

document.addEventListener('DOMContentLoaded', loadReport);
