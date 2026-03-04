// ---------------------------------------------------------------------------
// Theme toggle (shared across all pages)
// ---------------------------------------------------------------------------
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-bs-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-bs-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    // Hook for pages that need extra work (e.g. chart colours)
    if (typeof onThemeChanged === 'function') {
        onThemeChanged(newTheme);
    }
}

function updateThemeIcon(theme) {
    const lightIcon = document.getElementById('theme-icon-light');
    const darkIcon = document.getElementById('theme-icon-dark');
    if (!lightIcon || !darkIcon) return;
    if (theme === 'dark') {
        lightIcon.classList.add('d-none');
        darkIcon.classList.remove('d-none');
    } else {
        lightIcon.classList.remove('d-none');
        darkIcon.classList.add('d-none');
    }
}

// Apply saved theme immediately (before DOMContentLoaded)
(function() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-bs-theme', savedTheme);
    // Icon update deferred until DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            updateThemeIcon(savedTheme);
        });
    } else {
        updateThemeIcon(savedTheme);
    }
})();

// ---------------------------------------------------------------------------
// Collapsible chart headers – toggle collapse on click, but ignore clicks
// that land on buttons, inputs, labels or other controls in the header.
// ---------------------------------------------------------------------------
document.addEventListener('click', function(e) {
    const header = e.target.closest('.chart-collapse-header');
    if (!header) return;
    // Ignore clicks inside the controls area
    if (e.target.closest('.chart-header-controls')) return;
    const targetId = header.getAttribute('aria-controls');
    const body = document.getElementById(targetId);
    if (!body) return;
    const collapse = bootstrap.Collapse.getOrCreateInstance(body, {toggle: false});
    collapse.toggle();
    // Update aria-expanded
    const expanded = header.getAttribute('aria-expanded') === 'true';
    header.setAttribute('aria-expanded', String(!expanded));
});

// ---------------------------------------------------------------------------
// Shared URL hash helpers – read/modify/write individual params without
// clobbering unrelated ones (e.g. tab, cols, cm, log all coexist).
// ---------------------------------------------------------------------------
function _hashParams() {
    return new URLSearchParams(location.hash.slice(1));
}

function _hashSet(key, value) {
    const params = _hashParams();
    if (value === null || value === undefined || value === '') {
        params.delete(key);
    } else {
        params.set(key, value);
    }
    history.replaceState(null, '', '#' + params.toString());
}

function _parseChartHash(colsKey, logKey) {
    const params = _hashParams();
    const colParam = params.get(colsKey);
    const columns = colParam ? colParam.split(',').filter(Boolean) : null;
    const log = params.get(logKey) === '1';
    return { columns, log };
}

function _updateChartHash(checkboxSelector, logCheckboxId, colsKey, logKey) {
    const selected = [];
    document.querySelectorAll(checkboxSelector + ':checked').forEach(cb => {
        selected.push(cb.dataset.column);
    });
    const logCb = document.getElementById(logCheckboxId);
    const useLog = logCb && logCb.checked;

    const params = _hashParams();
    if (selected.length > 0) {
        params.set(colsKey, selected.join(','));
    } else {
        params.delete(colsKey);
    }
    if (useLog) {
        params.set(logKey, '1');
    } else {
        params.delete(logKey);
    }
    history.replaceState(null, '', '#' + params.toString());
}

// ---------------------------------------------------------------------------
// Tab persistence – save active tab in URL hash, restore on page load.
// Works on both protocol and report pages.
// ---------------------------------------------------------------------------
document.addEventListener('shown.bs.tab', function(e) {
    const tabId = e.target.id;  // e.g. "chart-tab", "config-tab"
    if (tabId) _hashSet('tab', tabId);
});

document.addEventListener('DOMContentLoaded', function() {
    const params = _hashParams();
    const tabId = params.get('tab');
    if (tabId) {
        const tabEl = document.getElementById(tabId);
        if (tabEl) {
            const tab = new bootstrap.Tab(tabEl);
            tab.show();
        }
    }

    // Preserve query string + hash when switching language
    document.querySelectorAll('.btn-lang').forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = link.getAttribute('href') + location.search + location.hash;
        });
    });
});


