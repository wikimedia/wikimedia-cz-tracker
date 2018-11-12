$(document).ready(() => {
    const allButton = $('#all');
    const otherNotifTypes = $('.otherNotifTypes');

    $(allButton).change(() => {
        if ($( allButton ).prop( "checked" )) {

            otherNotifTypes.each((index, notifType) => {
                $( notifType ).prop('checked', true);
            });
        } else {
            otherNotifTypes.each((index, notifType) => {
                $( notifType ).prop('checked', false);
            });
        }
    });
});
