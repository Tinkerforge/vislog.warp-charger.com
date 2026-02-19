let chart  = undefined;
let config = undefined;
let originalDatasets = undefined;

function open_tab(evt, tab) {
    var i, tabcontent, tablinks;

    // Get all elements with class="tabcontent" and hide them
    tabcontent = document.getElementsByClassName("tabcontent");
    for (i = 0; i < tabcontent.length; i++) {
        tabcontent[i].style.display = "none";
    }

    // Get all elements with class="tablinks" and remove the class "active"
    tablinks = document.getElementsByClassName("tablinks");
    for (i = 0; i < tablinks.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }

    // Show the current tab, and add an "active" class to the button that opened the tab
    document.getElementById(tab).style.display = "block";
    evt.currentTarget.className += " active";
}

function log_axis_clicked() {
    checkbox = document.getElementById('log-axis');

    chart.destroy()
    if(checkbox.checked) {
        config.options.scales.y = {
            display: true,
            type: 'logarithmic',
            ticks: {
                color: '#f0f0f0'
            },
            grid: {
                color: '#3a3a3a'
            }
        }
    } else {
        config.options.scales.y = {
            display: true,
            ticks: {
                color: '#f0f0f0'
            },
            grid: {
                color: '#3a3a3a'
            }
        }
    }
    chart = new Chart(document.getElementById('warp_chart'), config);
}

function toggle_column_visibility(column_name, visible) {
    const datasetIndex = config.data.datasets.findIndex(dataset =>
        dataset.csv_column === column_name
    );

    if (datasetIndex !== -1) {
        if (visible) {
            // Show the dataset
            config.data.datasets[datasetIndex].hidden = false;
        } else {
            // Hide the dataset
            config.data.datasets[datasetIndex].hidden = true;
        }
        chart.update('none'); // Update without animation for better performance
    }
}

function toggle_all_columns(visible) {
    const checkboxes = document.querySelectorAll('#column-checkboxes input[type="checkbox"]:not([style*="display: none"])');
    checkboxes.forEach(checkbox => {
        checkbox.checked = visible;
        const columnName = checkbox.dataset.column;
        toggle_column_visibility(columnName, visible);
    });
}

function filter_columns() {
    const searchTerm = document.getElementById('column-search').value.toLowerCase();
    const columnItems = document.querySelectorAll('.column-item');
    let visibleCount = 0;

    columnItems.forEach(item => {
        const label = item.querySelector('label').textContent.toLowerCase();
        if (label.includes(searchTerm)) {
            item.style.display = 'flex';
            visibleCount++;
        } else {
            item.style.display = 'none';
        }
    });

    update_column_count(visibleCount, columnItems.length);
}

function update_column_count(visible, total) {
    const countElement = document.getElementById('column-count');
    if (visible < total) {
        countElement.textContent = T.columns_shown_filtered.replace('${visible}', visible).replace('${total}', total);
    } else {
        countElement.textContent = T.columns_available.replace('${total}', total);
    }
}