// ---------------------------------------------------------------------------
// Shared chart infrastructure – colors, factory, helpers
// ---------------------------------------------------------------------------
const CHART_COLORS = [
    '#0d6efd', '#fd7e14', '#198754', '#dc3545', '#6f42c1',
    '#20c997', '#ffc107', '#0dcaf0', '#d63384', '#6c757d',
    '#0b5ed7', '#e35d13', '#157347', '#bb2d3b', '#5a32a3',
    '#1aa179', '#e0a800', '#0aa2c0', '#b52b6a', '#565e64',
    '#3d8bfd', '#ff922b', '#2dce89', '#f5365c', '#8965e0',
    '#4fd1c5', '#ffcb6b', '#45d0ff', '#e8569a', '#8898aa',
];

/**
 * Create (or recreate) a time-series Chart.js line chart.
 *
 * @param {Object} cfg
 * @param {string}        cfg.canvasId           - canvas element id
 * @param {Chart|null}    cfg.prevChart          - previous Chart instance to destroy (or null)
 * @param {Array}         cfg.labels             - x-axis labels
 * @param {Array}         cfg.datasets           - Chart.js dataset objects
 * @param {string}        cfg.titleText          - chart title
 * @param {boolean}       cfg.useLog             - use logarithmic y-axis
 * @param {Function}      [cfg.xTickCallback]    - custom x-axis tick callback
 * @param {Function}      [cfg.tooltipTitleCallback] - custom tooltip title callback
 * @param {number}        [cfg.xMaxTicksLimit]   - max x-axis tick count
 * @returns {Chart}       the new Chart instance
 */
function _createTimeSeriesChart(cfg) {
    const canvas = document.getElementById(cfg.canvasId);
    if (!canvas) return null;

    if (cfg.prevChart) {
        cfg.prevChart.destroy();
    }

    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    const textColor = isDark ? '#f0f0f0' : '#212529';
    const gridColor = isDark ? '#3a3a3a' : '#dee2e6';

    const yScale = {
        display: true,
        ticks: { color: textColor },
        grid: { color: gridColor },
    };
    if (cfg.useLog) {
        yScale.type = 'logarithmic';
    }

    const xTicks = { color: textColor };
    if (cfg.xTickCallback) xTicks.callback = cfg.xTickCallback;
    if (cfg.xMaxTicksLimit) xTicks.maxTicksLimit = cfg.xMaxTicksLimit;

    const tooltipCallbacks = {};
    if (cfg.tooltipTitleCallback) {
        tooltipCallbacks.title = cfg.tooltipTitleCallback;
    }

    return new Chart(canvas, {
        type: 'line',
        data: { labels: cfg.labels, datasets: cfg.datasets },
        options: {
            animation: false,
            maintainAspectRatio: false,
            elements: { point: { radius: 0 } },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                title: {
                    display: true,
                    text: cfg.titleText,
                    color: textColor,
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: tooltipCallbacks,
                },
                legend: {
                    labels: { color: textColor, font: { size: 11 } },
                    position: 'bottom',
                },
                zoom: {
                    zoom: {
                        drag: {
                            enabled: true,
                            backgroundColor: 'rgba(85, 85, 85, 0.3)',
                            borderColor: 'rgba(85, 85, 85, 0.8)',
                            borderWidth: 1,
                            threshold: 20,
                        },
                        wheel: { enabled: false },
                        mode: 'xy',
                    },
                    pan: {
                        enabled: true,
                        mode: 'xy',
                        modifierKey: 'ctrl',
                        threshold: 5,
                    }
                }
            },
            scales: {
                x: {
                    display: true,
                    ticks: xTicks,
                    grid: { color: gridColor }
                },
                y: yScale
            }
        }
    });
}

/**
 * Build a single Chart.js dataset object from raw data.
 */
function _chartDataset(label, data, colorIdx) {
    const color = CHART_COLORS[colorIdx % CHART_COLORS.length];
    return {
        label: label,
        data: data,
        borderColor: color,
        backgroundColor: color + '33',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0,
        fill: false,
    };
}

/**
 * Select/deselect all checkboxes in a container and re-render the chart.
 */
function chartSelectAll(checkboxSelector, checked, renderFn) {
    document.querySelectorAll(checkboxSelector).forEach(cb => {
        cb.checked = checked;
    });
    renderFn();
}

/**
 * Reset zoom on a Chart.js instance.
 */
function chartResetZoom(chartRef) {
    if (chartRef) chartRef.resetZoom();
}

