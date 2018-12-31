{
	function dataTablesInit() {
		const disabledatatables = document.querySelector( '#disabledatatables' );
		if ( disabledatatables === null || disabledatatables.textContent.length === 0 ) {
			const LANGUAGE = document.querySelector( 'meta[http-equiv="Content-Language"]' ).getAttribute( 'content' );

			fetch( '/api/tracker/languages/', { headers: { Accept: 'application/json' } } ).then( response => response.json() )
				.then( ( data ) => {
					const fullLanguage = data[ LANGUAGE.toLowerCase() ];
					const url = `https://cdn.datatables.net/plug-ins/9dcbecd42ad/i18n/${fullLanguage}.json`;

					const columnsDefsElem = document.querySelector( '#custom-columnDefs-datatables' );
					const orderingElem = document.querySelector( '#custom-ordering-datatables' );

					const columnDefs = ( columnsDefsElem !== null ) ?
						JSON.parse( columnsDefsElem.textContent ) :
						null;
					const ordering = ( orderingElem !== null ) ?
						JSON.parse( orderingElem.textContent ) :
						[ [ 0, 'asc ' ] ];

					fetch( '/api/tracker/trackerpreferences/', { headers: { Accept: 'application/json' } } ).then( response => response.json() )
						.then( ( jsonPreferences ) => {
							$( 'table' ).DataTable( {
								pageLength:
									jsonPreferences[ 0 ] ?
										jsonPreferences[ 0 ].display_items :
										25,
								order: ordering,
								columnDefs,
								language: { url }
							} );
						} );
				} );
		}
	}
	document.addEventListener( 'DOMContentLoaded', dataTablesInit );

	if ( 'matchMedia' in window ) {
		// Chrome, Firefox, and IE 10 support mediaMatch listeners
		window.matchMedia( 'print' ).addListener( ( media ) => {
			if ( media.matches ) {
				$( 'table' ).DataTable().destroy();
			} else {
				// Fires immediately, so wait for the first mouse movement
				document.addEventListener( 'mouseover', function cb() {
					dataTablesInit();
					document.removeEventListener( 'mouseover', cb );
				} );
			}
		} );
	}
}