function create_column_selector(datasets) {
    const container = document.getElementById('column-checkboxes');
    container.innerHTML = '';

    datasets.forEach((dataset, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'column-item';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = 'col-' + index;
        checkbox.dataset.column = dataset.csv_column;
        checkbox.checked = !dataset.hidden;

        checkbox.addEventListener('change', function() {
            toggle_column_visibility(dataset.csv_column, this.checked);
        });

        const label = document.createElement('label');
        label.htmlFor = checkbox.id;
        label.textContent = dataset.label;
        label.title = dataset.label; // Add tooltip for long names

        wrapper.appendChild(checkbox);
        wrapper.appendChild(label);
        container.appendChild(wrapper);
    });

    // Initialize count display
    update_column_count(datasets.length, datasets.length);
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

function _annotateConstants(tree, apiDocs, hwVersion) {
    // Walk the jsonview tree and annotate leaf values with constant
    // descriptions and unit abbreviations.
    jsonview.traverse(tree, function(node) {
        if (!node.el || node.value === null || node.value === undefined) return;
        if (typeof node.value === 'object') return; // skip objects/arrays

        const resolved = _resolveFieldEntry(node, apiDocs);
        if (!resolved) return;

        const { fieldEntry } = resolved;
        const valueEl = node.el.querySelector('.json-value');
        if (!valueEl) return;

        // --- constant annotation -----------------------------------------
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

        // --- unit annotation ---------------------------------------------
        if (fieldEntry.unit) {
            const unitEl = document.createElement('span');
            unitEl.className = 'unit-hint';
            unitEl.textContent = ` ${fieldEntry.unit.abbr}`;
            unitEl.title = fieldEntry.unit.name;
            valueEl.appendChild(unitEl);
        }
    });
}

function _addInfoButtons(tree, apiDocs, hwVersion) {
    // Add clickable info buttons next to field keys that have API documentation.
    // Uses Bootstrap 5 popovers to show description, unit, and constants.
    jsonview.traverse(tree, function(node) {
        if (!node.el || node.value === null || node.value === undefined) return;
        if (typeof node.value === 'object') return;

        const resolved = _resolveFieldEntry(node, apiDocs);
        if (!resolved) return;

        const { fieldEntry } = resolved;

        // Only add info button if there is a description
        if (!fieldEntry.desc) return;

        // Build popover HTML content
        let bodyHtml = `<div class="field-info-body">`;
        bodyHtml += `<p class="field-info-desc">${_escapeHtml(fieldEntry.desc)}</p>`;

        if (fieldEntry.unit) {
            bodyHtml += `<p class="field-info-unit">${_escapeHtml(T.popover_unit)}: <strong>${_escapeHtml(fieldEntry.unit.name)}</strong> (${_escapeHtml(fieldEntry.unit.abbr)})</p>`;
        }

        if (fieldEntry.constants && fieldEntry.constants.length > 0) {
            // Filter by hw version for display
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

        // Create info button
        const btn = document.createElement('i');
        btn.className = 'bi bi-info-circle field-info-btn';
        btn.setAttribute('tabindex', '0');
        btn.setAttribute('role', 'button');

        // Insert at the very start of the line
        node.el.insertBefore(btn, node.el.firstChild);

        // Initialize Bootstrap popover
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
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
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

            // Add timestamp formatting — only for plausible real-world dates
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
                search = node.key.replace('_modified', '')
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
        _annotateConstants(tree, apiConstants, hwVersion);
        _addInfoButtons(tree, apiConstants, hwVersion);
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
                jsonview.traverse(tree, function(node) {
                    if (node.el) {
                        let show = true;

                        switch(filter) {
                            case 'numbers':
                                show = node.el.classList.contains('json-type-number');
                                break;
                            case 'strings':
                                show = node.el.classList.contains('json-type-string');
                                break;
                            case 'booleans':
                                show = node.el.classList.contains('json-type-boolean');
                                break;
                            case 'objects':
                                show = node.el.classList.contains('json-type-object');
                                break;
                            case 'all':
                            default:
                                show = true;
                        }

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
            if (node.el && node.el.style.display !== 'none' && node.children.length > 0) {
                jsonview.toggleNode(node); // This will expand if collapsed
                // Make sure it's expanded, not collapsed
                if (!node.isExpanded) {
                    jsonview.toggleNode(node);
                }
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

function vislog_protocol(data) {
    // Store original datasets for reference
    originalDatasets = JSON.parse(JSON.stringify(data.chart.datasets));

    // Add csv_column property to datasets if not present
    data.chart.datasets.forEach((dataset, index) => {
        if (!dataset.csv_column) {
            dataset.csv_column = dataset.label;
        }
    });

    config = {
        type: 'line',
        data: data.chart,
        options: {
            animation: false,
            maintainAspectRatio: false,
            elements: {
                point: {
                    radius: 0
                }
            },
            hover: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                title: {
                    display: true,
                    text: T.chart_title,
                    color: '#f0f0f0'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                legend: {
                    labels: {
                        color: '#f0f0f0'
                    }
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
                        wheel: {
                            enabled: false,
                        },
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
                    ticks: {
                        color: '#f0f0f0'
                    },
                    grid: {
                        color: '#3a3a3a'
                    }
                },
                y: {
                    display: true,
                    type: 'logarithmic',
                    ticks: {
                        color: '#f0f0f0'
                    },
                    grid: {
                        color: '#3a3a3a'
                    }
                }
            }
        }
    };
    chart = new Chart(document.getElementById('warp_chart'), config);

    // Only create column selector if the element exists (for backward compatibility)
    if (document.getElementById('column-checkboxes')) {
        create_column_selector(data.chart.datasets);
    }

    // Detect hardware version from either before or after protocol JSON
    const protocolJson = data.before_protocol_json || data.after_protocol_json || {};
    const hwVersion = _detectHwVersion(protocolJson);
    const jsonviewOpts = data.api_constants
        ? { apiConstants: data.api_constants, hwVersion: hwVersion }
        : {};
    make_jsonview(data.before_protocol_json, '#before-protocol-json', jsonviewOpts)
    make_jsonview(data.after_protocol_json,  '#after-protocol-json', jsonviewOpts)

    document.getElementById('before-protocol-log-text').value = data.before_protocol_log;
    document.getElementById('after-protocol-log-text').value = data.after_protocol_log;
}

function reset_zoom() {
    if (chart) {
        chart.resetZoom();
    }
}function vislog_report(data) {
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

    // Coredump is now rendered server-side, no JS needed

    // Store tree reference for report JSON
    setTimeout(() => {
        const reportContainer = document.querySelector('#report-json');
        if (reportContainer && reportContainer.querySelector('.enhanced-json-viewer')) {
            const tree = reportContainer._jsonTree;
            if (tree) {
                reportContainer._jsonTree = tree;
            }
        }
    }, 100);
}