function _detectHwVersion(json) {
    // Detect hardware version from report/protocol JSON.
    // Returns the Version IntFlag value matching the api_doc_generator Version enum.
    const VERSION_MAP = {
        'warp':  1,  // WARP1
        'warp2': 2,  // WARP2
        'warp3': 4,  // WARP3
        'wem':   8,  // WEM
        'wem2':  16, // WEM2
    };
    const deviceType = json?.['info/name']?.type;
    if (deviceType && VERSION_MAP[deviceType] !== undefined) {
        return VERSION_MAP[deviceType];
    }
    return -1; // ANY
}

function _resolveFieldEntry(node, apiDocs) {
    // Resolve the API doc entry for a leaf node.
    // Returns {fieldEntry, apiPath} or null if not found.
    const fieldKey = node.key;
    if (fieldKey === undefined || fieldKey === null) return null;

    let apiPath = null;
    let isArrayChild = false;
    let current = node.parent;
    while (current) {
        if (current.key !== undefined && current.key !== null) {
            if (typeof current.key === 'string' && current.key.includes('/')) {
                apiPath = current.key;
                break;
            }
            if (!isNaN(current.key)) {
                isArrayChild = true;
            }
        }
        current = current.parent;
    }

    if (!apiPath) return null;

    const pathDocs = apiDocs[apiPath];
    if (!pathDocs) return null;

    let fieldEntry = pathDocs[fieldKey];
    if (!fieldEntry && isArrayChild && pathDocs._array_members) {
        fieldEntry = pathDocs._array_members[fieldKey];
    }

    if (!fieldEntry || typeof fieldEntry !== 'object' || Array.isArray(fieldEntry)) return null;

    return { fieldEntry, apiPath };
}

function _annotateTree(tree, apiDocs, hwVersion) {
    // Single-pass tree traversal that annotates leaf values with constant
    // descriptions, unit abbreviations, and clickable info buttons.
    jsonview.traverse(tree, function(node) {
        if (!node.el) return;

        // Handle censored null values: show explanatory text instead of "null"
        if (node.value === null || node.value === undefined) {
            const resolved = _resolveFieldEntry(node, apiDocs);
            if (resolved && resolved.fieldEntry && resolved.fieldEntry.censored) {
                const valueEl = node.el.querySelector('.json-value');
                if (valueEl) {
                    valueEl.textContent = `*${T.censored_value || 'censored in debug report'}*`;
                    valueEl.classList.add('json-censored');
                }
            }
            return;
        }
        if (typeof node.value === 'object') return; // skip objects/arrays

        const resolved = _resolveFieldEntry(node, apiDocs);
        if (!resolved) return;

        const { fieldEntry } = resolved;
        const valueEl = node.el.querySelector('.json-value');

        // --- constant & unit annotations on the value element ------------
        if (valueEl) {
            const constants = fieldEntry.constants;
            if (constants && Array.isArray(constants)) {
                const nodeVal = node.value;
                let matchDesc = null;

                for (const c of constants) {
                    if (c.version !== -1 && hwVersion !== -1 && (c.version & hwVersion) === 0) {
                        continue;
                    }
                    if (typeof nodeVal === 'boolean') {
                        if (c.val === String(nodeVal)) { matchDesc = c.desc; break; }
                    } else if (typeof nodeVal === 'number') {
                        if (c.val === nodeVal) { matchDesc = c.desc; break; }
                    } else if (typeof nodeVal === 'string') {
                        if (c.val === nodeVal) { matchDesc = c.desc; break; }
                    }
                }

                if (matchDesc) {
                    const hintEl = document.createElement('span');
                    hintEl.className = 'enum-hint';
                    hintEl.textContent = ` (${matchDesc})`;
                    hintEl.title = matchDesc;
                    valueEl.appendChild(hintEl);
                }
            }

            if (fieldEntry.unit) {
                const unitEl = document.createElement('span');
                unitEl.className = 'unit-hint';
                unitEl.textContent = ` ${fieldEntry.unit.abbr}`;
                unitEl.title = fieldEntry.unit.name;
                valueEl.appendChild(unitEl);
            }
        }

        // --- info button with popover ------------------------------------
        if (!fieldEntry.desc) return;

        let bodyHtml = `<div class="field-info-body">`;
        bodyHtml += `<p class="field-info-desc">${_escapeHtml(fieldEntry.desc)}</p>`;

        if (fieldEntry.unit) {
            bodyHtml += `<p class="field-info-unit">${_escapeHtml(T.popover_unit)}: <strong>${_escapeHtml(fieldEntry.unit.name)}</strong> (${_escapeHtml(fieldEntry.unit.abbr)})</p>`;
        }

        if (fieldEntry.constants && fieldEntry.constants.length > 0) {
            const relevantConsts = fieldEntry.constants.filter(c =>
                c.version === -1 || hwVersion === -1 || (c.version & hwVersion) !== 0
            );
            if (relevantConsts.length > 0) {
                bodyHtml += `<div class="field-info-constants"><strong>${_escapeHtml(T.popover_values)}</strong><table class="field-info-table">`;
                for (const c of relevantConsts) {
                    bodyHtml += `<tr><td class="field-info-val">${_escapeHtml(String(c.val))}</td><td>${_escapeHtml(c.desc)}</td></tr>`;
                }
                bodyHtml += `</table></div>`;
            }
        }

        bodyHtml += `</div>`;

        const btn = document.createElement('i');
        btn.className = 'bi bi-info-circle field-info-btn';
        btn.setAttribute('tabindex', '0');
        btn.setAttribute('role', 'button');

        node.el.insertBefore(btn, node.el.firstChild);

        new bootstrap.Popover(btn, {
            html: true,
            content: bodyHtml,
            placement: 'right',
            trigger: 'focus',
            fallbackPlacements: ['right', 'left', 'top', 'bottom'],
            customClass: 'field-info-popover',
        });
    });
}

