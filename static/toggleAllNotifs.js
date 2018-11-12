$(document).ready(() => {
    const allButton = $('#all');
    const otherNotifTypes = $('.notif-form input[type=checkbox]');

    $(allButton).change(() => {
        if ($(allButton).prop('checked')) {
            otherNotifTypes.each((index, notifType) => {
                $(notifType).prop('checked', true);
            });
        } else {
            otherNotifTypes.each((index, notifType) => {
                $(notifType).prop('checked', false);
            });
        }
    });
});
