document.addEventListener( 'DOMContentLoaded', () => {
	const allButton = document.querySelector( '#all' ),
		otherNotifTypes = document.querySelectorAll( '.notif-form input.otherNotifTypes[type=checkbox]' );

	allButton.addEventListener( 'change', () => {
		otherNotifTypes.forEach( checkbox => {
			checkbox.checked = allButton.checked;
		} );
	} );

	otherNotifTypes.forEach( checkbox => {
		checkbox.addEventListener( 'change', () => {
			// set "all" checkbox unchecked if some checkboxes are not checked
			allButton.checked = !Array.from( otherNotifTypes )
				.some( checkbox => !checkbox.checked );
		} );
	} );
} );