function _escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function make_jsonview(json, selector, options = {}) {
    const container = document.querySelector(selector);
    const tree = jsonview.create(json);
    const apiConstants = options.apiConstants || null;
    const hwVersion = options.hwVersion || -1;  // -1 = ANY

    // Create enhanced JSON viewer container
    const wrapper = document.createElement('div');
    wrapper.className = 'enhanced-json-viewer';

    // Add search and filter controls
    const controls = document.createElement('div');
    controls.className = 'json-controls';
    controls.innerHTML = `
        <div class="json-search-container">
            <input type="text" class="json-search form-control" placeholder="${T.search_placeholder}" />
            <div class="search-results-count"></div>
        </div>
        <div class="json-filters-actions">
            <div class="json-filters btn-group btn-group-sm">
                <button class="btn btn-outline-secondary active" data-filter="all" title="${T.filter_all_title}">${T.filter_all}</button>
                <button class="btn btn-outline-secondary" data-filter="modified" title="${T.filter_modified_title}">${T.filter_modified}</button>
                <button class="btn btn-outline-secondary" data-filter="numbers" title="${T.filter_numbers_title}">${T.filter_numbers}</button>
                <button class="btn btn-outline-secondary" data-filter="strings" title="${T.filter_strings_title}">${T.filter_strings}</button>
                <button class="btn btn-outline-secondary" data-filter="booleans" title="${T.filter_booleans_title}">${T.filter_booleans}</button>
                <button class="btn btn-outline-secondary" data-filter="objects" title="${T.filter_objects_title}">${T.filter_objects}</button>
            </div>
            <div class="json-actions btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="expandAllJson('${selector}')" title="${T.expand_all_title}">${T.expand_all}</button>
                <button class="btn btn-outline-primary" onclick="collapseAllJson('${selector}')" title="${T.collapse_all_title}">${T.collapse_all}</button>
            </div>
        </div>
    `;

    // Create JSON content container
    const jsonContent = document.createElement('div');
    jsonContent.className = 'json-content';

    // Create legend for colored line highlights
    const legend = document.createElement('div');
    legend.className = 'json-legend';
    legend.innerHTML = `
        <span class="json-legend-item">
            <span class="json-legend-swatch json-legend-modified"></span> ${T.legend_modified}
        </span>
        <span class="json-legend-item">
            <span class="json-legend-swatch json-legend-important"></span> ${T.legend_important}
        </span>
        <span class="json-legend-item">
            <i class="bi bi-info-circle json-legend-info-icon"></i> ${T.legend_info}
        </span>
    `;

    wrapper.appendChild(controls);
    wrapper.appendChild(legend);
    wrapper.appendChild(jsonContent);
    container.innerHTML = '';
    container.appendChild(wrapper);

    // Render JSON tree
    jsonview.render(tree, jsonContent);
    jsonview.expand(tree);

    // Store tree reference on the container for later use
    container._jsonTree = tree;    // Enhanced highlighting and processing
    jsonview.traverse(tree, function(node) {
        // Add data type classes
        if (node.el && node.value !== null) {
            const valueType = typeof node.value;
            node.el.classList.add(`json-type-${valueType}`);

            // Add timestamp formatting, only for plausible real-world dates
            // (uptimes, boot_ids, bitmasks, etc. also fall into the Unix range
            //  but decode to implausible years like 2057 or 2106)
            if (typeof node.value === 'number' && node.value > 1000000000 && node.value < 9999999999) {
                const date = new Date(node.value * 1000);
                const year = date.getFullYear();
                if (!isNaN(year) && year >= 2020 && year <= new Date().getFullYear() + 2) {
                    const timeEl = document.createElement('span');
                    timeEl.className = 'timestamp-hint';
                    timeEl.textContent = ` (${date.toLocaleString()})`;
                    const valueEl = node.el.querySelector('.json-value');
                    if (valueEl) valueEl.appendChild(timeEl);
                }
            }
        }

        // Handle modified configurations
        if(node.key && node.key.includes('modified')) {
            if(node.value && (node.value.modified == 1 || node.value.modified == 2 || node.value.modified == 3)) {
                const search = node.key.replace('_modified', '')
                jsonview.traverse(tree, function(searchNode) {
                    if(searchNode.key == search) {
                        if (node.value.modified == 1 || node.value.modified == 3) {
                            searchNode.el.classList.add("important");
                        }
                        searchNode.el.classList.add("modified-config");
                    }
                });
            }
        }
    });

    // Annotate leaf values with API doc constant descriptions and units;
    // add info buttons with Bootstrap popovers for field documentation.
    if (apiConstants) {
        _annotateTree(tree, apiConstants, hwVersion);
    }

    // Add search functionality
    const searchInput = wrapper.querySelector('.json-search');
    const resultsCount = wrapper.querySelector('.search-results-count');
    let searchResults = [];
    let currentSearchIndex = -1;

    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase();
        searchResults = [];
        currentSearchIndex = -1;

        // Clear previous highlights
        wrapper.querySelectorAll('.search-highlight').forEach(el => {
            el.classList.remove('search-highlight', 'search-current');
        });

        if (searchTerm.length > 0) {
            jsonview.traverse(tree, function(node) {
                if (node.el) {
                    const keyMatch = node.key && node.key.toLowerCase().includes(searchTerm);
                    const valueMatch = node.value && String(node.value).toLowerCase().includes(searchTerm);

                    if (keyMatch || valueMatch) {
                        node.el.classList.add('search-highlight');
                        searchResults.push(node.el);
                    }
                }
            });

            resultsCount.textContent = `${searchResults.length} ${T.matches}`;
            if (searchResults.length > 0) {
                currentSearchIndex = 0;
                searchResults[0].classList.add('search-current');
                searchResults[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        } else {
            resultsCount.textContent = '';
        }
    });

    // Add keyboard navigation for search results
    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && searchResults.length > 0) {
            e.preventDefault();
            if (e.shiftKey) {
                // Previous result
                currentSearchIndex = currentSearchIndex > 0 ? currentSearchIndex - 1 : searchResults.length - 1;
            } else {
                // Next result
                currentSearchIndex = currentSearchIndex < searchResults.length - 1 ? currentSearchIndex + 1 : 0;
            }

            // Update highlighting
            searchResults.forEach(el => el.classList.remove('search-current'));
            searchResults[currentSearchIndex].classList.add('search-current');
            searchResults[currentSearchIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });

            resultsCount.textContent = `${currentSearchIndex + 1} ${T.of} ${searchResults.length} ${T.matches}`;
        }
    });

    // Add filter functionality
    const filterBtns = wrapper.querySelectorAll('.json-filters .btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            filterBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            const filter = this.dataset.filter;

            if (filter === 'modified') {
                // Special handling for modified filter - show modified items and their children
                const modifiedNodes = [];

                // First, find all modified nodes
                jsonview.traverse(tree, function(node) {
                    if (node.el && node.el.classList.contains('modified-config')) {
                        modifiedNodes.push(node);
                    }
                });

                // Hide all nodes initially
                jsonview.traverse(tree, function(node) {
                    if (node.el) {
                        node.el.style.display = 'none';
                    }
                });

                // Show modified nodes and all their descendants
                modifiedNodes.forEach(modifiedNode => {
                    showNodeAndChildren(modifiedNode);
                });

            } else {
                // Standard filtering for other types
                const filterClass = {
                    numbers: 'json-type-number',
                    strings: 'json-type-string',
                    booleans: 'json-type-boolean',
                    objects: 'json-type-object',
                }[filter];
                jsonview.traverse(tree, function(node) {
                    if (node.el) {
                        const show = !filterClass || node.el.classList.contains(filterClass);
                        node.el.style.display = show ? '' : 'none';
                    }
                });
            }
        });
    });

    return tree;
}

