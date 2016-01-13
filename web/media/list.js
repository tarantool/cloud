function render(row){
    var html = '<li class="list-group-item">';
    html += '<span class="badge badge-info">';
    html += '<a class="drop" id="'+row.id+'" href="javascript:void(0)">Delete</a></span>';
    html += '<b><a href="/detail?id='+row.id+'">' + row.name + '</a></b></li>'
    $('.clusters').append(html);
}

function list(){
    // get clusters list and render it
    var res = $.post(
        tnt_uri, 
        JSON.stringify({ "method": "list", "params": [], "id": 1 }),
        function(res){
            $.map(res.result, function(resp, id){
                render(get_pair(res.result[id]));
            });
        }
    );
}

function create(){
    var name = $('#create_box').val();
    if(name == ''){
        return;
    }

    $('.loader').show();
    $('.limit-error').hide();
    $('#create_box').hide();
    $.post(
        tnt_uri, 
        JSON.stringify(
            {
                "method": "create", 
                "params": [name, ], 
                "id": 1
            }
        ),
        function(res){
            if(res.result[0][0]){
                $('.loader').hide();
                $('#create_box').show();
                $('.limit-error').show();
                return;
            };
            window.location = window.location;
        }
    );
}

$(document).ready(function(){
    list();
    $(document).on('click', '.drop', drop_pair)
    $(document).on('click', '#create_btn', create)
});
