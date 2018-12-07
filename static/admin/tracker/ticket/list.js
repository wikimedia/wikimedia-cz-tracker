( function () {
	function refreshActionForm() {
		if ( $( 'select[name="action"]' ).val() === 'add_ack' ) {
			$( 'select[name="ack_type"]' ).parent().show();
		} else {
			$( 'select[name="ack_type"]' ).parent().hide();
		}
	}

	$( document ).ready( function () {
		$( 'select[name="action"]' ).change( refreshActionForm );
		refreshActionForm();
	} );
}() );