function showNodeAndChildren(node) {
    if (node.el) {
        node.el.style.display = '';
    }
    if (node.children && node.children.length > 0) {
        node.children.forEach(child => {
            showNodeAndChildren(child);
        });
    }
}

function expandAllJson(selector) {
    const container = document.querySelector(selector);
    const tree = container._jsonTree;
    if (tree) {
        // Only expand visible nodes
        jsonview.traverse(tree, function(node) {
            if (node.el && node.el.style.display !== 'none' && node.children.length > 0 && !node.isExpanded) {
                jsonview.toggleNode(node);
            }
        });
    } else {
        console.log('Tree not found for selector:', selector);
    }
}

function collapseAllJson(selector) {
    const container = document.querySelector(selector);
    const tree = container._jsonTree;
    if (tree) {
        // Only collapse visible nodes
        jsonview.traverse(tree, function(node) {
            if (node.el && node.el.style.display !== 'none' && node.children.length > 0) {
                // Make sure it's collapsed
                if (node.isExpanded) {
                    jsonview.toggleNode(node);
                }
            }
        });
    } else {
        console.log('Tree not found for selector:', selector);
    }
}

// ---------------------------------------------------------------------------
// Protocol Chart (unified single-page)
// ---------------------------------------------------------------------------
let protoChart = null;
let protoData = null;

