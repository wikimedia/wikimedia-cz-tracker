function refresh_action_form() {
    if ($('select[name="action"]').val() == 'add_ack') {
        $('select[name="ack_type"]').parent().show();
    } else {
        $('select[name="ack_type"]').parent().hide();
    }
}

$(document).ready(function() {
    $('select[name="action"]').change(refresh_action_form);
    refresh_action_form();
});