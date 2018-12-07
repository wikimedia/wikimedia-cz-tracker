$( document ).ready( () => {
	const allButton = $( '#all' ),
		otherNotifTypes = $( '.notif-form input.otherNotifTypes[type=checkbox]' );

	$( allButton ).change( () => {
		otherNotifTypes.each( ( index, notifType ) => {
			$( notifType ).prop( 'checked', $( allButton ).prop( 'checked' ) );
		} );
	} );

	$( otherNotifTypes ).change( () => {
		const unCheckedNotifs = otherNotifTypes.not( ':checked' );
		allButton.prop( 'checked', unCheckedNotifs.length === 0 );
	} );
} );