function initProtocolChart(data) {
    protoData = data;
    if (!protoData || !protoData.column_metadata) return;

    // --- Backward compatibility: convert old ?configuration= or ?selected= to hash ---
    const urlParams = new URLSearchParams(window.location.search);
    const legacyCfg = data.legacy_config || urlParams.get('configuration') || '';
    const legacySel = data.legacy_selected || urlParams.get('selected') || '';
    if (legacyCfg || legacySel) {
        const cols = (legacyCfg || legacySel).split(',').filter(Boolean);
        if (cols.length > 0) {
            // Apply these as initial selection and put in hash
            const checkboxes = document.querySelectorAll('#proto-column-checkboxes input[type="checkbox"]');
            const colSet = new Set(cols);
            checkboxes.forEach(cb => {
                cb.checked = colSet.has(cb.dataset.column);
            });
            // If came from ?configuration=, also enable log axis (old default was log)
            if (legacyCfg) {
                const logCb = document.getElementById('proto-log-axis');
                if (logCb) logCb.checked = true;
            }
            // Strip query params, put state in hash instead
            const cleanUrl = window.location.pathname;
            history.replaceState(null, '', cleanUrl);
            _protoUpdateHash();
        }
    } else {
        // Restore selection from URL hash if present
        const hashState = _protoParseHash();
        if (hashState.columns !== null) {
            const colSet = new Set(hashState.columns);
            const checkboxes = document.querySelectorAll('#proto-column-checkboxes input[type="checkbox"]');
            checkboxes.forEach(cb => {
                cb.checked = colSet.has(cb.dataset.column);
            });
            if (hashState.log) {
                const logCb = document.getElementById('proto-log-axis');
                if (logCb) logCb.checked = true;
            }
        }
    }

    // Initialize JSON viewers and log textareas
    const protocolJson = data.before_protocol_json || data.after_protocol_json || {};
    const hwVersion = _detectHwVersion(protocolJson);
    const jsonviewOpts = data.api_constants
        ? { apiConstants: data.api_constants, hwVersion: hwVersion }
        : {};
    make_jsonview(data.before_protocol_json, '#before-protocol-json', jsonviewOpts);
    make_jsonview(data.after_protocol_json, '#after-protocol-json', jsonviewOpts);

    document.getElementById('before-protocol-log-text').value = data.before_protocol_log;
    document.getElementById('after-protocol-log-text').value = data.after_protocol_log;

    // Render chart with initial selection
    protoRenderChart();
}

