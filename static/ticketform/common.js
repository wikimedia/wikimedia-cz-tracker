( function () {
	function statutoryDeclaration() {
		$( '.field_statutory_declaration' ).toggle( $( '#id_car_travel' ).prop( 'checked' ) );
	}

	$( document ).ready( function () {
		$( '.field_car_travel' ).change( statutoryDeclaration );

		statutoryDeclaration();
	} );
}() );
