document.addEventListener( 'DOMContentLoaded', () => {
	const allButton = document.querySelector( '.all-checkbox' ),
		otherNotifTypes = document.querySelectorAll( '.otherNotifTypes' );

	allButton.addEventListener( 'change', () => {
		otherNotifTypes.forEach( ( checkbox ) => {
			checkbox.checked = allButton.checked;
		} );
	} );

	// looks at all the checkboxes and (un)checks the 'all' checkbox. Is run on every checkbox change.
	function checkAllButton() {
		allButton.checked = !Array.from( otherNotifTypes ).some( checkbox => !checkbox.checked );
	}

	// Sets the all button to the right initial value on page load.
	checkAllButton();

	otherNotifTypes.forEach( ( checkbox ) => {
		checkbox.addEventListener( 'change', () => {
			// set "all" checkbox unchecked if some checkboxes are not checked
			checkAllButton();
		} );
	} );
} );