function _protoParseHash() {
    return _parseChartHash('cols', 'log');
}

function _protoUpdateHash() {
    _updateChartHash('#proto-column-checkboxes input[type="checkbox"]', 'proto-log-axis', 'cols', 'log');
}

function protoRenderChart() {
    if (!protoData) return;

    // Gather selected columns
    const selected = [];
    document.querySelectorAll('#proto-column-checkboxes input[type="checkbox"]:checked').forEach(cb => {
        selected.push(cb.dataset.column);
    });

    // Build column label lookup from metadata
    const labelLookup = {};
    protoData.column_metadata.forEach(col => {
        labelLookup[col.name] = col.label;
    });

    // Log / linear Y-axis
    const logCheckbox = document.getElementById('proto-log-axis');
    const useLog = logCheckbox && logCheckbox.checked;

    // Build datasets
    const datasets = [];
    let colorIdx = 0;

    selected.forEach(colName => {
        const rawData = protoData.all_column_data[colName];
        if (!rawData) return;

        // For log view: replace 0 with 0.01 (Chart.js can't show 0 on log scale)
        // See https://github.com/chartjs/Chart.js/issues/9629
        const chartData = useLog ? rawData.map(v => (v === 0 ? 0.01 : v)) : rawData;

        datasets.push(_chartDataset(labelLookup[colName] || colName, chartData, colorIdx++));
    });

    protoChart = _createTimeSeriesChart({
        canvasId: 'proto-chart',
        prevChart: protoChart,
        labels: protoData.labels,
        datasets: datasets,
        titleText: T.chart_title || 'Charge Log',
        useLog: useLog,
    });

    // Persist selection in URL hash for sharing
    _protoUpdateHash();
}

function protoSelectAll(checked) {
    chartSelectAll('#proto-column-checkboxes input[type="checkbox"]', checked, protoRenderChart);
}

function protoResetZoom() {
    chartResetZoom(protoChart);
}

function vislog_report(data) {
    const hwVersion = _detectHwVersion(data.report_json);
    const jsonviewOpts = data.api_constants
        ? { apiConstants: data.api_constants, hwVersion: hwVersion }
        : {};
    make_jsonview(data.report_json, '#report-json', jsonviewOpts);

    document.getElementById('report-log-text').value = data.report_log;

    // Only set trace text if the element exists (might not if no remaining trace content)
    const traceText = document.getElementById('report-trace-text');
    if (traceText) {
        traceText.value = data.report_trace;
    }

    // Populate module trace textareas (filled via JS to avoid HTML injection in <textarea>)
    if (data.trace_modules) {
        for (const [moduleName, moduleContent] of Object.entries(data.trace_modules)) {
            const el = document.getElementById('trace-' + moduleName + '-text');
            if (el) {
                el.value = moduleContent;
            }
        }
    }

    // Initialize charge manager chart if parsed data is available
    if (data.cm_parsed) {
        initCmChart(data.cm_parsed);
    }

    // Coredump is now rendered server-side, no JS needed
}

// ---------------------------------------------------------------------------
// Charge Manager Chart
// ---------------------------------------------------------------------------
let cmChart = null;
let cmData = null;

function initCmChart(data) {
    cmData = data;
    if (!cmData || !cmData.columns) return;

    const container = document.getElementById('cm-column-groups');
    if (!container) return;

    // Group columns
    const groups = {};
    cmData.columns.forEach(col => {
        if (!groups[col.group]) groups[col.group] = [];
        groups[col.group].push(col);
    });

    // Default selected: PM group + first few key columns
    const defaultKeys = new Set(['pm_mtr', 'pm_avl', 'pv_raw', 's0_raw_total', 's9_raw_total', 'alloc_current']);

    // Restore selection from URL hash if present
    const hashState = _cmParseHash();
    const restoredKeys = hashState.columns;
    const restoredLog = hashState.log;
    const useRestored = restoredKeys !== null;
    const selectedKeys = useRestored ? new Set(restoredKeys) : defaultKeys;

    container.innerHTML = '';
    for (const [groupName, cols] of Object.entries(groups)) {
        const groupDiv = document.createElement('div');
        groupDiv.className = 'chart-column-group';
        const heading = document.createElement('h6');
        heading.textContent = groupName;
        groupDiv.appendChild(heading);

        cols.forEach(col => {
            const label = document.createElement('label');
            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.dataset.column = col.key;
            cb.checked = selectedKeys.has(col.key);
            cb.addEventListener('change', renderCmChart);
            label.appendChild(cb);
            label.appendChild(document.createTextNode(' ' + col.label));
            groupDiv.appendChild(label);
        });

        container.appendChild(groupDiv);
    }

    // Restore log axis state
    if (restoredLog) {
        const logCb = document.getElementById('cm-log-axis');
        if (logCb) logCb.checked = true;
    }

    // Auto-render with defaults/restored state
    renderCmChart();
}

