{
	function statutoryDeclaration() {
		const fieldStatuatoryDeclaration = document.querySelector( '.field_statutory_declaration' ),
			idCarTravel = document.querySelector( '#id_car_travel' );
		fieldStatuatoryDeclaration.hidden = !idCarTravel.checked;
	}

	document.addEventListener( 'DOMContentLoaded', () => {
		document.querySelector( '.field_car_travel' ).addEventListener( 'change', statutoryDeclaration );
		statutoryDeclaration();
	} );
}
