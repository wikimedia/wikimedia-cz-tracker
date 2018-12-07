( function () {
	function dataTablesInit() {
		var language, fullLanguage, url, ordering;
		if ( $( '#disabledatatables' ).text().length === 0 ) {
			language = $( 'meta[http-equiv="Content-Language"]' ).attr( 'content' );
			fullLanguage = 'English';
			url = 'https://cdn.datatables.net/plug-ins/9dcbecd42ad/i18n/' + fullLanguage + '.json';
			ordering = $( '#custom-ordering-datatables' ).text();

			switch ( language ) {
				case 'cs':
					fullLanguage = 'Czech';
			}
			if ( ordering === '' ) {
				ordering = [ [ 0, 'asc ' ] ];
			} else {
				ordering = JSON.parse( ordering );
			}
			$.get( '/user/display_items', function ( displayItems ) {
				$( 'table' ).DataTable( {
					pageLength: displayItems,
					order: ordering,
					language: { url: url }
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
