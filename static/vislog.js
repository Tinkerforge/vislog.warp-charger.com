let chart  = undefined;
let config = undefined;

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
            type: 'logarithmic'
        }
    } else {
        config.options.scales.y = {
            display: true,
        }
    }
    chart = new Chart(document.getElementById('warp_chart'), config);
};

function make_jsonview(json, selector) {
    const tree = jsonview.create(json);
    jsonview.render(tree, document.querySelector(selector));
    // To only show modified configs, don't expand the tree, only toggle the head and then expand the important children below.
    //jsonview.toggleNode(tree);
    jsonview.expand(tree);
    jsonview.traverse(tree, function(node) {
        if(node.key.includes('modified')) {
            if(node.value.modified == 2) {
                search = node.key.replace('_modified', '')
                jsonview.traverse(tree, function(node) {
                    if(node.key == search) {
                        node.el.classList.add("important");
                        //jsonview.expand(node);
                        // color children?
                        //node.children.forEach((child) => {
                        //    child.el.classList.add("important");
                        //});
                    }
                });
            }
        }
    });
}

function vislog_protocol(data) {
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
                    text: 'Ladeprotokoll'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
            },
            scales: {
                x: {
                    display: true,
                },
                y: {
                    display: true,
                    type: 'logarithmic',
                }
            }
        }
    };
    chart = new Chart(document.getElementById('warp_chart'), config);

    make_jsonview(data.before_protocol_json, '#before-protocol-json')
    make_jsonview(data.after_protocol_json,  '#after-protocol-json')

    document.getElementById('before-protocol-log-text').value = data.before_protocol_log;
    document.getElementById('after-protocol-log-text').value = data.after_protocol_log;
 }

function vislog_report(data) {
    make_jsonview(data.report_json, '#report-json')

    document.getElementById('report-log-text').value = data.report_log;
    document.getElementById('report-trace-text').value = data.report_trace;
    document.getElementById('report-dump-text').value = data.report_dump;
}
