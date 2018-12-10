{
	document.addEventListener( 'DOMContentLoaded', () => {
		const ackTypeSelect = document.querySelector( 'select[name="ack_type"]' ),
			actionSelect = document.querySelector( 'select[name="action"]' );

		function refreshActionForm() {
			if ( actionSelect.value === 'add_ack' ) {
				ackTypeSelect.parentNode.hidden = false;
			} else {
				ackTypeSelect.parentNode.hidden = true;
			}
		}
		actionSelect.addEventListener( 'change', refreshActionForm );
		refreshActionForm();
	} );
}
