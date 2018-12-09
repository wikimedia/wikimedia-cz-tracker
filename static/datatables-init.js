( function () {
	function dataTablesInit() {
		var language, fullLanguage, url, ordering, columnDefs;
		if ( $( '#disabledatatables' ).text().length === 0 ) {
			language = $( 'meta[http-equiv="Content-Language"]' ).attr( 'content' );

			fetch( '/api/tracker/languages/', { headers: { Accept: 'application/json' } } ).then( function ( response ) {
				return response.json();
			} ).then( function ( data ) {
				fullLanguage = data[ language.toLowerCase() ];
				url = 'https://cdn.datatables.net/plug-ins/9dcbecd42ad/i18n/' + fullLanguage + '.json';
				columnDefs = $( '#custom-columnDefs-datatables' ).text();
				ordering = $( '#custom-ordering-datatables' ).text();
				if ( ordering === '' ) {
					ordering = [ [ 0, 'asc ' ] ];
				} else {
					ordering = JSON.parse( ordering );
				}
				if ( columnDefs === '' ) {
					columnDefs = null;
				} else {
					columnDefs = JSON.parse( columnDefs );
				}
				$.get( '/user/display_items', function ( displayItems ) {
					$( 'table' ).DataTable( {
						pageLength: displayItems,
						order: ordering,
						columnDefs: columnDefs,
						language: { url: url }
					} );
				} );
			} );
		}
	}
	$( document ).ready( dataTablesInit );

	if ( 'matchMedia' in window ) {
		// Chrome, Firefox, and IE 10 support mediaMatch listeners
		window.matchMedia( 'print' ).addListener( function ( media ) {
			if ( media.matches ) {
				$( 'table' ).DataTable().destroy();
			} else {
				// Fires immediately, so wait for the first mouse movement
				$( document ).one( 'mouseover', dataTablesInit );
			}
		} );
	}
}() );
