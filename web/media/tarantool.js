var tnt_uri = '/tarantool';

function pair(raw_data){
    // serialize pair tuple
    var result = {}
    $.map(['first', 'second'], function(field, i){
        result[field] = {}
        $.map(
            [
                'image_id', 'ip', 'server', 
                'size', 'used', 'arena_size', 
                'arena_used', 'replication', 
                'alive', 'stats'
            ], function(data, j){
                result[field][data] = raw_data[i][j]
            }
        );
    });
    return result
}

function drop_pair(){
    var id = $(this).attr('id');
    var elem = $(this).closest('li');

    $.post(
        tnt_uri, 
        JSON.stringify(
            {
                "method": "delete", 
                "params": [id, ], 
                "id": 1
            }
        ),
        function(res){
            elem.fadeOut('slow');
            elem.remove();
            $('.limit-error').hide();
        }
    );
}

function get_pair(tuple){
    // serialize tuple to js object
    var schema = ['id', 'user', 'name', 'pair', 'state'];
    var result = {};
    $.map(schema, function(field, i){
        var value = tuple[i];
        // serialize order pair
        if(field == 'pair'){
            value = pair(value);
        }
        result[field] = value;
    });
    return result;
}
