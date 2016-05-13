var RPL_WORKS = 'follow';
var NODE_ALIVE = 1;
var gaugeOptions = {
    chart: {
        type: 'solidgauge'
    },

    title: null,

    pane: {
        center: ['50%', '85%'],
        size: '140%',
        startAngle: -90,
        endAngle: 90,
        background: {
            backgroundColor: (Highcharts.theme && Highcharts.theme.background2) || '#EEE',
            innerRadius: '60%',
            outerRadius: '100%',
            shape: 'arc'
        }
    },

    tooltip: {
        enabled: false
    },

    // the value axis
    yAxis: {
        stops: [
            [0.1, '#55BF3B'], // green
            [0.5, '#DDDF0D'], // yellow
            [0.9, '#DF5353'] // red
        ],
        lineWidth: 0,
        minorTickInterval: null,
        tickPixelInterval: 400,
        tickWidth: 0,
        title: {
            y: -70
        },
        labels: {
            y: 16
        }
    },

    plotOptions: {
        solidgauge: {
            dataLabels: {
                y: 5,
                borderWidth: 0,
                useHTML: true
            }
        }
    }
};

function get_param(name){
    var regexS = "[\\?&]"+name+"=([^&#]*)", 
    regex = new RegExp( regexS ),
    results = regex.exec( window.location.search );
    if( results == null ){
        return "";
    } else {
        return decodeURIComponent(results[1].replace(/\+/g, " "));
    }
}

function render_node(name, node){
    $('.' + name).text(node.ip);
    var elem = $('.' + name + '-status');
    if(node.alive == NODE_ALIVE){
        elem.addClass('badge-ok');
        elem.text('Operational');
        $('.drop-' + name ).attr('cid', node.image_id);
    }
    else{
        elem.text('down');
        elem.addClass('badge-error');
        $('.pair-' + name).addClass('replica-fails');
    }
}

function memory_render(first){
    var k = 1024*1024
    var arena_size = 100.0 * first.arena_size/first.size;
    var arena_used = 100.0 * first.arena_used/first.size;
    var quota_used = 100.0 * first.used/first.size;
    var quota_size = 100.0;

    $('.mem1').css('width', quota_used.toString() + '%')
    $('.progress-info').text(
        (first.used/k).toString() + ' / ' + (first.size/k).toString() + ' MB'
    );

    $('.memory-diagram').highcharts({
        chart: {
            type: 'bar'
        },
        title: {
            text: ''
        },
        xAxis: {
            categories: ['Details', 'Arena',]
        },
        yAxis: {
            min: 0,
            title: {
                text: 'Available memory (%)'
            }
        },
        legend: {
            reversed: true
        },
        plotOptions: {
            series: {
                stacking: 'normal'
            }
        },
        series: [
        {
            name: 'Free memory',
            data: [quota_size - quota_used, quota_size - quota_used]
        },
        {
            name: 'Indexes and system',
            data: [quota_used - arena_size, quota_used - arena_size]
        },
                {
            name: 'Arena allocation',
            data: [arena_size - arena_used, ]
        },
        {
            name: ['Tuples'],
            data: [arena_used, arena_size]
        }]
    });
}

function rps_render(first){
    var stats = [
        'SELECT', 'UPDATE', 'INSERT', 'CALL', 
        'EVAL', 'REPLACE', 'DELETE', 'ERROR'
    ];
    $.map(stats, function(data){
        $('.rps-' + data.toLowerCase()).highcharts(Highcharts.merge(gaugeOptions, {
            yAxis: {
                min: 0,
                max: 2000,
                title: {
                    text: data
                }
            },

            credits: {
                enabled: false
            },

            series: [{
                name: data,
                data: [first.stats[data].rps],
                dataLabels: {
                    format: '<div style="text-align:center"><span style="font-size:25px;color:' +
                        ((Highcharts.theme && Highcharts.theme.contrastTextColor) || 'black') + '">{y}</span><br/>' +
                           '<span style="font-size:12px;color:silver">RPS</span></div>'
                },
                tooltip: {
                    valueSuffix: ' rps'
                }
            }]

        }));
    });
}

function render(data){
    var first = data.pair.first;
    var second = data.pair.second;

    $('.pair_name').text(data.name);
    render_node('first', first);
    render_node('second', second);
    memory_render(first);
    rps_render(first);
    
    if(first.replication == second.replication &&
            first.replication == RPL_WORKS){
        $('.replication').text(RPL_WORKS);
        $('.replication').addClass('badge-ok');
        $('.pair-replica').addClass('replica-works');
    }
    else{
        $('.replication').text('error')
        $('.replication').addClass('badge-error')
        $('.pair-replica').addClass('replica-fails');
    }
}

function detail(id){
    console.log('locking for pair id=' + id);
    var res = $.post(
        tnt_uri, 
        JSON.stringify({ "method": "detail", "params": [id], "id": 1 }),
        function(res){
            res = $.parseJSON(res)
            var pair = get_pair(res.result[0]);
            console.log(pair);
            render(pair);
        }
    );
}

function kill_node(){
    var cid = $(this).attr('cid');
    console.log(cid);
    $(this).parent().hide();
    $(this).closest('li').find('.loader').show();
    $.post(
        tnt_uri, 
        JSON.stringify(
            {
                "method": "drop", 
                "params": [cid, ], 
                "id": 1
            }
        ),
        function(res){
            window.location = window.location;
        }
    );
}

$(document).ready(function(){
    detail(get_param('id'));
    $(document).on('click', '.drop', kill_node)
});
