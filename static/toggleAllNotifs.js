$(document).ready(() => {
    const allButton = $('#all');
    const otherNotifTypes = $('.notif-form input.otherNotifTypes[type=checkbox]');

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

    $(otherNotifTypes).change(() => {
        const unCheckedNotifs = otherNotifTypes.not(':checked');
        if (unCheckedNotifs.length === 0){
            allButton.prop('checked', true)
        }else{
            allButton.prop('checked', false)
        }

    })

});
