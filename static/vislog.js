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

function vislog_protocol(data) {
    let config = {
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
    let chart = new Chart(document.getElementById('warp_chart'), config);

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

    new JsonViewer({value: data.before_protocol_json, maxDisplayLength: 10}).render('#before-protocol-json');
    new JsonViewer({value: data.after_protocol_json, maxDisplayLength: 10}).render('#after-protocol-json');
    document.getElementById('before-protocol-log-text').value = data.before_protocol_log;
    document.getElementById('after-protocol-log-text').value = data.after_protocol_log;
 }