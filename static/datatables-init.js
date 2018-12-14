{
	function dataTablesInit() {
		const disabledatatables = document.querySelector( '#disabledatatables' );
		if ( disabledatatables === null || disabledatatables.textContent.length === 0 ) {
			const LANGUAGE = document.querySelector( 'meta[http-equiv="Content-Language"]' ).getAttribute( 'content' );

			fetch( '/api/tracker/languages/', { headers: { Accept: 'application/json' } } ).then( response => response.json() )
				.then( ( data ) => {
					const fullLanguage = data[ LANGUAGE.toLowerCase() ],
						url = `https://cdn.datatables.net/plug-ins/9dcbecd42ad/i18n/${fullLanguage}.json`,
						columnDefs = JSON.parse( document.querySelector( '#custom-columnDefs-datatables' ).textContent ) || null,
						ordering = JSON.parse( document.querySelector( '#custom-ordering-datatables' ).textContent ) || [ [ 0, 'asc ' ] ];

					fetch( '/user/display_items', { headers: { Accept: 'application/json' } } ).then( response => response.json() )
						.then( ( displayItems ) => {
							$( 'table' ).DataTable( {
								pageLength: displayItems,
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