function _cmParseHash() {
    return _parseChartHash('cm', 'cmlog');
}

function _cmUpdateHash() {
    _updateChartHash('#cm-column-groups input[type="checkbox"]', 'cm-log-axis', 'cm', 'cmlog');
}

function cmSelectAll(checked) {
    chartSelectAll('#cm-column-groups input[type="checkbox"]', checked, renderCmChart);
}

function cmResetZoom() {
    chartResetZoom(cmChart);
}

function renderCmChart() {
    if (!cmData) return;

    // Gather selected columns
    const selected = [];
    document.querySelectorAll('#cm-column-groups input[type="checkbox"]:checked').forEach(cb => {
        selected.push(cb.dataset.column);
    });

    // Build timestamp lookup: sorted array of [row_idx, timestamp_string]
    // for nearest-match lookups on the x-axis
    const tsEntries = cmData.timestamps || [];
    const tsMap = {};
    tsEntries.forEach(([idx, ts]) => { tsMap[idx] = ts; });

    // Find the nearest timestamp for a given row index
    function nearestTimestamp(rowIdx) {
        if (tsEntries.length === 0) return null;
        // Binary search for closest entry
        let lo = 0, hi = tsEntries.length - 1;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (tsEntries[mid][0] < rowIdx) lo = mid + 1;
            else hi = mid;
        }
        // lo is the first entry >= rowIdx; compare with lo-1
        if (lo > 0 && (lo >= tsEntries.length ||
            Math.abs(tsEntries[lo - 1][0] - rowIdx) <= Math.abs(tsEntries[lo][0] - rowIdx))) {
            lo = lo - 1;
        }
        return tsEntries[lo][1];
    }

    // Build x-axis labels (row indices)
    const labels = [];
    for (let i = 0; i < cmData.row_count; i++) {
        labels.push(i);
    }

    // Build datasets
    const datasets = [];
    let colorIdx = 0;

    const colLookup = {};
    cmData.columns.forEach(c => { colLookup[c.key] = c; });

    selected.forEach(key => {
        const colMeta = colLookup[key];
        if (!colMeta) return;

        let data;
        if (cmData.table_data && cmData.table_data[key]) {
            // Dense table data, use directly as array
            data = cmData.table_data[key];
        } else if (cmData.summary_data && cmData.summary_data[key]) {
            // Sparse summary data, convert to {x, y} points
            data = cmData.summary_data[key].map(([idx, val]) => ({ x: idx, y: val }));
        } else {
            return;
        }

        datasets.push(_chartDataset(colMeta.label, data, colorIdx++));
    });

    // Log / linear Y-axis
    const logCheckbox = document.getElementById('cm-log-axis');
    const useLog = logCheckbox && logCheckbox.checked;

    cmChart = _createTimeSeriesChart({
        canvasId: 'cm-chart',
        prevChart: cmChart,
        labels: labels,
        datasets: datasets,
        titleText: T.cm_chart_title || 'Charge Manager',
        useLog: useLog,
        xMaxTicksLimit: 10,
        xTickCallback: function(value) {
            const ts = nearestTimestamp(value);
            if (ts) return ts.split(' ')[1] || ts;
            return '';
        },
        tooltipTitleCallback: function(items) {
            if (!items.length) return '';
            const idx = items[0].dataIndex;
            const ts = tsMap[idx] || nearestTimestamp(idx);
            return ts ? `Row ${idx} - ${ts}` : `Row ${idx}`;
        },
    });

    // Persist selection in URL hash for sharing
    _cmUpdateHash();
}
